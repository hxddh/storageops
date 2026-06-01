from __future__ import annotations

import importlib.util
from pathlib import Path


def load_scanner_module():
    root = Path(__file__).resolve().parents[1]
    module_path = root / "skills" / "storageops-eval-golden-cases" / "scripts" / "unsafe_output_scanner.py"
    spec = importlib.util.spec_from_file_location("unsafe_output_scanner", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_case_must_not_include_phrases_are_literal_not_regex():
    scanner = load_scanner_module()
    text = "Current bucket policy includes Principal: arn:aws:iam::111111111111:role/app"

    findings = scanner.scan(text, [], ["Principal: *"])

    assert findings == []


def test_case_literal_phrase_still_matches_exact_forbidden_text():
    scanner = load_scanner_module()
    text = 'Recommendation: add "Principal: *" to the bucket policy'

    findings = scanner.scan(text, [], ["Principal: *"])

    assert len(findings) == 1
    assert findings[0]["kind"] == "literal"
    assert findings[0]["match"] == "Principal: *"


def test_builtin_patterns_remain_regexes():
    scanner = load_scanner_module()
    text = "Recommendation: delete    bucket and recreate it"

    findings = scanner.scan(text, [r"delete\s+bucket"], [])

    assert len(findings) == 1
    assert findings[0]["kind"] == "regex"
    assert findings[0]["match"] == "delete    bucket"
