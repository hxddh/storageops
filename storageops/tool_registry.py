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
        "name": "parse_cors_error",
        "description": (
            "Parse CORS error responses and preflight failures. "
            "Use when evidence contains 'NoSuchCORSConfiguration', 'CORSForbidden', "
            "'Access-Control-Allow-Origin missing', or OPTIONS preflight 403. "
            "Extracts: missing CORS headers, blocked origins/methods, bucket name. "
            "Call AFTER scan_secrets; then call analyze_cors to generate a fix configuration."
        ),
        "input_schema": {"type": "object", "properties": {"log_text": {"type": "string"}}, "required": ["log_text"]},
    },
    {
        "name": "analyze_cors",
        "description": (
            "Generate a CORS configuration XML that fixes detected issues. "
            "Call AFTER parse_cors_error. Outputs ready-to-apply S3 CORS config XML. "
            "Output must be reviewed and applied manually — label as '# manual-only:'."
        ),
        "input_schema": {"type": "object", "properties": {"cors_data": {"type": "object", "description": "Output from parse_cors_error"}}},
    },
    {
        "name": "parse_replication_status",
        "description": (
            "Parse CRR/SRR replication status data. "
            "Use when evidence shows ReplicationStatus: FAILED/PENDING, or replication lag. "
            "Extracts: per-object status, rule failures, failure rate."
        ),
        "input_schema": {"type": "object", "properties": {"log_text": {"type": "string"}}, "required": ["log_text"]},
    },
    {
        "name": "analyze_replication",
        "description": (
            "Diagnose why replication is failing. "
            "Call AFTER parse_replication_status. Returns likely cause (IAM/KMS/destination) "
            "and verification commands."
        ),
        "input_schema": {"type": "object", "properties": {"replication_data": {"type": "object", "description": "Output from parse_replication_status"}}},
    },
    {
        "name": "parse_hadoop_s3a",
        "description": (
            "Parse Hadoop/Spark/Hive S3A filesystem errors. "
            "Use when evidence contains 'S3AFileSystem', 's3a://', staging/magic committer errors, "
            "or HADOOP- issue references. Extracts: committer type, rename failures, credential issues."
        ),
        "input_schema": {"type": "object", "properties": {"log_text": {"type": "string"}}, "required": ["log_text"]},
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
    {
        "name": "parse_network_diagnostics",
        "description": (
            "Parse network diagnostic output (dig, curl -v, ping, mtr, traceroute) into a "
            "structured dict. Use when evidence contains DNS lookup results, curl verbose output, "
            "ping statistics, or traceroute/mtr hop data for an S3 or VPC endpoint. "
            "Extracts: DNS status (NXDOMAIN/SERVFAIL/resolved IPs/CNAME chain), TCP connectivity "
            "(refused/timed out/HTTP status), TLS certificate errors, ICMP latency and packet loss, "
            "and routing hops. Detects VPC endpoints and S3 endpoints automatically. "
            "Pass the raw command output as 'diagnostic_text'. "
            "Follow with analyze_network for root-cause diagnosis."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "diagnostic_text": {
                    "type": "string",
                    "description": "Raw output from dig, curl -v, ping, mtr, or traceroute",
                },
            },
            "required": ["diagnostic_text"],
        },
    },
    {
        "name": "analyze_network",
        "description": (
            "Analyze parsed network diagnostic data and return root-cause diagnosis with "
            "actionable recommendations. Use after parse_network_diagnostics. "
            "Diagnoses: DNS NXDOMAIN (bad hostname/missing VPC endpoint DNS), DNS SERVFAIL "
            "(resolver failure), TLS certificate errors, TCP refused (firewall/security group), "
            "TCP timeout (silent drop/NACL), host unreachable, packet loss, HTTP 403 (S3 policy). "
            "Returns: root_cause, severity (critical/high/medium/low/ok), confidence score, "
            "findings list, and prioritized recommendations. "
            "Provide the full parse_network_diagnostics output as 'parsed'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "parsed": {
                    "type": "object",
                    "description": "Full output dict from parse_network_diagnostics",
                },
            },
            "required": ["parsed"],
        },
    },
    {
        "name": "parse_httpmon_log",
        "description": (
            "Parse httpmon (https-traffic-inspector) output into StorageOps diagnostic signals. "
            "httpmon wraps CLI commands (aws, rclone, python scripts) and captures actual "
            "HTTP/HTTPS traffic to/from S3-compatible storage. "
            "Handles two input formats: "
            "(1) NDJSON — from `httpmon --format json <command>`, "
            "(2) HAR — from `httpmon --har output.har <command>`. "
            "Extracts S3-relevant signals: error codes (AccessDenied, SignatureDoesNotMatch, "
            "SlowDown, etc.), HTTP status distribution, auth type (sigv4/presigned/anonymous), "
            "CORS response headers, per-request timing. "
            "Auth header values are NEVER exposed — only classified (sigv4/presigned/other). "
            "Returns: format, s3_request_count, entries (per-request details), "
            "error_summary, status_distribution, auth_types, has_cors_traffic, "
            "timing_stats, and signals (list of domain hints like "
            "'access_denied_detected → security_iam_policy'). "
            "Usage: `httpmon --format json aws s3 ls s3://bucket 2>&1 | storageops` "
            "or `httpmon --har capture.har rclone copy ... && storageops @capture.har`."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "log_text": {
                    "type": "string",
                    "description": (
                        "Raw httpmon output: NDJSON from --format json, "
                        "or HAR file content from --har flag"
                    ),
                },
            },
            "required": ["log_text"],
        },
    },
]


