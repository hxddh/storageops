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


def _make_package_data(tmp_path):
    data = tmp_path / "pkg" / "storageops_cli"
    (data / "extensions").mkdir(parents=True)
    (data / "extensions" / "storageops.ts").write_text("// extension\n")
    skill = data / "skills" / "storageops-demo"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# demo\n")
    return data


def test_cmd_install_warns_when_local_package_is_older_than_pypi(tmp_path, monkeypatch, capsys):
    data = _make_package_data(tmp_path)
    root = tmp_path / ".storageops"
    agent_dir = root / "agent"

    monkeypatch.setattr(storageops_cli, "ROOT", root)
    monkeypatch.setattr(storageops_cli, "AGENT_DIR", agent_dir)
    monkeypatch.setattr(storageops_cli, "PI_DEFAULT", tmp_path / ".pi")
    monkeypatch.setattr(storageops_cli, "PI_DEFAULT_AGENT", tmp_path / ".pi" / "agent")
    monkeypatch.setattr(storageops_cli, "find_pi", lambda: "/tmp/pi")
    monkeypatch.setattr(storageops_cli, "check_pi_version", lambda _exe: (True, "pi 0.78.0"))
    monkeypatch.setattr(storageops_cli, "_package_data_dir", lambda: data)
    monkeypatch.setattr(storageops_cli, "_package_version", lambda: "0.4.18")
    monkeypatch.setattr(storageops_cli, "_latest_pypi_version", lambda: "0.4.19")

    storageops_cli.cmd_install(force=True)

    output = capsys.readouterr().out
    assert "StorageOps package: v0.4.18" in output
    assert "Latest StorageOps on PyPI is v0.4.19" in output
    assert "deploying bundled files from the old local package" in output


def test_cmd_install_writes_install_marker(tmp_path, monkeypatch):
    data = _make_package_data(tmp_path)
    root = tmp_path / ".storageops"
    agent_dir = root / "agent"

    monkeypatch.setattr(storageops_cli, "ROOT", root)
    monkeypatch.setattr(storageops_cli, "AGENT_DIR", agent_dir)
    monkeypatch.setattr(storageops_cli, "PI_DEFAULT", tmp_path / ".pi")
    monkeypatch.setattr(storageops_cli, "PI_DEFAULT_AGENT", tmp_path / ".pi" / "agent")
    monkeypatch.setattr(storageops_cli, "find_pi", lambda: "/tmp/pi")
    monkeypatch.setattr(storageops_cli, "check_pi_version", lambda _exe: (True, "pi 0.78.0"))
    monkeypatch.setattr(storageops_cli, "_package_data_dir", lambda: data)
    monkeypatch.setattr(storageops_cli, "_package_version", lambda: "0.4.20")
    monkeypatch.setattr(storageops_cli, "_latest_pypi_version", lambda: None)

    storageops_cli.cmd_install(force=True)

    marker = json.loads((root / "install.json").read_text())
    assert marker["package_version"] == "0.4.20"
    assert marker["package_path"] == str(data)
    assert marker["target_agent"] == str(agent_dir)
    assert marker["skills_path"] == str(root / "skills")
    assert marker["install_mode"] == "independent"
    assert "installed_at" in marker
