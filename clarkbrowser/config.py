# Copyright 2026 Clark Labs Inc.
# SPDX-License-Identifier: MIT

"""Stealth defaults and platform detection for clark-browser."""
from __future__ import annotations

import os
import platform
import random
import re
from hashlib import sha256
from pathlib import Path
from xml.sax.saxutils import escape

from ._version import __version__

# ---------------------------------------------------------------------------
# Chromium version shipped with this release of clark-browser.
# Updated when we rebase against a newer upstream + ungoogled-chromium tag.
# ---------------------------------------------------------------------------
CHROMIUM_VERSION = "148.0.7778.96"
CHROMIUM_RELEASE_TAG = "chromium-v148.0.7778.96-stealth5"

PLATFORM_CHROMIUM_VERSIONS: dict[str, str] = {
    "linux-x64": CHROMIUM_VERSION,
    "darwin-arm64": CHROMIUM_VERSION,
    "darwin-x64": CHROMIUM_VERSION,
    "windows-x64": CHROMIUM_VERSION,
}

# Playwright default args we suppress — they leak automation signals.
IGNORE_DEFAULT_ARGS = ["--enable-automation", "--enable-unsafe-swiftshader"]

# Default viewport — used as a fallback when the seed-derived screen size
# is not available (e.g. stealth_args=False without explicit screen switches).
DEFAULT_VIEWPORT = {"width": 1920, "height": 947}

# Screen-size pool — must match the C++ pool in patches/000-shared/clark_seed.cc.
# The launcher picks deterministically from this pool so the Playwright viewport
# and the binary's screen.width/height never disagree.
SCREEN_SIZE_POOL: tuple[tuple[int, int], ...] = (
    (1920, 1080),
    (1536, 864),
    (2560, 1440),
    (1366, 768),
    (1440, 900),
)

# Taskbar height per platform — must match clark::seed::TaskbarHeight().
PLATFORM_TASKBAR_HEIGHTS: dict[str, int] = {"windows": 48, "macos": 95, "linux": 0}


# UA strings matched to --fingerprint-platform. Chromium reads the HTTP
# User-Agent from the browser process at request time, not from
# navigator.userAgent — so we MUST pass --user-agent on the command line too,
# otherwise the HTTP header and the JS string disagree (a textbook
# bot-detection signal). The patched binary still rewrites
# navigator.userAgent based on --fingerprint-platform; we just match.
_CHROMIUM_BROWSER_VERSION = CHROMIUM_VERSION.split(".")[0] + ".0.0.0"
PLATFORM_USER_AGENTS: dict[str, str] = {
    "windows": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{_CHROMIUM_BROWSER_VERSION} Safari/537.36"
    ),
    "macos": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{_CHROMIUM_BROWSER_VERSION} Safari/537.36"
    ),
    "linux": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{_CHROMIUM_BROWSER_VERSION} Safari/537.36"
    ),
}

PLATFORM_CLIENT_HINT_VERSIONS: dict[str, str] = {
    "windows": "19.0.0",
    "macos": "10.15.7",
    "linux": "",
}

