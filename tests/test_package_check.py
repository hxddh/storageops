from __future__ import annotations

import importlib.util
from pathlib import Path


def load_module():
    root = Path(__file__).resolve().parents[1]
    module_path = root / "scripts" / "package_check.py"
    spec = importlib.util.spec_from_file_location("package_check", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_skill(skills: Path, name: str, with_skill_md: bool = True) -> None:
    d = skills / name
    d.mkdir(parents=True)
    if with_skill_md:
        (d / "SKILL.md").write_text("# skill\n", encoding="utf-8")


def test_count_source_skills_counts_valid_packs(tmp_path, monkeypatch):
    mod = load_module()
    skills = tmp_path / "skills"
    make_skill(skills, "storageops-one")
    make_skill(skills, "storageops-two")
    # Not counted: missing SKILL.md, wrong prefix, or a stray file.
    make_skill(skills, "storageops-no-md", with_skill_md=False)
    make_skill(skills, "other-three")
    (skills / "README.md").write_text("notes\n", encoding="utf-8")

    monkeypatch.setattr(mod, "ROOT", tmp_path)
    assert mod._count_source_skills() == 2


def test_count_source_skills_zero_when_empty(tmp_path, monkeypatch):
    mod = load_module()
    (tmp_path / "skills").mkdir()
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    assert mod._count_source_skills() == 0


def test_check_names_passes_on_complete_artifact(tmp_path, monkeypatch):
    mod = load_module()
    monkeypatch.setattr(mod, "EXPECTED_SKILLS", 2)
    names = [
        "storageops-a/SKILL.md",
        "storageops-b/SKILL.md",
        "storageops_cli/extensions/storageops.ts",
        "storageops_cli/_vendor/httpmon/httpmon.tar.gz",
    ]
    assert mod.check_names(names, Path("pkg.whl")) == []


def test_check_names_flags_wrong_skill_count(tmp_path, monkeypatch):
    mod = load_module()
    monkeypatch.setattr(mod, "EXPECTED_SKILLS", 3)
    names = [
        "storageops-a/SKILL.md",
        "storageops_cli/extensions/storageops.ts",
        "storageops_cli/_vendor/httpmon/httpmon.tar.gz",
    ]
    errors = mod.check_names(names, Path("pkg.whl"))
    assert any("expected 3 SKILL.md files, found 1" in e for e in errors)


def test_check_names_flags_missing_extension(tmp_path, monkeypatch):
    mod = load_module()
    monkeypatch.setattr(mod, "EXPECTED_SKILLS", 1)
    names = [
        "storageops-a/SKILL.md",
        "storageops_cli/_vendor/httpmon/httpmon.tar.gz",
    ]
    errors = mod.check_names(names, Path("pkg.whl"))
    assert any("missing" in e and "storageops.ts" in e for e in errors)


def test_check_names_flags_missing_httpmon_and_pyc(tmp_path, monkeypatch):
    mod = load_module()
    monkeypatch.setattr(mod, "EXPECTED_SKILLS", 1)
    names = [
        "storageops-a/SKILL.md",
        "storageops_cli/extensions/storageops.ts",
        "storageops_cli/__pycache__/mod.cpython.pyc",
    ]
    errors = mod.check_names(names, Path("pkg.whl"))
    assert any("bundled httpmon assets" in e for e in errors)
    assert any("pyc/__pycache__" in e for e in errors)
