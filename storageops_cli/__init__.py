#!/usr/bin/env python3
"""
StorageOps CLI -- one-command install, ready to use.

Usage:
    storageops install         first-time install
    storageops install --merge merge into an existing Pi setup
    storageops [pi args]       start a StorageOps diagnosis session

Post-install layout (independent mode):
    ~/.storageops/
    |-- agent/                 Pi config dir (PI_CODING_AGENT_DIR)
    |   |-- settings.json
    |   |-- api-key            optional: persistent API key
    |   `-- extensions/storageops.ts
    `-- skills/                16 skill packs
"""

import subprocess
import sys
import os
import json
import re
import shutil
from pathlib import Path
from importlib import resources


ROOT = Path.home() / ".storageops"
AGENT_DIR = ROOT / "agent"          # PI_CODING_AGENT_DIR
PI_DEFAULT = Path.home() / ".pi"
PI_DEFAULT_AGENT = PI_DEFAULT / "agent"
MIN_PI_VERSION = "0.78.0"
REQUIRED_API_KEYS = ["ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY"]

# Pi settings.json content
SETTINGS = {
    "skills": ["../skills"],
    "enableSkillCommands": True,
}
SETTINGS_JSON = json.dumps(SETTINGS, indent=2)
STORAGEOPS_KEYS = {"skills", "enableSkillCommands"}

# Pi auth.json provider key -> environment variable mapping
PROVIDER_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google": "GEMINI_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "groq": "GROQ_API_KEY",
    "cerebras": "CEREBRAS_API_KEY",
}


def find_pi() -> str:
    """Locate the pi binary."""
    found = shutil.which("pi")
    if found:
        return found
    for c in [
        str(ROOT / "bin" / "pi"),
        str(PI_DEFAULT / "bin" / "pi"),
        "/usr/local/bin/pi",
    ]:
        if os.path.isfile(c):
            return c
    return "pi"


def check_pi_version(exe: str) -> tuple[bool, str]:
    """Return (meets_minimum, version_string) for the given pi binary."""
    try:
        r = subprocess.run([exe, "--version"], capture_output=True, text=True)
        raw = (r.stdout + r.stderr).strip()
        ver = raw.strip() if raw else "0.0.0"
    except Exception:
        return False, "not found"

    def _parse(v: str) -> tuple[int, int, int]:
        match = re.search(r"(\d+)\.(\d+)\.(\d+)", v)
        if not match:
            return (0, 0, 0)
        return tuple(int(p) for p in match.groups())

    return _parse(ver) >= _parse(MIN_PI_VERSION), ver


def _ensure_pi() -> str:
    """
    Ensure Pi Coding Agent is available; return the pi executable path.

    - pi present, version OK  : print confirmation, return path.
    - pi present, version low : warn and print upgrade command, return path.
      (No auto-upgrade: upgrading may break the user's existing Pi config.)
    - pi not found            : attempt npm auto-install; exit with guidance
      if npm is also absent.
    """
    pi_exe = find_pi()
    ok, ver = check_pi_version(pi_exe)

    if ok:
        print(f"[ok] pi {ver} -> {pi_exe}")
        return pi_exe

    if ver != "not found":
        # pi exists but version is too old; do not auto-upgrade
        print(f"[warn] pi {ver} < {MIN_PI_VERSION} -- some features may not work.")
        print(f"       To upgrade: npm update -g @earendil-works/pi-coding-agent")
        print()
        return pi_exe

    # pi not found at all -- attempt auto-install via npm
    npm = shutil.which("npm")
    if not npm:
        print("[error] Pi Coding Agent not found and npm is not available.")
        print("        Install Node.js first: https://nodejs.org")
        print("        Then re-run: storageops install")
        sys.exit(1)

    print("[info] Pi Coding Agent not found. Installing via npm...")
    result = subprocess.run([npm, "install", "-g", "@earendil-works/pi-coding-agent"])
    if result.returncode != 0:
        print("[error] Pi Coding Agent installation failed.")
        print("        Run manually: npm install -g @earendil-works/pi-coding-agent")
        sys.exit(1)

    # Re-locate after npm install (global bin dir is already in PATH)
    pi_exe = shutil.which("pi") or find_pi()
    ok, ver = check_pi_version(pi_exe)
    if ok:
        print(f"[ok] Pi Coding Agent {ver} installed -> {pi_exe}")
    else:
        print(f"[warn] Pi Coding Agent installed but version detection returned: {ver}")
    return pi_exe


