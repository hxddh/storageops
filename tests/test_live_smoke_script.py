import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LIVE_SMOKE = ROOT / "scripts" / "live_smoke.sh"

_STRIP_ENV = (
    "DEEPSEEK_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "STORAGEOPS_MODEL_KEY",
)


def test_live_smoke_script_exists():
    assert LIVE_SMOKE.is_file()


def test_live_smoke_exits_when_live_diagnosis_unavailable(tmp_path):
    """Uses an empty HOME so doctor reports live_diagnosis_available=false."""
    env = {k: v for k, v in os.environ.items() if k not in _STRIP_ENV}
    env["HOME"] = str(tmp_path)
    env["PATH"] = os.environ.get("PATH", "")
    result = subprocess.run(
        ["bash", str(LIVE_SMOKE)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    combined = result.stdout + result.stderr
    assert result.returncode != 0
    assert "Live diagnosis is not available" in combined
