"""
Tool registry: wraps storageops-core parsers + analyzers as Pi tool definitions.

Each tool has a name, description, input_schema (JSON Schema), and a handler
function. All tools operate on in-memory text/dicts — zero network calls,
zero filesystem writes, zero cloud operations.

Pi calls these tools via StorageOps MCP or CLI. sys.path is set up by
storageops/__init__.py when the package is imported.
"""
from __future__ import annotations


# ── Tool Definitions ──────────────────────────────────────────────────

TOOL_DEFINITIONS: list[dict] = [
    {
        "name": "scan_secrets",
        "description": (
            "Scan text for exposed credentials and redact them before they reach your output. "
            "Detects: AWS access keys (AKIA...), session tokens, Authorization headers, "
            "Alibaba/Tencent/Baidu Cloud AK/SK, rclone config secrets, private keys. "
            "Returns: findings list + redacted_text with secrets replaced by [REDACTED]. "
            "Call this BEFORE passing any user-provided text to other tools or including "
            "it in your response. Also call on tool result text if it may echo back user input."
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
            "Parse an rclone debug or info log. "
            "Use when evidence contains rclone output, e.g. lines like: "
            "'ERROR ... corrupted on transfer' or 'rclone v1.64.2'. "
            "Extracts: rclone version, transfer failures, ETag/checksum mismatches "
            "(multipart_etag_format_mismatch is the most common cause of corrupted-on-transfer), "
            "retry counts, timeouts, bandwidth stats, and overall transfer summary. "
            "Call AFTER scan_secrets on the log text."
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
            "Parse an AWS SigV4 error XML response. "
            "Use when evidence contains XML error bodies like: "
            "'<Code>SignatureDoesNotMatch</Code>' or '<Code>RequestExpired</Code>'. "
            "Also use for: InvalidSignature, AuthorizationHeaderMalformed. "
            "Extracts: error code, canonical request diff, string-to-sign, server time "
            "and client time (for clock skew detection — skew >5 min causes RequestExpired). "
            "Call AFTER scan_secrets; provide system_time if the user ran `date -u`."
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
            "Parse AWS CLI debug log output. "
            "Use when evidence contains AWS CLI debug output, e.g. lines like: "
            "'DEBUG botocore.endpoint' or 'urllib3.connectionpool'. "
            "Also useful for s5cmd logs and generic HTTP request/response traces. "
            "Extracts: HTTP status codes, error codes (SignatureDoesNotMatch, AccessDenied, "
            "NoSuchKey, etc.), credential source (instance profile vs env vs config file), "
            "endpoint URL, and request/response headers. "
            "Call AFTER scan_secrets on the log text."
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
            "Parse an S3 lifecycle configuration XML. "
            "Use when evidence contains XML starting with '<LifecycleConfiguration>' "
            "or when the user asks about lifecycle rules, transition policies, or expiration. "
            "Extracts: all transition and expiration rules, detects overlapping prefixes "
            "(logs/ overlaps logs/2024/), warns about STANDARD_IA or GLACIER transitions "
            "without ObjectSizeGreaterThan filter (objects <128KB billed at 128KB minimum — "
            "the most common lifecycle cost trap). "
            "Call BEFORE analyze_cost for lifecycle-related cost questions; "
            "call BEFORE generate_lifecycle_fix to get the problem list."
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
            "Trace a 403 AccessDenied through IAM and/or bucket policies. "
            "Use when the user reports 403 / AccessDenied errors on S3 operations. "
            "Handles: explicit Deny overriding Allow, cross-account access where BOTH "
            "IAM and bucket policy must allow, missing Allow statement, condition mismatches "
            "(e.g. aws:SourceVpc, aws:PrincipalOrgID), KMS key policy gaps. "
            "Supports action wildcards like s3:Get*. "
            "Provide principal ARN, action, resource ARN, and policy JSON(s). "
            "If policy JSON is unavailable, pass error_text and the tool will do "
            "inline text analysis to identify likely denial source. "
            "Call generate_policy_fix afterward if a fix statement is needed."
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
            "Use when the user reports unexpectedly high storage bills or provides "
            "inventory data with object counts, sizes, and storage classes. "
            "Detects: minimum billable size penalty (STANDARD_IA/Glacier objects <128KB "
            "are billed at 128KB — most expensive per-byte tier), minimum storage duration "
            "charges (STANDARD_IA: 30 days, Glacier: 90–180 days), and cost amplification "
            "from many small objects in tiered storage. "
            "Requires prefix-level inventory with object_count, total_size_bytes, storage_class."
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
            "Detect S3 throttling patterns from HTTP status code and error distributions. "
            "Use when evidence mentions 429, SlowDown, RequestRateLimitExceeded, "
            "or when transfer speed is intermittently poor with retries. "
            "Returns: throttle_rate_percent, severity (low/medium/high/critical), "
            "affected prefixes (hot prefix detection), retry recommendations. "
            "Extract status_codes and errors from parse_awscli_debug or parse_rclone_log first, "
            "then pass those structured results here."
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
            "Generate a corrected S3 lifecycle XML that fixes issues identified by parse_lifecycle_xml. "
            "Call AFTER parse_lifecycle_xml has confirmed problems (missing size filter, "
            "overlapping prefixes, or too-short transition delay). "
            "Automatically adds ObjectSizeGreaterThan 128 KB filter to STANDARD_IA/Glacier "
            "transitions, enforces minimum 30-day transition delay, and deduplicates overlapping rules. "
            "Output is complete XML the user MUST review and apply manually — "
            "this tool never modifies live configurations. Label your recommendation '# manual-only:'."
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
            "Generate specific IAM or bucket policy statement(s) to fix a 403 AccessDenied. "
            "Call AFTER analyze_policy has identified the denial source "
            "(e.g. missing Allow in IAM, explicit Deny in bucket policy, cross-account gap). "
            "Outputs a ready-to-paste policy JSON statement targeted at the exact gap. "
            "Output MUST be reviewed by the user before applying — "
            "this tool never modifies live policies. Label as '# manual-only:'."
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
            "Search past diagnosed cases by BM25 keyword similarity. "
            "Call this as your FIRST tool (before any parsing) to check for prior art. "
            "If a match is found, it may tell you the root cause immediately and save turns. "
            "Query with symptoms and domain keywords, e.g. "
            "'ETag mismatch multipart rclone corrupted transfer' or '403 AccessDenied cross-account KMS'. "
            "Returns: matching cases with root_cause, summary, domain, and timestamp. "
            "Always verify memory results against the current evidence — don't assume same root cause "
            "without checking tool output from this case."
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
        "name": "parse_s5cmd_log",
        "description": (
            "Parse s5cmd debug log output into structured operation records. "
            "Use when evidence contains s5cmd output, e.g. lines starting with "
            "'ERROR' or 's5cmd [0-9]'. "
            "Extracts: operation type (cp/sync/rm), error codes, failed keys, "
            "throughput stats, and retry patterns. "
            "Call AFTER scan_secrets on the log text."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "log_text": {
                    "type": "string",
                    "description": "Raw s5cmd log content (already redacted of secrets)",
                },
            },
            "required": ["log_text"],
        },
    },
    {
        "name": "analyze_throughput",
        "description": (
            "Analyze upload/download throughput against theoretical limits given RTT and bandwidth. "
            "Use when the user reports slow transfer speeds and provides timing or bandwidth data. "
            "Key insight: throughput = TCP_window / RTT; a 192ms RTT with default 64KB TCP window "
            "limits single-stream throughput to ~2.7 Mbps regardless of bandwidth. "
            "Returns: theoretical max throughput, actual vs expected ratio, bottleneck type "
            "(bandwidth-bound vs latency-bound vs concurrency-bound), multipart part size recommendation, "
            "and suggested concurrency level. "
            "Provide observed_throughput_mbps if available for gap analysis."
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

        elif name == "parse_s5cmd_log":
            from parse_s5cmd_error import parse
            return parse(inputs["log_text"])

        elif name == "analyze_throughput":
            from analyze_throughput import analyze  # noqa: E402
            return analyze(inputs)

        else:
            return {"error": f"Unknown tool: {name!r}"}

    except Exception as exc:
        return {"error": str(exc), "tool": name}
