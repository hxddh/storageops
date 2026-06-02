import importlib.util
from pathlib import Path


def load_detector():
    root = Path(__file__).resolve().parents[1]
    module_path = root / "skills" / "storageops-performance-diagnosis" / "scripts" / "throttle_detector.py"
    spec = importlib.util.spec_from_file_location("throttle_detector", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_status_codes_require_throttle_or_error_context():
    detector_module = load_detector()
    detector = detector_module.ThrottleDetector(
        [
            "2026-06-02T10:00:00Z copied 503 bytes successfully",
            "2026-06-02T10:00:01Z HTTP status 503 SlowDown path=/bucket/hot/file",
            "2026-06-02T10:00:02Z request failed with status 429 path=/bucket/hot/file2",
        ]
    )

    detector.scan()
    summary = detector.summary()

    assert summary["status_503"] == 1
    assert summary["status_429"] == 1
    # Two throttle lines: the "503 SlowDown" line carries both a status code and
    # a keyword but is a single event (no double counting).
    assert summary["total_events"] == 2
