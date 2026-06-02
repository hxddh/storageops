import json

import pytest

import storageops_cli
from storageops_cli import _ensure_pi, _merge_settings, _merge_skill_paths


def test_merge_skill_paths_preserves_existing_and_appends_required():
    assert _merge_skill_paths(["../custom", "../skills"], ["../skills", "../ops"]) == [
        "../custom",
        "../skills",
        "../ops",
    ]


def test_merge_skill_paths_ignores_invalid_values():
    assert _merge_skill_paths("../custom", ["../skills", 42, None]) == ["../skills"]


def test_merge_settings_preserves_existing_pi_skill_paths(tmp_path):
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    settings_path = agent_dir / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "skills": ["../custom-skills", "../skills"],
                "enableSkillCommands": False,
                "theme": "dark",
            }
        )
    )

    _merge_settings(agent_dir, {"skills": ["../skills"], "enableSkillCommands": True})

    merged = json.loads(settings_path.read_text())
    assert merged["skills"] == ["../custom-skills", "../skills"]
    assert merged["enableSkillCommands"] is True
    assert merged["theme"] == "dark"
    assert (agent_dir / "settings.json.storageops-backup").exists()


def test_merge_settings_adds_storageops_skills_when_missing(tmp_path):
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    settings_path = agent_dir / "settings.json"
    settings_path.write_text(json.dumps({"skills": ["../custom-skills"]}))

    _merge_settings(agent_dir, {"skills": ["../skills"], "enableSkillCommands": True})

    merged = json.loads(settings_path.read_text())
    assert merged["skills"] == ["../custom-skills", "../skills"]


def test_ensure_pi_stops_before_deploying_for_old_pi(monkeypatch, capsys):
    monkeypatch.setattr(storageops_cli, "find_pi", lambda: "/tmp/pi")
    monkeypatch.setattr(storageops_cli, "check_pi_version", lambda _exe: (False, "pi 0.77.0"))

    with pytest.raises(SystemExit) as exc:
        _ensure_pi()

    assert exc.value.code == 1
    output = capsys.readouterr().out
    assert "StorageOps cannot run safely" in output
    assert "No files were deployed" in output
    assert "npm update -g @earendil-works/pi-coding-agent" in output


def test_cmd_install_does_not_deploy_files_when_pi_is_too_old(tmp_path, monkeypatch):
    agent_dir = tmp_path / ".storageops" / "agent"
    monkeypatch.setattr(storageops_cli, "AGENT_DIR", agent_dir)
    monkeypatch.setattr(storageops_cli, "ROOT", tmp_path / ".storageops")
    monkeypatch.setattr(storageops_cli, "PI_DEFAULT", tmp_path / ".pi")
    monkeypatch.setattr(storageops_cli, "PI_DEFAULT_AGENT", tmp_path / ".pi" / "agent")
    monkeypatch.setattr(storageops_cli, "find_pi", lambda: "/tmp/pi")
    monkeypatch.setattr(storageops_cli, "check_pi_version", lambda _exe: (False, "pi 0.77.0"))

    with pytest.raises(SystemExit) as exc:
        storageops_cli.cmd_install(force=True)

    assert exc.value.code == 1
    assert not agent_dir.exists()
