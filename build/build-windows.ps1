param(
  [string]$Work = $(if ($env:CLARK_WORK_DIR) { $env:CLARK_WORK_DIR } else { "C:\clark-browser-build" }),
  [string]$Out = $(if ($env:CLARK_OUT_DIR) { $env:CLARK_OUT_DIR } else { "$(Get-Location)\dist" }),
  [string]$UcTag = $(if ($env:CLARK_UC_TAG) { $env:CLARK_UC_TAG } else { "148.0.7778.96-1" }),
  [int]$NinjaJobs = $(if ($env:CLARK_NINJA_JOBS) { [int]$env:CLARK_NINJA_JOBS } else { [Environment]::ProcessorCount })
)

$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Patches = Join-Path $Repo "patches"
$env:DEPOT_TOOLS_WIN_TOOLCHAIN = "0"
$env:GYP_MSVS_VERSION = "2022"
$Vs2022Install = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\2022\BuildTools"
if (!(Test-Path $Vs2022Install)) {
  throw "Visual Studio 2022 Build Tools not found at $Vs2022Install"
}
$env:vs2022_install = $Vs2022Install
$env:GYP_MSVS_OVERRIDE_PATH = $Vs2022Install
function Test-AtlHeaders {
  $atl = Get-ChildItem "$Vs2022Install\VC\Tools\MSVC" -Recurse `
    -Filter atldef.h -ErrorAction SilentlyContinue
  return [bool]$atl
}
if (!(Test-AtlHeaders)) {
  Write-Host "[clark-win-build] installing Visual Studio ATL/MFC component"
  $Bootstrapper = Join-Path $env:TEMP "vs_BuildTools.exe"
  curl.exe -L -o $Bootstrapper "https://aka.ms/vs/17/release/vs_BuildTools.exe"
  $InstallArgs = @(
    "--quiet",
    "--wait",
    "--norestart",
    "--nocache",
    "--installPath",
    "`"$Vs2022Install`"",
    "--add",
    "Microsoft.VisualStudio.Component.VC.ATL"
  )
  $Install = Start-Process -FilePath $Bootstrapper -ArgumentList $InstallArgs `
    -Wait -PassThru
  if ($Install.ExitCode -ne 0 -and $Install.ExitCode -ne 3010) {
    throw "Visual Studio ATL/MFC install failed: $($Install.ExitCode)"
  }
  if (!(Test-AtlHeaders)) {
    throw "Visual Studio ATL/MFC headers are still missing after install"
  }
}
$WinSdkBinRoot = "${env:ProgramFiles(x86)}\Windows Kits\10\bin"
$RcExe = Get-ChildItem $WinSdkBinRoot -Recurse -Filter rc.exe `
  -ErrorAction SilentlyContinue |
  Where-Object { $_.FullName -match "\\x64\\rc\.exe$" } |
  Sort-Object FullName -Descending |
  Select-Object -First 1
if (!$RcExe) {
  throw "Windows SDK rc.exe not found under $WinSdkBinRoot"
}
$env:Path = "$($RcExe.DirectoryName);$env:Path"
$GitCmdDir = "${env:ProgramFiles}\Git\cmd"
$GitUsrBinDir = "${env:ProgramFiles}\Git\usr\bin"
$GitExe = "$GitCmdDir\git.exe"
if (Test-Path "$GitCmdDir\git.exe") {
  $env:Path = "$GitCmdDir;$env:Path"
} else {
  $GitExe = "git"
}
$PythonExe = $null
$PythonArgs = @()
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if ($pythonCmd) {
  $PythonExe = $pythonCmd.Source
} elseif (Test-Path "C:\Python312\python.exe") {
  $PythonExe = "C:\Python312\python.exe"
} elseif (Test-Path "${env:ProgramFiles}\Python312\python.exe") {
  $PythonExe = "${env:ProgramFiles}\Python312\python.exe"
} else {
  $pyCmd = Get-Command py -ErrorAction SilentlyContinue
  if ($pyCmd) {
    $PythonExe = $pyCmd.Source
    $PythonArgs = @("-3")
  }
}
if (!$PythonExe) {
  throw "python not found; install Python 3.12 or put python.exe on PATH"
}
@'
import importlib.util
import subprocess
import sys

