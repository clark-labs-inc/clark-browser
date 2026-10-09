# clark-browser

![clark-browser bot detection check](./promo/clark-browser-bot-check.gif)

*by [Clark](https://clarkchat.com) — open source; see [License](#license)*

**Stealth Chromium for browser automation.** Browser-level fingerprint fixes
compiled into patched Chromium source, so Playwright/CDP clients do not have to
rely on fragile JavaScript injections.

## What this is

A fork of [ungoogled-chromium](https://github.com/ungoogled-software/ungoogled-chromium)
148.0.7778.96 with a patch series that moves common automation fingerprint
values into the browser itself: navigator properties, UA Client Hints, WebGL GPU
strings, screen dimensions, plugins, timezones, and related JS-visible surfaces.

Clark's Python wrapper and patch series are MIT-licensed. Redistributed
Chromium/ungoogled-chromium components retain their upstream licenses. This is
an open-source project, **not** a commercial-licensed stealth browser like
CloakBrowser or Multilogin. Build it from source yourself, or use the prebuilt
binaries from
[GitHub Releases](https://github.com/clark-labs-inc/clark-browser/releases).

## Why

Stock `chromium --headless` is trivially detectable: `navigator.webdriver
= true`, empty plugin list, `HeadlessChrome` in the User-Agent, software-renderer
WebGL strings, and a dozen other signals that detection sites grep for. JS-level
"stealth" shims (puppeteer-extra-plugin-stealth, playwright-stealth, undetected-
chromedriver) only paper over the surface — sites like FingerprintJS, BrowserScan,
and Cloudflare Turnstile catch them because the patches themselves are
detectable.

clark-browser patches Chromium where the values come from, in browser and
renderer source, so public detector pages see a coherent Chrome-like automation
profile instead of Playwright/headless defaults.

## Supported platforms

| Platform | Status |
|---|---|
| Linux x86_64 | prebuilt binary in [releases](https://github.com/clark-labs-inc/clark-browser/releases) |
| macOS arm64 | prebuilt binary in [releases](https://github.com/clark-labs-inc/clark-browser/releases) |

Other targets (macOS x86_64, Windows) need a source build.

## Usage

Install the Python wrapper from PyPI:

```bash
pip install clark-browser
```

Use it as a Playwright launcher. The wrapper downloads the matching patched
Chromium build from GitHub Releases on first launch and caches it under
`~/.clarkbrowser/`.

```python
from clarkbrowser import launch

browser = launch()
page = browser.new_page()
page.goto("https://bot.sannysoft.com")
print(page.title())
browser.close()
```

You can also prefetch or inspect the browser binary with the CLI:

```bash
clark-browser info
clark-browser fetch
```

For Vercel `agent-browser` usage, see
[`examples/agent_browser.md`](./examples/agent_browser.md).

Examples:

- [`examples/basic.py`](./examples/basic.py) - launch, navigate, screenshot.
- [`examples/stealth_check.py`](./examples/stealth_check.py) - local smoke check
  for the main JS-visible patches.
- [`examples/interaction_hygiene.py`](./examples/interaction_hygiene.py) -
  launch hygiene checks plus paced Playwright clicks.
- [`examples/agent_browser.md`](./examples/agent_browser.md) - use the patched
  binary through Vercel `agent-browser`.
- [`examples/bot_detection_promo.py`](./examples/bot_detection_promo.py) -
  maintainer script for refreshing the README promo media from a live SannySoft
  run.

For direct CDP usage, download the tarball for your platform from the
[releases page](https://github.com/clark-labs-inc/clark-browser/releases),
extract it, and run the binary directly. Drive it via any Chrome DevTools
Protocol client (CDP over HTTP/WebSocket).

```bash
# Linux: extract and launch with CDP on port 9222
tar -xzf clark-browser-linux-x64.tar.gz
CLARK_UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
./chrome \
  --headless=new \
  --no-sandbox \
  --remote-debugging-port=9222 \
  --remote-debugging-address=127.0.0.1 \
  --remote-allow-origins=* \
  --user-data-dir=/tmp/clark-browser-cdp-profile \
  --fingerprint=12345 \
  --fingerprint-platform=linux \
  --fingerprint-brand=Chrome \
  --fingerprint-brand-version=148.0.0.0 \
  --fingerprint-timezone=America/Los_Angeles \
  --fingerprint-locale=en-US \
  --fingerprint-network-profile=datacenter \
  --disable-features=WebGPU \
  --lang=en-US \
  --accept-lang=en-US,en \
  --user-agent="$CLARK_UA" \
  about:blank
```

The Linux tarball contains the `chrome` binary, a `headless_shell`
compatibility launcher, Chrome resource packs, and runtime helper libraries.
The macOS arm64 build produces a normal `Chromium.app` bundle.

### Windows portable builds

After extracting a Windows source-build ZIP, prepare the browser directory's
sandbox permissions before launching `chrome.exe`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\repair-sandbox.ps1
.\chrome.exe --headless=new --dump-dom about:blank
```

For an older ZIP, run the repository script with
`-BrowserDirectory "C:\path\to\extracted\browser"`. The Python wrapper applies
these permissions automatically to downloaded and cached Windows builds.
For `CLARK_BINARY_PATH`, run the repair script on that binary's directory.

`Sandbox cannot access executable ... Check filesystem permissions are valid`
(issue #4) means an AppContainer access check failed. Portable ZIP extraction
does not preserve the NTFS permissions normally set by Chromium's installer.
The script grants AppContainer and LPAC read/execute access only to the browser
folder and its contents. Keep profiles and private data outside that folder.
See [Chromium's LPAC filesystem requirements](https://chromium.googlesource.com/chromium/src/+/HEAD/docs/design/sandbox.md#lpac-file-system-permissions).

## Stealth surface

`--fingerprint-*` switches drive the patches. The Python launcher supplies a
coherent default set, including a matched User-Agent and `Accept-Language`
header. When running the raw binary, keep User-Agent, UA-CH brand/platform,
locale, timezone, viewport, Network Information profile, and proxy geography
consistent for the whole session.

Launcher defaults follow the host platform so font enumeration does not fight
the claimed OS: Linux hosts default to a Linux profile, and macOS hosts default
to macOS. To use a Windows profile from Linux, configure a licensed Windows font
pack with `CLARK_WINDOWS_FONTS_DIR=/path/to/fonts`; the launcher validates that
core families such as Arial, Calibri, and Segoe UI are present before adding
`--fingerprint-platform=windows` and `--fingerprint-fonts-dir=...`. Linux font
packs can be supplied with `CLARK_LINUX_FONTS_DIR=/path/to/fonts`, and the
Python launcher exposes configured profile font directories to Linux Chromium
through Fontconfig. Advanced callers can force a platform with
`CLARK_FINGERPRINT_PLATFORM=windows|macos|linux` and pass a font directory with
`CLARK_FINGERPRINT_FONTS_DIR=/path/to/fonts`. Windows profiles on non-Windows
hosts require a valid Windows font directory. See `profiles/fonts/README.md`
for profile-pack expectations.

All fingerprint switches have seed-derived defaults when omitted. Pass
`--fingerprint=<integer>` for a deterministic identity, or let the binary pick a
fresh seed at startup for per-launch variation.

Set `CLARK_FINGERPRINT_NETWORK_PROFILE=desktop|datacenter|residential|mobile|slow`
or pass `network_profile=` to the Python launcher when the proxy/IP type is known.
The profile drives `navigator.connection.{rtt,downlink,effectiveType}` with
seed-stable values; direct CLI overrides are available for tight proxy pools.

For proxied sessions, WebRTC routing must be coherent with the HTTP route too.
Pass `webrtc_policy="proxy-coherent"` to the Python launcher, or set
`CLARK_WEBRTC_POLICY=proxy-coherent`, to add
`--force-webrtc-ip-handling-policy=disable_non_proxied_udp` and
`--webrtc-ip-handling-policy=disable_non_proxied_udp`. This is opt-in because
forcing WebRTC through the configured proxy can hurt or break real-time media,
especially when the proxy only supports TCP.

WebGPU is treated as a profile choice instead of a surprise runtime leak. The
headless launcher default adds `--disable-features=WebGPU`, matching the common
headless/no-accelerated-adapter profile. Use `webgpu_policy="coherent"` or
`CLARK_WEBGPU_POLICY=coherent` when deliberately enabling WebGPU; patch #49 then
maps `GPUAdapterInfo.{vendor,architecture,device,description}` to the same GPU
pool used by WebGL.

Operational hygiene matters too. Clark's launcher warns when caller-supplied
options re-enable `--enable-automation`, auto-open DevTools, bind CDP outside
loopback, or allow every CDP origin. Set `CLARK_LAUNCH_HYGIENE=strict` to fail
fast in CI, or `CLARK_LAUNCH_HYGIENE=off` for local experiments. For agent code,
use `InteractionPacer` to prevent accidental burst-clicks and repeated
same-target clicks:

```python
from clarkbrowser import InteractionPacer, launch_context

context = launch_context()
page = context.new_page()
pacer = InteractionPacer()

page.goto("https://example.com", wait_until="domcontentloaded")
pacer.click(page, "a")
```

```
--fingerprint=<int>              master RNG seed (10000..99999)
--fingerprint-platform=          windows | macos | linux
--fingerprint-platform-version=  client hints platform version
--fingerprint-brand=             Chrome | Edge | Opera | Vivaldi
--fingerprint-brand-version=
--fingerprint-gpu-vendor=        WebGL UNMASKED_VENDOR_WEBGL
--fingerprint-gpu-renderer=      WebGL UNMASKED_RENDERER_WEBGL
--fingerprint-hardware-concurrency=
--fingerprint-device-memory=     in GB
--fingerprint-screen-width=
--fingerprint-screen-height=
--fingerprint-taskbar-height=    Win=48, Mac=95, Linux=0
--fingerprint-storage-quota=     in MB
--fingerprint-timezone=          IANA tz, e.g. America/New_York
--fingerprint-locale=            BCP 47
--fingerprint-fonts-dir=         path to platform font directory
--fingerprint-location=          lat,lon for geolocation API
--fingerprint-webrtc-ip=         literal IPv4 to spoof in ICE candidates
--fingerprint-network-profile=   desktop | residential | datacenter | mobile | slow
--fingerprint-connection-type=   wifi | ethernet | cellular | ...
--fingerprint-effective-type=    slow-2g | 2g | 3g | 4g
--fingerprint-rtt=               navigator.connection.rtt in ms
--fingerprint-downlink=          navigator.connection.downlink in Mbps
--fingerprint-noise=             true | false  (canvas/audio noise on/off)
--force-webrtc-ip-handling-policy=disable_non_proxied_udp
--webrtc-ip-handling-policy=disable_non_proxied_udp
--disable-features=WebGPU        default for headless launcher profiles
```

## Verified-working patches

Confirmed firing in smoke tests against the built binary
(`tests/linux_smoke.py`, `tests/integration_smoke.py`,
`tests/webrtc_proxy_smoke.py`):

| Detection vector | Patched | Verification |
|---|---|---|
| `navigator.webdriver` | always `false` | `navigator.webdriver === false` |
| `navigator.plugins` | 5 PDF-viewer entries | `navigator.plugins.length === 5` |
| `window.chrome` | always an object | `typeof window.chrome === "object"` |
| `navigator.platform` | spoofed from `--fingerprint-platform` | returns `"Win32"` under `=windows` |
| `navigator.userAgentData` | brand/platform/version coherent with spoofed UA | returns Windows + Google Chrome under `=windows` |
| `navigator.hardwareConcurrency` | seed-derived from {4, 6, 8, 12, 16} | deterministic per seed |
| `navigator.maxTouchPoints` | matched to platform | `0` on `=windows` |
| timezone / locale | from `--fingerprint-timezone` / `--fingerprint-locale` plus `--lang` | reaches Blink as set |
| `navigator.connection` | seed/profile-derived network quality | nonzero RTT, plausible downlink/effectiveType |
| WebRTC proxy coherence | opt-in `webrtc_policy="proxy-coherent"` | `tests/webrtc_proxy_smoke.py` verifies no private/local IP or direct STUN route |
| WebGPU adapter info | absent by headless policy, or GPUAdapterInfo matches WebGL pool | `vendor/device/description` coherent when WebGPU is enabled |
| User-Agent | no `HeadlessChrome` | full Chrome UA under `--user-agent=...` |
| Audio fingerprint | seed-derived deterministic noise | two distinct seeds yield distinct audio FP |

See [`PATCHES.md`](./PATCHES.md) for the full patch catalog and `specs/` for
per-category implementation notes.

## Live detector results

The latest saved live-detector snapshot was captured from
[`chromium-v148.0.7778.96-stealth1`](https://github.com/clark-labs-inc/clark-browser/releases/tag/chromium-v148.0.7778.96-stealth1)
on 2026-05-20 inside an E2B Ubuntu 24.04 sandbox with the real
`agent-browser 0.27.0` CLI driving the released Linux binary. Newer releases
must still pass the local smoke suites and release-artifact smoke before upload.

`PASS` means the captured page matched the specific evidence shown here. It is
not a promise that every detector, challenge, proxy, or traffic pattern will
pass. `OBSERVED` means the page loaded and was captured, but did not expose a
stable passive pass/fail verdict.

| Target | Result | Evidence |
|---|---:|---|
| Cloudflare challenge smoke (`nowsecure.nl`) | PASS | Loaded target without visible challenge/block text |
| SannySoft | PASS | WebDriver missing, Chrome present, HEADCHR UA/permissions/plugins/iframe all `ok` |
| Antoine Vastel headless test | PASS with `--accept-lang=en-US,en` | The same released binary failed without an HTTP `Accept-Language` header and passed with one |
| BrowserLeaks Client Hints | PASS | Windows + Google Chrome UA-CH, no `HeadlessChrome` |
| BrowserLeaks WebGL | PASS | Google/NVIDIA ANGLE, WebGL/WebGL2 enabled, no SwiftShader/llvmpipe text |
| Incolumitas, Pixelscan, BotD demo, CreepJS | OBSERVED | Loaded and captured; no stable passive verdict for several pages; CreepJS still shows a Headless panel |

Full table and raw captured output:
[`docs/bot-detection-results.md`](./docs/bot-detection-results.md).

## Methodology

We build on ungoogled-chromium (BSD-3) and inherit its existing Brave-derived
canvas/audio/clientRects noise infrastructure. Our patches are written from
public sources only — W3C specs, Chromium upstream code, MDN bot-detection
writeups, and curl-impersonate (MIT). We do not reverse-engineer or copy from
any proprietary stealth-browser binary. See [`METHODOLOGY.md`](./METHODOLOGY.md).

## Building from source

```bash
# 1. Fetch tooling
git clone https://github.com/clark-labs-inc/clark-browser
cd clark-browser

# 2. Fetch Chromium 148 source (~17 GB, ~30 min)
./build/fetch-source.sh

# 3. Apply patches (instant)
./build/apply-patches.sh

# 4. Build (4–12 hours, ~80 GB disk, 32+ GB RAM recommended)
./build/build.sh
```

For a clean Linux x86_64 build that mirrors what ships in our releases, use
`./build/build-linux.sh` instead (runs the full clone → patch → ninja pipeline
in a single script; designed for fresh Ubuntu hosts).

See [`build/README.md`](./build/README.md) for detailed prerequisites.

## License

Clark-authored wrapper code, specs, and patches are MIT. ungoogled-chromium,
Chromium upstream components, and ported open-source code retain their
respective BSD/MPL/other licenses; this project does not modify those upstream
license terms.

## Status

**Alpha.** Linux x86_64 and macOS arm64 builds are reproducible end-to-end and
the patches above are runtime-confirmed against the built binary. Other
documented surfaces are still backlog/spec work or need broader detection-site
benchmarking. Contributions welcome — see `specs/` for the patch backlog.
