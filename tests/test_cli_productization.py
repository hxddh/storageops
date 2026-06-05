import json
import subprocess

import storageops_cli
from storageops_cli import _default_model_label


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

    assert storageops_cli.cmd_doctor() == 0
    output = capsys.readouterr().out
    assert "newer Pi 0.78.1" in output
    assert "npm install -g @earendil-works/pi-coding-agent" in output


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