missing = [
    package
    for package, module in (("httplib2", "httplib2"), ("PySocks", "socks"))
    if importlib.util.find_spec(module) is None
]
if missing:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--user", *missing])
'@ | & $PythonExe @PythonArgs -
if ($LASTEXITCODE -ne 0) {
  throw "failed to install python depot_tools dependencies"
}
function Expand-TarXz {
  param(
    [string]$Archive,
    [string]$Destination
  )
  @'
import sys
import tarfile

archive, destination = sys.argv[1], sys.argv[2]
with tarfile.open(archive, "r:xz") as tar:
    tar.extractall(destination)
'@ | & $PythonExe @PythonArgs - $Archive $Destination
  if ($LASTEXITCODE -ne 0) {
    throw "failed to extract $Archive"
  }
}
function Expand-TarGz {
  param(
    [string]$Archive,
    [string]$Destination
  )
  @'
import sys
import tarfile

archive, destination = sys.argv[1], sys.argv[2]
with tarfile.open(archive, "r:gz") as tar:
    tar.extractall(destination)
'@ | & $PythonExe @PythonArgs - $Archive $Destination
  if ($LASTEXITCODE -ne 0) {
    throw "failed to extract $Archive"
  }
}
New-Item -ItemType Directory -Force -Path $Work, $Out | Out-Null
$ShimDir = Join-Path $Work ".shims"
New-Item -ItemType Directory -Force -Path $ShimDir | Out-Null
$PythonShim = Join-Path $ShimDir "python3.bat"
@"
@echo off
"$PythonExe" %*
"@ | Set-Content $PythonShim -Encoding ASCII
$env:Path = "$ShimDir;$env:Path"
Set-Location $Work

if (!(Test-Path "ungoogled-chromium")) {
  & $GitExe clone --depth=1 --branch $UcTag https://github.com/ungoogled-software/ungoogled-chromium.git
}

@'
from pathlib import Path
p = Path("ungoogled-chromium/utils/clone.py")
s = p.read_text()
s = s.replace("target_os = ['unix'];", "target_os = ['win'];")
s = s.replace("target_cpu = ['x64'];", "target_cpu = ['x64'];")
old = "(ucstaging / '.gclient').write_text(GC_CONFIG.replace('UC_OUT', str(args.output)))"
new = """out_for_gclient = str(args.output)
        if iswin:
            out_for_gclient = out_for_gclient.replace('\\\\', '/')
        (ucstaging / '.gclient').write_text(GC_CONFIG.replace('UC_OUT', out_for_gclient))"""
if old in s:
    s = s.replace(old, new)
p.write_text(s)
'@ | & $PythonExe @PythonArgs -
if ($LASTEXITCODE -ne 0) {
  throw "failed to patch ungoogled clone.py"
}

if (!(Test-Path "build/src/chrome")) {
  $CloneOutput = (($Work -replace "\\", "/") + "/build/src")
  & $PythonExe @PythonArgs "ungoogled-chromium/utils/clone.py" -p win64 -o $CloneOutput
  if ($LASTEXITCODE -ne 0) {
    throw "failed to clone chromium source"
  }
} elseif (!(Test-Path "build/src/third_party/skia/BUILD.gn") -or !(Test-Path "build/src/v8/gni/v8.gni")) {
  Write-Host "[clark-win-build] incomplete Chromium checkout; resyncing"
  $CloneOutput = (($Work -replace "\\", "/") + "/build/src")
  & $PythonExe @PythonArgs "ungoogled-chromium/utils/clone.py" -p win64 -o $CloneOutput
  if ($LASTEXITCODE -ne 0) {
    throw "failed to clone chromium source"
  }
}

