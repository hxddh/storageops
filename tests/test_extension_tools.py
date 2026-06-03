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
