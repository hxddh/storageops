import os
import subprocess
from pathlib import Path


def run_loader(home: Path, profile: str = "default") -> subprocess.CompletedProcess[str]:
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "credential-loader.sh"
    command = (
        f"source {script} aws {profile}; "
        'printf "AK=%s\\nSK=%s\\nTOKEN=%s\\n" '
        '"$AWS_ACCESS_KEY_ID" "$AWS_SECRET_ACCESS_KEY" "$AWS_SESSION_TOKEN"'
    )
    env = {
        **os.environ,
        "HOME": str(home),
        "AWS_ACCESS_KEY_ID": "",
        "AWS_SECRET_ACCESS_KEY": "",
        "AWS_SESSION_TOKEN": "",
        "BOS_ACCESS_KEY": "",
        "BOS_SECRET_KEY": "",
    }
    return subprocess.run(
        ["bash", "-c", command],
        check=True,
        env=env,
        text=True,
        capture_output=True,
        timeout=5,
    )


def test_loader_parses_standard_aws_credentials_without_spaces(tmp_path):
    aws_dir = tmp_path / ".aws"
    aws_dir.mkdir()
    (aws_dir / "credentials").write_text(
        "\n".join(
            [
                "[default]",
                "aws_access_key_id=AKIASTANDARD123456",
                "aws_secret_access_key=standard-secret",
                "aws_session_token=standard-token",
            ]
        )
    )

    result = run_loader(tmp_path)

    assert "AK=AKIASTANDARD123456" in result.stdout
    assert "SK=standard-secret" in result.stdout
    assert "TOKEN=standard-token" in result.stdout


def test_loader_parses_aws_credentials_with_spaces(tmp_path):
    aws_dir = tmp_path / ".aws"
    aws_dir.mkdir()
    (aws_dir / "credentials").write_text(
        "\n".join(
            [
                "[named]",
                "aws_access_key_id = AKIASPACED123456",
                "aws_secret_access_key = spaced-secret",
            ]
        )
    )

    result = run_loader(tmp_path, "named")

    assert "AK=AKIASPACED123456" in result.stdout
    assert "SK=spaced-secret" in result.stdout