Set-Location "$Work/build/src"
$env:Path = "$GitCmdDir;$Work\build\src\uc_staging\depot_tools;$env:Path"
$GnBin = "$Work\build\src\buildtools\win\gn.exe"
$NinjaBin = "$Work\build\src\third_party\ninja\ninja.exe"
if (!(Test-Path $GnBin)) {
  New-Item -ItemType Directory -Force "$Work\build\src\buildtools\win" | Out-Null
  "gn/gn/windows-amd64 git_revision:6e8dcdebbadf4f8aa75e6a4b6e0bdf89dce1513a" |
    Set-Content "$env:TEMP\clark-gn.ensure" -Encoding ASCII
  & "$Work\build\src\uc_staging\depot_tools\cipd.bat" ensure `
    -root "$Work\build\src\buildtools\win" `
    -ensure-file "$env:TEMP\clark-gn.ensure"
  if ($LASTEXITCODE -ne 0) {
    throw "failed to install gn via cipd"
  }
}
if (!(Test-Path $NinjaBin)) {
  New-Item -ItemType Directory -Force "$Work\build\src\third_party\ninja" | Out-Null
  "infra/3pp/tools/ninja/windows-amd64 version:3@1.12.1.chromium.4" |
    Set-Content "$env:TEMP\clark-ninja.ensure" -Encoding ASCII
  & "$Work\build\src\uc_staging\depot_tools\cipd.bat" ensure `
    -root "$Work\build\src\third_party\ninja" `
    -ensure-file "$env:TEMP\clark-ninja.ensure"
  if ($LASTEXITCODE -ne 0) {
    throw "failed to install ninja via cipd"
  }
}
if (!(Test-Path "$Work\build\src\third_party\rust-toolchain\VERSION")) {
  $RustArchive = "$env:TEMP\clark-rust-toolchain-win.tar.xz"
  $RustUrl = "https://storage.googleapis.com/chromium-browser-clang/Win/rust-toolchain-6f54d591c3116ee7f8ce9321ddeca286810cc142-7-llvmorg-23-init-5669-g8a0be0bc.tar.xz"
  curl.exe -L -o $RustArchive $RustUrl
  $RustHash = (Get-FileHash -Algorithm SHA256 $RustArchive).Hash.ToLowerInvariant()
  if ($RustHash -ne "37dd250549fed5a9765c3a88e3487409189e0c9c63b691fc77daa0b5f214bced") {
    throw "rust toolchain sha256 mismatch: $RustHash"
  }
  Remove-Item -Recurse -Force "$Work\build\src\third_party\rust-toolchain" -ErrorAction SilentlyContinue
  New-Item -ItemType Directory -Force "$Work\build\src\third_party\rust-toolchain" | Out-Null
  Expand-TarXz $RustArchive "$Work\build\src\third_party\rust-toolchain"
}
$LlvmDir = "$Work\build\src\third_party\llvm-build\Release+Asserts"
if (!(Test-Path "$LlvmDir\cr_build_revision")) {
  $ClangArchive = "$env:TEMP\clark-clang-win.tar.xz"
  $ClangUrl = "https://storage.googleapis.com/chromium-browser-clang/Win/clang-llvmorg-23-init-5669-g8a0be0bc-4.tar.xz"
  curl.exe -L -o $ClangArchive $ClangUrl
  $ClangHash = (Get-FileHash -Algorithm SHA256 $ClangArchive).Hash.ToLowerInvariant()
  if ($ClangHash -ne "3de6f77fcf0b2194a1353dfe5048fcbae67f14e9a6ee090c4c432ee60bbd9e80") {
    throw "clang toolchain sha256 mismatch: $ClangHash"
  }
  Remove-Item -Recurse -Force $LlvmDir -ErrorAction SilentlyContinue
  New-Item -ItemType Directory -Force $LlvmDir | Out-Null
  Expand-TarXz $ClangArchive $LlvmDir
}
$NodeDir = "$Work\build\src\third_party\node\win"
$NodeExe = "$NodeDir\node.exe"
if (!(Test-Path $NodeExe)) {
  $NodeUrl = "https://storage.googleapis.com/chromium-nodejs/2f710ced2db2beb7c3debf6097196c35ee5adb74"
  New-Item -ItemType Directory -Force $NodeDir | Out-Null
  curl.exe -L -o $NodeExe $NodeUrl
  $NodeHash = (Get-FileHash -Algorithm SHA256 $NodeExe).Hash.ToLowerInvariant()
  if ($NodeHash -ne "2ffe3acc0458fdde999f50d11809bbe7c9b7ef204dcf17094e325d26ace101d8") {
    throw "node sha256 mismatch: $NodeHash"
  }
}
$NodeModulesDir = "$Work\build\src\third_party\node\node_modules"
if (!(Test-Path "$NodeModulesDir\lit-html\directives\repeat.d.ts")) {
  $NodeModulesArchive = "$env:TEMP\clark-node-modules.tar.gz"
  $NodeModulesUrl = "https://storage.googleapis.com/chromium-nodejs/6c15205ac08a854251151c1fbeb8978d2ca5a022"
  curl.exe -L -o $NodeModulesArchive $NodeModulesUrl
  $NodeModulesHash = (Get-FileHash -Algorithm SHA256 $NodeModulesArchive).Hash.ToLowerInvariant()
  if ($NodeModulesHash -ne "2ca9e4b10119399283bf9e9da695cd747491921f77063d54729afcbeb304e6aa") {
    throw "node_modules sha256 mismatch: $NodeModulesHash"
  }
  Remove-Item -Recurse -Force $NodeModulesDir -ErrorAction SilentlyContinue
  New-Item -ItemType Directory -Force $NodeModulesDir | Out-Null
  Expand-TarGz $NodeModulesArchive $NodeModulesDir
}
$RcWrapper = "$Work\build\src\build\toolchain\win\rc\win\rc.exe"
$RcWrapperSha1 = "$Work\build\src\build\toolchain\win\rc\win\rc.exe.sha1"
$RcHash = (Get-Content $RcWrapperSha1).Trim()
$NeedRcDownload = $true
if (Test-Path $RcWrapper) {
  $ExistingRcHash = (Get-FileHash -Algorithm SHA1 $RcWrapper).Hash.ToLowerInvariant()
  $NeedRcDownload = $ExistingRcHash -ne $RcHash
}
if ($NeedRcDownload) {
  curl.exe -L -o $RcWrapper "https://storage.googleapis.com/chromium-browser-clang/rc/$RcHash"
  $DownloadedRcHash = (Get-FileHash -Algorithm SHA1 $RcWrapper).Hash.ToLowerInvariant()
  if ($DownloadedRcHash -ne $RcHash) {
    throw "rc.exe sha1 mismatch: $DownloadedRcHash"
  }
}
$PatchExe = "${env:ProgramFiles}\Git\usr\bin\patch.exe"
if (!(Test-Path $PatchExe)) {
  throw "patch.exe not found at $PatchExe"
}

