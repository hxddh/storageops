"""StorageOps user configuration stored in ~/.storageops/config.json."""
from __future__ import annotations

import json
import os
from pathlib import Path

_DIR = Path.home() / ".storageops"
_FILE = _DIR / "config.json"


def load() -> dict:
    if _FILE.exists():
        try:
            return json.loads(_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save(config: dict) -> None:
    _DIR.mkdir(parents=True, exist_ok=True)
    _FILE.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def update(**kwargs) -> None:
    cfg = load()
    cfg.update(kwargs)
    save(cfg)


def get_pi_command() -> str:
    """Resolve the Pi binary: config > env > 'pi'."""
    from storageops.pi_installer import pi_bin_path
    # Config override
    cfg_cmd = load().get("pi_command")
    if cfg_cmd:
        return cfg_cmd
    # Bundled bin
    bundled = pi_bin_path()
    if bundled.exists():
        return str(bundled)
    return "pi"


def get_workdir() -> Path:
    cfg = load()
    if "workdir" in cfg:
        return Path(cfg["workdir"]).expanduser()
    return _DIR


def get_skills_dir() -> Path | None:
    cfg = load()
    if "skills_dir" in cfg:
        d = Path(cfg["skills_dir"]).expanduser()
        if d.exists():
            return d
    default = _DIR / "skills"
    return default if default.exists() else None


def detect_provider_from_key(key: str) -> str:
    """Infer LLM provider from API key prefix."""
    if key.startswith("sk-ant-"):
        return "anthropic"
    if key.startswith("sk-"):
        return "openai"
    return "anthropic"


def get_provider() -> str:
    return load().get("provider", "anthropic")


def get_api_key() -> str | None:
    """Get LLM API key: config file first, then standard env vars."""
    cfg_key = load().get("api_key")
    if cfg_key:
        return cfg_key
    provider = get_provider()
    env_map = {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai":    "OPENAI_API_KEY",
    }
    env_var = env_map.get(provider, f"{provider.upper()}_API_KEY")
    return os.environ.get(env_var)

