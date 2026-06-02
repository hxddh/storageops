from pathlib import Path


def test_domain_signatures_use_skill_names_and_cover_routing_domains():
    root = Path(__file__).resolve().parents[1]
    extension = (root / "storageops_cli" / "extensions" / "storageops.ts").read_text()

    for skill in [
        "storageops-s3-protocol-compatibility",
        "storageops-bigdata-pipeline",
        "storageops-security-iam-policy",
        "storageops-performance-diagnosis",
        "storageops-network-endpoint-access",
    ]:
        assert f'"{skill}"' in extension

    for signature in ["SignatureDoesNotMatch", "CORS", "Spark", "FileOutputCommitter"]:
        assert signature in extension


def test_domain_confidence_has_single_signal_floor():
    root = Path(__file__).resolve().parents[1]
    extension = (root / "storageops_cli" / "extensions" / "storageops.ts").read_text()

    assert "0.5 + info.score * 0.15" in extension
    assert "recommended_skill: domain" in extension
    assert "signals: info.signals.slice(0, 5)" in extension
    assert "next_action: DOMAIN_NEXT_ACTION[domain]" in extension


def test_secret_scanner_deduplicates_overlapping_matches_by_range():
    root = Path(__file__).resolve().parents[1]
    extension = (root / "storageops_cli" / "extensions" / "storageops.ts").read_text()

    assert "const ranges: Array<[number, number]>" in extension
    assert "start < rangeEnd && end > rangeStart" in extension
    assert "matchSecretRange" in extension
    assert "lineAndColumn" in extension


def test_secret_scanner_findings_do_not_return_raw_secret_previews():
    root = Path(__file__).resolve().parents[1]
    extension = (root / "storageops_cli" / "extensions" / "storageops.ts").read_text()

    assert "fingerprint" in extension
    assert "secretFingerprint(value)" in extension
    assert "preview" not in extension
    assert "findings.push({ line, column, type, length, fingerprint })" in extension
    assert "findings.push({ line, type, preview })" not in extension


def test_memory_search_scores_and_redacts_snippets():
    root = Path(__file__).resolve().parents[1]
    extension = (root / "storageops_cli" / "extensions" / "storageops.ts").read_text()

    assert "searchTokens" in extension
    assert "scoreText" in extension
    assert "safeMemorySnippet" in extension
    assert "redactText(text.replace" in extension
    assert 'source: "jsonl"' in extension
    assert "score: jsonlScore" in extension


def test_capture_http_trace_is_registered_as_bounded_safe_tool():
    root = Path(__file__).resolve().parents[1]
    extension = (root / "storageops_cli" / "extensions" / "storageops.ts").read_text()

    assert 'name: "capture_http_trace"' in extension
    assert "validateTraceCommand" in extension
    assert "capture_body=true is not supported" in extension
    assert "presigned URL material is not accepted" in extension
    assert "shells and sudo are not allowed" in extension
    assert "MAX_TRACE_REQUESTS = 20" in extension
    assert "MAX_TRACE_SECONDS = 30" in extension


def test_capture_http_trace_does_not_expose_raw_httpmon_artifacts():
    root = Path(__file__).resolve().parents[1]
    extension = (root / "storageops_cli" / "extensions" / "storageops.ts").read_text()

    assert '"--format", "json", "--filter", filterHost' in extension
    assert '"--record"' not in extension
    assert '"--har"' not in extension
    assert '"--replay"' not in extension
    assert "raw_trace_saved: false" in extension
    assert "har_saved: false" in extension
    assert "replay_performed: false" in extension
    assert "body_captured: false" in extension
    assert "Authorization" in extension
    assert "credential_scope" in extension