if (!(Test-Path ".ungoogled-applied")) {
  $failed = @()
  foreach ($patchName in Get-Content "$Work/ungoogled-chromium/patches/series") {
    $patchFile = Join-Path "$Work/ungoogled-chromium/patches" $patchName
    cmd /c "`"$PatchExe`" -p1 --batch --forward --no-backup-if-mismatch -F3 < `"$patchFile`" > `"$env:TEMP\uc-patch.log`" 2>&1"
    if ($LASTEXITCODE -ne 0) {
      $failed += $patchName
      Write-Host "[clark-win-build] WARN: ungoogled patch skipped: $patchName"
      Get-Content "$env:TEMP\uc-patch.log" -TotalCount 5 | ForEach-Object { Write-Host "[clark-win-build]   $_" }
    }
  }
  Write-Host "[clark-win-build] ungoogled series done; $($failed.Count) patch(es) skipped"
  New-Item -ItemType File ".ungoogled-applied" | Out-Null
}

New-Item -ItemType Directory -Force ".clark-applied" | Out-Null
Get-ChildItem "$Patches\0*.patch" | ForEach-Object {
  $name = $_.Name
  if (Test-Path ".clark-applied\$name.done") { return }
  if (!(Select-String -Quiet -Pattern '^diff --git' -Path $_.FullName)) {
    Write-Host "[clark-win-build] $name (spec-only; skipping)"
    New-Item -ItemType File ".clark-applied\$name.done" | Out-Null
    return
  }
  Write-Host "[clark-win-build] $name"
  if ($name -eq "0016-webgl-vendor-renderer-from-cli.patch") {
    & $GitExe checkout -- "third_party/blink/renderer/modules/webgl/webgl_rendering_context_base.cc"
    Remove-Item -Force "third_party\blink\renderer\modules\webgl\webgl_rendering_context_base.cc.rej" -ErrorAction SilentlyContinue
  }
  cmd /c "`"$PatchExe`" -p1 --batch --forward --no-backup-if-mismatch -F3 < `"$($_.FullName)`""
  if ($LASTEXITCODE -ne 0) {
    if ($name -eq "0006-navigator-platform-hwc-ua-from-cli.patch") {
      Write-Host "[clark-win-build] repairing $name hardwareConcurrency hunk"
      @'
from pathlib import Path

p = Path("third_party/blink/renderer/core/execution_context/navigator_base.cc")
s = p.read_text()
if "clark-stealth #13" not in s:
    needle = "unsigned int NavigatorBase::hardwareConcurrency() const {\n"
    block = """  // clark-stealth #13: --fingerprint-hardware-concurrency takes precedence,
  // followed by seed-derived value, then reduced/probed values.
  auto* cl = base::CommandLine::ForCurrentProcess();
  if (cl->HasSwitch(clark::switches::kFingerprintHardwareConcurrency)) {
    unsigned int v = 0;
    if (base::StringToUint(
            cl->GetSwitchValueASCII(
                clark::switches::kFingerprintHardwareConcurrency),
            &v) &&
        v > 0 && v <= 256) {
      return v;
    }
  }
  if (cl->HasSwitch(clark::switches::kFingerprint)) {
    return clark::seed::HardwareConcurrency();
  }
"""
    if needle not in s:
        raise SystemExit("navigator_base.cc: hardwareConcurrency entry not found")
    p.write_text(s.replace(needle, needle + block, 1))
rej = p.with_suffix(p.suffix + ".rej")
if rej.exists():
    rej.unlink()
'@ | & $PythonExe @PythonArgs -
      if ($LASTEXITCODE -ne 0) {
        throw "failed to repair clark patch $name"
      }
    } elseif ($name -eq "0016-webgl-vendor-renderer-from-cli.patch") {
      Write-Host "[clark-win-build] repairing $name extension filter hunk"
      @'
from pathlib import Path

p = Path("third_party/blink/renderer/modules/webgl/webgl_rendering_context_base.cc")
s = p.read_text()
if "if (!ExtensionSupportedAndAllowed(tracker))" not in s:
    old = """  for (ExtensionTracker* tracker : extensions_) {
    if (ExtensionSupportedAndAllowed(tracker)) {
      result.push_back(tracker->ExtensionName());
    }
  }
"""
    new = """  for (ExtensionTracker* tracker : extensions_) {
    if (!ExtensionSupportedAndAllowed(tracker))
      continue;

    String name = tracker->ExtensionName();
    if (!clark_fingerprint) {
      result.push_back(name);
      continue;
    }

    const std::string name_utf8 = name.Utf8();
    for (const char* allowed : kRealChromeExts) {
      if (name_utf8 == allowed) {
        result.push_back(name);
        break;
      }
    }
  }
"""
    if old not in s:
        raise SystemExit("webgl_rendering_context_base.cc: extension loop not found")
    p.write_text(s.replace(old, new, 1))
rej = p.with_suffix(p.suffix + ".rej")
if rej.exists():
    rej.unlink()
'@ | & $PythonExe @PythonArgs -
      if ($LASTEXITCODE -ne 0) {
        throw "failed to repair clark patch $name"
      }
    } elseif ($name -eq "0050-renderer-arg-whitelist-fingerprint.patch") {
      Write-Host "[clark-win-build] accepting already-applied $name hunks"
      @'
from pathlib import Path

p = Path("content/browser/renderer_host/render_process_host_impl.cc")
s = p.read_text()
required = [
    '#include "third_party/blink/common/clark_fingerprint_switches.h"',
    '#include "components/ungoogled/ungoogled_switches.h"',
    "clark::switches::kFingerprintNoise",
    "switches::kFingerprintingClientRectsNoise",
    "switches::kFingerprintingCanvasMeasureTextNoise",
    "switches::kFingerprintingCanvasImageDataNoise",
]
missing = [item for item in required if item not in s]
if missing:
    raise SystemExit("render_process_host_impl.cc missing: " + ", ".join(missing))
rej = p.with_suffix(p.suffix + ".rej")
if rej.exists():
    rej.unlink()
'@ | & $PythonExe @PythonArgs -
      if ($LASTEXITCODE -ne 0) {
        throw "failed to verify clark patch $name"
      }
    } else {
      throw "failed to apply clark patch $name"
    }
  }
  New-Item -ItemType File ".clark-applied\$name.done" | Out-Null
}