def _skills_dir_for_agent(agent_dir: Path) -> Path:
    """Return the skills directory referenced by the default ../skills setting."""
    return agent_dir.parent / "skills"


def is_installed(agent_dir: Path | None = None) -> bool:
    """Return True if StorageOps files are deployed under agent_dir."""
    ad = agent_dir or AGENT_DIR
    return (
        (ad / "settings.json").exists()
        and (ad / "extensions" / "storageops.ts").exists()
        and _skills_dir_for_agent(ad).is_dir()
    )


def detect_existing_pi() -> bool:
    """Return True if the user already has a Pi Coding Agent config at ~/.pi/."""
    return (PI_DEFAULT_AGENT / "settings.json").exists()


def detect_api_keys() -> list[str]:
    """Return the names of model provider API keys already set in the environment."""
    return [k for k in REQUIRED_API_KEYS if os.environ.get(k)]


def _inject_auth_env(agent_dir: Path) -> None:
    """
    Inject API keys from Pi auth.json and the StorageOps api-key file into
    the current environment so that the pi subprocess can authenticate.
    """
    # 1. Pi auth.json
    auth_file = agent_dir / "auth.json"
    if auth_file.exists():
        try:
            auth = json.loads(auth_file.read_text())
            for provider, env_var in PROVIDER_ENV.items():
                if provider in auth and env_var not in os.environ:
                    val = auth[provider]
                    if isinstance(val, dict):
                        val = val.get("apiKey") or val.get("key") or ""
                    if val and isinstance(val, str):
                        os.environ[env_var] = val
        except Exception:
            pass

    # 2. StorageOps api-key file (plain-text key)
    key_file = agent_dir / "api-key"
    if key_file.exists():
        key = key_file.read_text().strip()
        if key:
            for candidate in ["DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"]:
                if candidate not in os.environ:
                    os.environ[candidate] = key
                    break


def _package_data_dir() -> Path:
    """Locate the installed package data directory (skills + extensions)."""
    try:
        ref = resources.files("storageops_cli")
        if isinstance(ref, Path):
            if (ref / "skills").is_dir():
                return ref
            if hasattr(ref, "joinpath"):
                p = Path(str(ref))
                if (p / "skills").is_dir():
                    return p
    except Exception:
        pass
    this_dir = Path(__file__).resolve().parent
    if (this_dir / "skills").is_dir():
        return this_dir
    raise FileNotFoundError(
        "StorageOps data directory not found. "
        "Try: pip install --force-reinstall storageops"
    )


def _copy_extension(data: Path, dst_agent: Path) -> None:
    """Copy the StorageOps Pi extension to the target agent directory."""
    ext_src = data / "extensions" / "storageops.ts"
    ext_dst = dst_agent / "extensions" / "storageops.ts"
    ext_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ext_src, ext_dst)
    print(f"  [ok] storageops.ts  -> {ext_dst}")


def _copy_skills(data: Path, dst_agent: Path) -> None:
    """Copy StorageOps skill packs to the directory referenced by ../skills."""
    skills_src = data / "skills"
    if not skills_src.is_dir():
        print(f"  [warn] skill directory not found: {skills_src}")
        return

    skills_dst = _skills_dir_for_agent(dst_agent)
    skills_dst.mkdir(parents=True, exist_ok=True)
    for skill_dir in sorted(skills_src.iterdir()):
        if skill_dir.is_dir() and skill_dir.name.startswith("storageops-"):
            dst = skills_dst / skill_dir.name
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(skill_dir, dst)
    count = sum(
        1 for d in skills_dst.iterdir()
        if d.is_dir() and d.name.startswith("storageops-")
    )
    print(f"  [ok] skills ({count}) -> {skills_dst}")


