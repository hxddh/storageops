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
_CORE_DIR = _CLI_DIR.parent.parent / "storageops-core"
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
            "scan_secrets":         {"text": "no secrets"},
            "parse_rclone_log":     {"log_text": "rclone v1.60 log"},
            "parse_sigv4_error":    {"xml_text": "<Error><Code>X</Code></Error>"},
            "parse_awscli_debug":   {"log_text": "botocore DEBUG 2024"},
            "parse_lifecycle_xml":  {"xml_text": "<LifecycleConfiguration/>"},
            "analyze_policy":       {"error_text": "AccessDenied"},
            "analyze_cost":         {"prefixes": [{"prefix": "p/", "storage_class": "STANDARD_IA",
                                                   "object_count": 10, "total_size_bytes": 1024}]},
            "detect_throttling":    {"status_codes": {"200": 100}, "errors": [],
                                    "total_operations": 100},
            "generate_lifecycle_fix": {"xml_text": "<LifecycleConfiguration/>"},
            "generate_policy_fix":  {"error_text": "AccessDenied"},
            "search_memory":        {"query": "test"},
            "analyze_throughput":   {"object_size_mb": 100, "rtt_ms": 50,
                                    "bandwidth_mbps": 1000},
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