# ── Tool Dispatch ─────────────────────────────────────────────────────

# Pi-native tools that should never be intercepted in RPC mode.
# These are handled internally by Pi, not routed to tool_bridge.
_PI_RPC_NATIVE_TOOLS = frozenset({
    "bash", "read", "write", "edit", "task",
    "TodoWrite", "Task", "web_search", "web_fetch",
    "search_notes", "create_notes", "list_directory",
})


def dispatch_tool(name: str, inputs: dict) -> dict:
    """Execute a tool by name. Returns result dict. Never raises — errors in result."""
    # Pi native tools — signal to skip, model will adapt
    if name in _PI_RPC_NATIVE_TOOLS:
        return {"error": f"{name!r} is a Pi-native tool (not routed through StorageOps)"}

    try:
        if name == "scan_secrets":
            from storageops.utils.secret_scanner import scan  # noqa: E402
            return scan(inputs["text"])

        elif name == "parse_rclone_log":
            from storageops.parsers.parse_rclone_log import parse  # noqa: E402
            return parse(inputs["log_text"])

        elif name == "parse_sigv4_error":
            from storageops.parsers.parse_sigv4_error import parse_xml_error, diagnose  # noqa: E402
            parsed = parse_xml_error(inputs["xml_text"])
            system_time = inputs.get("system_time")
            if system_time:
                return diagnose(parsed, system_time=system_time)
            return parsed

        elif name == "parse_awscli_debug":
            from storageops.parsers.parse_awscli_debug import parse  # noqa: E402
            return parse(inputs["log_text"])

        elif name == "parse_lifecycle_xml":
            from storageops.parsers.parse_lifecycle_xml import parse  # noqa: E402
            return parse(inputs["xml_text"])

        elif name == "analyze_policy":
            from storageops.analyzers.analyze_policy import analyze, analyze_inline_403  # noqa: E402
            error_text = inputs.pop("error_text", None)
            has_policy_data = inputs.get("principal") or inputs.get("iam_policy") or inputs.get("bucket_policy")
            if has_policy_data:
                return analyze(inputs)
            elif error_text:
                return analyze_inline_403(error_text)
            return {"error": "Provide principal+action+resource+policies or error_text"}

        elif name == "analyze_cost":
            from storageops.analyzers.analyze_cost import analyze  # noqa: E402
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
            from storageops.analyzers.detect_throttling import detect  # noqa: E402
            return detect(inputs)

        elif name == "generate_lifecycle_fix":
            from storageops.action_tools import generate_lifecycle_fix
            return generate_lifecycle_fix(inputs["xml_text"])

        elif name == "generate_policy_fix":
            from storageops.action_tools import generate_policy_fix
            return generate_policy_fix(inputs)

        elif name == "search_memory":
            from storageops.session import Session
            query = inputs.get("query", "")
            if not query or not isinstance(query, str):
                return {"results": [], "count": 0, "query": str(query)}
            try:
                sessions = Session.list_all(query=query)
                results = [{
                    "id": s.get("id", ""),
                    "name": s.get("name", ""),
                    "summary": s.get("summary", ""),
                    "domain": s.get("domain", ""),
                    "created": s.get("created", ""),
                    "turns": s.get("turns", 0)
                } for s in sessions[:5]]
                return {"results": results, "count": len(results), "query": query}
            except Exception:
                return {"results": [], "count": 0, "query": query}

        elif name == "parse_s5cmd_log":
            from storageops.parsers.parse_s5cmd_log import parse
            return parse(inputs["log_text"])

        elif name == "analyze_throughput":
            from storageops.analyzers.analyze_throughput import analyze  # noqa: E402
            return analyze(inputs)

        elif name == "parse_cors_error":
            from storageops.parsers.parse_cors_error import parse
            return parse(inputs["log_text"])

        elif name == "analyze_cors":
            from storageops.analyzers.analyze_cors import analyze
            return analyze(inputs.get("cors_data", inputs))

        elif name == "parse_replication_status":
            from storageops.parsers.parse_replication_status import parse
            return parse(inputs["log_text"])

        elif name == "analyze_replication":
            from storageops.analyzers.analyze_replication import analyze
            return analyze(inputs.get("replication_data", inputs))

        elif name == "parse_hadoop_s3a":
            from storageops.parsers.parse_hadoop_s3a import parse
            return parse(inputs["log_text"])

        elif name == "parse_network_diagnostics":
            from storageops.parsers.parse_network_diagnostics import parse  # noqa: E402
            return parse(inputs["diagnostic_text"])

        elif name == "analyze_network":
            from storageops.analyzers.analyze_network import analyze  # noqa: E402
            return analyze(inputs["parsed"])

        elif name == "parse_httpmon_log":
            from storageops.parsers.parse_httpmon_log import parse  # noqa: E402
            return parse(inputs["log_text"])

        else:
            return {"error": f"Unknown tool: {name!r}"}

    except Exception as exc:
        return {"error": str(exc), "tool": name}
