"""
pytest conftest: emit triage confidence metrics after each test run.

Writes storageops-eval-metrics.json to the project root when the
STORAGEOPS_EMIT_METRICS env var is set (or always in CI via
GITHUB_ACTIONS). Tracks per-case confidence over time for regression
detection.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_CLI_DIR = Path(__file__).parent.parent
_PROJECT_ROOT = _CLI_DIR.parent
_CORE_DIR = _PROJECT_ROOT / "storageops-core"
for _sub in ("utils", "parsers", "analyzers"):
    _p = str(_CORE_DIR / _sub)
    if _p not in sys.path:
        sys.path.insert(0, _p)

_CASES_DIR = _PROJECT_ROOT / "agents" / "skills" / "storageops-eval-golden-cases" / "cases"
_METRICS_FILE = _PROJECT_ROOT / "storageops-eval-metrics.json"

_EMIT = os.environ.get("STORAGEOPS_EMIT_METRICS") or os.environ.get("GITHUB_ACTIONS")


def pytest_sessionfinish(session, exitstatus):
    """After the full pytest run, write triage confidence metrics if enabled."""
    if not _EMIT:
        return
    if not _CASES_DIR.exists():
        return

    try:
        from storageops.cli import auto_detect
    except ImportError:
        return

    metrics: dict[str, float] = {}
    for case_dir in sorted(_CASES_DIR.iterdir()):
        if not case_dir.is_dir():
            continue
        input_dir = case_dir / "input"
        expected_path = case_dir / "expected.json"
        if not input_dir.exists() or not expected_path.exists():
            continue
        try:
            texts = [
                f.read_text(encoding="utf-8", errors="replace")
                for f in sorted(input_dir.iterdir())
                if f.is_file()
            ]
            expected = json.loads(expected_path.read_text())
            text = "\n\n".join(texts)
            category = expected.get("expected_category", "unknown")
            detections = auto_detect(text)
            conf = {d["domain"]: d["confidence"] for d in detections}
            metrics[case_dir.name] = conf.get(category, 0.0)
        except Exception:
            metrics[case_dir.name] = -1.0   # error sentinel

    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "exit_status": exitstatus,
        "confidence": metrics,
    }

    # Append to history
    history: list[dict] = []
    if _METRICS_FILE.exists():
        try:
            history = json.loads(_METRICS_FILE.read_text())
        except Exception:
            history = []
    history.append(record)
    _METRICS_FILE.write_text(json.dumps(history, indent=2))
