import json
import hashlib

import pytest

import storageops_cli
from storageops_cli import (
    MIN_NODE_VERSION,
    _configured_key_source,
    _ensure_httpmon,
    _ensure_pi,
    _inject_auth_env,
    _merge_settings,
    _merge_skill_paths,
    _node_too_old,
    _parse_version_triple,
    _resolve_api_key_entry,
)


def test_parse_version_triple():
    assert _parse_version_triple("v22.19.0") == (22, 19, 0)
    assert _parse_version_triple("v20.10.5") == (20, 10, 5)
    assert _parse_version_triple("garbage") is None


def test_min_node_threshold():
    # Pi 0.78+ needs Node >= 22.19.0; older must be rejected, equal/newer accepted.
    assert (20, 10, 0) < MIN_NODE_VERSION
    assert (22, 18, 9) < MIN_NODE_VERSION
    assert (22, 19, 0) >= MIN_NODE_VERSION
    assert (24, 0, 0) >= MIN_NODE_VERSION


def test_node_too_old_uses_threshold(monkeypatch):
    monkeypatch.setattr(storageops_cli, "_node_version", lambda: (20, 10, 0))
    assert _node_too_old() == (True, "20.10.0")
    monkeypatch.setattr(storageops_cli, "_node_version", lambda: (22, 19, 0))
    assert _node_too_old() == (False, "22.19.0")
    monkeypatch.setattr(storageops_cli, "_node_version", lambda: None)
    assert _node_too_old() == (False, "not found")


def _clear_all_provider_env(monkeypatch):
    for var in ["DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY",
                "GEMINI_API_KEY", "MISTRAL_API_KEY", "GROQ_API_KEY", "CEREBRAS_API_KEY"]:
        monkeypatch.delenv(var, raising=False)


def test_key_source_detects_api_key_file_without_env(tmp_path, monkeypatch):
    # The exact bug a real host surfaced: install summary said "not configured"
    # even though an api-key file was present and diagnoses worked.
    _clear_all_provider_env(monkeypatch)
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    (agent_dir / "api-key").write_text("sk-something\n")

    assert _configured_key_source(agent_dir) == "api-key file"


def test_key_source_detects_env_and_authjson(tmp_path, monkeypatch):
    _clear_all_provider_env(monkeypatch)
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-x")
    assert _configured_key_source(agent_dir) == "env (ANTHROPIC_API_KEY)"

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    (agent_dir / "auth.json").write_text(json.dumps({"deepseek": {"apiKey": "sk-d"}}))
    assert _configured_key_source(agent_dir) == "auth.json (deepseek)"


def test_key_source_none_when_unconfigured(tmp_path, monkeypatch):
    _clear_all_provider_env(monkeypatch)
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    assert _configured_key_source(agent_dir) is None


def test_resolve_api_key_entry_routes_known_provider_prefixes():
    assert _resolve_api_key_entry("anthropic:sk-ant-xyz") == ("ANTHROPIC_API_KEY", "sk-ant-xyz")
    assert _resolve_api_key_entry("openai:sk-proj-xyz") == ("OPENAI_API_KEY", "sk-proj-xyz")
    assert _resolve_api_key_entry("gemini:AIzaXYZ") == ("GEMINI_API_KEY", "AIzaXYZ")
    assert _resolve_api_key_entry("groq:gsk_xyz") == ("GROQ_API_KEY", "gsk_xyz")


def test_resolve_api_key_entry_without_known_prefix_is_unrouted():
    # Bare key -> no provider, caller applies the default fallback.
    assert _resolve_api_key_entry("sk-deepseekkey") == (None, "sk-deepseekkey")
    # Unknown prefix is not treated as a provider; the whole value stays the key.
    assert _resolve_api_key_entry("notaprovider:abc") == (None, "notaprovider:abc")


