"""Automatic Pi Agent binary installer for storageops setup."""
from __future__ import annotations

import os
import platform
import shutil
import stat
import tarfile
import urllib.request
from pathlib import Path

# Override via environment variable for testing or custom Pi builds.
_PI_RELEASES_BASE = os.environ.get(
    "STORAGEOPS_PI_RELEASES_URL",
    "https://github.com/earendil-works/pi/releases/latest/download",
)

_PLATFORM_MAP = {
    ("linux",  "x86_64"):  "pi-linux-x64.tar.gz",
    ("linux",  "aarch64"): "pi-linux-arm64.tar.gz",
    ("darwin", "x86_64"):  "pi-darwin-x64.tar.gz",
    ("darwin", "arm64"):   "pi-darwin-arm64.tar.gz",
    ("windows","amd64"):   "pi-windows-amd64.exe",
}


def detect_platform() -> str | None:
    """Return the Pi binary filename for the current platform, or None if unknown."""
    system = platform.system().lower()
    machine = platform.machine().lower()
    # Normalise arm variants
    if machine in ("arm64", "aarch64"):
        machine = "aarch64" if system == "linux" else "arm64"
    return _PLATFORM_MAP.get((system, machine))


def pi_bin_dir() -> Path:
    return Path.home() / ".storageops" / "bin"


def pi_bin_path() -> Path:
    name = "pi.exe" if platform.system().lower() == "windows" else "pi"
    return pi_bin_dir() / name


def is_installed() -> bool:
    return pi_bin_path().exists() or shutil.which("pi") is not None


def download_pi(progress_cb=None) -> Path:
    """Download the Pi binary for the current platform into ~/.storageops/bin/.

    progress_cb(downloaded_bytes, total_bytes) is called periodically.
    Returns the path to the installed binary.
    Raises RuntimeError if the platform is unsupported or download fails.
    """
    binary_name = detect_platform()
    if not binary_name:
        raise RuntimeError(
            f"Unsupported platform: {platform.system()} {platform.machine()}\n"
            "Install Pi manually and re-run: storageops setup"
        )

    url = f"{_PI_RELEASES_BASE}/{binary_name}"
    dest_dir = pi_bin_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = pi_bin_path()

    def _reporthook(block_num, block_size, total_size):
        if progress_cb and total_size > 0:
            downloaded = min(block_num * block_size, total_size)
            progress_cb(downloaded, total_size)

    is_tarball = binary_name.endswith((".tar.gz", ".tgz"))
    download_path = str(dest) if not is_tarball else str(dest_dir / binary_name)

    try:
        urllib.request.urlretrieve(url, download_path, reporthook=_reporthook)
    except Exception as exc:
        raise RuntimeError(f"Failed to download Pi from {url}: {exc}") from exc

    if is_tarball:
        # Extract the tarball and locate the pi binary + companion files
        with tarfile.open(download_path, "r:gz") as tf:
            tf.extractall(path=str(dest_dir))
        # Remove the tarball after extraction
        Path(download_path).unlink(missing_ok=True)
        if not dest.exists():
            raise RuntimeError(
                f"Pi binary not found after extracting {binary_name}. "
                "Expected 'pi' in the archive root."
            )

    # Make executable on Unix
    if platform.system().lower() != "windows":
        dest.chmod(dest.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    return dest


def ensure_path_entry(shell_rc: Path | None = None) -> bool:
    """Append ~/.storageops/bin to PATH in the user's shell rc file.

    Returns True if a new entry was added, False if it was already present.
    """
    bin_dir = str(pi_bin_dir())
    export_line = f'\nexport PATH="{bin_dir}:$PATH"  # added by storageops setup\n'

    if shell_rc is None:
        shell = os.environ.get("SHELL", "")
        home = Path.home()
        if "zsh" in shell:
            shell_rc = home / ".zshrc"
        elif "fish" in shell:
            shell_rc = home / ".config" / "fish" / "config.fish"
            export_line = f'\nset -gx PATH "{bin_dir}" $PATH  # added by storageops setup\n'
        else:
            shell_rc = home / ".bashrc"

    existing = shell_rc.read_text(encoding="utf-8") if shell_rc.exists() else ""
    if bin_dir in existing:
        return False

    with open(shell_rc, "a", encoding="utf-8") as f:
        f.write(export_line)
    return True
