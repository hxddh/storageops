from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def load_integrity_module():
    root = Path(__file__).resolve().parents[1]
    module_path = root / "scripts" / "skill_integrity_check.py"
    spec = importlib.util.spec_from_file_location("skill_integrity_check", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_case(case: Path, input_size: int) -> None:
    (case / "input").mkdir(parents=True)
    (case / "expected.json").write_text(
        json.dumps(
            {
                "expected_category": "security_iam_policy",
                "expected_min_confidence": 0.7,
                "must_include_evidence_keywords": ["AccessDenied"],
                "must_include_recommendation_keywords": ["policy"],
                "must_not_include": ["delete bucket"],
                "required_report_sections": ["Summary"],
            }
        ),
        encoding="utf-8",
    )
    (case / "input" / "error.log").write_text("x" * input_size, encoding="utf-8")


def test_golden_case_input_size_budget_is_enforced(tmp_path, monkeypatch):
    integrity = load_integrity_module()
    cases_root = tmp_path / "cases"
    write_case(cases_root / "oversized", integrity.MAX_GOLDEN_INPUT_BYTES + 1)
    monkeypatch.setattr(integrity, "EVAL_CASES", cases_root)

    errors: list[str] = []
    integrity.validate_golden_cases(errors, {"security_iam_policy": "storageops-security-iam-policy"})

    assert any("input artifact exceeds" in error for error in errors)


def _write_min_skill(skill_dir: Path, *, linked: list[str], on_disk: list[str]) -> None:
    """A minimal valid skill that links `linked` references and has `on_disk` files."""
    skill_dir.mkdir(parents=True)
    refs = "\n".join(f"- `references/{name}` — note | **Read when:** x" for name in linked)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        f"name: {skill_dir.name}\n"
        "description: test skill\n"
        "maturity: core\n"
        "mode: light_heavy\n"
        "trigger_keywords:\n  - foo\n"
        "recommended_tools:\n  - detect_domain\n"
        "---\n\n# Test\n\n## References\n" + refs + "\n",
        encoding="utf-8",
    )
    (skill_dir / "references").mkdir()
    for name in on_disk:
        (skill_dir / "references" / name).write_text("# ref\n", encoding="utf-8")


def test_orphan_reference_is_flagged(tmp_path, monkeypatch):
    integrity = load_integrity_module()
    skills_root = tmp_path / "skills"
    # linked.md is referenced; orphan.md exists on disk but is never linked.
    _write_min_skill(
        skills_root / "storageops-foo",
        linked=["linked.md"],
        on_disk=["linked.md", "orphan.md"],
    )
    monkeypatch.setattr(integrity, "SKILLS_DIR", skills_root)

    errors: list[str] = []
    integrity.validate_skills(errors)

    assert any("orphan.md is not linked" in e for e in errors), errors
    assert not any("linked.md is not linked" in e for e in errors), errors
