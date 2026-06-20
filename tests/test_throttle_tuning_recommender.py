import importlib.util
from pathlib import Path


def load_recommender():
    root = Path(__file__).resolve().parents[1]
    module_path = (
        root / "skills" / "storageops-performance-diagnosis"
        / "scripts" / "throttle_tuning_recommender.py"
    )
    spec = importlib.util.spec_from_file_location("throttle_tuning_recommender", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_high_throttle_rate_reduces_concurrency():
    mod = load_recommender()
    result = mod.recommend(throttle_rate=0.20, concurrency=32)
    assert result["ok"] is True
    # 20% throttle, 1% target -> roughly 1/20th of the concurrency.
    assert result["safe_concurrency"] < 32
    assert result["safe_concurrency"] >= 1
    assert result["expected_throttle_rate"] <= 0.20


def test_xy_rate_parsing():
    mod = load_recommender()
    assert abs(mod.parse_rate("7/500") - 7 / 500) < 1e-9
    assert abs(mod.parse_rate("5%") - 0.05) < 1e-9
    assert abs(mod.parse_rate("0.05") - 0.05) < 1e-9
    # End-to-end: "X/Y" form flows through recommend cleanly.
    result = mod.recommend(throttle_rate=mod.parse_rate("16/320"), concurrency=32)
    assert result["ok"] is True


def test_invalid_and_empty_input_emit_ok_false(capsys):
    import json
    mod = load_recommender()

    # Parse helpers reject empty/invalid input by raising (caught by main()).
    for bad in ["", "abc", "5/0", "1.5"]:
        try:
            mod.parse_rate(bad)
            raised = False
        except ValueError:
            raised = True
        assert raised, f"expected ValueError for rate {bad!r}"

    # CLI main returns ok:false JSON (never a traceback) on bad input.
    import sys
    argv = sys.argv
    try:
        sys.argv = ["prog", "--throttle-rate", "", "--concurrency", "8"]
        code = mod.main()
    finally:
        sys.argv = argv
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["ok"] is False
    assert code == 1


def test_backoff_fields_present_and_monotonic():
    mod = load_recommender()
    result = mod.recommend(throttle_rate=0.05, concurrency=32)
    for field in ("backoff_base_ms", "backoff_max_ms", "jitter", "safe_concurrency"):
        assert field in result
    assert result["jitter"] == "full"
    assert result["backoff_base_ms"] <= result["backoff_max_ms"]
    assert result["backoff_base_ms"] >= 1
