# Copyright 2026 Clark Labs Inc.
# SPDX-License-Identifier: MIT

"""Smoke tests that don't require the binary."""
from __future__ import annotations


def _font_pack(tmp_path, name: str, files: list[str]) -> str:
    fonts_dir = tmp_path / name
    fonts_dir.mkdir()
    for filename in files:
        (fonts_dir / filename).write_bytes(b"dummy font")
    return str(fonts_dir)


def _windows_font_pack(tmp_path) -> str:
    return _font_pack(
        tmp_path,
        "windows-fonts",
        ["arial.ttf", "calibri.ttf", "segoeui.ttf"],
    )


def _linux_font_pack(tmp_path) -> str:
    return _font_pack(tmp_path, "linux-fonts", ["DejaVuSans.ttf"])


def test_imports() -> None:
    import clarkbrowser  # noqa: F401
    from clarkbrowser import (  # noqa: F401
        InteractionPacer,
        assess_launch_hygiene,
        ensure_binary,
        launch,
        launch_async,
    )


def test_default_args_have_fingerprint(monkeypatch) -> None:
    from clarkbrowser import get_default_stealth_args
    monkeypatch.delenv("CLARK_FINGERPRINT_PLATFORM", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_WINDOWS_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_NETWORK_PROFILE", raising=False)
    monkeypatch.delenv("CLARK_WEBRTC_POLICY", raising=False)
    args = get_default_stealth_args()
    assert any(a.startswith("--fingerprint=") for a in args)


def test_default_args_have_client_hint_identity(monkeypatch) -> None:
    from clarkbrowser import get_default_stealth_args
    monkeypatch.delenv("CLARK_FINGERPRINT_PLATFORM", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_WINDOWS_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_NETWORK_PROFILE", raising=False)
    args = get_default_stealth_args()
    assert "--fingerprint-brand=Chrome" in args
    assert any(a.startswith("--fingerprint-brand-version=") for a in args)


def test_linux_default_profile_matches_linux_fonts(monkeypatch) -> None:
    from clarkbrowser import config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    monkeypatch.delenv("CLARK_FINGERPRINT_PLATFORM", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_WINDOWS_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_NETWORK_PROFILE", raising=False)

    args = config.get_default_stealth_args()

    assert "--fingerprint-platform=linux" in args
    assert any("X11; Linux x86_64" in a for a in args)
    assert not any(a.startswith("--fingerprint-platform-version=") for a in args)
    assert not any(a.startswith("--fingerprint-fonts-dir=") for a in args)


def test_linux_windows_profile_requires_font_pack(monkeypatch, tmp_path) -> None:
    from clarkbrowser import config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    monkeypatch.delenv("CLARK_FINGERPRINT_PLATFORM", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_FONTS_DIR", raising=False)
    windows_fonts = _windows_font_pack(tmp_path)
    monkeypatch.setenv("CLARK_WINDOWS_FONTS_DIR", windows_fonts)
    monkeypatch.delenv("CLARK_FINGERPRINT_NETWORK_PROFILE", raising=False)

    args = config.get_default_stealth_args()

    assert "--fingerprint-platform=windows" in args
    assert "--fingerprint-platform-version=19.0.0" in args
    assert f"--fingerprint-fonts-dir={windows_fonts}" in args
    assert any("Windows NT 10.0" in a for a in args)


def test_linux_profile_uses_linux_font_pack_when_configured(
    monkeypatch, tmp_path
) -> None:
    from clarkbrowser import config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    linux_fonts = _linux_font_pack(tmp_path)
    cache_dir = tmp_path / "cache"
    monkeypatch.delenv("CLARK_FINGERPRINT_PLATFORM", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_WINDOWS_FONTS_DIR", raising=False)
    monkeypatch.setenv("CLARK_LINUX_FONTS_DIR", linux_fonts)
    monkeypatch.setenv("CLARK_CACHE_DIR", str(cache_dir))
    monkeypatch.delenv("CLARK_FINGERPRINT_NETWORK_PROFILE", raising=False)

    args = config.get_default_stealth_args()
    font_env = config.get_fontconfig_env_for_args(args)

    assert "--fingerprint-platform=linux" in args
    assert f"--fingerprint-fonts-dir={linux_fonts}" in args
    assert "FONTCONFIG_FILE" in font_env
    with open(font_env["FONTCONFIG_FILE"]) as config_file:
        assert linux_fonts in config_file.read()


def test_fingerprint_platform_env_overrides_default(monkeypatch, tmp_path) -> None:
    from clarkbrowser import config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    windows_fonts = _windows_font_pack(tmp_path)
    monkeypatch.setenv("CLARK_FINGERPRINT_PLATFORM", "windows")
    monkeypatch.setenv("CLARK_FINGERPRINT_FONTS_DIR", windows_fonts)
    monkeypatch.delenv("CLARK_WINDOWS_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_NETWORK_PROFILE", raising=False)

    args = config.get_default_stealth_args()

    assert "--fingerprint-platform=windows" in args
    assert f"--fingerprint-fonts-dir={windows_fonts}" in args


def test_windows_profile_without_fonts_is_rejected(monkeypatch) -> None:
    import pytest
    from clarkbrowser import config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    monkeypatch.setenv("CLARK_FINGERPRINT_PLATFORM", "windows")
    monkeypatch.delenv("CLARK_FINGERPRINT_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_WINDOWS_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_NETWORK_PROFILE", raising=False)

    with pytest.raises(RuntimeError, match="Windows fingerprint profiles require"):
        config.get_default_stealth_args()


def test_windows_fonts_dir_must_exist(monkeypatch, tmp_path) -> None:
    import pytest
    from clarkbrowser import config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    monkeypatch.delenv("CLARK_FINGERPRINT_PLATFORM", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_FONTS_DIR", raising=False)
    monkeypatch.setenv("CLARK_WINDOWS_FONTS_DIR", str(tmp_path / "missing"))
    monkeypatch.delenv("CLARK_FINGERPRINT_NETWORK_PROFILE", raising=False)

    with pytest.raises(RuntimeError, match="does not exist"):
        config.get_default_stealth_args()


def test_windows_fonts_dir_must_contain_font_files(monkeypatch, tmp_path) -> None:
    import pytest
    from clarkbrowser import config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    empty_fonts = tmp_path / "empty-windows-fonts"
    empty_fonts.mkdir()
    monkeypatch.delenv("CLARK_FINGERPRINT_PLATFORM", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_FONTS_DIR", raising=False)
    monkeypatch.setenv("CLARK_WINDOWS_FONTS_DIR", str(empty_fonts))
    monkeypatch.delenv("CLARK_FINGERPRINT_NETWORK_PROFILE", raising=False)

    with pytest.raises(RuntimeError, match="contains no"):
        config.get_default_stealth_args()


def test_windows_profile_with_linux_fonts_is_rejected(monkeypatch, tmp_path) -> None:
    import pytest
    from clarkbrowser import config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    linux_fonts = _linux_font_pack(tmp_path)
    monkeypatch.setenv("CLARK_FINGERPRINT_PLATFORM", "windows")
    monkeypatch.setenv("CLARK_FINGERPRINT_FONTS_DIR", linux_fonts)
    monkeypatch.delenv("CLARK_WINDOWS_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_NETWORK_PROFILE", raising=False)

    with pytest.raises(RuntimeError, match="missing core families"):
        config.get_default_stealth_args()


def test_user_platform_override_rewrites_matched_identity(
    monkeypatch, tmp_path
) -> None:
    from clarkbrowser import browser, config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    monkeypatch.setattr(browser.host_platform, "system", lambda: "Linux")
    windows_fonts = _windows_font_pack(tmp_path)
    monkeypatch.delenv("CLARK_FINGERPRINT_PLATFORM", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_WINDOWS_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_NETWORK_PROFILE", raising=False)

    args = browser._resolve_args(
        [
            "--fingerprint-platform=windows",
            f"--fingerprint-fonts-dir={windows_fonts}",
        ],
        True,
        None,
        None,
        None,
        None,
        None,
        True,
    )

    assert "--fingerprint-platform=windows" in args
    assert "--fingerprint-platform-version=19.0.0" in args
    assert f"--fingerprint-fonts-dir={windows_fonts}" in args
    assert any("Windows NT 10.0" in a for a in args)
    assert not any("X11; Linux x86_64" in a for a in args)


def test_user_windows_platform_without_fonts_is_rejected(monkeypatch) -> None:
    import pytest
    from clarkbrowser import browser, config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    monkeypatch.setattr(browser.host_platform, "system", lambda: "Linux")
    monkeypatch.delenv("CLARK_FINGERPRINT_PLATFORM", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_WINDOWS_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_NETWORK_PROFILE", raising=False)
    monkeypatch.delenv("CLARK_WEBRTC_POLICY", raising=False)

    with pytest.raises(RuntimeError, match="Windows fingerprint profiles require"):
        browser._resolve_args(
            ["--fingerprint-platform=windows"],
            True,
            None,
            None,
            None,
            None,
            None,
            True,
        )


def test_user_windows_platform_with_linux_fonts_is_rejected(
    monkeypatch, tmp_path
) -> None:
    import pytest
    from clarkbrowser import browser, config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    monkeypatch.setattr(browser.host_platform, "system", lambda: "Linux")
    linux_fonts = _linux_font_pack(tmp_path)
    monkeypatch.delenv("CLARK_FINGERPRINT_PLATFORM", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_WINDOWS_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_NETWORK_PROFILE", raising=False)
    monkeypatch.delenv("CLARK_WEBRTC_POLICY", raising=False)

    with pytest.raises(RuntimeError, match="missing core families"):
        browser._resolve_args(
            [
                "--fingerprint-platform=windows",
                f"--fingerprint-fonts-dir={linux_fonts}",
            ],
            True,
            None,
            None,
            None,
            None,
            None,
            True,
        )


def test_launch_env_adds_fontconfig_for_profile_fonts(monkeypatch, tmp_path) -> None:
    from clarkbrowser import browser, config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    linux_fonts = _linux_font_pack(tmp_path)
    cache_dir = tmp_path / "cache"
    monkeypatch.setenv("CLARK_CACHE_DIR", str(cache_dir))

    kwargs = browser._cohere_browser_env(
        [f"--fingerprint-fonts-dir={linux_fonts}"],
        {},
    )

    assert "env" in kwargs
    assert "FONTCONFIG_FILE" in kwargs["env"]
    with open(kwargs["env"]["FONTCONFIG_FILE"]) as config_file:
        assert linux_fonts in config_file.read()


def test_network_profile_env_adds_default_arg(monkeypatch) -> None:
    from clarkbrowser import config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    monkeypatch.delenv("CLARK_FINGERPRINT_PLATFORM", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_WINDOWS_FONTS_DIR", raising=False)
    monkeypatch.setenv("CLARK_FINGERPRINT_NETWORK_PROFILE", "mobile")
    monkeypatch.delenv("CLARK_WEBRTC_POLICY", raising=False)

    args = config.get_default_stealth_args()

    assert "--fingerprint-network-profile=mobile" in args


def test_network_profile_launch_param_overrides_env(monkeypatch) -> None:
    from clarkbrowser import browser, config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    monkeypatch.delenv("CLARK_FINGERPRINT_PLATFORM", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_WINDOWS_FONTS_DIR", raising=False)
    monkeypatch.setenv("CLARK_FINGERPRINT_NETWORK_PROFILE", "mobile")
    monkeypatch.delenv("CLARK_WEBRTC_POLICY", raising=False)

    args = browser._resolve_args(
        [], True, None, None, "datacenter", None, None, True
    )

    assert "--fingerprint-network-profile=datacenter" in args
    assert "--fingerprint-network-profile=mobile" not in args


def test_webrtc_proxy_coherent_policy_adds_chromium_arg(monkeypatch) -> None:
    from clarkbrowser import browser, config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    monkeypatch.delenv("CLARK_FINGERPRINT_PLATFORM", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_WINDOWS_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_NETWORK_PROFILE", raising=False)
    monkeypatch.delenv("CLARK_WEBRTC_POLICY", raising=False)

    args = browser._resolve_args(
        [], True, None, None, None, "proxy-coherent", None, True
    )

    assert "--force-webrtc-ip-handling-policy=disable_non_proxied_udp" in args
    assert "--webrtc-ip-handling-policy=disable_non_proxied_udp" in args


def test_webrtc_policy_env_is_opt_in(monkeypatch) -> None:
    from clarkbrowser import browser, config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    monkeypatch.delenv("CLARK_FINGERPRINT_PLATFORM", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_WINDOWS_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_NETWORK_PROFILE", raising=False)
    monkeypatch.delenv("CLARK_WEBRTC_POLICY", raising=False)

    args = browser._resolve_args([], True, None, None, None, None, None, True)

    assert not any(
        a.startswith("--force-webrtc-ip-handling-policy=") for a in args
    )
    assert not any(a.startswith("--webrtc-ip-handling-policy=") for a in args)


def test_webrtc_policy_env_adds_proxy_coherent_arg(monkeypatch) -> None:
    from clarkbrowser import browser, config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    monkeypatch.delenv("CLARK_FINGERPRINT_PLATFORM", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_WINDOWS_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_NETWORK_PROFILE", raising=False)
    monkeypatch.setenv("CLARK_WEBRTC_POLICY", "proxy-coherent")

    args = browser._resolve_args([], True, None, None, None, None, None, True)

    assert "--force-webrtc-ip-handling-policy=disable_non_proxied_udp" in args
    assert "--webrtc-ip-handling-policy=disable_non_proxied_udp" in args


def test_user_webrtc_policy_arg_wins(monkeypatch) -> None:
    from clarkbrowser import browser, config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    monkeypatch.delenv("CLARK_FINGERPRINT_PLATFORM", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_WINDOWS_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_NETWORK_PROFILE", raising=False)
    monkeypatch.setenv("CLARK_WEBRTC_POLICY", "proxy-coherent")

    args = browser._resolve_args(
        ["--force-webrtc-ip-handling-policy=default"],
        True,
        None,
        None,
        None,
        None,
        None,
        True,
    )

    assert "--force-webrtc-ip-handling-policy=default" in args
    assert "--force-webrtc-ip-handling-policy=disable_non_proxied_udp" not in args
    assert "--webrtc-ip-handling-policy=disable_non_proxied_udp" not in args


def test_invalid_webrtc_policy_is_rejected(monkeypatch) -> None:
    import pytest
    from clarkbrowser import browser, config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    monkeypatch.delenv("CLARK_FINGERPRINT_PLATFORM", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_WINDOWS_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_NETWORK_PROFILE", raising=False)
    monkeypatch.delenv("CLARK_WEBRTC_POLICY", raising=False)

    with pytest.raises(RuntimeError, match="Unsupported WebRTC policy"):
        browser._resolve_args([], True, None, None, None, "leaky", None, True)


def test_headless_webgpu_defaults_to_deliberately_disabled(monkeypatch) -> None:
    from clarkbrowser import browser, config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    monkeypatch.delenv("CLARK_FINGERPRINT_PLATFORM", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_WINDOWS_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_NETWORK_PROFILE", raising=False)
    monkeypatch.delenv("CLARK_WEBGPU_POLICY", raising=False)

    args = browser._resolve_args([], True, None, None, None, None, None, True)

    assert "--disable-features=WebGPU" in args


def test_headed_webgpu_default_does_not_disable(monkeypatch) -> None:
    from clarkbrowser import browser, config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    monkeypatch.delenv("CLARK_FINGERPRINT_PLATFORM", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_WINDOWS_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_NETWORK_PROFILE", raising=False)
    monkeypatch.delenv("CLARK_WEBGPU_POLICY", raising=False)

    args = browser._resolve_args([], True, None, None, None, None, None, False)

    assert "--disable-features=WebGPU" not in args


def test_webgpu_default_respects_stealth_args_false(monkeypatch) -> None:
    from clarkbrowser import browser, config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    monkeypatch.delenv("CLARK_FINGERPRINT_PLATFORM", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_WINDOWS_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_NETWORK_PROFILE", raising=False)
    monkeypatch.delenv("CLARK_WEBGPU_POLICY", raising=False)

    args = browser._resolve_args([], False, None, None, None, None, None, True)

    assert "--disable-features=WebGPU" not in args


def test_webgpu_coherent_policy_keeps_webgpu_available(monkeypatch) -> None:
    from clarkbrowser import browser, config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    monkeypatch.delenv("CLARK_FINGERPRINT_PLATFORM", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_WINDOWS_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_NETWORK_PROFILE", raising=False)
    monkeypatch.setenv("CLARK_WEBGPU_POLICY", "coherent")

    args = browser._resolve_args([], True, None, None, None, None, None, True)

    assert "--disable-features=WebGPU" not in args


def test_user_webgpu_feature_arg_wins(monkeypatch) -> None:
    from clarkbrowser import browser, config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    monkeypatch.delenv("CLARK_FINGERPRINT_PLATFORM", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_WINDOWS_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_NETWORK_PROFILE", raising=False)
    monkeypatch.setenv("CLARK_WEBGPU_POLICY", "disabled")

    args = browser._resolve_args(
        ["--enable-features=WebGPU"], True, None, None, None, None, None, True
    )

    assert "--enable-features=WebGPU" in args
    assert "--disable-features=WebGPU" not in args


def test_webgpu_disabled_policy_merges_disable_features(monkeypatch) -> None:
    from clarkbrowser import browser, config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    monkeypatch.delenv("CLARK_FINGERPRINT_PLATFORM", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_WINDOWS_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_NETWORK_PROFILE", raising=False)
    monkeypatch.delenv("CLARK_WEBGPU_POLICY", raising=False)

    args = browser._resolve_args(
        ["--disable-features=Foo"], True, None, None, None, None, "disabled", True
    )

    assert "--disable-features=Foo,WebGPU" in args


def test_invalid_webgpu_policy_is_rejected(monkeypatch) -> None:
    import pytest
    from clarkbrowser import browser, config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    monkeypatch.delenv("CLARK_FINGERPRINT_PLATFORM", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_WINDOWS_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_NETWORK_PROFILE", raising=False)
    monkeypatch.delenv("CLARK_WEBGPU_POLICY", raising=False)

    with pytest.raises(RuntimeError, match="Unsupported WebGPU policy"):
        browser._resolve_args([], True, None, None, None, None, "leaky", True)


def test_launch_hygiene_flags_devtools_and_public_cdp() -> None:
    from clarkbrowser import assess_launch_hygiene

    findings = assess_launch_hygiene(
        [
            "--enable-automation",
            "--remote-debugging-port=9222",
            "--remote-debugging-address=0.0.0.0",
            "--remote-allow-origins=*",
        ],
        {"devtools": True},
    )

    codes = {finding.code for finding in findings}
    assert "enable-automation" in codes
    assert "devtools-kwarg" in codes
    assert "remote-debugging-public-address" in codes
    assert "remote-allow-origins-wildcard" in codes


def test_launch_hygiene_strict_policy_rejects_findings(monkeypatch) -> None:
    import pytest
    from clarkbrowser.hygiene import apply_launch_hygiene

    class Logger:
        def warning(self, *args) -> None:
            raise AssertionError("strict policy should raise before warning")

    monkeypatch.setenv("CLARK_LAUNCH_HYGIENE", "strict")

    with pytest.raises(RuntimeError, match="Clark launch hygiene failed"):
        apply_launch_hygiene(Logger(), ["--enable-automation"], {})


def test_launch_hygiene_off_policy_suppresses_findings(monkeypatch) -> None:
    from clarkbrowser.hygiene import apply_launch_hygiene

    class Logger:
        def warning(self, *args) -> None:
            raise AssertionError("off policy should not warn")

    monkeypatch.setenv("CLARK_LAUNCH_HYGIENE", "off")

    assert apply_launch_hygiene(Logger(), ["--enable-automation"], {}) == []


def test_interaction_pacer_enforces_min_interval() -> None:
    from clarkbrowser import InteractionPacer

    now = 0.0
    slept: list[float] = []

    def clock() -> float:
        return now

    def sleep(seconds: float) -> None:
        nonlocal now
        slept.append(seconds)
        now += seconds

    pacer = InteractionPacer(
        min_interval_ms=250,
        jitter_ms=0,
        same_target_cooldown_ms=0,
        now_fn=clock,
        sleep_fn=sleep,
    )

    assert pacer.wait("first") == 0
    assert pacer.wait("second") == 0.25
    assert slept == [0.25]


def test_interaction_pacer_same_target_cooldown_wins() -> None:
    from clarkbrowser import InteractionPacer

    now = 0.0
    slept: list[float] = []

    def clock() -> float:
        return now

    def sleep(seconds: float) -> None:
        nonlocal now
        slept.append(seconds)
        now += seconds

    pacer = InteractionPacer(
        min_interval_ms=100,
        jitter_ms=0,
        same_target_cooldown_ms=600,
        now_fn=clock,
        sleep_fn=sleep,
    )

    pacer.wait("button")
    assert pacer.wait("button") == 0.6
    assert slept == [0.6]


def test_version() -> None:
    from clarkbrowser import __version__
    assert isinstance(__version__, str)
    assert __version__.count(".") >= 1


def test_chromium_version() -> None:
    from clarkbrowser import get_chromium_version
    v = get_chromium_version()
    assert v.count(".") == 3  # major.minor.build.patch


def test_download_url_uses_current_stealth_release(monkeypatch) -> None:
    from clarkbrowser import config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    monkeypatch.setattr(config.platform, "machine", lambda: "x86_64")
    assert (
        config.get_download_url()
        == "https://github.com/clark-labs-inc/clark-browser/releases/download/"
        "chromium-v148.0.7778.96-stealth6/clark-browser-linux-x64.tar.gz"
    )


def test_windows_download_url_uses_zip_archive(monkeypatch) -> None:
    from clarkbrowser import config
    monkeypatch.setattr(config.platform, "system", lambda: "Windows")
    monkeypatch.setattr(config.platform, "machine", lambda: "AMD64")

    assert config.get_platform_tag() == "windows-x64"
    assert config.get_binary_path().name == "chrome.exe"
    assert config.get_archive_name() == "clark-browser-windows-x64.zip"
    assert (
        config.get_download_url()
        == "https://github.com/clark-labs-inc/clark-browser/releases/download/"
        "chromium-v148.0.7778.96-stealth6/clark-browser-windows-x64.zip"
    )


def test_windows_build_packages_side_by_side_manifests() -> None:
    from pathlib import Path

    script = Path(__file__).resolve().parents[1] / "build" / "build-windows.ps1"
    text = script.read_text()

    assert '".manifest"' in text
    assert '".xml"' in text


def test_zip_archive_extracts_and_flattens_single_dir(monkeypatch, tmp_path) -> None:
    import zipfile
    from clarkbrowser import config
    from clarkbrowser import download

    monkeypatch.setattr(config.platform, "system", lambda: "Windows")
    monkeypatch.setattr(config.platform, "machine", lambda: "AMD64")
    monkeypatch.setattr(download.platform, "system", lambda: "Windows")
    archive = tmp_path / "clark-browser-windows-x64.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("clark-browser-windows-x64/chrome.exe", "binary")
        zf.writestr("clark-browser-windows-x64/resources.pak", "pak")
    dest = tmp_path / "extract"
    monkeypatch.setattr(download, "_prepare_windows_sandbox", lambda _: None)

    download._extract_archive(archive, dest)

    assert (dest / "chrome.exe").exists()
    assert (dest / "resources.pak").exists()


def test_zip_archive_rejects_path_traversal(tmp_path) -> None:
    import pytest
    import zipfile
    from clarkbrowser import download

    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../extract2/chrome.exe", "binary")

    with pytest.raises(RuntimeError, match="Archive path traversal"):
        download._extract_archive(archive, tmp_path / "extract")


def test_linux_binary_path_prefers_chrome_tarball(monkeypatch) -> None:
    from clarkbrowser import config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    monkeypatch.setattr(config.platform, "machine", lambda: "x86_64")
    assert config.get_binary_path().name == "chrome"


def test_linux_binary_path_keeps_headless_fallback(monkeypatch, tmp_path) -> None:
    from clarkbrowser import config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    monkeypatch.setattr(config.platform, "machine", lambda: "x86_64")
    monkeypatch.setenv("CLARK_CACHE_DIR", str(tmp_path))
    binary_dir = config.get_binary_dir()
    binary_dir.mkdir(parents=True)
    (binary_dir / "headless_shell").touch()
    assert config.get_binary_path().name == "headless_shell"


def test_proxy_defaults_webrtc_to_proxy_coherent(monkeypatch) -> None:
    from clarkbrowser import browser, config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    monkeypatch.delenv("CLARK_FINGERPRINT_PLATFORM", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_WINDOWS_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_NETWORK_PROFILE", raising=False)
    monkeypatch.delenv("CLARK_WEBRTC_POLICY", raising=False)

    args = browser._resolve_args(
        [], True, None, None, None, None, None, True,
        proxy="http://proxy:8080",
    )

    assert "--force-webrtc-ip-handling-policy=disable_non_proxied_udp" in args
    assert "--webrtc-ip-handling-policy=disable_non_proxied_udp" in args


def test_proxy_with_explicit_webrtc_policy_wins(monkeypatch) -> None:
    from clarkbrowser import browser, config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    monkeypatch.delenv("CLARK_FINGERPRINT_PLATFORM", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_WINDOWS_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_NETWORK_PROFILE", raising=False)
    monkeypatch.delenv("CLARK_WEBRTC_POLICY", raising=False)

    args = browser._resolve_args(
        [], True, None, None, None, "default", None, True,
        proxy="http://proxy:8080",
    )

    assert "--force-webrtc-ip-handling-policy=disable_non_proxied_udp" not in args


def test_proxy_with_env_off_does_not_default_coherent(monkeypatch) -> None:
    from clarkbrowser import browser, config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    monkeypatch.delenv("CLARK_FINGERPRINT_PLATFORM", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_WINDOWS_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_NETWORK_PROFILE", raising=False)
    monkeypatch.setenv("CLARK_WEBRTC_POLICY", "off")

    args = browser._resolve_args(
        [], True, None, None, None, None, None, True,
        proxy="http://proxy:8080",
    )

    assert not any(
        a.startswith("--force-webrtc-ip-handling-policy=") for a in args
    )


def test_no_proxy_no_webrtc_default(monkeypatch) -> None:
    from clarkbrowser import browser, config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    monkeypatch.delenv("CLARK_FINGERPRINT_PLATFORM", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_WINDOWS_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_NETWORK_PROFILE", raising=False)
    monkeypatch.delenv("CLARK_WEBRTC_POLICY", raising=False)

    args = browser._resolve_args(
        [], True, None, None, None, None, None, True,
    )

    assert not any(
        a.startswith("--force-webrtc-ip-handling-policy=") for a in args
    )


def test_stealth_args_include_screen_dimensions(monkeypatch) -> None:
    from clarkbrowser import config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    monkeypatch.delenv("CLARK_FINGERPRINT_PLATFORM", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_WINDOWS_FONTS_DIR", raising=False)
    monkeypatch.delenv("CLARK_FINGERPRINT_NETWORK_PROFILE", raising=False)

    args = config.get_default_stealth_args()

    assert any(a.startswith("--fingerprint-screen-width=") for a in args)
    assert any(a.startswith("--fingerprint-screen-height=") for a in args)


def test_screen_size_deterministic_for_seed() -> None:
    from clarkbrowser import config
    s1 = config.pick_screen_size("42069")
    s2 = config.pick_screen_size("42069")
    assert s1 == s2
    assert s1 in config.SCREEN_SIZE_POOL


def test_viewport_from_args_matches_screen(monkeypatch) -> None:
    from clarkbrowser import config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    args = [
        "--fingerprint-screen-width=2560",
        "--fingerprint-screen-height=1440",
        "--fingerprint-platform=linux",
    ]
    vp = config.get_viewport_from_args(args)
    assert vp == {"width": 2560, "height": 1440}


def test_viewport_from_args_windows_subtracts_taskbar(monkeypatch) -> None:
    from clarkbrowser import config
    monkeypatch.setattr(config.platform, "system", lambda: "Linux")
    args = [
        "--fingerprint-screen-width=1920",
        "--fingerprint-screen-height=1080",
        "--fingerprint-platform=windows",
    ]
    vp = config.get_viewport_from_args(args)
    assert vp == {"width": 1920, "height": 1032}


def test_viewport_from_args_falls_back_without_screen() -> None:
    from clarkbrowser import config
    vp = config.get_viewport_from_args([])
    assert vp == config.DEFAULT_VIEWPORT


def test_windows_sandbox_permissions_after_zip_extraction(monkeypatch, tmp_path):
    import zipfile
    from clarkbrowser import download

    calls = []
    monkeypatch.setattr(download, "get_binary_path", lambda: tmp_path / "browser" / "chrome.exe")
    monkeypatch.setattr(download.platform, "system", lambda: "Windows")
    def run(args, **kwargs):
        # Permissions must be applied to the final layout, including resources.
        assert (tmp_path / "browser" / "chrome.exe").exists()
        assert (tmp_path / "browser" / "resources.pak").exists()
        calls.append((args, kwargs))
    monkeypatch.setattr(download.subprocess, "run", run)
    archive = tmp_path / "browser.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("build/chrome.exe", "binary")
        zf.writestr("build/resources.pak", "resources")
    download._extract_archive(archive, tmp_path / "browser")
    assert calls == [([
        "icacls.exe", str((tmp_path / "browser").resolve()), "/grant",
        "*S-1-15-2-1:(OI)(CI)(RX)", "*S-1-15-2-2:(OI)(CI)(RX)", "/T", "/Q",
    ], dict(check=True, capture_output=True, text=True, timeout=60))]


def test_windows_cached_binary_repairs_permissions(monkeypatch, tmp_path):
    from clarkbrowser import download
    binary = tmp_path / "chrome.exe"
    binary.touch()
    calls = []
    monkeypatch.setattr(download, "get_local_binary_override", lambda: None)
    monkeypatch.setattr(download, "get_binary_path", lambda: binary)
    monkeypatch.setattr(download, "_is_executable", lambda _: True)
    monkeypatch.setattr(download.platform, "system", lambda: "Windows")
    monkeypatch.setattr(download, "_prepare_windows_sandbox", calls.append)
    assert download.ensure_binary() == str(binary)
    assert calls == [tmp_path]


def test_windows_sandbox_permission_failure_is_actionable(monkeypatch, tmp_path):
    import subprocess
    import pytest
    from clarkbrowser import download
    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, args[0])
    monkeypatch.setattr(download.subprocess, "run", fail)
    with pytest.raises(RuntimeError, match="repair-sandbox.ps1"):
        download._prepare_windows_sandbox(tmp_path)