def _clear_provider_env(monkeypatch):
    for var in ("DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(var, raising=False)


def test_inject_auth_env_routes_explicit_provider(tmp_path, monkeypatch):
    _clear_provider_env(monkeypatch)
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    (agent_dir / "api-key").write_text("anthropic:sk-ant-zzz\n")

    _inject_auth_env(agent_dir)

    import os

    assert os.environ.get("ANTHROPIC_API_KEY") == "sk-ant-zzz"
    assert "DEEPSEEK_API_KEY" not in os.environ


def test_inject_auth_env_unprefixed_key_falls_back_to_deepseek(tmp_path, monkeypatch):
    _clear_provider_env(monkeypatch)
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    (agent_dir / "api-key").write_text("sk-plainkey\n")

    _inject_auth_env(agent_dir)

    import os

    assert os.environ.get("DEEPSEEK_API_KEY") == "sk-plainkey"


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
    monkeypatch.setattr(storageops_cli, "_node_version", lambda: (22, 19, 0))  # node OK

    with pytest.raises(SystemExit) as exc:
        _ensure_pi()

    assert exc.value.code == 1
    output = capsys.readouterr().out
    assert "StorageOps cannot run safely" in output
    assert "No files were deployed" in output
    assert "npm install -g @earendil-works/pi-coding-agent" in output


def test_ensure_pi_blocks_on_old_node_before_npm_install(monkeypatch, capsys):
    # pi not found + Node too old -> stop with an actionable Node message instead
    # of npm-installing a legacy Pi that gets rejected.
    monkeypatch.setattr(storageops_cli, "find_pi", lambda: "pi")
    monkeypatch.setattr(storageops_cli, "check_pi_version", lambda _exe: (False, "not found"))
    monkeypatch.setattr(storageops_cli.shutil, "which", lambda name: "/usr/bin/npm")
    monkeypatch.setattr(storageops_cli, "_node_version", lambda: (20, 10, 0))

    with pytest.raises(SystemExit) as exc:
        _ensure_pi()

    assert exc.value.code == 1
    output = capsys.readouterr().out
    assert "Node.js 20.10.0 is too old" in output
    assert "22.19" in output


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
    monkeypatch.setattr(storageops_cli, "_ensure_httpmon", lambda: None)
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
    monkeypatch.setattr(storageops_cli, "_ensure_httpmon", lambda: None)
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


def test_ensure_httpmon_downloads_managed_binary(tmp_path, monkeypatch):
    payload = b"fake-httpmon-binary"
    sha = hashlib.sha256(payload).hexdigest()

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return payload

    monkeypatch.setattr(storageops_cli, "ROOT", tmp_path / ".storageops")
    monkeypatch.setattr(storageops_cli, "BIN_DIR", tmp_path / ".storageops" / "bin")
    monkeypatch.setattr(storageops_cli.shutil, "which", lambda _name: None)
    monkeypatch.setattr(storageops_cli, "_httpmon_asset_for_platform", lambda: ("httpmon-test", sha))
    monkeypatch.setattr(storageops_cli, "_read_bundled_httpmon", lambda _asset_name: None)
    monkeypatch.setattr(storageops_cli.urllib.request, "urlopen", lambda *_args, **_kwargs: FakeResponse())

    installed = _ensure_httpmon()

    target = tmp_path / ".storageops" / "bin" / "httpmon"
    assert installed == str(target)
    assert target.read_bytes() == payload
    assert target.stat().st_mode & 0o111


def test_ensure_httpmon_prefers_bundled_binary(tmp_path, monkeypatch):
    payload = b"bundled-httpmon-binary"
    sha = hashlib.sha256(payload).hexdigest()

    def fail_urlopen(*_args, **_kwargs):
        raise AssertionError("bundled httpmon should avoid network download")

    monkeypatch.setattr(storageops_cli, "ROOT", tmp_path / ".storageops")
    monkeypatch.setattr(storageops_cli, "BIN_DIR", tmp_path / ".storageops" / "bin")
    monkeypatch.setattr(storageops_cli.shutil, "which", lambda _name: None)
    monkeypatch.setattr(storageops_cli, "_httpmon_asset_for_platform", lambda: ("httpmon-test", sha))
    monkeypatch.setattr(storageops_cli, "_read_bundled_httpmon", lambda _asset_name: payload)
    monkeypatch.setattr(storageops_cli.urllib.request, "urlopen", fail_urlopen)

    installed = _ensure_httpmon()

    target = tmp_path / ".storageops" / "bin" / "httpmon"
    assert installed == str(target)
    assert target.read_bytes() == payload
    assert target.stat().st_mode & 0o111


def test_ensure_httpmon_rejects_checksum_mismatch(tmp_path, monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b"tampered"

    monkeypatch.setattr(storageops_cli, "ROOT", tmp_path / ".storageops")
    monkeypatch.setattr(storageops_cli, "BIN_DIR", tmp_path / ".storageops" / "bin")
    monkeypatch.setattr(storageops_cli.shutil, "which", lambda _name: None)
    monkeypatch.setattr(storageops_cli, "_httpmon_asset_for_platform", lambda: ("httpmon-test", "0" * 64))
    monkeypatch.setattr(storageops_cli, "_read_bundled_httpmon", lambda _asset_name: None)
    monkeypatch.setattr(storageops_cli.urllib.request, "urlopen", lambda *_args, **_kwargs: FakeResponse())

    assert _ensure_httpmon() is None
    assert not (tmp_path / ".storageops" / "bin" / "httpmon").exists()


def test_httpmon_download_uses_bounded_curl_timeout():
    root = storageops_cli.Path(__file__).resolve().parents[1]
    source = (root / "storageops_cli" / "__init__.py").read_text()

    assert '"--max-time"' in source
    assert '"20"' in source
    assert "curl download failed" in source


def test_copy_skills_mirrors_bundle_and_removes_stale(tmp_path, monkeypatch):
    import storageops_cli
    # Fake package data: skills/storageops-{a,b}
    data = tmp_path / "pkg"
    for name in ("storageops-a", "storageops-b"):
        d = data / "skills" / name
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text("x")
    # Existing deploy: storageops-a (to be refreshed) + storageops-old (stale)
    agent = tmp_path / "agent"
    skills_dst = storageops_cli._skills_dir_for_agent(agent)
    (skills_dst / "storageops-a").mkdir(parents=True)
    (skills_dst / "storageops-old").mkdir(parents=True)
    (skills_dst / "keep-me").mkdir(parents=True)  # non-storageops dir is left alone

    storageops_cli._copy_skills(data, agent)

    present = sorted(d.name for d in skills_dst.iterdir() if d.is_dir())
    assert present == ["keep-me", "storageops-a", "storageops-b"]  # old removed, non-storageops kept


def test_unexpected_skills_reports_stale(tmp_path, monkeypatch):
    import storageops_cli
    data = tmp_path / "pkg"
    (data / "skills" / "storageops-a").mkdir(parents=True)
    monkeypatch.setattr(storageops_cli, "_package_data_dir", lambda: data)
    skills_dir = tmp_path / "deployed"
    (skills_dir / "storageops-a").mkdir(parents=True)
    (skills_dir / "storageops-ghost").mkdir(parents=True)
    assert storageops_cli._unexpected_skills(skills_dir) == ["storageops-ghost"]
