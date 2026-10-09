# Changelog

## Unreleased

- Added `patches/0047-suppress-cdc-globals.patch` — a V8 extension that
  strips `cdc_*`, `__webdriver*`, `__selenium*`, and `__$webdriver*`
  automation globals from `globalThis` at context creation, preventing
  CDP/ChromeDriver-injected globals from being visible to detection scripts.
- Added `patches/0027-analyser-node-noise.patch` — seed-derived per-bin
  noise on `AnalyserNode.getFloatFrequencyData` and `getByteFrequencyData`,
  closing the audio fingerprint gap where sites read the frequency domain
  directly instead of the AudioContext destination buffer.
- The launcher now defaults `webrtc_policy` to `proxy-coherent` when a
  `proxy` is configured, preventing WebRTC from leaking the host IP outside
  the proxy tunnel. Explicit `webrtc_policy` param or `CLARK_WEBRTC_POLICY`
  env var still takes precedence.
- The launcher now pins `--fingerprint-screen-width` and
  `--fingerprint-screen-height` from a seed-derived screen-size pool so the
  Playwright viewport (`window.innerWidth/innerHeight`) and the binary's
  `screen.width/height` stay coherent. `launch_context()` and
  `launch_persistent_context()` derive the default viewport from these
  values instead of using a hardcoded 1920x947.
- Added `tests/tls_fingerprint.py` — a TLS ClientHello capture harness that
  parses JA3/JA4 fingerprints from the Clark-stealth binary and compares
  against a known real-Chrome baseline.

## 0.2.2 — Windows sandbox permissions (2026-10-09)