def _merge_settings(dst_agent: Path, settings: dict) -> None:
    """Merge StorageOps keys into an existing settings.json, backing up first."""
    dst = dst_agent / "settings.json"
    dst.parent.mkdir(parents=True, exist_ok=True)

    if dst.exists():
        backup = dst_agent / "settings.json.storageops-backup"
        shutil.copy2(dst, backup)
        print(f"  [info] backed up existing config -> {backup}")
        try:
            existing = json.loads(dst.read_text())
        except Exception:
            existing = {}
    else:
        existing = {}

    merged = {**existing}
    for key in STORAGEOPS_KEYS:
        if key not in settings:
            continue
        if key == "skills":
            merged[key] = _merge_skill_paths(existing.get(key), settings[key])
        else:
            merged[key] = settings[key]

    dst.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n")
    print(f"  [ok] settings.json  -> {dst} (merged)")


def _merge_skill_paths(existing: object, required: object) -> list[str]:
    """Preserve existing Pi skill paths and append StorageOps paths once."""
    merged: list[str] = []
    for value in (existing, required):
        if not isinstance(value, list):
            continue
        for item in value:
            if isinstance(item, str) and item not in merged:
                merged.append(item)
    return merged


def _write_settings(dst_agent: Path, settings: dict) -> None:
    """Write a fresh settings.json."""
    dst = dst_agent / "settings.json"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(settings, indent=2) + "\n")
    print(f"  [ok] settings.json  -> {dst}")


def _final_check(agent_dir: Path, merge: bool) -> None:
    """
    Verify each component after install and print a clear status summary.
    Exit non-zero only when the tool cannot run at all (pi missing).
    A missing API key is a warning, not a hard failure -- it can be added later.
    """
    print()
    print("--- install summary ---")

    # StorageOps files
    if is_installed(agent_dir):
        print("[ok] StorageOps files    skills + extension deployed")
    else:
        print("[error] StorageOps files    deployment incomplete")
        print("        Re-run: storageops install --force")
        sys.exit(1)

    # Pi Coding Agent
    pi_exe = find_pi()
    ok, ver = check_pi_version(pi_exe)
    if ok:
        print(f"[ok] Pi Coding Agent     {ver}")
    else:
        print(f"[error] Pi Coding Agent     not ready ({ver})")
        print(f"        Run: npm install -g @earendil-works/pi-coding-agent")
        print()
        print("StorageOps files are in place. Install Pi Coding Agent to start diagnosing.")
        sys.exit(1)

    # API key
    keys = detect_api_keys()
    if keys:
        print(f"[ok] API key             detected ({keys[0]})")
        print()
        print("StorageOps is ready. Start a diagnosis:")
        print()
        print("  storageops --print 's5cmd sync reports 429 SlowDown; diagnose'")
        print("  storageops           # interactive mode")
    else:
        print("[warn] API key           not configured")
        print()
        print("Set a model provider key before running a diagnosis (pick one):")
        print()
        print("  export ANTHROPIC_API_KEY=sk-...   # Claude")
        print("  export DEEPSEEK_API_KEY=sk-...    # DeepSeek")
        print("  export OPENAI_API_KEY=sk-...      # OpenAI")
        print()
        print(f"  echo sk-... > {agent_dir / 'api-key'}")
        print(f"  chmod 600 {agent_dir / 'api-key'}")
        print()
        print("  Get a key: https://console.anthropic.com")
        print("         or: https://platform.deepseek.com")
    print()
    if merge:
        print("Merge install: original Pi config backed up; use the pi command to call StorageOps.")
    else:
        print("Independent install: your existing Pi config (~/.pi/) was not modified.")


