import importlib.util
from pathlib import Path


def load_parser():
    root = Path(__file__).resolve().parents[1]
    module_path = root / "skills" / "storageops-cli-sdk-diagnosis" / "scripts" / "parse_s5cmd_log.py"
    spec = importlib.util.spec_from_file_location("parse_s5cmd_log", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_finished_operations_pair_by_command_not_fifo():
    parser = load_parser()
    result = parser.parse_log(
        [
            "2026/06/02 10:00:00 cp s3://bucket/a.bin /tmp/a.bin started",
            "2026/06/02 10:00:01 cp s3://bucket/b.bin /tmp/b.bin started",
            "2026/06/02 10:00:02 cp s3://bucket/b.bin /tmp/b.bin finished in 1s",
            "2026/06/02 10:00:05 cp s3://bucket/a.bin /tmp/a.bin finished in 5s",
        ]
    )

    operations = result["details"]["operations"]
    assert [op["duration_sec"] for op in operations] == [1, 5]
    assert operations[0]["start"] > operations[1]["start"]


def test_status_code_requires_error_context():
    parser = load_parser()
    result = parser.parse_log(
        [
            "2026/06/02 10:00:00 copied 503 bytes successfully",
            "2026/06/02 10:00:01 ERROR request failed with status 503",
        ]
    )

    assert result["summary"]["error_distribution"] == {503: 1}
