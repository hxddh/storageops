"""CLI: config, setup, doctor, update commands."""
from __future__ import annotations

import argparse
import getpass
import json
import shutil
import subprocess
import sys
from pathlib import Path

from storageops.ui.terminal import c, bold, dim, green, yellow, red, cyan, hr


def cmd_config(args: argparse.Namespace) -> None:
    from storageops import config as cfg_mod

    action = getattr(args, "config_action", "list") or "list"

    if action == "list":
        data = cfg_mod.load()
        print()
        print(bold("StorageOps config"))
        print(hr(50))
        if not data:
            print(f"  {dim('(empty — run: storageops setup)')}")
        else:
            for k, v in data.items():
                v_display = "[REDACTED]" if "key" in k.lower() and v else str(v)
                print(f"  {bold(k):<22}  {dim(v_display)}")
        cfg_path = Path.home() / ".storageops" / "config.json"
        print()
        print(dim(f"  File: {cfg_path}"))
        print()

    elif action == "get":
        key = args.key
        data = cfg_mod.load()
        if key not in data:
            print(f"{red('✗')} Key not found: {key}", file=sys.stderr)
            sys.exit(1)
        v = data[key]
        if "key" in key.lower():
            print("[REDACTED]")
        else:
            print(v)

    elif action == "set":
        key = args.key
        value = args.value
        cfg_mod.update(**{key: value})
        print(f"  {green('✓')} Set {key} = {value}")


def _find_bundled_skills() -> Path | None:
    pkg = Path(__file__).resolve().parent / "_skills"
    if pkg.exists():
        return pkg
    repo = Path(__file__).resolve().parents[3] / "agents" / "skills"
    if repo.exists():
        return repo
    return None


def cmd_setup(args: argparse.Namespace) -> None:
    from storageops import pi_installer
    from storageops.config import (
        detect_provider_from_key, get_api_key, get_provider, update as _cfg_update,
    )

    storageops_dir = Path.home() / ".storageops"
    storageops_dir.mkdir(parents=True, exist_ok=True)

    print()
    print(bold("StorageOps"))
    print()

    # Pi Agent
    pi_cmd_arg = getattr(args, "pi_command", None)
    pi_path = shutil.which(pi_cmd_arg or "pi")
    pi_bin = pi_installer.pi_bin_path()

    if pi_path or pi_bin.exists():
        pi_cmd = str(pi_bin) if pi_bin.exists() else (pi_cmd_arg or "pi")
        try:
            ver = subprocess.check_output(
                [pi_path or pi_cmd, "--version"],
                text=True, stderr=subprocess.STDOUT, timeout=5,
            ).strip()
        except Exception:
            ver = ""
        detail = (ver + "  " + (pi_path or pi_cmd)).strip()
        print(f"  {green('✓')}  Pi Agent     {dim(detail)}")
    else:
        sys.stdout.write(f"  {dim('·')}  Pi Agent     installing…")
        sys.stdout.flush()
        try:
            def _progress(done: int, total: int) -> None:
                if total:
                    kb = done // 1024
                    pct = int(done / total * 20)
                    bar = "━" * pct + "╌" * (20 - pct)
                    sys.stdout.write(f"\r  {dim('·')}  Pi Agent     {bar}  {kb} KB")
                    sys.stdout.flush()
            dest = pi_installer.download_pi(progress_cb=_progress)
            pi_installer.ensure_path_entry()
            pi_cmd = str(dest)
            sys.stdout.write(f"\r\033[K  {green('✓')}  Pi Agent     {dim(pi_cmd)}\n")
        except RuntimeError as exc:
            sys.stdout.write(f"\r\033[K  {yellow('!')}  Pi Agent     {dim(str(exc))}\n")
            pi_cmd = pi_cmd_arg or "pi"
        sys.stdout.flush()

    # Skills
    skills_dst = storageops_dir / "skills"
    bundled = _find_bundled_skills()
    if bundled and (not skills_dst.exists() or getattr(args, "force", False)):
        if skills_dst.exists():
            shutil.rmtree(str(skills_dst))
        shutil.copytree(str(bundled), str(skills_dst))
    if skills_dst.exists():
        count = sum(1 for d in skills_dst.iterdir() if d.is_dir())
        print(f"  {green('✓')}  Skills       {dim(f'{count} skills  {skills_dst}')}")
    else:
        print(f"  {yellow('!')}  Skills       {dim('not found — re-install storageops')}")

    # API key
    existing_key = get_api_key()
    if existing_key:
        print(f"  {green('✓')}  API key      {dim(get_provider() + '  (configured)')}")
    else:
        print(f"  {dim('·')}  API key      not configured")
        print()
        print(f"  {dim('Anthropic:  console.anthropic.com/settings/api-keys')}")
        print(f"  {dim('OpenAI:     platform.openai.com/api-keys')}")
        print()
        try:
            key = getpass.getpass("  API key: ").strip()
        except (EOFError, KeyboardInterrupt):
            key = ""
        if key:
            provider = detect_provider_from_key(key)
            _cfg_update(provider=provider, api_key=key)
            print(f"  {green('✓')}  {dim(provider + '  ·  saved')}")
        else:
            print(f"  {yellow('!')}  No key — set ANTHROPIC_API_KEY or OPENAI_API_KEY")

    # Config
    pi_settings_dir = storageops_dir / ".pi"
    pi_settings_dir.mkdir(exist_ok=True)
    (pi_settings_dir / "settings.json").write_text(
        json.dumps({"skills": ["../skills"], "enableSkillCommands": True}, indent=2) + "\n",
        encoding="utf-8",
    )
    _cfg_update(
        pi_command=pi_cmd,
        workdir=str(storageops_dir),
        skills_dir=str(skills_dst) if skills_dst.exists() else "",
    )
    print()
    print(f"  {green('Done.')}  Run: {bold('storageops')}")
    print()


