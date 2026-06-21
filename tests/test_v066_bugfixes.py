"""Regression tests for the v0.6.6 correctness fixes in the deterministic helpers.

Each test pins a bug found in the v0.6.6 bug-hunt so it cannot silently return.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(rel: str, name: str):
    p = ROOT / rel
    spec = importlib.util.spec_from_file_location(name, p)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# --- #1 throttle_tuning_recommender.parse_size: decimal vs binary units --------
def test_throttle_parse_size_decimal_vs_binary():
    t = _load("skills/storageops-performance-diagnosis/scripts/throttle_tuning_recommender.py", "thr")
    assert t.parse_size("64MB") == 64_000_000
    assert t.parse_size("64MiB") == 67_108_864
    assert t.parse_size("2GB") == 2_000_000_000
    assert t.parse_size("1KB") == 1000
    assert t.parse_size("1KiB") == 1024
    assert t.parse_size("1048576") == 1_048_576  # raw bytes unchanged


# --- #2 small_object_analyzer._min_billable: GLACIER IR spelling variants ------
def test_small_object_glacier_ir_spellings():
    s = _load("skills/storageops-lifecycle-cost/scripts/small_object_analyzer.py", "soa")
    assert s._min_billable("GLACIER_IR") == 128 << 10
    assert s._min_billable("GLACIER IR") == 128 << 10
    assert s._min_billable("Glacier Instant Retrieval") == 128 << 10
    assert s._min_billable("glacier-ir") == 128 << 10
    assert s._min_billable("GLACIER") == 40 << 10  # plain Glacier unchanged


# --- #3 cross_account_access_validator: Deny via NotAction must not be dropped --
def test_cross_account_deny_notaction_blocks():
    m = _load("skills/storageops-security-iam-policy/scripts/cross_account_access_validator.py", "cav")
    idp = {"Statement": [
        {"Effect": "Allow", "Action": "s3:*", "Resource": "*"},
        {"Effect": "Deny", "NotAction": "s3:GetObject", "Resource": "*"},
    ]}
    r = m.validate("arn:aws:iam::111:user/a", "s3:PutObject", "arn:aws:s3:::b/k", idp, None)
    idlink = next(l for l in r["links"] if l["link"] == "identity_policy")
    assert idlink["result"] == "explicit_deny"
    assert any("inverted" in q for q in r["open_questions"])
    # The excluded action is still allowed.
    r2 = m.validate("arn:aws:iam::111:user/a", "s3:GetObject", "arn:aws:s3:::b/k", idp, None)
    assert next(l for l in r2["links"] if l["link"] == "identity_policy")["result"] == "allow"


# --- #4 migration_cost_estimator: total_size_bytes="0" must fall back to GB -----
def test_migration_zero_bytes_falls_back(tmp_path):
    m = _load("skills/storageops-migration-sync/scripts/migration_cost_estimator.py", "mce")
    row = {"object_count": "10", "total_size_bytes": "0", "total_size_gb": "500", "bandwidth_mbps": "1000"}
    assert m._resolve_total_bytes(row) == 500 * 1e9
    # explicit 0 with no other size still resolves to 0, not an error
    assert m._resolve_total_bytes({"total_size_bytes": "0"}) == 0


# --- #7 migration_cost_estimator: bad I/O yields the JSON error envelope --------
def test_migration_bad_input_envelope(capsys, monkeypatch):
    m = _load("skills/storageops-migration-sync/scripts/migration_cost_estimator.py", "mce2")
    monkeypatch.setattr("sys.argv", ["x", "--file", "/no/such/file.csv"])
    m.main()
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and "error" in out


# --- #5 notification_target_policy_validator: wildcard principal permits delivery
def test_notification_wildcard_principal_permits():
    m = _load("skills/storageops-event-notification/scripts/notification_target_policy_validator.py", "ntp")
    policy = {"Statement": [{"Effect": "Allow", "Principal": "*", "Action": "lambda:InvokeFunction"}]}
    r = m.validate(policy, "lambda", None)
    assert r["policy_ok"] is True
    assert "over-broad" in r["recommendation"]


# --- #8 lifecycle_rule_simulator: same-day expire precedes transition -----------
def test_lifecycle_same_day_expire_precedence():
    m = _load("skills/storageops-lifecycle-cost/scripts/lifecycle_rule_simulator.py", "lrs")
    events = [(30, "transition", "GLACIER"), (30, "expire", None), (10, "transition", "STANDARD_IA")]
    events.sort(key=lambda e: (e[0], 0 if e[1] == "expire" else 1))
    same_day = [e for e in events if e[0] == 30]
    assert same_day[0][1] == "expire"  # expire sorts first on the tie


# --- #6 parse_sigv4_error: short fragment must not mislabel payload_hash --------
def test_sigv4_short_fragment_no_payload_hash():
    m = _load("skills/storageops-s3-protocol-compatibility/scripts/parse_sigv4_error.py", "psv")
    short = m._canonical_summary("GET\n/path\n")
    assert "payload_hash" not in short
    full = m._canonical_summary("GET\n/path\n\nhost;x-amz-date\n\nhost;x-amz-date\nABCDEF")
    assert full.get("payload_hash") == "ABCDEF"
