"""
Tests for mcp_server.

The mcp package is an optional dependency, so two levels are tested:
1. Graceful sys.exit(1) when the package is absent.
2. Consistency between TOOL_DEFINITIONS and dispatch_tool — the layer
   mcp_server wraps — ensuring every declared tool actually dispatches.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_CLI_DIR = Path(__file__).parent.parent
_CORE_DIR = _CLI_DIR.parent / "storageops-core"
for _sub in ("utils", "parsers", "analyzers"):
    _p = str(_CORE_DIR / _sub)
    if _p not in sys.path:
        sys.path.insert(0, _p)


class TestMcpServerMissingPackage(unittest.TestCase):

    def test_exits_gracefully_without_mcp(self):
        """run_mcp_server() must call sys.exit(1) when mcp is not installed."""
        blocked = {k: None for k in list(sys.modules) if k.startswith("mcp")}
        blocked.update({"mcp": None, "mcp.server": None, "mcp.server.stdio": None,
                        "mcp.types": None})
        with patch.dict("sys.modules", blocked):
            import importlib
            import storageops.mcp_server as ms
            importlib.reload(ms)
            with self.assertRaises(SystemExit) as ctx:
                ms.run_mcp_server()
            self.assertEqual(ctx.exception.code, 1)


class TestToolRegistryConsistency(unittest.TestCase):
    """TOOL_DEFINITIONS must be consistent with dispatch_tool — the layer mcp_server wraps."""

    def test_all_tools_have_name_description_schema(self):
        from storageops.tool_registry import TOOL_DEFINITIONS
        for t in TOOL_DEFINITIONS:
            self.assertIn("name", t)
            self.assertIn("description", t)
            self.assertIn("input_schema", t)
            self.assertIsInstance(t["description"], str)
            self.assertGreater(len(t["description"]), 10,
                               f"{t['name']}: description too short")

    def test_tool_names_unique(self):
        from storageops.tool_registry import TOOL_DEFINITIONS
        names = [t["name"] for t in TOOL_DEFINITIONS]
        self.assertEqual(len(names), len(set(names)))

    def test_dispatch_returns_dict_not_exception(self):
        from storageops.tool_registry import TOOL_DEFINITIONS, dispatch_tool
        minimal: dict[str, dict] = {
            "scan_secrets":             {"text": "no secrets"},
            "parse_rclone_log":         {"log_text": "rclone v1.60 log"},
            "parse_sigv4_error":        {"xml_text": "<Error><Code>X</Code></Error>"},
            "parse_awscli_debug":       {"log_text": "botocore DEBUG 2024"},
            "parse_lifecycle_xml":      {"xml_text": "<LifecycleConfiguration/>"},
            "analyze_policy":           {"error_text": "AccessDenied"},
            "analyze_cost":             {"prefixes": [{"prefix": "p/", "storage_class": "STANDARD_IA",
                                                       "object_count": 10, "total_size_bytes": 1024}]},
            "detect_throttling":        {"status_codes": {"200": 100}, "errors": [],
                                        "total_operations": 100},
            "generate_lifecycle_fix":   {"xml_text": "<LifecycleConfiguration/>"},
            "generate_policy_fix":      {"error_text": "AccessDenied"},
            "search_memory":            {"query": "test"},
            "parse_s5cmd_log":          {"log_text": "s5cmd cp s3://bucket/key local 200 OK"},
            "analyze_throughput":       {"object_size_mb": 100, "rtt_ms": 50,
                                        "bandwidth_mbps": 1000},
            "parse_cors_error":         {"log_text": "NoSuchCORSConfiguration"},
            "analyze_cors":             {"cors_data": {"cors_errors": [], "no_cors_config": True,
                                                       "preflight_failed": False,
                                                       "missing_headers": [],
                                                       "summary": {"error_count": 0,
                                                                   "needs_cors_config": True}}},
            "parse_replication_status": {"log_text": "ReplicationStatus: FAILED"},
            "analyze_replication":      {"replication_data": {
                                            "objects": [], "rules": [],
                                            "status_counts": {"FAILED": 1, "PENDING": 0, "COMPLETED": 0},
                                            "has_failures": True, "failure_reasons": [],
                                            "summary": {"total_objects": 0, "failure_rate_pct": 0.0}}},
            "parse_hadoop_s3a":         {"log_text": "S3AFileSystem error s3a://bucket/path"},
            "parse_network_diagnostics": {"diagnostic_text": "HTTP/1.1 200 OK"},
            "analyze_network":          {"parsed": {
                                            "endpoint": None,
                                            "is_vpc_endpoint": False,
                                            "is_s3_endpoint": False,
                                            "dns": {"status": None, "resolved_ips": [],
                                                    "nxdomain": False, "servfail": False,
                                                    "query_time_ms": None, "cname_chain": []},
                                            "tcp": {"connected": None, "refused": False,
                                                    "timed_out": False, "http_status": None,
                                                    "redirect_location": None, "server_header": None,
                                                    "timing": {}},
                                            "tls": {"error": None, "cert_common_name": None,
                                                    "verified": True},
                                            "latency": {"min_ms": None, "avg_ms": None,
                                                        "max_ms": None, "packet_loss_pct": None,
                                                        "host_unreachable": False},
                                            "hops": [],
                                            "summary": {"error_count": 0,
                                                        "root_cause_hint": "unknown"}}},
        }
        for t in TOOL_DEFINITIONS:
            name = t["name"]
            result = dispatch_tool(name, minimal.get(name, {}))
            self.assertIsInstance(result, dict, f"dispatch_tool({name!r}) must return dict")

    def test_unknown_tool_returns_error_dict(self):
        from storageops.tool_registry import dispatch_tool
        result = dispatch_tool("nonexistent_tool_xyz", {})
        self.assertIn("error", result)


if __name__ == "__main__":
    unittest.main()
