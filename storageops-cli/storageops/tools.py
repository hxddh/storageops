"""
Tool definitions — JSON schemas and call functions for LLM tool-use.

Each tool wraps a storageops-core parser or analyzer.
"""
import json
import sys
from pathlib import Path

# Ensure core modules are importable
CLI_DIR = Path(__file__).parent.parent
PROJECT_ROOT = CLI_DIR.parent
CORE_DIR = PROJECT_ROOT / 'storageops-core'
for sub in ['utils', 'parsers', 'analyzers']:
    p = str(CORE_DIR / sub)
    if p not in sys.path:
        sys.path.insert(0, p)

from secret_scanner import scan as scan_secrets
from parse_awscli_debug import parse as parse_awscli
from parse_rclone_log import parse as parse_rclone
from parse_sigv4_error import parse_xml_error, diagnose as diagnose_sigv4
from parse_s5cmd_error import parse as parse_s5cmd_err
from parse_s5cmd_log import parse as parse_s5cmd
from parse_lifecycle_xml import parse as parse_lifecycle
from analyze_throughput import analyze as analyze_throughput
from detect_throttling import detect as detect_throttling
from analyze_policy import analyze as analyze_policy, analyze_inline_403
from analyze_metadata_amplification import analyze as analyze_metadata_amp
from analyze_cost import analyze as analyze_cost


