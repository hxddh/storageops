from __future__ import annotations

import importlib.util
from pathlib import Path


def load_module():
    root = Path(__file__).resolve().parents[1]
    module_path = root / "scripts" / "version_reference_check.py"
    spec = importlib.util.spec_from_file_location("version_reference_check", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_fixture(tmp_path: Path, version: str, overrides: dict[str, str] | None = None) -> None:
    overrides = overrides or {}
    (tmp_path / "pyproject.toml").write_text(
        f'[project]\nname = "storageops"\nversion = "{version}"\n', encoding="utf-8"
    )
    (tmp_path / "skill-registry.yaml").write_text(
        f"# StorageOps Skill Registry v{overrides.get('registry', version)}\n",
        encoding="utf-8",
    )
    docs = tmp_path / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "ARCHITECTURE.md").write_text(
        f"# Architecture\n\nStorageOps v{overrides.get('arch', version)} is a Pi Coding Agent extension.\n",
        encoding="utf-8",
    )
    (docs / "cli-reference.md").write_text(
        f"StorageOps v{overrides.get('cli', version)} (pi: 1.2.3)\n",
        encoding="utf-8",
    )
    (tmp_path / "CHANGELOG.md").write_text(
        f"## v{overrides.get('changelog', version)} - 2026-06-19\n\n- changes\n",
        encoding="utf-8",
    )


def test_consistent_versions_pass(tmp_path, monkeypatch, capsys):
    mod = load_module()
    build_fixture(tmp_path, "2.5.0")
    monkeypatch.setattr(mod, "ROOT", tmp_path)

    assert mod.main() == 0
    out = capsys.readouterr().out
    assert "passed" in out
    assert "2.5.0" in out


def test_mismatched_changelog_flagged(tmp_path, monkeypatch, capsys):
    mod = load_module()
    build_fixture(tmp_path, "2.5.0", overrides={"changelog": "2.4.0"})
    monkeypatch.setattr(mod, "ROOT", tmp_path)

    assert mod.main() == 1
    out = capsys.readouterr().out
    assert "CHANGELOG.md" in out
    assert "v2.4.0" in out
    assert "expected v2.5.0" in out


def test_mismatched_docs_flagged(tmp_path, monkeypatch, capsys):
    mod = load_module()
    build_fixture(tmp_path, "2.5.0", overrides={"arch": "1.0.0", "cli": "1.0.0"})
    monkeypatch.setattr(mod, "ROOT", tmp_path)

    assert mod.main() == 1
    out = capsys.readouterr().out
    assert "docs/ARCHITECTURE.md" in out
    assert "docs/cli-reference.md" in out


def test_missing_version_reference_flagged(tmp_path, monkeypatch, capsys):
    mod = load_module()
    build_fixture(tmp_path, "2.5.0")
    # Clobber the changelog so its pattern no longer matches.
    (tmp_path / "CHANGELOG.md").write_text("No version header here.\n", encoding="utf-8")
    monkeypatch.setattr(mod, "ROOT", tmp_path)

    assert mod.main() == 1
    out = capsys.readouterr().out
    assert "no version reference found" in out


def test_missing_pyproject_version_fails(tmp_path, monkeypatch, capsys):
    mod = load_module()
    build_fixture(tmp_path, "2.5.0")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")
    monkeypatch.setattr(mod, "ROOT", tmp_path)

    assert mod.main() == 1
    err = capsys.readouterr().err
    assert "could not read version from pyproject.toml" in err
