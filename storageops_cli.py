#!/usr/bin/env python3
"""Thin CLI shim: `storageops` → `pi` with StorageOps extension and skills.

This is the only Python file in the StorageOps project.
It forwards to Pi Coding Agent with the storageops extension and skills auto-loaded.
"""

import subprocess
import sys
import os
import shutil
from pathlib import Path


def find_pi() -> str:
    """Locate the pi binary."""
    # Check common locations
    candidates = [
        os.path.expanduser("~/.storageops/bin/pi"),
        os.path.expanduser("~/.pi/bin/pi"),
        "/usr/local/bin/pi",
        shutil.which("pi"),
    ]
    for c in candidates:
        if c and os.path.isfile(c if isinstance(c, str) else str(c)):
            return c if isinstance(c, str) else str(c)
    return "pi"  # fallback to PATH


def get_skills_dir() -> str:
    """Locate the StorageOps skills directory."""
    repo_root = Path(__file__).resolve().parent
    skills = repo_root / "skills"
    if skills.is_dir():
        return str(skills)
    # Also check installed location
    import site
    for sp in site.getsitepackages():
        p = Path(sp) / "storageops_skills"
        if p.is_dir():
            return str(p)
    return str(repo_root / "skills")


def main():
    pi_bin = find_pi()
    skills_dir = get_skills_dir()

    # Prepare pi args
    pi_args = [
        pi_bin,
        "--skills", skills_dir,
    ]

    # Forward all arguments
    pi_args.extend(sys.argv[1:])

    # Execute pi
    os.execvp(pi_bin, pi_args[1:])


if __name__ == "__main__":
    main()
