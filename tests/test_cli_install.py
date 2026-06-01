import json

from storageops_cli import _merge_settings, _merge_skill_paths


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
