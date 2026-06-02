#!/usr/bin/env python3
"""Build wheel/sdist in a temp dir and verify packaged StorageOps assets."""

from __future__ import annotations

import argparse
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _count_source_skills() -> int:
    """Count canonical skill packs in the source tree (the single source of truth)."""
    skills_dir = ROOT / "skills"
    return sum(
        1
        for d in skills_dir.iterdir()
        if d.is_dir() and d.name.startswith("storageops-") and (d / "SKILL.md").exists()
    )


EXPECTED_SKILLS = _count_source_skills()
EXTENSION_PATH = "storageops_cli/extensions/storageops.ts"
HTTPMON_VENDOR_PREFIX = "storageops_cli/_vendor/httpmon/"
EXPECTED_HTTPMON_VENDOR_ASSETS = 1


def run_build(out_dir: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--sdist", "--outdir", str(out_dir)],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        raise SystemExit(result.returncode)


def check_names(names: list[str], artifact: Path) -> list[str]:
    errors: list[str] = []
    skill_count = sum(1 for name in names if name.endswith("/SKILL.md"))
    has_extension = any(name.endswith(EXTENSION_PATH) for name in names)
    httpmon_vendor_count = sum(
        1
        for name in names
        if HTTPMON_VENDOR_PREFIX in name and name.endswith(".gz")
    )
    pycache_count = sum(1 for name in names if name.endswith(".pyc") or "/__pycache__/" in name)

    if skill_count != EXPECTED_SKILLS:
        errors.append(f"{artifact.name}: expected {EXPECTED_SKILLS} SKILL.md files, found {skill_count}")
    if not has_extension:
        errors.append(f"{artifact.name}: missing {EXTENSION_PATH}")
    if httpmon_vendor_count != EXPECTED_HTTPMON_VENDOR_ASSETS:
        errors.append(
            f"{artifact.name}: expected {EXPECTED_HTTPMON_VENDOR_ASSETS} bundled httpmon assets, "
            f"found {httpmon_vendor_count}"
        )
    if pycache_count:
        errors.append(f"{artifact.name}: contains {pycache_count} pyc/__pycache__ entries")
    return errors


def check_wheel(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as zf:
        return check_names(zf.namelist(), path)


def check_sdist(path: Path) -> list[str]:
    with tarfile.open(path) as tf:
        return check_names(tf.getnames(), path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "prepare_httpmon_vendor.py")],
        cwd=ROOT,
        check=True,
    )

    with tempfile.TemporaryDirectory(prefix="storageops-package-") as tmp:
        out_dir = Path(tmp)
        run_build(out_dir)
        artifacts = sorted(out_dir.iterdir())
        wheels = [p for p in artifacts if p.suffix == ".whl"]
        sdists = [p for p in artifacts if p.name.endswith(".tar.gz")]
        errors: list[str] = []

        if len(wheels) != 1:
            errors.append(f"expected exactly one wheel, found {len(wheels)}")
        if len(sdists) != 1:
            errors.append(f"expected exactly one sdist, found {len(sdists)}")

        for wheel in wheels:
            errors.extend(check_wheel(wheel))
        for sdist in sdists:
            errors.extend(check_sdist(sdist))

    if errors:
        print("Package check failed:")
        for error in errors:
            print(f"  - {error}")
        return 1

    print("Package check passed: wheel/sdist include skills, extension, httpmon helpers and exclude pyc")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