# ── Tool Registry ────────────────────────────────────────────────────

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "secret_scan",
            "description": "Scan text for secrets (AK/SK, tokens, Authorization headers) and return redacted version. Always call this before processing any user-provided logs or configs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "The text to scan for secrets."
                    }
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "parse_awscli_debug",
            "description": "Parse awscli --debug log output. Extracts request/response cycles, signature details, retry events, error codes, and timing data. Use when the user provides awscli debug logs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "log": {
                        "type": "string",
                        "description": "The raw awscli --debug log content."
                    }
                },
                "required": ["log"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "parse_rclone_log",
            "description": "Parse rclone -vv log output. Extracts transfer records, MD5/ETag comparisons, corrupted-on-transfer detections, size diffs, and timeout errors. Use when the user provides rclone logs, especially for 'corrupted on transfer' or 'size differ' errors.",
            "parameters": {
                "type": "object",
                "properties": {
                    "log": {
                        "type": "string",
                        "description": "The raw rclone verbose log content."
                    }
                },
                "required": ["log"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "parse_sigv4_error",
            "description": "Parse a SignatureDoesNotMatch XML error response. Extracts CanonicalRequest, StringToSign, and diagnoses the root cause (clock skew, region mismatch, missing headers). Use when the user encounters SignatureDoesNotMatch or InvalidSignature.",
            "parameters": {
                "type": "object",
                "properties": {
                    "xml": {
                        "type": "string",
                        "description": "The XML error response body from the S3-compatible endpoint."
                    }
                },
                "required": ["xml"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "parse_s5cmd_error",
            "description": "Parse s5cmd error output (non-debug mode). Extracts error types like InvalidBucketName or AccessDenied. Also detects cross-tool patterns (e.g., awscli works but s5cmd fails).",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "The s5cmd error output text."
                    }
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "parse_s5cmd_log",
            "description": "Parse s5cmd --log debug output. Extracts status codes, timing, concurrency config, and throttling events (429/SlowDown). Use for s5cmd performance analysis.",
            "parameters": {
                "type": "object",
                "properties": {
                    "log": {
                        "type": "string",
                        "description": "The raw s5cmd --log debug output."
                    }
                },
                "required": ["log"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "parse_lifecycle_xml",
            "description": "Parse S3 Lifecycle Configuration XML. Extracts transition rules, expiration rules, and their filters. Auto-detects risks like small objects in Standard-IA.",
            "parameters": {
                "type": "object",
                "properties": {
                    "xml": {
                        "type": "string",
                        "description": "The lifecycle configuration XML."
                    }
                },
                "required": ["xml"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_policy",
            "description": "Analyze IAM and bucket policies to trace why access was denied. Requires JSON input with principal, action, resource, iam_policy, and bucket_policy. Use for cross-account, explicit-deny, or missing-allow diagnosis.",
            "parameters": {
                "type": "object",
                "properties": {
                    "policy_json": {
                        "type": "string",
                        "description": "JSON string containing principal, action, resource, iam_policy, bucket_policy."
                    }
                },
                "required": ["policy_json"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_inline_403",
            "description": "Analyze a 403 AccessDenied error when full policy JSON is not available. Extracts what it can from error messages and lists possible causes. Use when the user only has an error message, not the policies.",
            "parameters": {
                "type": "object",
                "properties": {
                    "error_text": {
                        "type": "string",
                        "description": "The 403 error response text (XML or log containing AccessDenied)."
                    }
                },
                "required": ["error_text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_throughput",
            "description": "Analyze timing data to identify performance bottlenecks. Requires JSON with object_size_mb, rtt_ms, bandwidth_mbps, and observed_throughput_mbps.",
            "parameters": {
                "type": "object",
                "properties": {
                    "data_json": {
                        "type": "string",
                        "description": "JSON string with object_size_mb, rtt_ms, bandwidth_mbps, observed_throughput_mbps, and optional timing breakdown."
                    }
                },
                "required": ["data_json"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "detect_throttling",
            "description": "Detect throttling patterns from error distribution data. Extracted from parsed logs. Requires JSON with status_codes and errors arrays.",
            "parameters": {
                "type": "object",
                "properties": {
                    "data_json": {
                        "type": "string",
                        "description": "JSON string with status_codes (map of HTTP status to count) and errors array."
                    }
                },
                "required": ["data_json"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_metadata_amplification",
            "description": "Estimate metadata amplification cost for mount/workspace scenarios. Requires JSON with rtt_ms and syscalls (map of syscall name to count). Use when object storage mount is slow for git/IDE/workspace operations.",
            "parameters": {
                "type": "object",
                "properties": {
                    "data_json": {
                        "type": "string",
                        "description": "JSON string with rtt_ms, syscalls (e.g., {\"stat\": 10000, \"open\": 2000}), and operation_name."
                    }
                },
                "required": ["data_json"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_cost",
            "description": "Analyze inventory data for per-prefix cost attribution. Detects small-object minimum-billable-size penalties in Standard-IA and minimum storage duration risks. Requires JSON with storage_price_per_gb and prefixes array.",
            "parameters": {
                "type": "object",
                "properties": {
                    "data_json": {
                        "type": "string",
                        "description": "JSON string with storage_price_per_gb and prefixes array."
                    }
                },
                "required": ["data_json"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "final_report",
            "description": "Submit the final diagnostic report. Call this when you have collected and analyzed all evidence. The report must include: summary, diagnosis conclusion, key evidence, root cause ranking, recommendations, risk notes, and next-step checklist.",
            "parameters": {
                "type": "object",
                "properties": {
                    "report": {
                        "type": "string",
                        "description": "The complete diagnostic report in markdown format following the diagnosis report template structure."
                    }
                },
                "required": ["report"]
            }
        }
    },
]


# ── Tool call dispatch ───────────────────────────────────────────────

def call_tool(name: str, arguments: dict) -> str:
    """Execute a tool and return its output as a JSON string."""
    try:
        if name == "secret_scan":
            result = scan_secrets(arguments["text"])
            return json.dumps(result, ensure_ascii=False, default=str)

        elif name == "parse_awscli_debug":
            result = parse_awscli(arguments["log"])
            return json.dumps(result, ensure_ascii=False, default=str)

        elif name == "parse_rclone_log":
            result = parse_rclone(arguments["log"])
            return json.dumps(result, ensure_ascii=False, default=str)

        elif name == "parse_sigv4_error":
            error = parse_xml_error(arguments["xml"])
            result = diagnose_sigv4(error)
            return json.dumps(result, ensure_ascii=False, default=str)

        elif name == "parse_s5cmd_error":
            result = parse_s5cmd_err(arguments["text"])
            return json.dumps(result, ensure_ascii=False, default=str)

        elif name == "parse_s5cmd_log":
            result = parse_s5cmd(arguments["log"])
            return json.dumps(result, ensure_ascii=False, default=str)

        elif name == "parse_lifecycle_xml":
            result = parse_lifecycle(arguments["xml"])
            return json.dumps(result, ensure_ascii=False, default=str)

        elif name == "analyze_policy":
            data = json.loads(arguments["policy_json"])
            result = analyze_policy(data)
            return json.dumps(result, ensure_ascii=False, default=str)

        elif name == "analyze_inline_403":
            result = analyze_inline_403(arguments["error_text"])
            return json.dumps(result, ensure_ascii=False, default=str)

        elif name == "analyze_throughput":
            data = json.loads(arguments["data_json"])
            result = analyze_throughput(data)
            return json.dumps(result, ensure_ascii=False, default=str)

        elif name == "detect_throttling":
            data = json.loads(arguments["data_json"])
            result = detect_throttling(data)
            return json.dumps(result, ensure_ascii=False, default=str)

        elif name == "analyze_metadata_amplification":
            data = json.loads(arguments["data_json"])
            result = analyze_metadata_amp(data)
            return json.dumps(result, ensure_ascii=False, default=str)

        elif name == "analyze_cost":
            data = json.loads(arguments["data_json"])
            result = analyze_cost(data)
            return json.dumps(result, ensure_ascii=False, default=str)

        elif name == "final_report":
            # Just pass through — the agent loop handles this
            return json.dumps({"status": "report_received"}, ensure_ascii=False)

        else:
            return json.dumps({"error": f"Unknown tool: {name}"})

    except Exception as e:
        return json.dumps({"error": str(e), "tool": name})


def get_tool_schemas_for_domain(domain: str = None) -> list:
    """Return tool schemas for a given domain, or all if no domain specified."""
    if domain is None:
        return TOOL_DEFINITIONS

    domain_tools = {
        "s3_protocol_compatibility": ["secret_scan", "parse_sigv4_error", "final_report"],
        "cli_sdk_behavior": ["secret_scan", "parse_rclone_log", "parse_awscli_debug",
                            "parse_s5cmd_error", "parse_s5cmd_log", "final_report"],
        "performance_throughput": ["secret_scan", "parse_awscli_debug", "parse_s5cmd_log",
                                   "analyze_throughput", "detect_throttling", "final_report"],
        "mount_filesystem_workspace": ["secret_scan", "analyze_metadata_amplification", "final_report"],
        "network_endpoint_access": ["secret_scan", "final_report"],
        "security_iam_policy": ["secret_scan", "analyze_policy", "analyze_inline_403", "final_report"],
        "lifecycle_cost": ["secret_scan", "parse_lifecycle_xml", "analyze_cost", "final_report"],
        "unknown": ["secret_scan", "final_report"],
    }

    names = domain_tools.get(domain, ["secret_scan", "final_report"])
    return [t for t in TOOL_DEFINITIONS if t["function"]["name"] in names]
