"""
Tests verifying that configuration files match the expected post-Pi-migration schema.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PI_SETTINGS = REPO_ROOT / ".pi" / "settings.json"
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"


# ── .pi/settings.json ────────────────────────────────────────────────


def test_pi_settings_exists():
    assert PI_SETTINGS.exists(), ".pi/settings.json must exist"


def test_pi_settings_skills_is_list():
    data = json.loads(PI_SETTINGS.read_text())
    assert isinstance(data.get("skills"), list), (
        "skills must be a top-level list, not a nested object"
    )


def test_pi_settings_skills_contains_agents_path():
    data = json.loads(PI_SETTINGS.read_text())
    skills = data.get("skills", [])
    assert "../agents/skills" in skills, (
        "skills must include '../agents/skills' (relative to .pi directory)"
    )


def test_pi_settings_enable_skill_commands():
    data = json.loads(PI_SETTINGS.read_text())
    assert data.get("enableSkillCommands") is True, (
        "enableSkillCommands must be true"
    )


def test_pi_settings_no_old_schema():
    data = json.loads(PI_SETTINGS.read_text())
    assert not isinstance(data.get("skills"), dict), (
        "skills must not be a nested object (old schema)"
    )
    assert "commands_enabled" not in data, (
        "commands_enabled is the old schema key; use enableSkillCommands"
    )


# ── CLAUDE.md ────────────────────────────────────────────────────────


def test_claude_md_exists():
    assert CLAUDE_MD.exists(), "CLAUDE.md must exist"


def test_claude_md_imports_agents_md():
    content = CLAUDE_MD.read_text()
    assert "@AGENTS.md" in content, "CLAUDE.md must import AGENTS.md with @AGENTS.md"


def test_claude_md_does_not_describe_stale_byok_provider():
    content = CLAUDE_MD.read_text()
    stale_phrases = [
        "ANTHROPIC_API_KEY / STORAGEOPS_LLM_KEY",
        "~/.storageops/config.yaml",
        "llm_key",
        "Supported providers: `anthropic`, `openai`",
        "Prompt caching is enabled for Anthropic",
    ]
    for phrase in stale_phrases:
        assert phrase not in content, (
            f"CLAUDE.md must not describe stale BYOK provider architecture: {phrase!r}"
        )


def test_claude_md_does_not_describe_native_react_loop():
    content = CLAUDE_MD.read_text()
    assert "ReAct loop" not in content or "Pi" in content, (
        "CLAUDE.md must not describe the native ReAct loop as the active runtime"
    )
    assert "run_llm_agent()" not in content, (
        "CLAUDE.md must not reference run_llm_agent() as active code"
    )
    assert "run_supervisor_agent()" not in content, (
        "CLAUDE.md must not reference run_supervisor_agent() as active code"
    )


def test_claude_md_under_200_lines():
    lines = CLAUDE_MD.read_text().splitlines()
    assert len(lines) <= 200, f"CLAUDE.md must be <= 200 lines, got {len(lines)}"


# ── CLI availability without Pi ───────────────────────────────────────


@pytest.mark.parametrize("subcommand", ["triage", "analyze", "report", "eval", "agent"])
def test_cli_help_works_without_pi(subcommand: str, tmp_path: Path):
    env = {"PYTHONPATH": str(REPO_ROOT / "storageops-cli")}
    import os
    full_env = {**os.environ, **env}
    proc = subprocess.run(
        [sys.executable, "-m", "storageops.cli", subcommand, "--help"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=10,
        env=full_env,
    )
    assert proc.returncode == 0, (
        f"storageops {subcommand} --help failed:\n{proc.stderr}"
    )
