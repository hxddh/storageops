from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def load():
    root = Path(__file__).resolve().parents[1]
    p = root / "skills" / "storageops-security-iam-policy" / "scripts" / "cross_account_access_validator.py"
    spec = importlib.util.spec_from_file_location("cross_account_access_validator", p)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


PRINCIPAL = "arn:aws:iam::111111111111:user/alice"
RESOURCE = "arn:aws:s3:::shared-data/report.csv"

IDENTITY_ALLOW = {"Version": "2012-10-17", "Statement": [
    {"Effect": "Allow", "Action": "s3:GetObject", "Resource": "arn:aws:s3:::shared-data/*"}]}
IDENTITY_NOALLOW = {"Version": "2012-10-17", "Statement": [
    {"Effect": "Allow", "Action": "s3:ListAllMyBuckets", "Resource": "*"}]}
BUCKET_ALLOW = {"Version": "2012-10-17", "Statement": [
    {"Sid": "Cross", "Effect": "Allow", "Principal": {"AWS": "arn:aws:iam::111111111111:root"},
     "Action": ["s3:GetObject", "s3:ListBucket"],
     "Resource": ["arn:aws:s3:::shared-data", "arn:aws:s3:::shared-data/*"]}]}


def test_missing_identity_allow_blocks_at_identity():
    m = load()
    r = m.validate(PRINCIPAL, "s3:GetObject", RESOURCE, IDENTITY_NOALLOW, BUCKET_ALLOW,
                   resource_account="222222222222")
    assert r["decision"] == "deny"
    assert r["blocked_at"] == "identity_policy"
    assert r["cross_account"] is True


def test_both_allow_is_allow():
    m = load()
    r = m.validate(PRINCIPAL, "s3:GetObject", RESOURCE, IDENTITY_ALLOW, BUCKET_ALLOW)
    assert r["decision"] == "allow"
    assert r["ok"] is True
    assert r["blocked_at"] is None


def test_bucket_missing_principal_blocks_at_resource():
    m = load()
    other_bucket = {"Version": "2012-10-17", "Statement": [
        {"Effect": "Allow", "Principal": {"AWS": "arn:aws:iam::999999999999:root"},
         "Action": "s3:GetObject", "Resource": "arn:aws:s3:::shared-data/*"}]}
    r = m.validate(PRINCIPAL, "s3:GetObject", RESOURCE, IDENTITY_ALLOW, other_bucket)
    assert r["decision"] == "deny"
    assert r["blocked_at"] == "resource_policy"


def test_explicit_deny_wins():
    m = load()
    deny_bucket = {"Version": "2012-10-17", "Statement": [
        {"Effect": "Allow", "Principal": {"AWS": "arn:aws:iam::111111111111:root"},
         "Action": "s3:GetObject", "Resource": "arn:aws:s3:::shared-data/*"},
        {"Sid": "DenyAll", "Effect": "Deny", "Principal": "*",
         "Action": "s3:GetObject", "Resource": "arn:aws:s3:::shared-data/*"}]}
    r = m.validate(PRINCIPAL, "s3:GetObject", RESOURCE, IDENTITY_ALLOW, deny_bucket)
    assert r["decision"] == "deny"
    assert r["blocked_at"] == "resource_policy"
    assert any(l["result"] == "explicit_deny" for l in r["links"])


def test_not_provided_identity_is_indeterminate():
    m = load()
    r = m.validate(PRINCIPAL, "s3:GetObject", RESOURCE, None, BUCKET_ALLOW)
    assert r["decision"] == "indeterminate"
    assert "identity_policy" in r["summary"]


def test_kms_missing_blocks_at_kms():
    m = load()
    kms_noallow = {"Version": "2012-10-17", "Statement": [
        {"Effect": "Allow", "Principal": {"AWS": "arn:aws:iam::222222222222:root"},
         "Action": "kms:Decrypt", "Resource": "*"}]}
    r = m.validate(PRINCIPAL, "s3:GetObject", RESOURCE, IDENTITY_ALLOW, BUCKET_ALLOW,
                   kms_key_policy=kms_noallow)
    assert r["decision"] == "deny"
    assert r["blocked_at"] == "kms_key_policy"


def test_same_account_not_cross():
    m = load()
    same_principal = "arn:aws:iam::222222222222:user/bob"
    same_bucket = {"Version": "2012-10-17", "Statement": [
        {"Effect": "Allow", "Principal": {"AWS": "arn:aws:iam::222222222222:root"},
         "Action": "s3:GetObject", "Resource": "arn:aws:s3:::shared-data/*"}]}
    r = m.validate(same_principal, "s3:GetObject", RESOURCE, IDENTITY_ALLOW, same_bucket)
    assert r["cross_account"] is False
    assert r["decision"] == "allow"


def test_cli_malformed_policy_emits_ok_false(tmp_path, capsys):
    m = load()
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    rc = m.main(["--principal-arn", PRINCIPAL, "--action", "s3:GetObject",
                 "--resource", RESOURCE, "--identity-policy", str(bad)])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False
    assert "error" in out
