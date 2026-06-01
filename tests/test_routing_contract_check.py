import importlib.util
from pathlib import Path


def load_checker():
    root = Path(__file__).resolve().parents[1]
    module_path = root / "scripts" / "routing_contract_check.py"
    spec = importlib.util.spec_from_file_location("routing_contract_check", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_current_routing_contract_is_consistent():
    checker = load_checker()
    taxonomy = checker.load_json(checker.TAXONOMY)
    registry_names = checker.registry_skill_names()
    cases = checker.case_categories()

    errors = []
    errors.extend(checker.validate_taxonomy(taxonomy, registry_names))
    errors.extend(checker.validate_cases(taxonomy, cases))
    errors.extend(checker.validate_baselines(taxonomy, cases))
    errors.extend(checker.validate_extension_coverage(taxonomy))

    assert errors == []


def test_baseline_requires_enabled_category(tmp_path, monkeypatch):
    checker = load_checker()
    baseline_dir = tmp_path / "baseline-outputs"
    baseline_dir.mkdir()
    (baseline_dir / "case.md").write_text("Category: reporting\n")
    monkeypatch.setattr(checker, "BASELINES", baseline_dir)
    taxonomy = {"categories": {"reporting": {"baseline": False}}}

    errors = checker.validate_baselines(taxonomy, {"case": "reporting"})

    assert errors == ["case: category reporting is not baseline-enabled"]
