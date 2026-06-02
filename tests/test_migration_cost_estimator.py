import importlib.util
from pathlib import Path


def load_estimator():
    root = Path(__file__).resolve().parents[1]
    module_path = root / "skills" / "storageops-migration-sync" / "scripts" / "migration_cost_estimator.py"
    spec = importlib.util.spec_from_file_location("migration_cost_estimator", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_cloud_egress_requires_override_for_complete_cost():
    estimator = load_estimator()
    result = estimator.estimate(
        {
            "object_count": 1000,
            "total_size_gb": 100,
            "bandwidth_mbps": 1000,
            "source_provider": "aws_s3",
            "dest_provider": "gcs",
        }
    )

    assert result["summary"]["cost_complete"] is False
    assert result["details"]["source_egress_per_gb"] is None
    assert result["details"]["source_egress_cost"] is None
    assert result["summary"]["pricing_warnings"]


def test_zero_bandwidth_returns_error_not_crash():
    estimator = load_estimator()
    result = estimator.estimate(
        {
            "object_count": 1000,
            "total_size_gb": 100,
            "bandwidth_mbps": 0,
            "source_provider": "aws_s3",
            "dest_provider": "gcs",
        }
    )

    assert result["ok"] is False
    assert "bandwidth_mbps" in result["error"]


def test_egress_override_makes_cost_complete():
    estimator = load_estimator()
    result = estimator.estimate(
        {
            "object_count": 1000,
            "total_size_gb": 100,
            "bandwidth_mbps": 1000,
            "source_provider": "aws_s3",
            "dest_provider": "gcs",
            "source_egress_per_gb": 0.09,
        }
    )

    assert result["summary"]["cost_complete"] is True
    assert result["details"]["source_egress_cost"] == 9.0
    assert result["summary"]["total_cost_usd"] > 9.0
