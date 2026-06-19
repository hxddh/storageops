from __future__ import annotations

import importlib.util
from pathlib import Path


def load_parser_module():
    root = Path(__file__).resolve().parents[1]
    module_path = root / "skills" / "storageops-s3-protocol-compatibility" / "scripts" / "parse_sigv4_error.py"
    spec = importlib.util.spec_from_file_location("parse_sigv4_error", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parse_sigv4_xml_response(tmp_path):
    parser = load_parser_module()
    xml = tmp_path / "error.xml"
    xml.write_text(
        """<Error>
  <Code>SignatureDoesNotMatch</Code>
  <Message>The request signature we calculated does not match.</Message>
  <StringToSign>AWS4-HMAC-SHA256
20260602T010203Z
20260602/us-east-1/s3/aws4_request
abcdef</StringToSign>
  <CanonicalRequest>GET
/bucket/key
X-Amz-Algorithm=AWS4-HMAC-SHA256
host:s3.example.com
x-amz-date:20260602T010203Z

host;x-amz-date
UNSIGNED-PAYLOAD</CanonicalRequest>
</Error>""",
        encoding="utf-8",
    )

    result = parser.parse_sigv4_evidence(xml)

    assert result["ok"] is True
    assert result["code"] == "SignatureDoesNotMatch"
    assert result["credential_scope"]["region"] == "us-east-1"
    assert result["credential_scope"]["service"] == "s3"
    assert result["canonical_summary"]["method"] == "GET"
    assert result["canonical_summary"]["path"] == "/bucket/key"
    assert result["canonical_summary"]["signed_headers"] == ["host", "x-amz-date"]
    assert result["xml_parse_fallback"] is False


def test_parse_client_debug_blocks(tmp_path):
    parser = load_parser_module()
    log = tmp_path / "debug.log"
    log.write_text(
        """2026-06-02 01:02:03,100 - MainThread - botocore.auth - DEBUG - CanonicalRequest:
PUT
/bucket/object

host:s3.example.com
x-amz-content-sha256:012345
x-amz-date:20260602T010203Z

host;x-amz-content-sha256;x-amz-date
012345
2026-06-02 01:02:03,101 - MainThread - botocore.auth - DEBUG - StringToSign:
AWS4-HMAC-SHA256
20260602T010203Z
20260602/ap-southeast-1/s3/aws4_request
beef
""",
        encoding="utf-8",
    )

    result = parser.parse_sigv4_evidence(log)

    assert result["ok"] is True
    assert result["client_canonical_request"].startswith("PUT\n/bucket/object")
    assert result["credential_scope"]["region"] == "ap-southeast-1"
    assert "verify credential-scope region" in result["likely_causes"][0]


def test_parse_sigv4_xml_inside_markdown_fence(tmp_path):
    parser = load_parser_module()
    markdown = tmp_path / "error.md"
    markdown.write_text(
        """# Error

```xml
<Error>
  <Code>SignatureDoesNotMatch</Code>
  <StringToSign>AWS4-HMAC-SHA256
20260602T010203Z
20260602/us-west-2/s3/aws4_request
abcdef</StringToSign>
</Error>
```
""",
        encoding="utf-8",
    )

    result = parser.parse_sigv4_evidence(markdown)

    assert result["ok"] is True
    assert result["code"] == "SignatureDoesNotMatch"
    assert result["credential_scope"]["region"] == "us-west-2"
    # XML wrapped in a markdown fence fails strict XML parsing and falls back to
    # the lossy regex path, which must be signalled.
    assert result["xml_parse_fallback"] is True
