#!/usr/bin/env python3
"""Download verified httpmon release assets for packaging into StorageOps wheels."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR_DIR = ROOT / "storageops_cli" / "_vendor" / "httpmon"
DOWNLOAD_TIMEOUT_SECONDS = "60"
BUNDLED_ASSET_NAMES = {"httpmon-v1.0.2-linux-amd64"}


def _metadata() -> tuple[str, dict[tuple[str, str], tuple[str, str]]]:
    sys.path.insert(0, str(ROOT))
    from storageops_cli import HTTPMON_ASSETS, HTTPMON_BASE_URL

    return HTTPMON_BASE_URL, HTTPMON_ASSETS


def _download(url: str) -> bytes:
    curl = shutil.which("curl")
    if curl:
        result = subprocess.run(
            [
                curl,
                "--fail",
                "--location",
                "--silent",
                "--show-error",
                "--max-time",
                DOWNLOAD_TIMEOUT_SECONDS,
                url,
            ],
            capture_output=True,
        )
        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(stderr or "curl download failed")
        return result.stdout

    request = urllib.request.Request(url, headers={"User-Agent": "storageops-packaging"})
    with urllib.request.urlopen(request, timeout=int(DOWNLOAD_TIMEOUT_SECONDS)) as response:
        return response.read()


def prepare_vendor() -> None:
    base_url, assets = _metadata()
    unique_assets = sorted(
        (asset_name, sha)
        for asset_name, sha in set(assets.values())
        if asset_name in BUNDLED_ASSET_NAMES
    )
    VENDOR_DIR.mkdir(parents=True, exist_ok=True)

    for asset_name, expected_sha in unique_assets:
        target = VENDOR_DIR / f"{asset_name}.gz"
        if target.exists():
            raw = gzip.decompress(target.read_bytes())
            if hashlib.sha256(raw).hexdigest() == expected_sha:
                print(f"[ok] bundled {asset_name}")
                continue
            target.unlink()

        print(f"[info] downloading {asset_name}")
        raw = _download(f"{base_url}/{asset_name}")
        actual_sha = hashlib.sha256(raw).hexdigest()
        if actual_sha != expected_sha:
            raise RuntimeError(f"{asset_name}: checksum mismatch {actual_sha} != {expected_sha}")

        target.write_bytes(gzip.compress(raw, compresslevel=9, mtime=0))
        print(f"[ok] wrote {target.relative_to(ROOT)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    prepare_vendor()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
