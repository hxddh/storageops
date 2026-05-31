"""StorageOps user configuration stored in ~/.storageops/config.json."""
from __future__ import annotations

import json
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


def get_pi_command() -> str:
    return load().get("pi_command", "pi")


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
