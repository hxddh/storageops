"""
Secret detection and redaction engine.

Scans input for AK/SK, tokens, Authorization headers, and other credential
patterns. Outputs sanitized text with all findings replaced by [REDACTED].

Usage:
    cat log.txt | python -m storageops-core.utils.secret_scanner > clean.txt
    python -m storageops-core.utils.secret_scanner log.txt > clean.txt
"""
import re
import sys
import json
from pathlib import Path

# ── Patterns ──────────────────────────────────────────────────────────

SECRET_PATTERNS = [
    # AWS-style access key IDs (AKIA + 16 alphanumeric)
    (re.compile(r'\bAKIA[0-9A-Z]{16}\b'), 'AWS Access Key ID'),

    # Authorization header (contains signed credentials)
    (re.compile(r'Authorization:\s*AWS4-HMAC-SHA256\s+.*?(?=\n|$)', re.IGNORECASE),
     'Authorization Header (SigV4)'),

    # Authorization header (Bearer tokens, JWT)
    (re.compile(r'Authorization:\s*Bearer\s+\S+', re.IGNORECASE),
     'Authorization Header (Bearer)'),

    # bce-auth Authorization header (Baidu Cloud)
    (re.compile(r'Authorization:\s*bce-auth-v1/\S+', re.IGNORECASE),
     'Authorization Header (bce-auth)'),

    # Session token header (long base64)
    (re.compile(r'X-Amz-Security-Token:\s*\S+', re.IGNORECASE),
     'AWS Session Token Header'),

    # Presigned URL signatures
    (re.compile(r'X-Amz-Signature=[0-9a-f]{64}', re.IGNORECASE),
     'S3 Pre-signed URL Signature'),

    # Secret access key assignment patterns
    (re.compile(r'(secret_access_key|aws_secret_access_key|SecretAccessKey|secretKey|sk)\s*[:=]\s*\S+',
                re.IGNORECASE),
     'Secret Key Assignment'),

    # bcecmd credential format (may appear mid-line in debug output)
    (re.compile(r'(?:\[DEBUG\]\s*)?(ak|sk)\s*=\s*\S+', re.IGNORECASE),
     'bcecmd Credential'),

    # Connection strings with credentials
    (re.compile(r'(https?://)[^:@\s]+:[^@\s]+@', re.IGNORECASE),
     'URL with Embedded Credentials'),

    # Generic base64 session tokens (long strings)
    (re.compile(r'SessionToken["\s:=]+\s*([A-Za-z0-9+/=]{500,})'),
     'Session Token (long base64)'),

    # rclone env_auth credential lines
    (re.compile(r'(access_key_id|secret_access_key)\s*=\s*\S+', re.IGNORECASE),
     'rclone Credential'),

    # Alibaba Cloud Access Key ID (LTAI prefix + 16-24 alphanumeric chars)
    (re.compile(r'\bLTAI[A-Za-z0-9]{16,24}\b'), 'Alibaba Cloud Access Key ID'),

    # Alibaba Cloud secret key assignment (AccessKeySecret / aliyun_secret)
    (re.compile(r'(?:AccessKeySecret|aliyun_secret|oss_secret)\s*[:=]\s*\S+', re.IGNORECASE),
     'Alibaba Cloud Secret Key'),

    # Tencent Cloud Secret ID (AKID prefix + 32 alphanumeric chars)
    (re.compile(r'\bAKID[A-Za-z0-9]{32}\b'), 'Tencent Cloud Secret ID'),

    # Tencent Cloud secret key assignment (SecretKey in Tencent SDK context)
    (re.compile(r'(?:secretKey|secret_key|cos_secret)\s*[:=]\s*[A-Za-z0-9]{32,64}\b',
                re.IGNORECASE),
     'Tencent Cloud Secret Key'),

    # Google Cloud service account private key (JSON format)
    (re.compile(r'"private_key"\s*:\s*"-----BEGIN [A-Z ]+-----', re.IGNORECASE),
     'GCP Service Account Private Key'),

    # Google Cloud private_key_id
    (re.compile(r'"private_key_id"\s*:\s*"[0-9a-f]{40}"', re.IGNORECASE),
     'GCP Service Account Key ID'),
]

# Patterns for "safe" placeholders that should NOT be redacted
SAFE_PLACEHOLDERS = re.compile(
    r'(YOUR_ACCESS_KEY|YOUR_SECRET_KEY|<your-key>|<placeholder>|\[REDACTED\])',
    re.IGNORECASE
)

# ── Core ──────────────────────────────────────────────────────────────

def _is_safe_context(match, text, start, end):
    """Check if a match is within a safe placeholder context (already redacted)."""
    matched_text = match.group()
    # Check if the matched text ITSELF contains a safe placeholder
    if SAFE_PLACEHOLDERS.search(matched_text):
        return True
    if '[redacted]' in matched_text.lower():
        return True
    # Check surrounding context
    before = text[max(0, start - 30):start].lower()
    after = text[end:end + 30].lower()
    surrounding = before + after
    if SAFE_PLACEHOLDERS.search(surrounding):
        return True
    if '[redacted]' in surrounding:
        return True
    return False


def scan(text: str) -> dict:
    """
    Scan text for secrets.

    Returns:
        {
            "findings": [{"line": 1, "pattern": "...", "type": "..."}],
            "count": N,
            "redacted_text": "..."
        }
    """
    findings = []

    for pattern, secret_type in SECRET_PATTERNS:
        for m in pattern.finditer(text):
            start = m.start()
            end = m.end()
            if _is_safe_context(m, text, start, end):
                continue
            line_no = text[:start].count('\n') + 1
            findings.append({
                "line": line_no,
                "match_preview": m.group()[:60] + ("..." if len(m.group()) > 60 else ""),
                "type": secret_type,
            })

    # Sort by line number
    findings.sort(key=lambda f: f["line"])

    # Apply redaction
    redacted = text
    for f in reversed(findings):
        # Re-find to get exact span (line numbers may have shifted with earlier redactions,
        # but since we process in reverse, earlier replacements don't affect later positions)
        for pattern, secret_type in SECRET_PATTERNS:
            for m in pattern.finditer(redacted):
                if m.group()[:60].rstrip() == f["match_preview"].rstrip():
                    redacted = redacted[:m.start()] + '[REDACTED]' + redacted[m.end():]
                    break

    return {
        "findings": findings,
        "count": len(findings),
        "redacted_text": redacted,
    }


def main():
    """CLI entry point."""
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
        if path.exists():
            text = path.read_text(encoding='utf-8', errors='replace')
        else:
            print(json.dumps({"ok": False, "error": f"file not found: {sys.argv[1]}"}))
            sys.exit(1)
    else:
        text = sys.stdin.read()

    result = scan(text)
    result["ok"] = True
    result["module"] = "secret_scanner"

    # Don't output the redacted text by default (too large); output on request
    include_text = '--output-text' in sys.argv
    if not include_text:
        del result["redacted_text"]

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