FINGERPRINT_PLATFORM_ENV = "CLARK_FINGERPRINT_PLATFORM"
FINGERPRINT_FONTS_DIR_ENV = "CLARK_FINGERPRINT_FONTS_DIR"
WINDOWS_FONTS_DIR_ENV = "CLARK_WINDOWS_FONTS_DIR"
LINUX_FONTS_DIR_ENV = "CLARK_LINUX_FONTS_DIR"
FINGERPRINT_NETWORK_PROFILE_ENV = "CLARK_FINGERPRINT_NETWORK_PROFILE"
NETWORK_PROFILES = {"desktop", "residential", "datacenter", "mobile", "slow"}
WEBRTC_POLICY_ENV = "CLARK_WEBRTC_POLICY"
WEBRTC_FORCE_IP_HANDLING_SWITCH = "--force-webrtc-ip-handling-policy"
WEBRTC_IP_HANDLING_POLICY_SWITCH = "--webrtc-ip-handling-policy"
WEBRTC_PROXY_COHERENT_POLICY = "disable_non_proxied_udp"
WEBGPU_POLICY_ENV = "CLARK_WEBGPU_POLICY"
WEBGPU_DISABLE_FEATURE_SWITCH = "--disable-features"
WEBGPU_ENABLE_FEATURE_SWITCH = "--enable-features"
WEBGPU_UNSAFE_ENABLE_SWITCH = "--enable-unsafe-webgpu"
WEBGPU_FEATURE_NAME = "WebGPU"
WEBRTC_POLICY_ALIASES = {
    "proxy-coherent": WEBRTC_PROXY_COHERENT_POLICY,
    "proxy_coherent": WEBRTC_PROXY_COHERENT_POLICY,
    "disable-non-proxied-udp": WEBRTC_PROXY_COHERENT_POLICY,
    "disable_non_proxied_udp": WEBRTC_PROXY_COHERENT_POLICY,
    "public-only": "default_public_interface_only",
    "public_only": "default_public_interface_only",
    "default-public-interface-only": "default_public_interface_only",
    "default_public_interface_only": "default_public_interface_only",
    "public-and-private": "default_public_and_private_interfaces",
    "public_and_private": "default_public_and_private_interfaces",
    "default-public-and-private-interfaces": (
        "default_public_and_private_interfaces"
    ),
    "default_public_and_private_interfaces": (
        "default_public_and_private_interfaces"
    ),
    "default": "default",
    "off": "",
    "false": "",
    "0": "",
}
WEBGPU_POLICY_ALIASES = {
    "headless-off": "headless-off",
    "headless_off": "headless-off",
    "auto": "headless-off",
    "disabled": "disabled",
    "disable": "disabled",
    "off": "disabled",
    "false": "disabled",
    "0": "disabled",
    "coherent": "coherent",
    "profile": "coherent",
    "on": "coherent",
    "true": "coherent",
    "1": "coherent",
}
FONT_FILE_SUFFIXES = {".ttf", ".ttc", ".otf"}
FINGERPRINT_FONTS_DIR_SWITCH = "--fingerprint-fonts-dir"
WINDOWS_REQUIRED_FONT_FAMILIES: dict[str, tuple[str, ...]] = {
    "Arial": ("arial",),
    "Calibri": ("calibri",),
    "Segoe UI": ("segoe",),
}
LINUX_RECOMMENDED_FONT_FAMILIES = (
    "DejaVu Sans",
    "Liberation Sans",
    "Noto Sans",
    "Ubuntu",
    "Ubuntu Mono",
)