$Shared = Join-Path $Patches "000-shared"
if (Test-Path $Shared) {
  Copy-Item "$Shared\clark_fingerprint_switches.h" "third_party\blink\common\" -Force
  Copy-Item "$Shared\clark_fingerprint_switches.cc" "third_party\blink\common\" -Force
  Copy-Item "$Shared\clark_seed.h" "third_party\blink\common\" -Force
  Copy-Item "$Shared\clark_seed.cc" "third_party\blink\common\" -Force
  New-Item -ItemType Directory -Force "chrome\common" | Out-Null
  Copy-Item "$Shared\clark_seed.h" "chrome\common\" -Force
  Copy-Item "$Shared\clark_fingerprint_switches.h" "chrome\common\" -Force
  if (!(Select-String -Quiet -Pattern "clark_seed.cc" -Path "third_party\blink\common\BUILD.gn")) {
    @'
from pathlib import Path
p = Path("third_party/blink/common/BUILD.gn")
s = p.read_text()
needle = "sources = ["
i = s.find(needle)
if i < 0:
    raise SystemExit("BUILD.gn: no sources = [ block found")
nl = s.find("\n", i)
inject = (
    '\n    "clark_fingerprint_switches.cc",'
    '\n    "clark_fingerprint_switches.h",'
    '\n    "clark_seed.cc",'
    '\n    "clark_seed.h",'
)
p.write_text(s[:nl] + inject + s[nl:])
'@ | & $PythonExe @PythonArgs -
    if ($LASTEXITCODE -ne 0) {
      throw "failed to update third_party\blink\common\BUILD.gn"
    }
  }
}