- Prepare AppContainer and LPAC read/execute permissions after Windows ZIP
  extraction and on existing Python-managed caches (issue #4).
- Include `repair-sandbox.ps1` in Windows portable packages for direct launches.
- Add Windows NTFS and released-binary startup regression coverage.
- Guard Windows credential-provider startup when ungoogled Chromium removes
  its preference registration. Windows binaries require a source rebuild before
  the staged stealth6 release can be published. Downloads remain on stealth5
  until the release passes native startup verification.

## 0.2.1 — patch bump (June 2026)

## 0.2.0 — fingerprint plumbing fixes + audio noise (June 2026)

- Added `patches/0007-user-agent-client-hints-from-cli.patch` so
  `navigator.userAgentData` / UA Client Hints follow
  `--fingerprint-platform`, `--fingerprint-platform-version`,
  `--fingerprint-brand`, and `--fingerprint-brand-version` instead of leaking
  the host identity when `--user-agent` is set.
- The Python launcher now passes a Chrome UA-CH brand/version and a coherent
  platform version for the default stealth profile.
- Fixed Linux auto-download resolution to prefer the packaged `chrome` binary
  while falling back to `headless_shell` for older cached tarballs.
- Linux launcher defaults now use a Linux fingerprint profile unless
  `CLARK_WINDOWS_FONTS_DIR` is configured, preventing a Windows UA/Win32 profile
  from pairing with a tiny Linux font set.
- Added `CLARK_FINGERPRINT_PLATFORM`, `CLARK_FINGERPRINT_FONTS_DIR`, and
  `CLARK_WINDOWS_FONTS_DIR` launcher hooks for explicit platform/font profiles.
- Added `CLARK_LINUX_FONTS_DIR`, target-platform font directory validation, and
  Linux Fontconfig profile generation so configured font packs are visible to
  Chromium instead of only being passed as audit metadata.
- `Notification.permission` now returns `default` under Clark fingerprint mode,
  matching `permissions.query({name: "notifications"})` returning `prompt`.
- Added `patches/0051-network-information-profile.patch` so
  `navigator.connection.rtt`, `downlink`, and `effectiveType` come from
  seed-stable network profiles instead of leaking host NQE values like `rtt=0`.
- Added opt-in proxy-coherent WebRTC routing via `webrtc_policy="proxy-coherent"`
  or `CLARK_WEBRTC_POLICY=proxy-coherent`, mapping to Chromium's
  `--force-webrtc-ip-handling-policy=disable_non_proxied_udp` and
  `--webrtc-ip-handling-policy=disable_non_proxied_udp` so proxied sessions do
  not leak a separate non-proxied UDP route.
- Added `patches/0049-webgpu-adapter-info-coherent.patch` so
  `GPUAdapter.info` and `GPUDevice.adapterInfo` match the WebGL GPU pool when
  WebGPU is enabled. Headless launches now deliberately disable WebGPU by
  default; set `CLARK_WEBGPU_POLICY=coherent` or pass
  `webgpu_policy="coherent"` to leave it available.
- Added launch hygiene warnings for accidental DevTools/CDP/automation switch
  footguns, plus `InteractionPacer` helpers to keep agent clicks from bursting
  faster than the page can reasonably respond.
- Linux builds now support `CLARK_BROWSER_TARGET=chrome` while keeping the
  existing `headless_shell` lane for rollback. Chrome-target tarballs include
  the real `chrome` binary plus a `headless_shell` compatibility launcher.
- The Linux Docker build runner now defaults to host memory and keeps
  `CLARK_LINUX_BUILD_MEMORY` as an opt-in cap for constrained local builds.
- The Linux Docker runner now builds and runs the same amd64 platform image,
  resets stale architecture-specific toolchains in persistent build volumes,
  and the GitHub Actions Linux build can dispatch either `chrome` or
  `headless_shell` via the `target` input.

## 0.2.0 — fingerprint plumbing fixes + audio noise (May 2026)

Major audit pass after the 0.1.0 patches were verified end-to-end against
`bot.sannysoft.com` and via the `agent-browser` CLI driving the patched
binary over CDP. Most of the changes below fix patches that were *present*
in 0.1.0 but did not actually fire at runtime because the patch site was
unreachable from the JS-visible code path.

### Verified end-to-end (this release)

| Fingerprint vector                    | Source              | Per-seed |
|--------------------------------------|---------------------|----------|
| `navigator.webdriver`                 | always `false`      |          |
| `navigator.plugins.length`            | always `5`          |          |
| `typeof window.chrome`                | always `"object"`   |          |
| `navigator.platform`                  | `--fingerprint-platform` |     |
| `navigator.userAgent`                 | matched-platform UA |          |
| `navigator.hardwareConcurrency`       | `--fingerprint-hardware-concurrency` or seed |     |
| `navigator.maxTouchPoints`            | `--fingerprint-max-touch-points` |          |
| `screen.{width,height,avail*}`        | seed-derived from a coherent pool | ✓        |
| WebGL `UNMASKED_{VENDOR,RENDERER}_WEBGL` | `--fingerprint-gpu-{vendor,renderer}` | ✓ |
| Canvas `toDataURL` hash               | inaudible per-pixel jitter | ✓     |
| `getBoundingClientRect` widths        | sub-pixel jitter    | ✓        |
| `Intl.DateTimeFormat().resolvedOptions().timeZone` | `--fingerprint-timezone` | |
| `navigator.language` / `languages`    | `--fingerprint-locale` |          |
| `OfflineAudioContext` sum-of-abs hash | tiny per-sample noise | ✓        |
| `HeadlessChrome` token in UA          | stripped            |          |

`bot.sannysoft.com` reports a 100% pass with all checks (`WebDriver`,
`Plugins`, `HEADCHR_*`, `PHANTOM_*`, `SELENIUM_DRIVER`, `CHR_BATTERY`,
`CHR_MEMORY`, `TRANSPARENT_PIXEL`, and so on) when the binary is launched
with a Windows fingerprint and swiftshader-WebGL enabled.

### Patches that were silently dead in 0.1.0 (now fixed)

- **`navigator.platform`** — patch was on `NavigatorID::platform`, but the
  actual JS-visible call goes through `NavigatorBase::platform` which
  short-circuits to `GetReducedNavigatorPlatform()` (a hard-coded host
  string). Moved override to `NavigatorBase`. See
  `patches/0006-navigator-platform-hwc-ua-from-cli.patch`.
- **`navigator.hardwareConcurrency`** — patch was on
  `NavigatorConcurrentHardware`. `NavigatorBase::hardwareConcurrency`
  short-circuits to a hard-coded `2` when `kReducedSystemInfo` is enabled
  (which we enable in patch 0019). Moved override to `NavigatorBase`.
- **`--fingerprint-timezone`** — patch only called
  `icu::TimeZone::adoptDefault(...)` from `RenderThreadImpl::Init`, which
  successfully changed ICU's default but did NOT invalidate V8's
  `ICUTimezoneCache`, so `Intl.DateTimeFormat().resolvedOptions().timeZone`
  kept returning the host zone. Now plumbs through a new
  `blink::ClarkSetTimeZoneOverride` public function that wraps
  `TimeZoneController::SetTimeZoneOverride` and intentionally leaks the
  RAII handle so the override survives the renderer's lifetime.
- **`--fingerprint-*` switches not reaching renderer** — Chromium's
  `RenderProcessHostImpl::AppendRendererCommandLine` only propagates
  switches that are explicitly listed in `kSwitchNames[]`. New patch
  `0050-renderer-arg-whitelist-fingerprint.patch` adds every
  `clark::switches::kFingerprint*` to that list.

### New patches in this release

- `0006-navigator-platform-hwc-ua-from-cli.patch` (replaces dead 0006/0007)
- `0009-navigator-max-touch-points-from-cli.patch`
- `0026-audio-fingerprint-noise.patch` — seed-derived per-sample jitter on
  the `AudioBuffer::getChannelData` v8-binding entry path. Hooks ONLY the
  `ExceptionState` overload (the no-exception-state overload is also called
  internally by `SharedAudioBuffer` setup BEFORE the audio thread fills the
  buffer; hooking it there would latch "already noised" on an empty buffer
  and the renderer would overwrite our changes).
- `0032-fingerprint-timezone-cli.patch` — rewritten with the
  `ClarkSetTimeZoneOverride` bridge approach (see above).
- `0050-renderer-arg-whitelist-fingerprint.patch` — propagate all
  `--fingerprint-*` switches to renderer/worker processes.

### Build infrastructure

- `build/Dockerfile.linux` + `build/build-linux.sh` +
  `build/run-linux-build.sh` — reproducible Linux x86_64 build harness.
  Pins `ungoogled-chromium` to tag `148.0.7778.96-1` (the macOS variant's
  ref) to avoid the stale 120.x submodule pin in
  `ungoogled-chromium-debian`.

### Known gaps (deferred to 0.3.0)

- Audio noise covers only `AudioBuffer::getChannelData` and `copyFromChannel`.
  `AnalyserNode.getFloatFrequencyData()` and `MediaStreamAudioSourceNode`
  routes are not yet perturbed.
- Font enumeration still depends on real installed/profile fonts. The launcher
  validates configured font dirs and exposes them through Fontconfig on Linux,
  but full native FontCache plumbing and synthetic fallback metrics are still
  deferred.
- TLS / ClientHello fingerprint (#40-#44) not patched. Requires BoringSSL
  customization (or an external utls-style proxy) to alter JA3/JA4.
- WebGPU adapter info (#49) is wired when WebGPU is enabled, but live
  detection-site evidence still needs a rebuilt binary with WebGPU explicitly
  enabled.

## 0.1.0 — initial release (May 2026)

First public release.

### Patched Chromium

- Base: **ungoogled-chromium 148.0.7778.96**
- 18 source-level patches integrated; 31 more specified for follow-up
  (see PATCHES.md)
- Build verified end-to-end on macOS arm64

### Python wrapper

- `launch()`, `launch_async()`, `launch_context()`,
  `launch_persistent_context()` mirroring Playwright's API
- Auto-download from GitHub Releases (override with `CLARK_BINARY_PATH`)
- `--use-mock-keychain` baked into default args for unsigned macOS dev builds
