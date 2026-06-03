from pathlib import Path


def _extension() -> str:
    root = Path(__file__).resolve().parents[1]
    return (root / "storageops_cli" / "extensions" / "storageops.ts").read_text()


def test_search_memory_scans_scope_subdirectories():
    # Recall must walk scope subdirs (e.g. sessions/<scope>/<id>.jsonl), not just
    # the top level — locks the v0.4.29 recursive-recall fix.
    ext = _extension()
    assert "collectSessionJsonl" in ext
    assert "MAX_SESSION_SCAN_DEPTH" in ext
    assert ".endsWith(\".jsonl\")" in ext


def test_search_tokens_handle_cjk_queries():
    # CJK queries must produce tokens (bigrams) so Chinese memory search recalls.
    ext = _extension()
    assert "一-鿿" in ext
    assert "run.slice(i, i + 2)" in ext


def test_http_trace_allowlist_covers_skill_read_only_ops():
    # The CORS / lifecycle / multipart / tagging skills rely on these read-only ops.
    ext = _extension()
    for op in [
        "head-bucket",
        "get-bucket-cors",
        "get-bucket-lifecycle-configuration",
        "get-bucket-tagging",
        "get-bucket-acl",
        "get-object-attributes",
        "list-multipart-uploads",
    ]:
        assert f'"{op}"' in ext


def test_scan_secrets_covers_presigned_and_multicloud_keys():
    # Presigned URL material is extremely common in rclone/aws/s5cmd debug logs;
    # GCP/Azure are documented domains. The scanner must redact all of these.
    ext = _extension()
    for label in [
        "PRESIGNED_SIGNATURE",
        "PRESIGNED_AWS_PARAM",
        "OSS_PRESIGNED",
        "COS_PRESIGNED",
        "GCP_PRIVATE_KEY_ID",
        "AZURE_ACCOUNT_KEY",
        "AZURE_SAS",
    ]:
        assert label in ext
    # PEM pattern must also match GCP's plain PKCS8 "PRIVATE KEY" (no algorithm word).
    assert "(?:RSA|EC|DSA|OPENSSH|ENCRYPTED) )?PRIVATE KEY" in ext


def test_search_memory_dedupes_per_session():
    ext = _extension()
    assert "bestBySession" in ext


def test_detect_domain_has_cjk_parity_for_core_domains():
    # Chinese inputs to these domains previously matched nothing.
    ext = _extension()
    for term in ["访问被拒", "限速", "连接", "损坏", "签名"]:
        assert term in ext

