"""
Analyze CORS configuration issues and generate a corrected CORS XML.

Input: output from parse_cors_error.
Output: ready-to-apply S3 CORS config XML and usage instructions.

Usage:
    python analyze_cors.py cors_parsed.json
"""
import json
import sys
from pathlib import Path


def _build_cors_xml(origins: list, methods: list, headers: list, expose_headers: list = None) -> str:
    """Build a minimal, valid S3 CORS configuration XML."""
    if not origins:
        origins = ["*"]
    if not methods:
        methods = ["GET", "PUT", "POST", "DELETE", "HEAD"]
    if not headers:
        headers = ["*"]

    allowed_origins = "\n".join(
        f"    <AllowedOrigin>{o}</AllowedOrigin>" for o in origins
    )
    allowed_methods = "\n".join(
        f"    <AllowedMethod>{m}</AllowedMethod>" for m in methods
    )
    allowed_headers = "\n".join(
        f"    <AllowedHeader>{h}</AllowedHeader>" for h in headers
    )
    expose_block = ""
    if expose_headers:
        expose_block = "\n" + "\n".join(
            f"    <ExposeHeader>{h}</ExposeHeader>" for h in expose_headers
        )

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<CORSConfiguration xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
  <CORSRule>
{allowed_origins}
{allowed_methods}
{allowed_headers}{expose_block}
    <MaxAgeSeconds>3000</MaxAgeSeconds>
  </CORSRule>
</CORSConfiguration>"""


def analyze(data: dict) -> dict:
    """
    Generate a CORS configuration XML that fixes detected issues.

    Input: output from parse_cors_error
    Returns:
        {
            "issues": [str],
            "recommended_cors_xml": str,
            "explanation": str,
            "usage": str
        }
    """
    cors_errors = data.get("cors_errors", [])
    no_cors_config = data.get("no_cors_config", False)
    preflight_failed = data.get("preflight_failed", False)
    missing_headers = data.get("missing_headers", [])
    bucket = data.get("bucket")
    summary = data.get("summary", {})

    issues = []
    origins = []
    methods = []
    req_headers = []
    expose_headers = []

    # Collect unique origins, methods, headers from all errors
    for err in cors_errors:
        origin = err.get("origin", "").strip()
        if origin and origin not in origins:
            origins.append(origin)
        method = err.get("method", "").strip()
        if method and method not in methods:
            methods.append(method)
        for h in err.get("headers", []):
            h = h.strip()
            if h and h not in req_headers:
                req_headers.append(h)

    # Build issue list
    if no_cors_config:
        issues.append("No CORS configuration found on bucket (NoSuchCORSConfiguration). "
                      "A CORS rule must be created before browsers can make cross-origin requests.")
    for err in cors_errors:
        t = err.get("type", "")
        if t == "CORSForbidden":
            issues.append(
                f"Origin '{err.get('origin', 'unknown')}' is not listed in AllowedOrigin. "
                "Add this origin to the CORS rule."
            )
        elif t == "preflight_failed":
            issues.append(
                f"Preflight OPTIONS request failed (403). "
                f"Method '{err.get('method', '')}' or headers {err.get('headers', [])} "
                "may not be permitted by the CORS rule."
            )
        elif t == "missing_allow_origin_header":
            issues.append(
                "Response is missing Access-Control-Allow-Origin header. "
                "The CORS rule may not match the request origin."
            )
        elif t == "cors_policy_mismatch":
            issues.append("CORS policy mismatch: request origin or method does not match any AllowedOrigin/AllowedMethod.")

    for h in missing_headers:
        issues.append(f"Response header '{h}' is missing — it must be in AllowedHeader or ExposeHeader.")

    if not issues:
        issues.append("CORS configuration issue detected. Review AllowedOrigin, AllowedMethod, and AllowedHeader.")

    # Default methods if none extracted
    if not methods:
        methods = ["GET", "PUT", "POST", "DELETE", "HEAD"]

    # Default headers if none extracted
    if not req_headers:
        req_headers = ["Content-Type", "Authorization", "x-amz-*"]

    # Add OPTIONS for preflight support
    if preflight_failed and "OPTIONS" not in methods:
        methods.insert(0, "OPTIONS")

    cors_xml = _build_cors_xml(
        origins=origins if origins else ["https://example.com"],
        methods=methods,
        headers=req_headers,
        expose_headers=expose_headers,
    )

    bucket_ref = bucket or "<your-bucket-name>"
    usage = (
        "# manual-only: Review and apply the CORS configuration above.\n"
        f"# aws s3api put-bucket-cors --bucket {bucket_ref} --cors-configuration file://cors.json\n"
        "# Or with the XML directly:\n"
        f"# aws s3api put-bucket-cors --bucket {bucket_ref} --cors-configuration '{{\n"
        "#   \"CORSRules\": [{ ... }]\n"
        "# }}'"
    )

    explanation = (
        "The CORS configuration above allows the detected origins and methods. "
        "Replace 'https://example.com' with your actual allowed origins. "
        "After applying, verify with a preflight OPTIONS request. "
        "All changes must be reviewed and applied manually — never apply automatically."
    )

    return {
        "issues": issues,
        "recommended_cors_xml": cors_xml,
        "explanation": explanation,
        "usage": usage,
    }


def main():
    if len(sys.argv) > 1:
        data = json.loads(Path(sys.argv[1]).read_text())
    else:
        data = json.loads(sys.stdin.read())

    result = analyze(data)
    result["ok"] = True
    result["module"] = "analyze_cors"
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