@'
from pathlib import Path

p = Path("chrome/test/BUILD.gn")
s = p.read_text()
marker = (
    "      # clark-browser: safe_browsing_mode=0 leaves these Mac test deps "
    "undefined.\n"
)
old = (
    '      "//chrome/common/safe_browsing:archive_analyzer_results",\n'
    '      "//chrome/common/safe_browsing:disk_image_type_sniffer_mac",\n'
)
if marker not in s:
    if old not in s:
        raise SystemExit("chrome/test/BUILD.gn safe browsing Mac deps not found")
    p.write_text(s.replace(old, marker, 1))
'@ | & $PythonExe @PythonArgs -
if ($LASTEXITCODE -ne 0) {
  throw "failed to update chrome/test/BUILD.gn safe browsing deps"
}

@'
from pathlib import Path

setup = Path("chrome/installer/setup/BUILD.gn")
s = setup.read_text()
marker = "      # clark-browser: enable_rlz_support=false leaves rlz_lib_no_network undefined.\n"
old = '      "//rlz:rlz_lib_no_network",\n'
if marker not in s:
    if old not in s:
        raise SystemExit("chrome/installer/setup/BUILD.gn RLZ dep not found")
    setup.write_text(s.replace(old, marker, 1))

rlz = Path("rlz/BUILD.gn")
s = rlz.read_text()
marker = "      # clark-browser: enable_rlz_support=false leaves rlz_lib undefined.\n"
old = '      ":rlz_lib",\n'
if marker not in s:
    idx = s.rfind('executable("rlz_id")')
    if idx < 0:
        raise SystemExit("rlz_id target not found")
    dep_idx = s.find(old, idx)
    if dep_idx < 0:
        raise SystemExit("rlz_id rlz_lib dep not found")
    s = s[:dep_idx] + marker + s[dep_idx + len(old):]
    rlz.write_text(s)
