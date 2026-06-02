import importlib.util
import json
import sys
from pathlib import Path


def load_reporter():
    root = Path(__file__).resolve().parents[1]
    module_path = root / "skills" / "storageops-eval-golden-cases" / "scripts" / "regression_reporter.py"
    spec = importlib.util.spec_from_file_location("regression_reporter", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_load_results_handles_wrapped_and_list_shapes(tmp_path):
    reporter = load_reporter()
    wrapped = tmp_path / "wrapped.json"
    wrapped.write_text(json.dumps({"results": [{"case": "a", "status": "PASS"}]}), encoding="utf-8")
    listed = tmp_path / "listed.json"
    listed.write_text(json.dumps([{"case": "b", "status": "HARD_FAIL"}]), encoding="utf-8")

    assert reporter.load_results(wrapped) == {"a": "PASS"}
    assert reporter.load_results(listed) == {"b": "HARD_FAIL"}


def test_main_reports_regression_and_exits_nonzero(tmp_path, monkeypatch, capsys):
    reporter = load_reporter()
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps([{"case": "a", "status": "PASS"}]), encoding="utf-8")
    current = tmp_path / "current.json"
    current.write_text(json.dumps([{"case": "a", "status": "HARD_FAIL"}]), encoding="utf-8")

    monkeypatch.setattr(sys, "argv", ["regression_reporter.py", "--baseline", str(baseline), "--current", str(current)])
    rc = reporter.main()

    assert rc == 1
    report = json.loads(capsys.readouterr().out)
    assert report["ok"] is False
    assert report["regressions"][0]["case"] == "a"


def test_main_passes_when_no_regression(tmp_path, monkeypatch, capsys):
    reporter = load_reporter()
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps([{"case": "a", "status": "SOFT_FAIL"}]), encoding="utf-8")
    current = tmp_path / "current.json"
    current.write_text(json.dumps([{"case": "a", "status": "PASS"}]), encoding="utf-8")

    monkeypatch.setattr(sys, "argv", ["regression_reporter.py", "--baseline", str(baseline), "--current", str(current)])
    rc = reporter.main()

    assert rc == 0
    report = json.loads(capsys.readouterr().out)
    assert report["ok"] is True
    assert report["improvements"][0]["case"] == "a"