def cmd_install(force: bool = False, merge: bool = False):
    """Install StorageOps."""
    target_agent = AGENT_DIR  # default: independent mode

    # --- Step 0: ensure Pi Coding Agent is present (auto-install if absent) ---
    _ensure_pi()

    # --- Step 1: detect existing Pi config ---
    has_existing = detect_existing_pi()

    if merge:
        if not has_existing:
            print("[warn] No existing Pi config found (~/.pi/agent/settings.json). Using independent install.")
            print()
            merge = False
        else:
            target_agent = PI_DEFAULT_AGENT
            if is_installed(target_agent) and not force:
                print("StorageOps is already merged into your Pi config.")
                print(f"  Config dir: {target_agent}")
                print(f"  To reinstall: storageops install --merge --force")
                return

    elif has_existing:
        if is_installed() and not force:
            print("StorageOps is already installed.")
            print(f"  Config dir: {AGENT_DIR}")
            print(f"  To reinstall: storageops install --force")
            return

        if force:
            if is_installed(PI_DEFAULT_AGENT):
                target_agent = PI_DEFAULT_AGENT
                merge = True
        else:
            print()
            print("-" * 60)
            print("An existing Pi Coding Agent config was detected (~/.pi/).")
            print()
            print("StorageOps supports two install modes:")
            print()
            print("  1. Independent (recommended) -- installs to ~/.storageops/")
            print("     Your existing Pi config is untouched.")
            print()
            print("  2. Merge -- installs into ~/.pi/")
            print("     StorageOps skills and extension are added to your Pi.")
            print("     settings.json is backed up automatically.")
            print("-" * 60)
            print()
            try:
                choice = input("Install mode [Enter = independent / m = merge]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                choice = ""
            print()
            if choice == "m":
                target_agent = PI_DEFAULT_AGENT
                merge = True
                if is_installed(target_agent) and not force:
                    print("StorageOps is already merged. To reinstall: storageops install --merge --force")
                    return

    # --- Step 2: deploy files ---
    data = _package_data_dir()

    print(f"Source : {data}")
    print(f"Target : {target_agent}")
    print()

    if merge and target_agent == PI_DEFAULT_AGENT:
        _merge_settings(target_agent, SETTINGS)
    else:
        _write_settings(target_agent, SETTINGS)

    _copy_extension(data, target_agent)
    _copy_skills(data, target_agent)

    # --- Step 3: post-install verification and guidance ---
    _final_check(target_agent, merge)


def cmd_version():
    """Print version and install status."""
    try:
        from importlib.metadata import version
        v = version("storageops")
    except Exception:
        v = "unknown"
    ok, ver = check_pi_version(find_pi())
    independent = is_installed(AGENT_DIR)
    merged = is_installed(PI_DEFAULT_AGENT)
    print(f"StorageOps v{v}  (pi: {ver})")
    print(f"  independent install : {'yes' if independent else 'no'}  ({AGENT_DIR})")
    print(f"  merged install      : {'yes' if merged else 'no'}  ({PI_DEFAULT_AGENT})")


def cmd_help():
    """Print usage help."""
    print("StorageOps -- AI-powered S3-compatible object storage diagnostics")
    print()
    print("  Install:")
    print("    pip install storageops")
    print("    storageops install")
    print()
    print("  Run a diagnosis:")
    print("    storageops 's5cmd reports 429 SlowDown error'")
    print()
    print("  Install options:")
    print("    storageops install                 independent install (default)")
    print("    storageops install --merge         merge into existing Pi config")
    print("    storageops install --force         force reinstall")
    print()
    print("  Other:")
    print("    storageops --version               version and install status")
    print()
    print("  Configure an API key (pick one):")
    print("    export ANTHROPIC_API_KEY=sk-...     environment variable")
    print(f"    echo sk-... > {AGENT_DIR / 'api-key'}  local file")
    print("    storageops --api-key sk-... ...     pass at runtime")
    print("    pi /login                           login inside Pi TUI")


def main():
    args = sys.argv[1:]

    if len(args) >= 1 and args[0] == "install":
        force = "--force" in args or "-f" in args
        merge = "--merge" in args or "-m" in args
        cmd_install(force=force, merge=merge)
        return

    if len(args) >= 1 and args[0] in ("--version", "-V"):
        cmd_version()
        return

    if len(args) >= 1 and args[0] in ("--help", "-h"):
        cmd_help()
        return

    # Check installed
    installed_independent = is_installed(AGENT_DIR)
    installed_merged = is_installed(PI_DEFAULT_AGENT)

    if not (installed_independent or installed_merged):
        print("[error] StorageOps is not installed.")
        print()
        print("  Run: storageops install")
        sys.exit(1)

    agent_dir = AGENT_DIR if installed_independent else PI_DEFAULT_AGENT

    pi = find_pi()

    # Inject API key from file/auth.json so it survives shell changes
    _inject_auth_env(agent_dir)

    if len(args) == 0 and not detect_api_keys():
        print("[info] No API key set (ANTHROPIC / DEEPSEEK / OPENAI).")
        print(f"       Run /login inside Pi, or: export ANTHROPIC_API_KEY=sk-...")
        print(f"       Or write to: {agent_dir / 'api-key'}")

    os.environ["PI_CODING_AGENT_DIR"] = str(agent_dir)
    os.execvp(pi, [pi] + args)
