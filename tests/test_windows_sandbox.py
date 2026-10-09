"""Native NTFS verification for the portable Windows permission setup."""
import platform
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(platform.system() != "Windows", reason="requires NTFS ACLs")


def test_portable_directory_permissions(tmp_path):
    from clarkbrowser.download import _prepare_windows_sandbox

    root = tmp_path / "portable browser"
    root.mkdir()
    binary = root / "chrome.exe"
    binary.touch()
    nested = root / "locales"
    nested.mkdir()
    resource = nested / "en-US.pak"
    resource.touch()
    # Remove inherited grants to reproduce extraction into a private directory.
    subprocess.run(["icacls.exe", str(root), "/inheritance:d"], check=True)
    for sid in ("*S-1-15-2-1", "*S-1-15-2-2"):
        subprocess.run(["icacls.exe", str(root), "/remove:g", sid, "/T"], check=True)
    _prepare_windows_sandbox(root)
    _prepare_windows_sandbox(root)  # Existing cache repair must be repeatable.
    # Read ACLs as numeric SIDs; account names vary with Windows language.
    script = """
param($Root)
foreach ($file in Get-ChildItem -LiteralPath $Root -Recurse) {
  $rules = (Get-Acl -LiteralPath $file.FullName).GetAccessRules(
    $true, $true, [System.Security.Principal.SecurityIdentifier])
  foreach ($sid in @('S-1-15-2-1', 'S-1-15-2-2')) {
    $allow = $rules | Where-Object {
      $_.IdentityReference.Value -eq $sid -and
      $_.AccessControlType -eq 'Allow' -and
      ($_.FileSystemRights -band [System.Security.AccessControl.FileSystemRights]::ReadAndExecute) -eq
        [System.Security.AccessControl.FileSystemRights]::ReadAndExecute
    }
    if (-not $allow) { throw "Missing read/execute ACE: $sid $file" }
  }
}
"""
    check = tmp_path / "check.ps1"
    check.write_text(script)
    subprocess.run(["pwsh", "-NoProfile", "-File", str(check), str(root)], check=True)
    repair = Path(__file__).resolve().parents[1] / "build" / "repair-sandbox.ps1"
    subprocess.run(["pwsh", "-NoProfile", "-ExecutionPolicy", "Bypass",
                    "-File", str(repair), "-BrowserDirectory", str(root)], check=True)
    subprocess.run(["pwsh", "-NoProfile", "-File", str(check), str(root)], check=True)


def test_released_browser_sandbox_startup(tmp_path):
    import os
    import zipfile
    from clarkbrowser.download import _prepare_windows_sandbox

    archive_path = os.environ.get("CLARK_WINDOWS_TEST_ARCHIVE")
    if not archive_path:
        pytest.skip("set CLARK_WINDOWS_TEST_ARCHIVE to a released Windows ZIP")
    root = tmp_path / "browser"
    with zipfile.ZipFile(archive_path) as archive:
        archive.extractall(root)
    binary = next(root.rglob("chrome.exe"))
    root = binary.parent
    subprocess.run(["icacls.exe", str(root), "/inheritance:d"], check=True)
    for sid in ("*S-1-15-2-1", "*S-1-15-2-2"):
        subprocess.run(["icacls.exe", str(root), "/remove:g", sid, "/T", "/Q"], check=True)

    def launch(profile):
        command = [str(binary), "--headless=new", "--fingerprint=12345",
                   "--enable-features=NetworkServiceSandbox", "--no-first-run",
                   "--no-default-browser-check", "--enable-logging",
                   f"--log-file={profile}.log",
                   f"--user-data-dir={profile}", "--dump-dom",
                   "data:text/html,<title>clark-sandbox-smoke</title>"]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=45)
            logfile = Path(f"{profile}.log")
            if logfile.exists():
                result.stderr += logfile.read_text(errors="replace")
            return result
        except subprocess.TimeoutExpired as exc:
            # A denied utility launch may repeatedly restart until timeout.
            return subprocess.CompletedProcess(command, -1, exc.stdout or b"", exc.stderr or b"")

    before = launch(tmp_path / "before-profile")
    before_error = before.stderr
    if isinstance(before_error, bytes):
        before_error = before_error.decode(errors="replace")
    assert "Sandbox cannot access executable" in before_error, before_error
    _prepare_windows_sandbox(root)
    after = launch(tmp_path / "after-profile")
    if after.returncode != 0:
        print("Before stderr:", before_error)
        print("After stderr:", after.stderr)
        # Capture a native exception dump rather than infer the crash cause.
        debugger = Path(os.environ.get("RUNNER_TEMP", str(tmp_path))) / "procdump" / "procdump64.exe"
        if debugger.exists():
            dump_dir = Path(os.environ["RUNNER_TEMP"]) / "chrome-dumps"
            dump_dir.mkdir(exist_ok=True)
            cmd = list(after.args)
            cmd = [arg.replace("after-profile", "debug-profile") for arg in cmd]
            subprocess.run([str(debugger), "-accepteula", "-ma", "-e", "1", "-f", "80000003", "-x",
                            str(dump_dir), *cmd], timeout=60)
        control_cmd = [arg.replace("after-profile", "control-profile") for arg in after.args]
        control_cmd.insert(1, "--no-sandbox")
        control = subprocess.run(control_cmd, capture_output=True, text=True, timeout=30)
        print("Unsandboxed diagnostic control:", control)
        for log in tmp_path.glob("*.log"):
            print(log.name, log.read_text(errors="replace"))
    assert after.returncode == 0, after.stderr
    assert "clark-sandbox-smoke" in after.stdout
    assert "Sandbox cannot access executable" not in after.stderr
