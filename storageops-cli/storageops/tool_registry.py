"""
Tool registry: wraps storageops-core parsers + analyzers as LLM tool definitions.

Each tool has a name, description, input_schema (JSON Schema), and a handler
function. All tools operate on in-memory text/dicts — zero network calls,
zero filesystem writes, zero cloud operations.

The LLM decides which tools to call and in what order. This replaces the
hardcoded dispatch in the legacy rule-based agent.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure storageops-core modules are importable
_CORE = Path(__file__).parent.parent.parent / "storageops-core"
for _sub in ("utils", "parsers", "analyzers"):
    _p = str(_CORE / _sub)
    if _p not in sys.path:
        sys.path.insert(0, _p)


# ── Tool Definitions (schema for LLM) ────────────────────────────────

TOOL_DEFINITIONS: list[dict] = [
    {
        "name": "scan_secrets",
        "description": (
            "Scan text for exposed credentials: AWS access keys, session tokens, "
            "Authorization headers, Alibaba/Tencent/Baidu Cloud keys, rclone config secrets. "
            "Returns findings list and redacted text. "
            "ALWAYS call this first before including any user-provided text in analysis or output."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to scan for secrets"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "parse_rclone_log",
        "description": (
            "Parse an rclone debug or info log. Extracts: rclone version, transfer failures, "
            "ETag/checksum mismatches (multipart_etag_format_mismatch is the most common cause "
            "of corrupted-on-transfer), retry counts, timeouts, and overall transfer summary. "
            "Use when the user provides rclone log output."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "log_text": {
                    "type": "string",
                    "description": "Raw rclone log content (already redacted of secrets)",
                },
            },
            "required": ["log_text"],
        },
    },
    {
        "name": "parse_sigv4_error",
        "description": (
            "Parse an AWS SigV4 error XML response (SignatureDoesNotMatch, "
            "InvalidSignature, AuthorizationHeaderMalformed, RequestExpired). "
            "Extracts canonical request, string-to-sign, server/client time for clock skew check. "
            "Use when the user provides an XML error response from S3 or a compatible provider."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "xml_text": {
                    "type": "string",
                    "description": "Raw XML error response body",
                },
                "system_time": {
                    "type": "string",
                    "description": "Client system time (e.g. from `date -u`) for clock skew check",
                },
            },
            "required": ["xml_text"],
        },
    },
    {
        "name": "parse_awscli_debug",
        "description": (
            "Parse AWS CLI debug log output (from `aws --debug`). "
            "Extracts HTTP operations, status codes, error codes (SignatureDoesNotMatch, "
            "AccessDenied, etc.), credential source (instance profile, env, config), "
            "and request/response details. "
            "Use when the user provides `aws --debug` or `aws s3 ... --debug` output."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "log_text": {
                    "type": "string",
                    "description": "Raw AWS CLI debug log content",
                },
            },
            "required": ["log_text"],
        },
    },
    {
        "name": "parse_lifecycle_xml",
        "description": (
            "Parse an S3 lifecycle configuration XML. Extracts transition and expiration rules, "
            "detects overlapping prefixes (including hierarchical: logs/ overlaps logs/2024/), "
            "and warns about STANDARD_IA transitions without object size filters "
            "(objects <128KB are billed at 128KB minimum). "
            "Use when the user provides lifecycle XML."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "xml_text": {
                    "type": "string",
                    "description": "S3 lifecycle configuration XML text",
                },
            },
            "required": ["xml_text"],
        },
    },
    {
        "name": "analyze_policy",
        "description": (
            "Analyze IAM and/or bucket policy JSON to trace a 403 AccessDenied. "
            "Handles: explicit denies, cross-account missing IAM allow, "
            "no-allow-statement, condition mismatches. "
            "Supports prefix wildcards like s3:Get*. "
            "Provide principal, action, resource, and at least one policy. "
            "If policy JSON is unavailable, provide error_text for inline 403 analysis."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "principal": {
                    "type": "string",
                    "description": "ARN of the principal (user/role) attempting access",
                },
                "action": {
                    "type": "string",
                    "description": "S3 action being attempted, e.g. s3:GetObject",
                },
                "resource": {
                    "type": "string",
                    "description": "ARN of the resource, e.g. arn:aws:s3:::my-bucket/key",
                },
                "iam_policy": {
                    "type": "object",
                    "description": "IAM policy JSON with Statement array",
                },
                "bucket_policy": {
                    "type": "object",
                    "description": "Bucket policy JSON with Statement array",
                },
                "error_text": {
                    "type": "string",
                    "description": "Raw 403 error text when policy JSON is unavailable",
                },
            },
        },
    },
    {
        "name": "analyze_cost",
        "description": (
            "Analyze per-prefix inventory data for storage cost issues. "
            "Detects: minimum billable size penalties (IA/Glacier with small objects), "
            "minimum duration risks (objects deleted before 30/90/180 day minimum), "
            "and cost amplification. "
            "Use when the user provides object count, size, and storage class per prefix."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "storage_price_per_gb": {
                    "type": "object",
                    "description": "Price per GB per storage class. Defaults used if omitted.",
                },
                "prefixes": {
                    "type": "array",
                    "description": "Per-prefix inventory data",
                    "items": {
                        "type": "object",
                        "properties": {
                            "prefix": {"type": "string"},
                            "storage_class": {"type": "string"},
                            "object_count": {"type": "integer"},
                            "total_size_bytes": {"type": "integer"},
                            "avg_object_age_days": {
                                "type": "number",
                                "description": "Omit if unknown — no false-positive warning",
                            },
                        },
                        "required": ["prefix", "storage_class", "object_count", "total_size_bytes"],
                    },
                },
            },
            "required": ["prefixes"],
        },
    },
    {
        "name": "detect_throttling",
        "description": (
            "Detect throttling patterns from error distribution data. "
            "Returns throttle rate (%), severity, affected prefixes, and recommendations. "
            "Use when the user reports 429 errors, SlowDown responses, or RequestRateLimitExceeded."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "status_codes": {
                    "type": "object",
                    "description": "HTTP status code counts, e.g. {\"429\": 10, \"200\": 1000}",
                },
                "errors": {
                    "type": "array",
                    "description": "Array of error objects or strings from the log",
                    "items": {},
                },
                "total_operations": {
                    "type": "integer",
                    "description": "Total number of operations in the measurement window",
                },
                "prefix_errors": {
                    "type": "object",
                    "description": "Error counts keyed by prefix, e.g. {\"logs/\": 5}",
                },
            },
        },
    },
    {
        "name": "generate_lifecycle_fix",
        "description": (
            "Generate a corrected S3 lifecycle configuration XML that fixes detected issues. "
            "Automatically adds ObjectSizeGreaterThan 128 KB filters to STANDARD_IA transitions "
            "(preventing minimum-size billing for small objects) and enforces minimum 30-day "
            "transition delays. Output is XML the user must review and apply manually."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "xml_text": {
                    "type": "string",
                    "description": "The original lifecycle configuration XML to fix",
                },
            },
            "required": ["xml_text"],
        },
    },
    {
        "name": "generate_policy_fix",
        "description": (
            "Generate a fix for an IAM or bucket policy causing AccessDenied (403). "
            "Analyzes the denial source and outputs specific policy statement(s) to add. "
            "Output must be reviewed and applied manually — this tool never modifies live policies."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "principal": {"type": "string", "description": "ARN of the denied principal"},
                "action": {"type": "string", "description": "S3 action, e.g. s3:GetObject"},
                "resource": {"type": "string", "description": "Resource ARN"},
                "iam_policy": {"type": "object", "description": "IAM policy JSON"},
                "bucket_policy": {"type": "object", "description": "Bucket policy JSON"},
            },
        },
    },
    {
        "name": "search_memory",
        "description": (
            "Search your memory of past diagnosed cases for similar patterns. "
            "Call this early in the investigation — before parsing tools — to check whether "
            "a similar issue has been seen before. Returns matching past diagnoses with their "
            "root causes, summaries, and timestamps. Use results to guide your investigation "
            "but always verify against the current evidence."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Keywords describing the current problem, "
                        "e.g. 'ETag mismatch multipart rclone S3 corrupted transfer'"
                    ),
                },
                "domain": {
                    "type": "string",
                    "description": (
                        "Optional domain filter, e.g. 'cli_sdk_behavior'. "
                        "Omit to search all domains."
                    ),
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of results to return (1–5, default 3)",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "analyze_throughput",
        "description": (
            "Analyze upload/download throughput against theoretical limits. "
            "Identifies bandwidth bottlenecks, RTT impact, and multipart tuning opportunities. "
            "Use when the user reports slow transfer speeds and can provide timing data."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "object_size_mb": {"type": "number", "description": "Object size in MB"},
                "rtt_ms": {"type": "number", "description": "Round-trip time to endpoint in ms"},
                "bandwidth_mbps": {
                    "type": "number",
                    "description": "Available bandwidth in Mbps (from speedtest or known limit)",
                },
                "observed_throughput_mbps": {
                    "type": "number",
                    "description": "Actual observed throughput in Mbps",
                },
                "concurrency": {
                    "type": "integer",
                    "description": "Number of parallel upload/download streams",
                },
                "part_size_mb": {
                    "type": "number",
                    "description": "Multipart upload part size in MB",
                },
            },
        },
    },
]


# ── Tool Dispatch ─────────────────────────────────────────────────────

def dispatch_tool(name: str, inputs: dict) -> dict:
    """Execute a tool by name. Returns result dict. Never raises — errors in result."""
    try:
        if name == "scan_secrets":
            from secret_scanner import scan  # noqa: E402
            return scan(inputs["text"])

        elif name == "parse_rclone_log":
            from parse_rclone_log import parse  # noqa: E402
            return parse(inputs["log_text"])

        elif name == "parse_sigv4_error":
            from parse_sigv4_error import parse_xml_error, diagnose  # noqa: E402
            parsed = parse_xml_error(inputs["xml_text"])
            system_time = inputs.get("system_time")
            if system_time:
                return diagnose(parsed, system_time=system_time)
            return parsed

        elif name == "parse_awscli_debug":
            from parse_awscli_debug import parse  # noqa: E402
            return parse(inputs["log_text"])

        elif name == "parse_lifecycle_xml":
            from parse_lifecycle_xml import parse  # noqa: E402
            return parse(inputs["xml_text"])

        elif name == "analyze_policy":
            from analyze_policy import analyze, analyze_inline_403  # noqa: E402
            error_text = inputs.pop("error_text", None)
            has_policy_data = inputs.get("principal") or inputs.get("iam_policy") or inputs.get("bucket_policy")
            if has_policy_data:
                return analyze(inputs)
            elif error_text:
                return analyze_inline_403(error_text)
            return {"error": "Provide principal+action+resource+policies or error_text"}

        elif name == "analyze_cost":
            from analyze_cost import analyze  # noqa: E402
            if "storage_price_per_gb" not in inputs:
                inputs["storage_price_per_gb"] = {
                    "STANDARD": 0.023,
                    "STANDARD_IA": 0.0125,
                    "ONEZONE_IA": 0.01,
                    "GLACIER": 0.004,
                    "DEEP_ARCHIVE": 0.00099,
                }
            return analyze(inputs)

        elif name == "detect_throttling":
            from detect_throttling import detect  # noqa: E402
            return detect(inputs)

        elif name == "generate_lifecycle_fix":
            from storageops.action_tools import generate_lifecycle_fix
            return generate_lifecycle_fix(inputs["xml_text"])

        elif name == "generate_policy_fix":
            from storageops.action_tools import generate_policy_fix
            return generate_policy_fix(inputs)

        elif name == "search_memory":
            from storageops.memory_store import search_cases
            query = inputs.get("query", "")
            domain_filter = inputs.get("domain")
            top_k = min(int(inputs.get("top_k", 3)), 5)
            results = search_cases(query, domain=domain_filter, top_k=top_k)
            return {"results": results, "count": len(results), "query": query}

        elif name == "analyze_throughput":
            from analyze_throughput import analyze  # noqa: E402
            return analyze(inputs)

        else:
            return {"error": f"Unknown tool: {name!r}"}

    except Exception as exc:
        return {"error": str(exc), "tool": name}