'@ | & $PythonExe @PythonArgs -
if ($LASTEXITCODE -ne 0) {
  throw "failed to patch disabled RLZ GN deps"
}

@'
from pathlib import Path

build = Path("chrome/browser/safe_browsing/BUILD.gn")
source = Path("chrome/browser/safe_browsing/clark_empty_safe_browsing.cc")
text = build.read_text()
marker = '    "clark_empty_safe_browsing.cc",\n'
if marker not in text:
    needle = 'static_library("safe_browsing") {\n'
    if needle not in text:
        raise SystemExit("safe_browsing static_library target not found")
    text = text.replace(needle, needle + "  sources = [\n" + marker + "  ]\n", 1)
    build.write_text(text)
if not source.exists():
    source.write_text(
        "namespace safe_browsing {\n"
        "void ClarkBrowserSafeBrowsingDisabledAnchor() {}\n"
        "}  // namespace safe_browsing\n"
    )
'@ | & $PythonExe @PythonArgs -
if ($LASTEXITCODE -ne 0) {
  throw "failed to patch empty safe_browsing target"
}

@'
from pathlib import Path

p = Path("chrome/browser/policy/configuration_policy_handler_list_factory.cc")
s = p.read_text()
include = '#include "components/signin/public/base/signin_pref_names.h"\n'
if include not in s:
    anchor = '#include "components/policy/policy_constants.h"\n'
    if anchor not in s:
        raise SystemExit("configuration_policy_handler_list_factory.cc include anchor not found")
    s = s.replace(anchor, anchor + include, 1)
s = s.replace(
    "prefs::kBoundSessionCredentialsEnabled",
    '"signin.bound_session_credentials_enabled"',
)
p.write_text(s)
'@ | & $PythonExe @PythonArgs -
if ($LASTEXITCODE -ne 0) {
  throw "failed to patch bound session pref include"
}

@'
from pathlib import Path

p = Path("chrome/browser/signin/signin_util_win.cc")
s = p.read_text()
include = '#include "components/signin/public/base/signin_pref_names.h"\n'
if include not in s:
    anchor = '#include "components/signin/public/base/signin_metrics.h"\n'
    if anchor not in s:
        raise SystemExit("signin_util_win.cc include anchor not found")
    s = s.replace(anchor, anchor + include, 1)
s = s.replace(
    "prefs::kSignedInWithCredentialProvider",
    '"signin.with_credential_provider"',
)
# ungoogled-chromium removes this preference's registration. Keep the Google
# credential-provider entry points inert when that integration is absent;
# replacing its removed constant with a literal only fixes compilation.
for signature, result in (
    ("void SigninWithCredentialProviderIfPossible(Profile* profile) {", "return;"),
    ("bool ReauthWithCredentialProviderIfPossible(Profile* profile) {", "return false;"),
):
    guard = (
        signature + "\n"
        '  // clark-browser: ungoogled profiles have no GCPW preference.\n'
        '  if (!profile->GetPrefs()->FindPreference("signin.with_credential_provider"))\n'
        f"    {result}\n"
    )
    if guard not in s:
        if signature not in s:
            raise SystemExit(f"credential provider entry point not found: {signature}")
        s = s.replace(signature, guard, 1)
p.write_text(s)
'@ | & $PythonExe @PythonArgs -
if ($LASTEXITCODE -ne 0) {
  throw "failed to patch signed-in credential provider pref include"
}

@'
from pathlib import Path

