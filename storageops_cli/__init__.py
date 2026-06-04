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
    `-- skills/                16 packs (15 diagnostic + 1 eval)
"""

import subprocess
import sys
import os
import json
import re
import shutil
import urllib.request
import hashlib
import platform
import gzip
import getpass
from datetime import datetime, timezone
from pathlib import Path
from importlib import resources
from importlib import metadata


ROOT = Path.home() / ".storageops"
AGENT_DIR = ROOT / "agent"          # PI_CODING_AGENT_DIR
BIN_DIR = ROOT / "bin"
PI_DEFAULT = Path.home() / ".pi"
PI_DEFAULT_AGENT = PI_DEFAULT / "agent"
MIN_PI_VERSION = "0.78.0"
# Pi 0.78+ declares engines node >= 22.19.0; on older Node, npm installs an
# incompatible legacy Pi that StorageOps rejects, so check Node before installing.
MIN_NODE_VERSION = (22, 19, 0)
REQUIRED_API_KEYS = ["ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY"]
PYPI_JSON_URL = "https://pypi.org/pypi/storageops/json"
HTTPMON_VERSION = "v1.0.2"
HTTPMON_BASE_URL = f"https://github.com/hxddh/https-traffic-inspector/releases/download/{HTTPMON_VERSION}"
HTTPMON_ASSETS = {
    ("linux", "x86_64"): ("httpmon-v1.0.2-linux-amd64", "0ff838fc6eb9fd19c10185d5ce789e54b972291723ed4077e7c8954c920d669c"),
    ("linux", "amd64"): ("httpmon-v1.0.2-linux-amd64", "0ff838fc6eb9fd19c10185d5ce789e54b972291723ed4077e7c8954c920d669c"),
    ("linux", "aarch64"): ("httpmon-v1.0.2-linux-arm64", "43dd49804ca3d235a339349a080eb32e9054a2daa1811fbdf002cc391a3a173d"),
    ("linux", "arm64"): ("httpmon-v1.0.2-linux-arm64", "43dd49804ca3d235a339349a080eb32e9054a2daa1811fbdf002cc391a3a173d"),
    ("darwin", "x86_64"): ("httpmon-v1.0.2-macos-amd64", "45fb0e2e97a4264ef4b0ce04b97acc6fdfb6f58d022261fd314d71e6141f1fde"),
    ("darwin", "amd64"): ("httpmon-v1.0.2-macos-amd64", "45fb0e2e97a4264ef4b0ce04b97acc6fdfb6f58d022261fd314d71e6141f1fde"),
    ("darwin", "arm64"): ("httpmon-v1.0.2-macos-arm64", "dc849b83fd7dd5e7336ad8d86944fa4b7cfccc2398733d8a8aae9e1f607d1874"),
    ("windows", "amd64"): ("httpmon-v1.0.2-windows-amd64.exe", "c650807a927f96c5695272a1d0435e38d0ca9b37193324f59e24bb67cdf8fa88"),
    ("windows", "x86_64"): ("httpmon-v1.0.2-windows-amd64.exe", "c650807a927f96c5695272a1d0435e38d0ca9b37193324f59e24bb67cdf8fa88"),
}

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

# Provider prefixes accepted in the plain api-key file ("provider:key"), plus a
# couple of friendly aliases. Pi binds credentials to an explicit provider, so
# the file does too rather than guessing the provider from the key shape.
API_KEY_FILE_PROVIDERS = {**PROVIDER_ENV, "gemini": "GEMINI_API_KEY", "claude": "ANTHROPIC_API_KEY"}


def _resolve_api_key_entry(raw: str) -> tuple[str | None, str]:
    """
    Parse an api-key file value, honoring an optional ``provider:key`` prefix.

    Returns ``(env_var, key)``. ``env_var`` is None when no known provider
    prefix is present, in which case the caller applies the default fallback.
    """
    prefix, sep, rest = raw.partition(":")
    if sep:
        env_var = API_KEY_FILE_PROVIDERS.get(prefix.strip().lower())
        if env_var:
            return env_var, rest.strip()
    return None, raw


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


def _prepend_storageops_bin_to_path() -> None:
    """Make StorageOps-managed helper binaries visible to Pi and extensions."""
    current = os.environ.get("PATH", "")
    bin_path = str(BIN_DIR)
    parts = current.split(os.pathsep) if current else []
    if bin_path not in parts:
        os.environ["PATH"] = os.pathsep.join([bin_path, *parts]) if current else bin_path


def find_httpmon() -> str | None:
    """Locate httpmon, preferring the StorageOps-managed binary."""
    managed = BIN_DIR / ("httpmon.exe" if os.name == "nt" else "httpmon")
    if managed.exists():
        return str(managed)
    found = shutil.which("httpmon")
    return found


def _httpmon_asset_for_platform() -> tuple[str, str] | None:
    """Return (asset_name, sha256) for the current platform, if supported."""
    system = platform.system().lower()
    machine = platform.machine().lower()
    return HTTPMON_ASSETS.get((system, machine))


def _read_bundled_httpmon(asset_name: str) -> bytes | None:
    """Read a bundled gzip-compressed httpmon asset from the installed package."""
    try:
        asset = resources.files("storageops_cli").joinpath("_vendor", "httpmon", f"{asset_name}.gz")
        if not asset.is_file():
            return None
        return gzip.decompress(asset.read_bytes())
    except Exception:
        return None


def _install_httpmon_bytes(data: bytes, expected_sha: str, target: Path) -> str | None:
    """Validate and install httpmon bytes into the managed StorageOps bin dir."""
    actual_sha = hashlib.sha256(data).hexdigest()
    if actual_sha != expected_sha:
        return None

    BIN_DIR.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.chmod(0o755)
    tmp.replace(target)
    return str(target)


def _ensure_httpmon() -> str | None:
    """
    Ensure httpmon is available for capture_http_trace.

    The helper is installed into ~/.storageops/bin so users do not need to
    install Go or manage PATH manually. Failure is a warning: StorageOps can
    still diagnose from logs, but capture_http_trace will be unavailable.
    """
    _prepend_storageops_bin_to_path()
    existing = find_httpmon()
    if existing:
        print(f"[ok] httpmon -> {existing}")
        return existing

    asset = _httpmon_asset_for_platform()
    if not asset:
        print("[warn] httpmon helper     unsupported platform for automatic install")
        print("       capture_http_trace will be unavailable until httpmon is installed manually.")
        return None

    asset_name, expected_sha = asset
    url = f"{HTTPMON_BASE_URL}/{asset_name}"
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    target = BIN_DIR / ("httpmon.exe" if asset_name.endswith(".exe") else "httpmon")
    tmp = target.with_suffix(target.suffix + ".tmp")

    print(f"[info] httpmon not found. Installing {HTTPMON_VERSION}...")
    bundled = _read_bundled_httpmon(asset_name)
    if bundled:
        installed = _install_httpmon_bytes(bundled, expected_sha, target)
        if installed:
            print(f"[ok] httpmon {HTTPMON_VERSION} -> {target}")
            return installed
        print("[warn] httpmon helper     bundled helper checksum mismatch")

    try:
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
                    "20",
                    "--output",
                    str(tmp),
                    url,
                ],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise RuntimeError((result.stderr or result.stdout or "curl download failed").strip())
            data = tmp.read_bytes()
        else:
            req = urllib.request.Request(url, headers={"User-Agent": f"storageops/{_package_version()}"})
            with urllib.request.urlopen(req, timeout=10) as response:
                data = response.read()
            tmp.write_bytes(data)
        installed = _install_httpmon_bytes(data, expected_sha, target)
        if not installed:
            print("[warn] httpmon helper     download checksum mismatch")
            print("       capture_http_trace will be unavailable; no helper was installed.")
            if tmp.exists():
                tmp.unlink()
            return None
        print(f"[ok] httpmon {HTTPMON_VERSION} -> {target}")
        return installed
    except Exception as exc:
        if tmp.exists():
            try:
                tmp.unlink()
            except Exception:
                pass
        print(f"[warn] httpmon helper     automatic install failed: {exc}")
        print("       capture_http_trace will be unavailable until httpmon is installed manually.")
        return None


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


def _parse_version_triple(raw: str) -> tuple[int, int, int] | None:
    """Parse the first X.Y.Z found in a version string (e.g. 'v22.19.0')."""
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", raw or "")
    return tuple(int(part) for part in match.groups()) if match else None


def _node_version() -> tuple[int, int, int] | None:
    """Return the installed Node.js version as a tuple, or None if not found."""
    node = shutil.which("node")
    if not node:
        return None
    try:
        result = subprocess.run([node, "--version"], capture_output=True, text=True)
        return _parse_version_triple(result.stdout + result.stderr)
    except Exception:
        return None


def _node_too_old() -> tuple[bool, str]:
    """Return (is_too_old, version_label). Absent Node is not 'too old' here."""
    nv = _node_version()
    if nv is None:
        return False, "not found"
    return nv < MIN_NODE_VERSION, ".".join(str(p) for p in nv)


def _ensure_pi() -> str:
    """
    Ensure Pi Coding Agent is available; return the pi executable path.

    - pi present, version OK  : print confirmation, return path.
    - pi present, version low : stop before deployment and print upgrade command.
      (No auto-upgrade: upgrading may break the user's existing Pi config.)
    - pi not found            : attempt npm auto-install; exit with guidance
      if npm is also absent.
    """
    pi_exe = find_pi()
    ok, ver = check_pi_version(pi_exe)

    if ok:
        print(f"[ok] pi {ver} -> {pi_exe}")
        return pi_exe

    min_node = ".".join(str(p) for p in MIN_NODE_VERSION)

    if ver != "not found":
        # pi exists but is too old for the extension/config contract; do not auto-upgrade.
        too_old, nv = _node_too_old()
        print(f"[error] pi {ver} < {MIN_PI_VERSION} -- StorageOps cannot run safely.")
        print("        StorageOps requires Pi Coding Agent with Extension API support.")
        print("        No files were deployed.")
        if too_old:
            # npm will keep serving the legacy Pi on old Node, so upgrading Node is the real fix.
            print(f"        Your Node.js is {nv}; Pi {MIN_PI_VERSION}+ requires Node >= {min_node}.")
            print("        Upgrade Node first (e.g. nvm install 22), then:")
        else:
            print("        To upgrade:")
        print("        npm install -g @earendil-works/pi-coding-agent")
        print()
        sys.exit(1)

    # pi not found at all -- attempt auto-install via npm
    npm = shutil.which("npm")
    if not npm:
        print("[error] Pi Coding Agent not found and npm is not available.")
        print(f"        Install Node.js {min_node}+ first: https://nodejs.org")
        print("        Then re-run: storageops install")
        sys.exit(1)

    # Pre-flight Node check: an old Node makes npm install an incompatible legacy
    # Pi that StorageOps then rejects. Stop with actionable guidance instead.
    too_old, nv = _node_too_old()
    if too_old:
        print(f"[error] Node.js {nv} is too old. Pi {MIN_PI_VERSION}+ requires Node >= {min_node}.")
        print("        npm would install an incompatible legacy Pi that StorageOps rejects.")
        print("        Upgrade Node (e.g. nvm install 22), then re-run: storageops install")
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


def _count_storageops_skills(skills_dir: Path) -> int:
    """Count deployed storageops-* skill packs in a skills directory."""
    if not skills_dir.is_dir():
        return 0
    return sum(1 for d in skills_dir.iterdir() if d.is_dir() and d.name.startswith("storageops-"))


def _expected_skill_count() -> int:
    """How many skill packs the installed package ships (source of truth).

    Avoids a hardcoded threshold: readiness compares deployed skills against the
    packs actually bundled with this wheel, so the check stays correct as the
    skill set grows or shrinks.
    """
    try:
        return _count_storageops_skills(_package_data_dir() / "skills")
    except Exception:
        return 0


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


def _configured_key_source(agent_dir: Path) -> str | None:
    """
    Return a human description of where a usable model key is configured, or None.

    Checks the same sources the launcher injects from -- environment variables, the
    StorageOps api-key file, and Pi auth.json -- so status output is honest when a
    key is configured via file rather than via the environment. Reports presence,
    not validity (a key being well-formed does not mean it authenticates).
    """
    for var in dict.fromkeys([*REQUIRED_API_KEYS, *PROVIDER_ENV.values()]):
        if os.environ.get(var):
            return f"env ({var})"
    key_file = agent_dir / "api-key"
    try:
        if key_file.exists() and key_file.read_text().strip():
            return "api-key file"
    except Exception:
        pass
    auth_file = agent_dir / "auth.json"
    try:
        if auth_file.exists():
            auth = json.loads(auth_file.read_text())
            for provider in PROVIDER_ENV:
                val = auth.get(provider)
                if isinstance(val, dict):
                    val = val.get("apiKey") or val.get("key")
                if isinstance(val, str) and val:
                    return f"auth.json ({provider})"
    except Exception:
        pass
    return None


def _active_agent_dir() -> Path:
    """Return the StorageOps agent dir currently most likely to be used."""
    independent = is_installed(AGENT_DIR)
    merged = is_installed(PI_DEFAULT_AGENT)
    return PI_DEFAULT_AGENT if (merged and not independent) else AGENT_DIR


def _read_json_file(path: Path) -> dict:
    """Read a JSON object from path; return {} for missing or invalid files."""
    try:
        if path.exists():
            value = json.loads(path.read_text())
            if isinstance(value, dict):
                return value
    except Exception:
        pass
    return {}


def _agent_settings(agent_dir: Path) -> dict:
    """Read settings.json for the selected agent directory."""
    return _read_json_file(agent_dir / "settings.json")


def _default_model_label(agent_dir: Path) -> str:
    """Return configured default provider/model, or a compact missing label."""
    settings = _agent_settings(agent_dir)
    provider = settings.get("defaultProvider") or "not set"
    model = settings.get("defaultModel") or "not set"
    return f"{provider}/{model}"


def _install_marker() -> dict:
    """Return the install provenance marker, if present."""
    return _read_json_file(ROOT / "install.json")


def _key_conflict(agent_dir: Path) -> str | None:
    """Detect common key-source confusion without exposing key values."""
    env_keys = [var for var in dict.fromkeys([*REQUIRED_API_KEYS, *PROVIDER_ENV.values()]) if os.environ.get(var)]
    key_file = agent_dir / "api-key"
    has_file = False
    try:
        has_file = key_file.exists() and bool(key_file.read_text().strip())
    except Exception:
        has_file = False
    if env_keys and has_file:
        return f"environment key overrides api-key file ({', '.join(env_keys[:3])})"
    return None


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

    # 2. StorageOps api-key file. Supports an optional explicit "provider:key"
    #    prefix (e.g. "anthropic:sk-ant-...") routed via the provider map, matching
    #    Pi's provider-explicit auth model. Without a known prefix it falls back to
    #    the DeepSeek-first default for backward compatibility.
    key_file = agent_dir / "api-key"
    if key_file.exists():
        raw = key_file.read_text().strip()
        if raw:
            env_var, key = _resolve_api_key_entry(raw)
            if env_var:
                if env_var not in os.environ:
                    os.environ[env_var] = key
            else:
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


def _package_version() -> str:
    """Return the installed StorageOps package version."""
    try:
        return metadata.version("storageops")
    except Exception:
        return "unknown"


def _version_tuple(value: str) -> tuple[int, ...]:
    """Parse simple numeric versions for best-effort comparisons."""
    match = re.match(r"^(\d+(?:\.\d+)*)", value)
    if not match:
        return ()
    return tuple(int(part) for part in match.group(1).split("."))


def _is_newer_version(candidate: str, current: str) -> bool:
    """Return True when candidate is newer than current."""
    cand = _version_tuple(candidate)
    cur = _version_tuple(current)
    return bool(cand and cur and cand > cur)


def _latest_pypi_version(timeout: float = 2.0) -> str | None:
    """Return latest PyPI version when reachable; never raise."""
    if os.environ.get("STORAGEOPS_SKIP_VERSION_CHECK"):
        return None
    try:
        req = urllib.request.Request(
            PYPI_JSON_URL,
            headers={
                "Accept": "application/json",
                "Cache-Control": "no-cache",
                "User-Agent": f"storageops/{_package_version()}",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        version = payload.get("info", {}).get("version")
        return version if isinstance(version, str) and version else None
    except Exception:
        return None


def _print_package_status(data: Path, target_agent: Path) -> None:
    """Print the exact local package that will provide deployed files."""
    local_version = _package_version()
    print(f"StorageOps package: v{local_version}")
    print(f"Package path      : {data}")
    print(f"Deploy target     : {_skills_dir_for_agent(target_agent)}")

    latest = _latest_pypi_version()
    if latest and _is_newer_version(latest, local_version):
        print()
        print(f"[warn] Latest StorageOps on PyPI is v{latest}, but local package is v{local_version}.")
        print("       You are deploying bundled files from the old local package.")
        print("       Upgrade first:")
        print("       python3 -m pip install --upgrade storageops -i https://pypi.org/simple")
    elif latest is None:
        print("[info] Could not check latest PyPI version; continuing with local package.")


def _write_install_marker(data: Path, target_agent: Path, merge: bool) -> None:
    """Write lightweight install provenance for later troubleshooting."""
    ROOT.mkdir(parents=True, exist_ok=True)
    marker = {
        "package_version": _package_version(),
        "package_path": str(data),
        "target_agent": str(target_agent),
        "skills_path": str(_skills_dir_for_agent(target_agent)),
        "install_mode": "merge" if merge else "independent",
        "installed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    marker_path = ROOT / "install.json"
    marker_path.write_text(json.dumps(marker, indent=2, ensure_ascii=False) + "\n")
    print(f"  [ok] install marker -> {marker_path}")


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


def _write_config_settings(agent_dir: Path, provider: str | None, model: str | None) -> None:
    """Update defaultProvider/defaultModel without disturbing other Pi settings.

    Schema invariant (verified against Pi 0.78 ``core/settings-manager``):
    Pi's ``globalSettingsPath`` is ``{agentDir}/settings.json`` — the exact file
    written here — and it reads defaults via ``getDefaultProvider()`` /
    ``getDefaultModel()`` from the keys ``defaultProvider`` / ``defaultModel``.
    Keep these key names aligned with Pi if its settings schema changes.
    """
    settings = _agent_settings(agent_dir) or dict(SETTINGS)
    for key, value in SETTINGS.items():
        settings.setdefault(key, value)
    if provider:
        settings["defaultProvider"] = provider
    if model:
        settings["defaultModel"] = model
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "settings.json").write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n")


def _write_api_key(agent_dir: Path, key_value: str) -> None:
    """Write the local model-provider key with restrictive permissions."""
    agent_dir.mkdir(parents=True, exist_ok=True)
    key_file = agent_dir / "api-key"
    key_file.write_text(key_value.strip() + "\n")
    try:
        key_file.chmod(0o600)
    except Exception:
        pass


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
    key_source = _configured_key_source(agent_dir)
    if key_source:
        print(f"[ok] API key             configured ({key_source})")
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
    _ensure_httpmon()

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

    _print_package_status(data, target_agent)
    print()

    if merge and target_agent == PI_DEFAULT_AGENT:
        _merge_settings(target_agent, SETTINGS)
    else:
        _write_settings(target_agent, SETTINGS)

    _copy_extension(data, target_agent)
    _copy_skills(data, target_agent)
    _write_install_marker(data, target_agent, merge)

    # --- Step 3: post-install verification and guidance ---
    _final_check(target_agent, merge)


def _runtime_status() -> dict:
    """Collect the shared install/runtime status used by version and doctor.

    Single source for both commands so their reports cannot drift apart.
    """
    nv = _node_version()
    pi_path = find_pi()
    pi_ok, pi_ver = check_pi_version(pi_path)
    active_agent = _active_agent_dir()
    skills_dir = _skills_dir_for_agent(active_agent)
    marker = _install_marker()
    return {
        "version": _package_version(),
        "latest": _latest_pypi_version(),
        "pi_path": pi_path,
        "pi_ok": pi_ok,
        "pi_ver": pi_ver,
        "node_triple": nv,
        "node_ok": bool(nv and nv >= MIN_NODE_VERSION),
        "independent": is_installed(AGENT_DIR),
        "merged": is_installed(PI_DEFAULT_AGENT),
        "active_agent": active_agent,
        "skills_dir": skills_dir,
        "skill_count": _count_storageops_skills(skills_dir),
        "expected_skills": _expected_skill_count(),
        "httpmon": find_httpmon(),
        "key_source": _configured_key_source(active_agent),
        "conflict": _key_conflict(active_agent),
        "default_model": _default_model_label(active_agent),
        "marker": marker,
        "package_path": marker.get("package_path") or str(Path(__file__).resolve().parent),
    }


def cmd_version():
    """Print version and install status."""
    s = _runtime_status()
    nv = s["node_triple"]
    node_str = ("v" + ".".join(str(p) for p in nv)) if nv else "not found"
    print(f"StorageOps v{s['version']}  (pi: {s['pi_ver']})")
    print(f"  node                : {node_str}")
    print(f"  package path        : {s['package_path']}")
    print(f"  deployed version    : {s['marker'].get('package_version') or 'unknown'}")
    print(f"  latest PyPI         : {s['latest'] or 'unknown'}")
    print(f"  default model       : {s['default_model']}")
    print(f"  httpmon             : {s['httpmon'] or 'not found'}")
    print(f"  api key             : {s['key_source'] or 'not configured'}")
    print(f"  independent install : {'yes' if s['independent'] else 'no'}  ({AGENT_DIR})")
    print(f"  merged install      : {'yes' if s['merged'] else 'no'}  ({PI_DEFAULT_AGENT})")


def _doctor_row(name: str, status: str, detail: str) -> None:
    print(f"{name:<14} {status:<5} {detail}")


def cmd_doctor() -> int:
    """Print a concise readiness report."""
    s = _runtime_status()
    nv = s["node_triple"]
    node_label = ".".join(str(p) for p in nv) if nv else "not found"
    latest, local_version = s["latest"], s["version"]
    independent, merged = s["independent"], s["merged"]
    skill_count, expected_skills = s["skill_count"], s["expected_skills"]
    key_source, marker = s["key_source"], s["marker"]

    print("StorageOps doctor")
    _doctor_row("Package", "ok", f"{local_version}" + (f" (latest {latest})" if latest else ""))
    if latest and _is_newer_version(latest, local_version):
        _doctor_row("PyPI", "warn", f"newer version available: {latest}")
    else:
        _doctor_row("PyPI", "ok", latest or "version check unavailable")
    _doctor_row("Node", "ok" if s["node_ok"] else "warn", node_label)
    _doctor_row("Pi", "ok" if s["pi_ok"] else "warn", f"{s['pi_ver']} ({s['pi_path']})")
    install_detail = "independent" if independent else "merged" if merged else "not installed"
    _doctor_row("Install", "ok" if (independent or merged) else "warn", f"{install_detail} ({s['active_agent']})")
    skills_ok = skill_count >= expected_skills if expected_skills else skill_count > 0
    skills_detail = f"{skill_count} packs" + (f" of {expected_skills}" if expected_skills else "") + f" ({s['skills_dir']})"
    _doctor_row("Skills", "ok" if skills_ok else "warn", skills_detail)
    _doctor_row("httpmon", "ok" if s["httpmon"] else "warn", s["httpmon"] or "not found")
    _doctor_row("API key", "ok" if key_source else "warn", key_source or "not configured")
    if s["conflict"]:
        _doctor_row("Key conflict", "warn", s["conflict"])
    _doctor_row("Default model", "ok", s["default_model"])
    if marker:
        _doctor_row("Deployed", "ok", f"v{marker.get('package_version', 'unknown')} from {marker.get('package_path', 'unknown')}")

    if not (independent or merged):
        print("Next: storageops install")
    elif not key_source:
        print("Next: storageops configure --provider deepseek --model deepseek-v4-pro --api-key")
    elif not s["pi_ok"] or not s["node_ok"]:
        print("Next: fix Node/Pi, then run storageops install --force")
    else:
        print("Ready: storageops --print 'hello'")
    return 0


def _option_value(args: list[str], name: str) -> str | None:
    """Return an option value for --name VALUE or --name=VALUE."""
    prefix = name + "="
    for i, arg in enumerate(args):
        if arg == name:
            if i + 1 >= len(args) or args[i + 1].startswith("--"):
                return ""
            return args[i + 1]
        if arg.startswith(prefix):
            return arg[len(prefix):]
    return None


def _has_flag(args: list[str], name: str) -> bool:
    return name in args or any(arg.startswith(name + "=") for arg in args)


def cmd_configure(args: list[str]) -> int:
    """Configure default provider/model and optional local api-key."""
    if "--help" in args or "-h" in args:
        print("Usage: storageops configure [--provider NAME] [--model ID] [--api-key [KEY]] [--show] [--merge]")
        return 0

    merge = "--merge" in args or "-m" in args
    agent_dir = PI_DEFAULT_AGENT if merge else AGENT_DIR
    if _has_flag(args, "--show"):
        print(f"Config dir     : {agent_dir}")
        print(f"default model  : {_default_model_label(agent_dir)}")
        print(f"api key        : {_configured_key_source(agent_dir) or 'not configured'}")
        return 0

    provider = _option_value(args, "--provider")
    model = _option_value(args, "--model")
    if provider == "" or model == "":
        print("[error] --provider and --model require values")
        return 2

    key_value = None
    if _has_flag(args, "--api-key"):
        value = _option_value(args, "--api-key")
        if value is None or value == "":
            try:
                value = getpass.getpass("Model API key (input hidden): ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                print("[error] API key input cancelled")
                return 2
        if not value:
            print("[error] empty API key")
            return 2
        key_value = value

    if not provider and not model and key_value is None:
        print("Nothing to configure. Try: storageops configure --provider deepseek --model deepseek-v4-pro")
        return 0

    if provider or model:
        _write_config_settings(agent_dir, provider, model)
        print(f"[ok] settings.json -> {agent_dir / 'settings.json'}")
    if key_value is not None:
        if provider and ":" not in key_value:
            key_value = f"{provider}:{key_value}"
        _write_api_key(agent_dir, key_value)
        print(f"[ok] api-key       -> {agent_dir / 'api-key'}")

    print("Check: storageops doctor")
    return 0


def cmd_smoke(args: list[str]) -> int:
    """Run an explicit minimal model smoke test through Pi."""
    if "--help" in args or "-h" in args:
        print("Usage: storageops smoke [--provider NAME] [--model ID] [--prompt TEXT] [--timeout SECONDS]")
        return 0
    if not (is_installed(AGENT_DIR) or is_installed(PI_DEFAULT_AGENT)):
        print("[error] StorageOps is not installed. Run: storageops install")
        return 1

    agent_dir = _active_agent_dir()
    _inject_auth_env(agent_dir)
    if not _configured_key_source(agent_dir):
        print("[error] API key is not configured. Run: storageops configure --api-key")
        return 1

    prompt = _option_value(args, "--prompt") or "hello"
    provider = _option_value(args, "--provider")
    model = _option_value(args, "--model")
    timeout_raw = _option_value(args, "--timeout") or "60"
    try:
        timeout = max(5, int(timeout_raw))
    except ValueError:
        print("[error] --timeout must be an integer number of seconds")
        return 2

    cmd = [find_pi()]
    if provider:
        cmd += ["--provider", provider]
    if model:
        cmd += ["--model", model]
    cmd += ["--print", prompt]

    _prepend_storageops_bin_to_path()
    env = {**os.environ, "PI_CODING_AGENT_DIR": str(agent_dir)}
    print(f"[info] running smoke via {cmd[0]} (prompt: {prompt!r})")
    try:
        result = subprocess.run(cmd, env=env, text=True, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        print(f"[error] smoke timed out after {timeout}s")
        return 1
    output = (result.stdout or result.stderr or "").strip()
    if result.returncode == 0:
        print("[ok] model smoke succeeded")
        if output:
            print(output[:1000])
        return 0
    print("[error] model smoke failed")
    if output:
        print(output[:1000])
    return result.returncode or 1


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
    print("    storageops doctor                  readiness checks")
    print("    storageops configure --show        show model/key config")
    print("    storageops smoke                   explicit model smoke test")
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

    if len(args) >= 1 and args[0] == "doctor":
        sys.exit(cmd_doctor())

    if len(args) >= 1 and args[0] == "configure":
        sys.exit(cmd_configure(args[1:]))

    if len(args) >= 1 and args[0] == "smoke":
        sys.exit(cmd_smoke(args[1:]))

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
    _prepend_storageops_bin_to_path()
    os.execvp(pi, [pi] + args)
