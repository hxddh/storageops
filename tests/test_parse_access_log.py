import importlib.util
import sys
from pathlib import Path


def load_parser():
    root = Path(__file__).resolve().parents[1]
    module_path = root / "skills" / "storageops-access-log-analysis" / "scripts" / "parse_access_log.py"
    spec = importlib.util.spec_from_file_location("parse_access_log", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


S3_OK = (
    'owner1 mybucket [06/Feb/2019:00:00:38 +0000] 192.0.2.3 requesterA '
    '3E57427F33A59F07 REST.GET.OBJECT photos/p.jpg "GET /photos/p.jpg HTTP/1.1" '
    '200 - 3914 3914 18 17 "-" "S3Console/0.4" -'
)
S3_DENIED = (
    'owner1 mybucket [06/Feb/2019:00:01:00 +0000] 192.0.2.4 requesterB '
    '3E57427F33A59F08 REST.GET.OBJECT photos/q.jpg "GET /photos/q.jpg HTTP/1.1" '
    '403 AccessDenied 0 0 - - "-" "aws-cli/2.0" -'
)


def test_detect_provider_by_format():
    parser = load_parser()
    assert parser.detect_provider('{"time": "2024"}') == "oss"
    assert parser.detect_provider("[06/Feb/2019:00:00:38 +0000] rest") == "s3"
    assert parser.detect_provider("just some random text") == "unknown"


def test_parse_s3_log_aggregates_status_and_errors():
    parser = load_parser()
    result = parser.parse_s3_log([S3_OK, S3_DENIED])

    assert result["ok"] is True
    details = result["details"]
    assert details["count"] == 2
    assert details["status_distribution"]["2xx"] == 1
    assert details["status_distribution"]["4xx"] == 1
    assert details["error_rate"] == 0.5
    assert details["top_operation"] == "REST.GET.OBJECT"
    assert any(sample["code"] == "AccessDenied" for sample in details["error_samples"])


def test_parse_s3_log_skips_malformed_lines():
    parser = load_parser()
    result = parser.parse_s3_log(["too few fields", "# comment", S3_OK])

    assert result["details"]["count"] == 1


def test_parse_s3_log_surfaces_skipped_and_parsed_counts():
    parser = load_parser()
    result = parser.parse_s3_log(["too few fields", "# comment", S3_OK, S3_DENIED])

    details = result["details"]
    # "# comment" and blank lines are not counted as skipped; only unparseable
    # data lines (too few fields) are.
    assert details["skipped_lines"] == 1
    assert details["parsed_lines"] == 2
    assert details["count"] == 2
