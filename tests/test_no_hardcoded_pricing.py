from __future__ import annotations

import importlib.util
from pathlib import Path


def load_module():
    root = Path(__file__).resolve().parents[1]
    module_path = root / "scripts" / "no_hardcoded_pricing.py"
    spec = importlib.util.spec_from_file_location("no_hardcoded_pricing", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_skill(skills_root: Path, name: str, body: str) -> None:
    skill_dir = skills_root / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(body, encoding="utf-8")


def test_dollar_literal_is_flagged(tmp_path, monkeypatch, capsys):
    mod = load_module()
    skills = tmp_path / "skills"
    write_skill(
        skills,
        "storageops-pricing",
        "# Pricing\nStorage costs $10 per TB each month.\n",
    )
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setattr(mod, "SKILLS", skills)

    assert mod.main() == 1
    err = capsys.readouterr().err
    assert "volatile pricing literal" in err


def test_yen_and_usd_literals_are_flagged(tmp_path, monkeypatch, capsys):
    mod = load_module()
    skills = tmp_path / "skills"
    write_skill(skills, "storageops-yen", "# Yen\nPlan A is ¥5 per request.\n")
    write_skill(skills, "storageops-usd", "# Usd\nRate is 0.023 USD per GB.\n")
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setattr(mod, "SKILLS", skills)

    assert mod.main() == 1
    err = capsys.readouterr().err
    assert "storageops-yen" in err
    assert "storageops-usd" in err


def test_placeholder_and_no_price_pass(tmp_path, monkeypatch, capsys):
    mod = load_module()
    skills = tmp_path / "skills"
    write_skill(
        skills,
        "storageops-method",
        "# Method\nLook up the current rate via ${PRICE_VAR} and apply it.\n"
        "Describe the pricing method, not a concrete number.\n",
    )
    write_skill(
        skills,
        "storageops-noprice",
        "# No Price\nThis skill explains bucket lifecycle policies.\n",
    )
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setattr(mod, "SKILLS", skills)

    assert mod.main() == 0
    out = capsys.readouterr().out
    assert "passed" in out


def test_only_storageops_prefixed_skills_are_scanned(tmp_path, monkeypatch, capsys):
    mod = load_module()
    skills = tmp_path / "skills"
    # Non-prefixed dir contains a price literal but must be ignored by the glob.
    write_skill(skills, "other-skill", "# Other\nCosts $99 here.\n")
    write_skill(skills, "storageops-clean", "# Clean\nNo prices here.\n")
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setattr(mod, "SKILLS", skills)

    assert mod.main() == 0