def _get_env(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _hash_seed_index(seed: str, key: str, modulus: int) -> int:
    """Deterministic (seed, key) → [0, modulus). Uses SHA-256 so the mapping
    is stable across Python versions and processes. Does NOT need to match the
    C++ SipHash — when the launcher passes --fingerprint-screen-{width,height}
    explicitly, the binary uses those values directly."""
    digest = sha256(f"{seed}|{key}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "little") % modulus


def pick_screen_size(seed: str) -> tuple[int, int]:
    """Pick a coherent (width, height) pair from the pool for a given seed."""
    return SCREEN_SIZE_POOL[_hash_seed_index(seed, "screen", len(SCREEN_SIZE_POOL))]


def get_taskbar_height(fp_platform: str | None = None) -> int:
    """Taskbar height for a platform — matches clark::seed::TaskbarHeight()."""
    platform_key = (fp_platform or get_default_fingerprint_platform()).lower()
    return PLATFORM_TASKBAR_HEIGHTS.get(platform_key, 48)


def get_screen_from_args(args: list[str]) -> tuple[int, int] | None:
    """Extract (width, height) from --fingerprint-screen-{width,height} args."""
    w = h = None
    for arg in args:
        key, sep, value = arg.partition("=")
        if not sep:
            continue
        if key == "--fingerprint-screen-width":
            w = int(value) if value.isdigit() else None
        elif key == "--fingerprint-screen-height":
            h = int(value) if value.isdigit() else None
    if w and h:
        return (w, h)
    return None


def get_viewport_from_args(args: list[str]) -> dict[str, int]:
    """Derive a Playwright viewport dict from resolved stealth args.

    The viewport (window.innerWidth/innerHeight) is set to screen.width ×
    (screen.height − taskbar) so it stays coherent with the binary's
    screen.* and window.outer* values.
    """
    screen = get_screen_from_args(args)
    if screen:
        fp_platform = None
        for arg in args:
            key, sep, value = arg.partition("=")
            if sep and key == "--fingerprint-platform":
                fp_platform = value
        taskbar = get_taskbar_height(fp_platform)
        return {"width": screen[0], "height": screen[1] - taskbar}
    return dict(DEFAULT_VIEWPORT)


def _font_files(fonts_dir: Path) -> list[Path]:
    return [
        path for path in fonts_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in FONT_FILE_SUFFIXES
    ]


def _font_stem_key(path: Path) -> str:
    return re.sub(r"[^a-z0-9]+", "", path.stem.lower())


def validate_fingerprint_fonts_dir(
    fonts_dir: str | os.PathLike[str],
    fp_platform: str | None,
) -> str:
    """Validate a configured target-platform font directory.

    This catches the high-signal incoherence where a non-Windows host claims a
    Windows profile but points the browser at a small Linux font directory.
    """
    path = Path(fonts_dir).expanduser()
    if not path.is_dir():
        raise RuntimeError(
            f"Fingerprint font directory does not exist or is not a directory: "
            f"{path}"
        )

    files = _font_files(path)
    if not files:
        raise RuntimeError(
            f"Fingerprint font directory contains no .ttf, .ttc, or .otf "
            f"files: {path}"
        )

    platform_key = (fp_platform or get_default_fingerprint_platform()).lower()
    if platform_key == "windows":
        stems = {_font_stem_key(file) for file in files}
        missing = [
            family
            for family, prefixes in WINDOWS_REQUIRED_FONT_FAMILIES.items()
            if not any(
                stem.startswith(prefix)
                for stem in stems
                for prefix in prefixes
            )
        ]
        if missing:
            raise RuntimeError(
                "Windows fingerprint profiles require a Windows font pack. "
                f"{path} is missing core families: {', '.join(missing)}. "
                f"Set {WINDOWS_FONTS_DIR_ENV} to a directory containing "
                "licensed Windows fonts, or use "
                f"{FINGERPRINT_PLATFORM_ENV}=linux."
            )

    return os.fspath(path)


def get_default_fingerprint_platform() -> str:
    """Return the coherent platform profile for launcher-supplied defaults."""
    override = _get_env(FINGERPRINT_PLATFORM_ENV)
    if override:
        fp_platform = override.lower()
        if fp_platform not in PLATFORM_USER_AGENTS:
            supported = ", ".join(sorted(PLATFORM_USER_AGENTS))
            raise RuntimeError(
                f"Unsupported {FINGERPRINT_PLATFORM_ENV}={override!r}. "
                f"Supported: {supported}"
            )
        return fp_platform

    if platform.system() == "Darwin":
        return "macos"

    # A Windows profile on Linux is only coherent when a target Windows font
    # pack is configured; otherwise detectors see a Windows UA plus Linux fonts.
    if _get_env(WINDOWS_FONTS_DIR_ENV):
        return "windows"
    return "linux"


def get_fingerprint_fonts_dir(fp_platform: str | None = None) -> str | None:
    """Return an optional platform font directory passed to Chromium."""
    platform_key = (fp_platform or get_default_fingerprint_platform()).lower()
    explicit = _get_env(FINGERPRINT_FONTS_DIR_ENV)
    if explicit:
        return validate_fingerprint_fonts_dir(explicit, platform_key)
    if platform_key == "windows":
        windows_dir = _get_env(WINDOWS_FONTS_DIR_ENV)
        if windows_dir:
            return validate_fingerprint_fonts_dir(windows_dir, platform_key)
        return None
    if platform_key == "linux":
        linux_dir = _get_env(LINUX_FONTS_DIR_ENV)
        if linux_dir:
            return validate_fingerprint_fonts_dir(linux_dir, platform_key)
    return None


def get_fingerprint_fonts_dir_from_args(args: list[str]) -> str | None:
    for arg in args:
        if arg.startswith(f"{FINGERPRINT_FONTS_DIR_SWITCH}="):
            return arg.split("=", 1)[1] or None
    return None


def get_fontconfig_env_for_fonts_dir(fonts_dir: str | None) -> dict[str, str]:
    """Return Linux Fontconfig env needed to expose a profile font directory."""
    if platform.system() != "Linux" or not fonts_dir:
        return {}

    fonts_path = Path(fonts_dir).expanduser()
    digest = sha256(os.fspath(fonts_path).encode("utf-8")).hexdigest()[:16]
    conf_dir = get_cache_dir() / "fontconfig"
    conf_dir.mkdir(parents=True, exist_ok=True)
    conf_path = conf_dir / f"profile-fonts-{digest}.conf"
    config = (
        '<?xml version="1.0"?>\n'
        '<!DOCTYPE fontconfig SYSTEM "fonts.dtd">\n'
        '<fontconfig>\n'
        '  <include ignore_missing="yes">/etc/fonts/fonts.conf</include>\n'
        f"  <dir>{escape(os.fspath(fonts_path))}</dir>\n"
        "</fontconfig>\n"
    )
    if not conf_path.exists() or conf_path.read_text() != config:
        conf_path.write_text(config)
    return {"FONTCONFIG_FILE": os.fspath(conf_path)}


def get_fontconfig_env_for_args(args: list[str]) -> dict[str, str]:
    return get_fontconfig_env_for_fonts_dir(
        get_fingerprint_fonts_dir_from_args(args)
    )


def get_fingerprint_network_profile() -> str | None:
    """Return an optional network profile matched to the proxy/IP type."""
    profile = _get_env(FINGERPRINT_NETWORK_PROFILE_ENV)
    if profile is None:
        return None
    profile = profile.lower()
    if profile not in NETWORK_PROFILES:
        raise RuntimeError(
            f"Unsupported {FINGERPRINT_NETWORK_PROFILE_ENV}={profile!r}. "
            f"Supported: {', '.join(sorted(NETWORK_PROFILES))}"
        )
    return profile


def normalize_webrtc_policy(policy: str | None) -> str | None:
    """Map Clark-friendly WebRTC policy names to Chromium policy values."""
    value = (policy or _get_env(WEBRTC_POLICY_ENV))
    if value is None:
        return None
    key = value.strip().lower()
    if key in WEBRTC_POLICY_ALIASES:
        normalized = WEBRTC_POLICY_ALIASES[key]
        return normalized or None
    supported = ", ".join(sorted(WEBRTC_POLICY_ALIASES))
    raise RuntimeError(
        f"Unsupported WebRTC policy {value!r}. Supported: {supported}"
    )


def normalize_webgpu_policy(policy: str | None) -> str | None:
    """Return Clark's WebGPU policy name, or None when not configured."""
    value = (policy or _get_env(WEBGPU_POLICY_ENV))
    if value is None:
        return None
    key = value.strip().lower()
    if key in WEBGPU_POLICY_ALIASES:
        return WEBGPU_POLICY_ALIASES[key]
    supported = ", ".join(sorted(WEBGPU_POLICY_ALIASES))
    raise RuntimeError(
        f"Unsupported WebGPU policy {value!r}. Supported: {supported}"
    )


def get_default_stealth_args() -> list[str]:
    """Stealth flags applied automatically by launch() unless stealth_args=False.

    The patched binary auto-generates the rest from --fingerprint=<seed>.
    """
    seed = random.randint(10000, 99999)
    seed_str = str(seed)
    fp_platform = get_default_fingerprint_platform()
    fonts_dir = get_fingerprint_fonts_dir(fp_platform)
    if fp_platform == "windows" and platform.system() != "Windows" and not fonts_dir:
        raise RuntimeError(
            "Windows fingerprint profiles require a configured font directory "
            f"on this host. Set {WINDOWS_FONTS_DIR_ENV} or "
            f"{FINGERPRINT_FONTS_DIR_ENV}, or use "
            f"{FINGERPRINT_PLATFORM_ENV}=linux."
        )

    screen_w, screen_h = pick_screen_size(seed_str)
    args = [
        "--no-sandbox",
        f"--fingerprint={seed}",
        f"--fingerprint-platform={fp_platform}",
        f"--fingerprint-brand=Chrome",
        f"--fingerprint-brand-version={_CHROMIUM_BROWSER_VERSION}",
        f"--user-agent={PLATFORM_USER_AGENTS[fp_platform]}",
        "--accept-lang=en-US,en",
        # Pin screen dimensions so the Playwright viewport and the binary's
        # screen.width/height stay coherent (patch #11 picks these up).
        f"--fingerprint-screen-width={screen_w}",
        f"--fingerprint-screen-height={screen_h}",
        # Ungoogled runtime noise switches are intentionally opt-in upstream;
        # Clark enables them by default and patch #50 forwards them to renderers.
        "--fingerprinting-client-rects-noise",
        "--fingerprinting-canvas-measuretext-noise",
        "--fingerprinting-canvas-image-data-noise",
        # macOS needs this to avoid hanging on Keychain mutex in unsigned dev builds.
        # No effect on Linux.
        "--use-mock-keychain",
    ]
    if fonts_dir:
        args.append(f"--fingerprint-fonts-dir={fonts_dir}")
    network_profile = get_fingerprint_network_profile()
    if network_profile:
        args.append(f"--fingerprint-network-profile={network_profile}")
    client_hint_platform_version = PLATFORM_CLIENT_HINT_VERSIONS[fp_platform]
    if client_hint_platform_version:
        args.append(f"--fingerprint-platform-version={client_hint_platform_version}")
    return args


# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------
SUPPORTED_PLATFORMS: dict[tuple[str, str], str] = {
    ("Linux", "x86_64"): "linux-x64",
    ("Darwin", "arm64"): "darwin-arm64",
    ("Darwin", "x86_64"): "darwin-x64",
    ("Windows", "AMD64"): "windows-x64",
    ("Windows", "x86_64"): "windows-x64",
}

AVAILABLE_PLATFORMS: set[str] = set(PLATFORM_CHROMIUM_VERSIONS.keys())


def get_chromium_version() -> str:
    return PLATFORM_CHROMIUM_VERSIONS.get(get_platform_tag(), CHROMIUM_VERSION)


def get_release_tag(version: str | None = None) -> str:
    """GitHub release tag that contains the patched binary for a Chromium version."""
    v = version or get_chromium_version()
    if v == CHROMIUM_VERSION:
        return CHROMIUM_RELEASE_TAG
    return f"chromium-v{v}"


def get_platform_tag() -> str:
    system = platform.system()
    machine = platform.machine()
    tag = SUPPORTED_PLATFORMS.get((system, machine))
    if tag is None:
        raise RuntimeError(
            f"Unsupported platform: {system} {machine}. "
            f"Supported: {', '.join(f'{s}-{m}' for (s, m) in SUPPORTED_PLATFORMS)}"
        )
    return tag


def get_cache_dir() -> Path:
    """Override with CLARK_CACHE_DIR env var. Default: ~/.clarkbrowser/."""
    custom = os.environ.get("CLARK_CACHE_DIR")
    if custom:
        return Path(custom)
    return Path.home() / ".clarkbrowser"


def get_binary_dir(version: str | None = None) -> Path:
    v = version or get_chromium_version()
    return get_cache_dir() / f"chromium-{v}"


def get_binary_path(version: str | None = None) -> Path:
    binary_dir = get_binary_dir(version)
    if platform.system() == "Darwin":
        return binary_dir / "Chromium.app" / "Contents" / "MacOS" / "Chromium"
    if platform.system() == "Windows":
        return binary_dir / "chrome.exe"
    chrome = binary_dir / "chrome"
    headless = binary_dir / "headless_shell"
    if chrome.exists() or not headless.exists():
        return chrome
    return headless


def get_local_binary_override() -> str | None:
    """Skip download — use a locally built clark-stealth-chromium binary."""
    return os.environ.get("CLARK_BINARY_PATH")


# ---------------------------------------------------------------------------
# Download URLs (GitHub Releases)
# ---------------------------------------------------------------------------
DOWNLOAD_BASE_URL = os.environ.get(
    "CLARK_DOWNLOAD_URL",
    "https://github.com/clark-labs-inc/clark-browser/releases/download",
)


def get_archive_ext(tag: str | None = None) -> str:
    platform_tag = tag or get_platform_tag()
    if platform_tag == "windows-x64":
        return ".zip"
    return ".tar.gz"


def get_archive_name(tag: str | None = None) -> str:
    t = tag or get_platform_tag()
    return f"clark-browser-{t}{get_archive_ext(t)}"


def get_download_url(version: str | None = None) -> str:
    return f"{DOWNLOAD_BASE_URL}/{get_release_tag(version)}/{get_archive_name()}"