def cmd_doctor(args: argparse.Namespace) -> None:
    import shutil
    import subprocess

    ok_count = 0
    fail_count = 0

    def _chk_ok(label: str, detail: str = "") -> None:
        nonlocal ok_count
        ok_count += 1
        suffix = f"  {dim(detail)}" if detail else ""
        print(f"  {green('✓')}  {label}{suffix}")

    def _chk_fail(label: str, hint: str = "") -> None:
        nonlocal fail_count
        fail_count += 1
        print(f"  {red('✗')}  {label}")
        if hint:
            print(f"       {dim(hint)}")

    print()
    print(bold("storageops doctor"))
    print(hr(40))
    print()

    _chk_ok(f"Python {sys.version.split()[0]}")

    try:
        from importlib.metadata import version as _pkg_ver
        _chk_ok(f"storageops {_pkg_ver('storageops')}")
    except Exception:
        _chk_ok("storageops (version unknown)")

    try:
        from storageops.config import get_pi_command
        pi_cmd = get_pi_command()
        pi_path = shutil.which(pi_cmd)
        if pi_path:
            try:
                ver_out = subprocess.check_output(
                    [pi_cmd, "--version"], text=True, stderr=subprocess.STDOUT, timeout=5,
                ).strip()
                _chk_ok(f"{pi_cmd} {ver_out}", pi_path)
            except Exception:
                _chk_ok(pi_cmd, pi_path)
        else:
            _chk_fail(f"{pi_cmd}: not found", "Install Pi Agent, then run: storageops setup")
    except Exception:
        _chk_fail("Pi: config error")

    from storageops.config import get_skills_dir
    skills = get_skills_dir()
    if skills and skills.exists():
        count = sum(1 for d in skills.iterdir() if d.is_dir())
        _chk_ok(f"skills  {count} directories", str(skills))
    else:
        _chk_fail("skills: not installed", "run: storageops setup")

    cfg_file = Path.home() / ".storageops" / "config.json"
    if cfg_file.exists():
        _chk_ok("config", str(cfg_file))
    else:
        _chk_fail("config: not found", "run: storageops setup")

    print()
    total = ok_count + fail_count
    if fail_count == 0:
        print(f"  {green('All')} {total} checks passed.")
    else:
        print(f"  {green(str(ok_count) + ' passed')}  {red(str(fail_count) + ' failed')}")
    print()


def cmd_update(args: argparse.Namespace) -> None:
    import shutil
    from storageops import pi_installer

    check_only = getattr(args, "check", False)

    print()
    print(bold("StorageOps Update"))
    print(hr(40))
    print()

    current = pi_installer.pi_bin_path()
    if current.exists():
        print(f"  {dim('Pi binary:')}  {dim(str(current))}")
    else:
        print(f"  {yellow('!')}  Pi binary not installed — run: storageops setup")

    if not check_only:
        print(f"  {dim('Downloading latest Pi...')}", end="", flush=True)
        try:
            def _progress(done: int, total: int) -> None:
                kb = done // 1024
                if total:
                    pct = int(done / total * 24)
                    bar = "━" * pct + "╌" * (24 - pct)
                    sys.stdout.write(f"\r  {dim('Downloading')}  {bar}  {kb} KB")
                else:
                    sys.stdout.write(f"\r  {dim('Downloading')}  {kb} KB")
                sys.stdout.flush()
            dest = pi_installer.download_pi(progress_cb=_progress)
            sys.stdout.write("\r\033[K")
            print(f"  {green('✓')} Pi updated → {dim(str(dest))}")
        except RuntimeError as exc:
            sys.stdout.write("\r\033[K")
            print(f"  {yellow('!')}  Pi update skipped: {exc}")

        bundled = _find_bundled_skills()
        if bundled:
            from storageops.config import get_workdir
            skills_dst = get_workdir() / "skills"
            if skills_dst.exists():
                shutil.rmtree(str(skills_dst))
            shutil.copytree(str(bundled), str(skills_dst))
            count = sum(1 for d in skills_dst.iterdir() if d.is_dir())
            print(f"  {green('✓')} {count} skills updated → {dim(str(skills_dst))}")

    print()
    if check_only:
        print("  Run without --check to apply updates.")
    else:
        print(f"  {green('Done.')}  Run {bold('storageops doctor')} to verify.")
    print()
