from __future__ import annotations

import importlib.util
from pathlib import Path


def load():
    root = Path(__file__).resolve().parents[1]
    p = root / "scripts" / "coverage_check.py"
    spec = importlib.util.spec_from_file_location("coverage_check", p)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_repo_passes_coverage():
    assert load().main() == 0


def test_min_cases_floor_is_set():
    m = load()
    assert m.MIN_CASES >= 2
