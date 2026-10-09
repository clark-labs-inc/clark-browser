# Copyright 2026 Clark Labs Inc.
# SPDX-License-Identifier: MIT

"""Binary download and cache management for clark-browser.

First launch fetches the patched Chromium binary from GitHub Releases.
Override with CLARK_BINARY_PATH to use a locally built binary.
"""
from __future__ import annotations

import logging
import os
import platform
import stat
import subprocess
import tarfile
import tempfile
import zipfile
from pathlib import Path

import httpx

from ._version import __version__ as _wrapper_version
from .config import (
    DOWNLOAD_BASE_URL,
    get_archive_ext,
    get_archive_name,
    get_binary_dir,
    get_binary_path,
    get_cache_dir,
    get_chromium_version,
    get_download_url,
    get_local_binary_override,
    get_platform_tag,
    get_release_tag,
)

logger = logging.getLogger("clarkbrowser")
DOWNLOAD_TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=10.0)


def ensure_binary() -> str:
    """Return the path to the patched Chromium binary. Download if missing.

    Override path with CLARK_BINARY_PATH=/path/to/Chromium.
    """
    override = get_local_binary_override()
    if override:
        p = Path(override)
        if not p.exists():
            raise FileNotFoundError(
                f"CLARK_BINARY_PATH={override} but file does not exist"
            )
        return str(p)

    binary_path = get_binary_path()
    if binary_path.exists() and _is_executable(binary_path):
        if platform.system() == "Windows":
            _prepare_windows_sandbox(binary_path.parent)
        return str(binary_path)

    logger.info(
        "Stealth Chromium %s not found. Downloading for %s...",
        get_chromium_version(),
        get_platform_tag(),
    )
    _download_and_extract()

    if not binary_path.exists():
        raise RuntimeError(
            f"Download completed but binary not found at {binary_path}"
        )
    return str(binary_path)


def _download_and_extract(version: str | None = None) -> None:
    url = get_download_url(version)
    binary_dir = get_binary_dir(version)
    binary_dir.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(suffix=get_archive_ext(), delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        _download_file(url, tmp_path)
        _extract_archive(tmp_path, binary_dir)
    finally:
        tmp_path.unlink(missing_ok=True)


def _download_file(url: str, dest: Path) -> None:
    logger.info("Downloading from %s", url)
    with httpx.stream(
        "GET", url, follow_redirects=True, timeout=DOWNLOAD_TIMEOUT
    ) as response:
        response.raise_for_status()
        total = int(response.headers.get("content-length", 0))
        downloaded = 0
        last_pct = -1
        with open(dest, "wb") as f:
            for chunk in response.iter_bytes(chunk_size=8192):
                f.write(chunk)
                downloaded += len(chunk)
                if total > 0:
                    pct = int(downloaded / total * 100)
                    if pct >= last_pct + 10:
                        last_pct = pct
                        logger.info(
                            "Download %d%% (%d/%d MB)",
                            pct,
                            downloaded // (1024 * 1024),
                            total // (1024 * 1024),
                        )


def _extract_archive(archive_path: Path, dest_dir: Path) -> None:
    logger.info("Extracting to %s", dest_dir)
    if dest_dir.exists():
        import shutil
        shutil.rmtree(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    if archive_path.suffix == ".zip":
        _extract_zip_archive(archive_path, dest_dir)
    else:
        _extract_tar_archive(archive_path, dest_dir)

    _flatten_single_subdir(dest_dir)

    if platform.system() == "Windows":
        _prepare_windows_sandbox(dest_dir)

    bp = get_binary_path()
    if bp.exists():
        _make_executable(bp)
    if platform.system() == "Darwin" and bp.exists():
        _remove_quarantine(dest_dir)


def _extract_tar_archive(archive_path: Path, dest_dir: Path) -> None:
    with tarfile.open(archive_path, "r:gz") as tar:
        safe = []
        for member in tar.getmembers():
            if member.issym() or member.islnk():
                if os.path.isabs(member.linkname) or ".." in member.linkname.split("/"):
                    logger.warning(
                        "Skipping suspicious symlink: %s -> %s",
                        member.name,
                        member.linkname,
                    )
                    continue
            else:
                rp = (dest_dir / member.name).resolve()
                if not str(rp).startswith(str(dest_dir.resolve())):
                    raise RuntimeError(f"Archive path traversal: {member.name}")
            safe.append(member)
        tar.extractall(dest_dir, members=safe)


def _extract_zip_archive(archive_path: Path, dest_dir: Path) -> None:
    root = dest_dir.resolve()
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            rp = (dest_dir / member.filename).resolve()
            try:
                rp.relative_to(root)
            except ValueError:
                raise RuntimeError(f"Archive path traversal: {member.filename}")
            archive.extract(member, dest_dir)


def _flatten_single_subdir(dest_dir: Path) -> None:
    """If extraction created a single subdirectory, flatten it."""
    import shutil
    entries = list(dest_dir.iterdir())
    if len(entries) == 1 and entries[0].is_dir() and not entries[0].name.endswith(".app"):
        subdir = entries[0]
        for item in subdir.iterdir():
            shutil.move(str(item), str(dest_dir / item.name))
        subdir.rmdir()


def _prepare_windows_sandbox(binary_dir: Path) -> None:
    """Grant AppContainer/LPAC read-execute access to portable browser files.

    ZIPs do not preserve NTFS ACLs. Chromium normally sets these permissions
    in its installer; restrict the grants to the browser distribution tree.
    Numeric SIDs work on localized Windows installations too.
    """
    try:
        subprocess.run(
            [
                "icacls.exe", str(binary_dir.resolve()), "/grant",
                "*S-1-15-2-1:(OI)(CI)(RX)",
                "*S-1-15-2-2:(OI)(CI)(RX)", "/T", "/Q",
            ],
            check=True, capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(
            f"Cannot prepare Windows sandbox permissions for {binary_dir}. "
            "Run repair-sandbox.ps1 in the extracted browser directory."
        ) from exc


def _is_executable(path: Path) -> bool:
    return os.access(path, os.X_OK)


def _make_executable(path: Path) -> None:
    current = path.stat().st_mode
    path.chmod(current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _remove_quarantine(path: Path) -> None:
    """macOS: strip quarantine xattrs so Gatekeeper doesn't prompt."""
    try:
        subprocess.run(["xattr", "-cr", str(path)], capture_output=True, timeout=30)
    except Exception:
        logger.debug("Failed to remove quarantine attributes", exc_info=True)


def clear_cache() -> None:
    """Remove all cached binaries. Forces re-download on next launch."""
    import shutil
    cache_dir = get_cache_dir()
    if cache_dir.exists():
        shutil.rmtree(cache_dir)
        logger.info("Cache cleared: %s", cache_dir)


def binary_info() -> dict:
    return {
        "wrapper_version": _wrapper_version,
        "chromium_version": get_chromium_version(),
        "release_tag": get_release_tag(),
        "platform": get_platform_tag(),
        "binary_path": str(get_binary_path()),
        "installed": get_binary_path().exists(),
        "cache_dir": str(get_binary_dir()),
        "download_url": get_download_url(),
    }
