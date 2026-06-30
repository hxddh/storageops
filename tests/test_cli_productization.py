import json
import subprocess

import storageops_cli
from storageops_cli import (
    _default_model_label,
    _node_doctor_detail,
    _node_readiness_action,
    _suggest_node_path,
)


def _clear_provider_env(monkeypatch):
    for var in ("DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(var, raising=False)


def _installed_agent(root):
    agent_dir = root / "agent"
    skills = root / "skills"
    (agent_dir / "extensions").mkdir(parents=True)
    (agent_dir / "settings.json").write_text("{}")
    (agent_dir / "extensions" / "storageops.ts").write_text("// ext\n")
    (skills / "storageops-demo").mkdir(parents=True)
    return agent_dir


def test_configure_writes_default_model_and_prefixed_key(tmp_path, monkeypatch):
    root = tmp_path / ".storageops"
    agent_dir = root / "agent"
    monkeypatch.setattr(storageops_cli, "ROOT", root)
    monkeypatch.setattr(storageops_cli, "AGENT_DIR", agent_dir)

    rc = storageops_cli.cmd_configure([
        "--provider", "deepseek",
        "--model", "deepseek-v4-pro",
        "--api-key", "sk-test",
    ])

    assert rc == 0
    settings = json.loads((agent_dir / "settings.json").read_text())
    assert settings["defaultProvider"] == "deepseek"
    assert settings["defaultModel"] == "deepseek-v4-pro"
    assert settings["skills"] == ["../skills"]
    assert (agent_dir / "api-key").read_text().strip() == "deepseek:sk-test"
    assert _default_model_label(agent_dir) == "deepseek/deepseek-v4-pro"


def test_doctor_reports_key_conflict(tmp_path, monkeypatch, capsys):
    root = tmp_path / ".storageops"
    agent_dir = _installed_agent(root)
    (agent_dir / "settings.json").write_text(json.dumps({"defaultProvider": "deepseek", "defaultModel": "deepseek-v4-pro"}))
    (agent_dir / "api-key").write_text("deepseek:sk-file\n")
    for i in range(15):
        (root / "skills" / f"storageops-extra-{i}").mkdir(parents=True)

    monkeypatch.setattr(storageops_cli, "ROOT", root)
    monkeypatch.setattr(storageops_cli, "AGENT_DIR", agent_dir)
    monkeypatch.setattr(storageops_cli, "BIN_DIR", root / "bin")
    monkeypatch.setattr(storageops_cli, "PI_DEFAULT_AGENT", tmp_path / ".pi" / "agent")
    monkeypatch.setattr(storageops_cli, "_package_version", lambda: "0.4.43")
    monkeypatch.setattr(storageops_cli, "_latest_pypi_version", lambda: "0.4.43")
    monkeypatch.setattr(storageops_cli, "_latest_pi_version", lambda: "0.78.0")
    monkeypatch.setattr(storageops_cli, "find_pi", lambda: "/tmp/pi")
    monkeypatch.setattr(storageops_cli, "check_pi_version", lambda _exe: (True, "pi 0.78.0"))
    monkeypatch.setattr(storageops_cli, "_node_version", lambda: (22, 19, 0))
    monkeypatch.setattr(storageops_cli, "find_httpmon", lambda: str(root / "bin" / "httpmon"))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-env")

    assert storageops_cli.cmd_doctor() == 0

    output = capsys.readouterr().out
    assert "StorageOps doctor" in output
    assert "Key conflict" in output
    assert "Default model" in output


def test_latest_pi_version_is_silent_when_skipped(monkeypatch):
    monkeypatch.setenv("STORAGEOPS_SKIP_VERSION_CHECK", "1")
    # Must not hit the network and must never raise.
    assert storageops_cli._latest_pi_version() is None


def test_doctor_hints_when_newer_pi_available(tmp_path, monkeypatch, capsys):
    root = tmp_path / ".storageops"
    agent_dir = _installed_agent(root)
    _clear_provider_env(monkeypatch)

    monkeypatch.setattr(storageops_cli, "ROOT", root)
    monkeypatch.setattr(storageops_cli, "AGENT_DIR", agent_dir)
    monkeypatch.setattr(storageops_cli, "BIN_DIR", root / "bin")
    monkeypatch.setattr(storageops_cli, "PI_DEFAULT_AGENT", tmp_path / ".pi" / "agent")
    monkeypatch.setattr(storageops_cli, "_package_version", lambda: "0.4.49")
    monkeypatch.setattr(storageops_cli, "_latest_pypi_version", lambda: "0.4.49")
    monkeypatch.setattr(storageops_cli, "find_pi", lambda: "/tmp/pi")
    monkeypatch.setattr(storageops_cli, "check_pi_version", lambda _exe: (True, "0.78.0"))
    monkeypatch.setattr(storageops_cli, "_latest_pi_version", lambda: "0.78.1")
    monkeypatch.setattr(storageops_cli, "_node_version", lambda: (22, 19, 0))
    monkeypatch.setattr(storageops_cli, "find_httpmon", lambda: str(root / "bin" / "httpmon"))
    monkeypatch.setattr(storageops_cli, "_configured_key_source", lambda _a: "api-key file")

    assert storageops_cli.cmd_doctor() == 0  # ready (key configured)
    output = capsys.readouterr().out
    assert "newer Pi 0.78.1" in output
    assert "npm install -g @earendil-works/pi-coding-agent" in output


def _ready_doctor_env(tmp_path, monkeypatch, *, key_source="api-key file"):
    """Monkeypatch a fully-ready doctor environment; return the root path."""
    root = tmp_path / ".storageops"
    agent_dir = _installed_agent(root)
    _clear_provider_env(monkeypatch)
    monkeypatch.setattr(storageops_cli, "ROOT", root)
    monkeypatch.setattr(storageops_cli, "AGENT_DIR", agent_dir)
    monkeypatch.setattr(storageops_cli, "BIN_DIR", root / "bin")
    monkeypatch.setattr(storageops_cli, "PI_DEFAULT_AGENT", tmp_path / ".pi" / "agent")
    monkeypatch.setattr(storageops_cli, "_package_version", lambda: "0.4.51")
    monkeypatch.setattr(storageops_cli, "_latest_pypi_version", lambda: "0.4.51")
    monkeypatch.setattr(storageops_cli, "find_pi", lambda: "/tmp/pi")
    monkeypatch.setattr(storageops_cli, "check_pi_version", lambda _exe: (True, "0.78.0"))
    monkeypatch.setattr(storageops_cli, "_latest_pi_version", lambda: "0.78.0")
    monkeypatch.setattr(storageops_cli, "_node_version", lambda: (22, 19, 0))
    monkeypatch.setattr(storageops_cli, "find_httpmon", lambda: str(root / "bin" / "httpmon"))
    monkeypatch.setattr(storageops_cli, "_configured_key_source", lambda _a: key_source)
    return root


def test_doctor_json_is_redacted_and_actionable(tmp_path, monkeypatch, capsys):
    import json as _json
    _ready_doctor_env(tmp_path, monkeypatch)
    monkeypatch.setattr(storageops_cli, "_configured_key_source", lambda _a: "environment variable: DEEPSEEK_API_KEY")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-supersecretvalue-should-not-leak")

    rc = storageops_cli.cmd_doctor(as_json=True)
    out = capsys.readouterr().out
    report = _json.loads(out)

    assert rc == 0 and report["ready"] is True
    assert report["next_action"] == "storageops --print 'hello'"
    assert report["install_mode"] == "independent"
    assert report["api_key_source"] == "environment variable: DEEPSEEK_API_KEY"
    assert report["live_diagnosis_available"] is True
    # The raw key value must never appear in the machine-readable report.
    assert "sk-supersecretvalue-should-not-leak" not in out


def test_doctor_exit_code_reflects_not_ready(tmp_path, monkeypatch, capsys):
    # Installed but no API key configured -> not ready -> exit 1.
    _ready_doctor_env(tmp_path, monkeypatch, key_source=None)
    rc = storageops_cli.cmd_doctor()
    out = capsys.readouterr().out
    assert rc == 1
    assert "Next: storageops configure" in out
    assert "Live diagnosis" in out


def test_doctor_json_live_diagnosis_false_without_key(tmp_path, monkeypatch, capsys):
    _ready_doctor_env(tmp_path, monkeypatch, key_source=None)
    rc = storageops_cli.cmd_doctor(as_json=True)
    report = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert report["live_diagnosis_available"] is False
    assert report["ready"] is False


def test_suggest_node_path_picks_newest_nvm(tmp_path, monkeypatch):
    nvm_root = tmp_path / ".nvm" / "versions" / "node"
    for ver in ("v22.19.0", "v22.22.2", "v20.10.0"):
        bindir = nvm_root / ver / "bin"
        bindir.mkdir(parents=True)
        (bindir / "node").write_text("")
    monkeypatch.setattr(storageops_cli.Path, "home", lambda: tmp_path)
    assert _suggest_node_path() == str(nvm_root / "v22.22.2" / "bin")


def test_doctor_node_detail_includes_path_hint(monkeypatch):
    monkeypatch.setattr(storageops_cli, "_suggest_node_path", lambda: "/opt/node22/bin")
    s = {"node_triple": (22, 14, 0), "node_ok": False}
    detail = _node_doctor_detail(s)
    assert "22.14.0" in detail
    assert "22.19" in detail
    assert 'export PATH="/opt/node22/bin:$PATH"' in detail


def test_node_readiness_action_prefers_nvm_hint(monkeypatch):
    monkeypatch.setattr(storageops_cli, "_suggest_node_path", lambda: "/opt/node22/bin")
    action = _node_readiness_action({"node_ok": False})
    assert action.startswith('export PATH="/opt/node22/bin:$PATH"')


def test_smoke_runs_pi_with_selected_agent_and_model(tmp_path, monkeypatch, capsys):
    root = tmp_path / ".storageops"
    agent_dir = _installed_agent(root)
    (agent_dir / "api-key").write_text("deepseek:sk-file\n")
    calls = {}

    def fake_run(cmd, env, text, capture_output, timeout):
        calls["cmd"] = cmd
        calls["env"] = env
        calls["timeout"] = timeout
        return subprocess.CompletedProcess(cmd, 0, stdout="pong\n", stderr="")

    monkeypatch.setattr(storageops_cli, "ROOT", root)
    monkeypatch.setattr(storageops_cli, "AGENT_DIR", agent_dir)
    monkeypatch.setattr(storageops_cli, "BIN_DIR", root / "bin")
    monkeypatch.setattr(storageops_cli, "PI_DEFAULT_AGENT", tmp_path / ".pi" / "agent")
    monkeypatch.setattr(storageops_cli, "find_pi", lambda: "/tmp/pi")
    monkeypatch.setattr(storageops_cli.subprocess, "run", fake_run)
    _clear_provider_env(monkeypatch)

    rc = storageops_cli.cmd_smoke(["--provider", "deepseek", "--model", "deepseek-v4-pro", "--prompt", "hello", "--timeout", "9"])

    assert rc == 0
    assert calls["cmd"] == ["/tmp/pi", "--provider", "deepseek", "--model", "deepseek-v4-pro", "--print", "hello"]
    assert calls["env"]["PI_CODING_AGENT_DIR"] == str(agent_dir)
    assert calls["env"]["DEEPSEEK_API_KEY"] == "sk-file"
    assert calls["timeout"] == 9
    assert "model smoke succeeded" in capsys.readouterr().out


def test_should_hint_no_key_logic(tmp_path, monkeypatch):
    agent = tmp_path / "agent"
    monkeypatch.setattr(storageops_cli, "_configured_key_source", lambda _a: None)
    # No key, no inline --api-key: hint (including for args-present diagnosis runs).
    assert storageops_cli._should_hint_no_key([], agent) is True
    assert storageops_cli._should_hint_no_key(["diagnose this 403"], agent) is True
    # Inline --api-key suppresses the hint.
    assert storageops_cli._should_hint_no_key(["--api-key", "sk-x", "diagnose"], agent) is False
    # A configured key (any source, e.g. gemini in the api-key file) suppresses it.
    monkeypatch.setattr(storageops_cli, "_configured_key_source", lambda _a: "api-key file")
    assert storageops_cli._should_hint_no_key(["diagnose"], agent) is False


def test_no_key_hint_leads_with_configure(tmp_path, capsys):
    storageops_cli._no_key_hint(tmp_path / "agent")
    out = capsys.readouterr().out
    assert "storageops configure --api-key" in out
    assert "ANTHROPIC_API_KEY" in out
    assert "pi /login" in out
    # The productized command is listed before the raw export.
    assert out.index("storageops configure --api-key") < out.index("export ")
