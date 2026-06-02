from __future__ import annotations

import importlib.util
from pathlib import Path


def load_scope_checker():
    root = Path(__file__).resolve().parents[1]
    module_path = root / "scripts" / "reference_scope_check.py"
    spec = importlib.util.spec_from_file_location("reference_scope_check", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_current_cli_references_have_scope_and_verification():
    checker = load_scope_checker()
    assert checker.main() == 0


def test_reference_scope_gate_rejects_missing_sections(tmp_path, monkeypatch):
    checker = load_scope_checker()
    cli_refs = tmp_path / "skills" / "storageops-cli-sdk-diagnosis" / "references"
    cli_refs.mkdir(parents=True)
    (cli_refs / "tool.md").write_text("# tool\n\n## Scope\n\nOnly scope.\n", encoding="utf-8")
    monkeypatch.setattr(checker, "ROOT", tmp_path)
    monkeypatch.setattr(checker, "CLI_REFS", cli_refs)

    assert checker.main() == 1


def test_reference_scope_gate_rejects_denylisted_bce_paths(tmp_path, monkeypatch):
    checker = load_scope_checker()
    cli_refs = tmp_path / "skills" / "storageops-cli-sdk-diagnosis" / "references"
    cli_refs.mkdir(parents=True)
    (cli_refs / "tool.md").write_text(
        "# tool\n\n## Scope\n\nTool only.\n\n## Verify Before Applying\n\nCheck version.\n",
        encoding="utf-8",
    )
    other_ref = tmp_path / "skills" / "storageops-security-iam-policy" / "references"
    other_ref.mkdir(parents=True)
    (other_ref / "bad.md").write_text("Check ~/.bce/credentials\n", encoding="utf-8")
    monkeypatch.setattr(checker, "ROOT", tmp_path)
    monkeypatch.setattr(checker, "CLI_REFS", cli_refs)

    assert checker.main() == 1