p = Path("build/vs_toolchain.py")
s = p.read_text()
marker = "      # clark-browser: AWS BuildTools images may omit SDK Debugging Tools.\n"
needle = "    full_path = os.path.join(win_sdk_dir, 'Debuggers', target_cpu, debug_file)\n"
fallback = (
    needle
    + marker
    + "    if not os.path.exists(full_path) and target_cpu == 'x64':\n"
    + "      system_path = os.path.join(os.environ.get('SystemRoot', 'C:\\\\Windows'),\n"
    + "                                 'System32', debug_file)\n"
    + "      if os.path.exists(system_path):\n"
    + "        full_path = system_path\n"
)
if marker not in s:
    if needle not in s:
        raise SystemExit("vs_toolchain.py debugger copy path not found")
    p.write_text(s.replace(needle, fallback, 1))
'@ | & $PythonExe @PythonArgs -
if ($LASTEXITCODE -ne 0) {
  throw "failed to patch vs_toolchain.py debugger fallback"
}

New-Item -ItemType Directory -Force "out\Default" | Out-Null
@"
is_debug = false
is_official_build = true
use_thin_lto = false
thin_lto_enable_optimizations = false
is_cfi = false
symbol_level = 0
blink_symbol_level = 0
v8_symbol_level = 0
target_cpu = "x64"
enable_nacl = false
enable_remoting = false
proprietary_codecs = true
ffmpeg_branding = "Chrome"
treat_warnings_as_errors = false
safe_browsing_mode = 0
chrome_pgo_phase = 0
"@ | Set-Content "out\Default\args.gn" -Encoding ASCII

& $GnBin gen out\Default
if ($LASTEXITCODE -ne 0) {
  throw "gn gen failed"
}
@'
import re
from pathlib import Path

headers = [
    (
        Path("gpu/webgpu/dawn_commit_hash.h"),
        "GPU_WEBGPU_DAWN_COMMIT_HASH_H_",
        "DAWN_COMMIT_HASH",
    ),
    (
        Path("skia/ext/skia_commit_hash.h"),
        "SKIA_EXT_SKIA_COMMIT_HASH_H_",
        "SKIA_COMMIT_HASH",
    ),
]
for path, guard, symbol in headers:
    text = path.read_text()
    match = re.search(r'#define\s+' + re.escape(symbol) + r'\s+"([^"]+)"', text)
    if not match:
        raise SystemExit(f"{path}: {symbol} definition not found")
    path.write_text(
        "/* Generated by lastchange.py, normalized by clark-browser.*/\n\n"
        f"#ifndef {guard}\n"
        f"#define {guard}\n\n"
        f"#define {symbol} \"{match.group(1)}\"\n\n"
        f"#endif  // {guard}\n"
    )
'@ | & $PythonExe @PythonArgs -
if ($LASTEXITCODE -ne 0) {
  throw "failed to normalize generated commit hash headers"
}
& $NinjaBin -C out\Default -j $NinjaJobs chrome
if ($LASTEXITCODE -ne 0) {
  throw "ninja build failed"
}

$BuildDir = Join-Path (Get-Location) "out\Default"
$PackageRoot = Join-Path $Work "package\clark-browser-windows-x64"
Remove-Item -Recurse -Force $PackageRoot -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $PackageRoot | Out-Null

Get-ChildItem $BuildDir -File | Where-Object {
  $_.Extension -in @(
    ".exe",
    ".dll",
    ".pak",
    ".bin",
    ".dat",
    ".json",
    ".manifest",
    ".xml"
  )
} | Copy-Item -Destination $PackageRoot -Force

foreach ($dir in @("locales", "MEIPreload", "WidevineCdm", "SwiftShader")) {
  $src = Join-Path $BuildDir $dir
  if (Test-Path $src) {
    Copy-Item $src -Destination $PackageRoot -Recurse -Force
  }
}

Copy-Item (Join-Path $PSScriptRoot "repair-sandbox.ps1") -Destination $PackageRoot

$Zip = Join-Path $Out "clark-browser-windows-x64.zip"
Remove-Item -Force $Zip -ErrorAction SilentlyContinue
Compress-Archive -Path "$PackageRoot\*" -DestinationPath $Zip -CompressionLevel Optimal
Get-FileHash -Algorithm SHA256 $Zip | Format-List
