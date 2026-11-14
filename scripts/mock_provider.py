#!/usr/bin/env python3
"""Mock OpenAI-compatible provider used by the end-to-end launch test.

It drives one deterministic tool sequence so CI can prove the packaged product
actually starts, exposes the read-only tool set, and accepts a contract-valid
diagnosis — without a model key or a real bucket.

Sequence:
  1. call probe_endpoint on the mock server itself
  2. call submit_diagnosis citing the evidence id the tool returned
  3. reply with a short final text
"""

from __future__ import annotations

import argparse
import json
import re
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

TARGET_DEFAULT = "http://127.0.0.1:0/"


def _chunk(delta: dict, finish: str | None = None) -> dict:
    return {
        "id": "mock",
        "object": "chat.completion.chunk",
        "created": 0,
        "model": "mock-1",
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "storageops-mock"
    log_path: Path
    target: str

    def log_message(self, *args):  # keep CI output clean
        pass

    def _tool_text(self, message: dict) -> str:
        content = message.get("content")
        if isinstance(content, list):
            return " ".join(part.get("text", "") for part in content if isinstance(part, dict))
        return str(content or "")

    def do_POST(self):
        length = int(self.headers.get("content-length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"model": body.get("model"), "messages": body.get("messages"), "tools": body.get("tools")}) + "\n")

        messages = body.get("messages", [])
        # Pi does not guarantee a tool name on the tool message; classify by the
        # payload the tool returned instead, and cap the conversation so a broken
        # product fails the test instead of looping forever.
        tool_messages = [m for m in messages if m.get("role") == "tool"]
        last_tool = self._tool_text(tool_messages[-1]) if tool_messages else ""
        if len(messages) > 10:
            events = [
                _chunk({"role": "assistant", "content": "STOP: tool loop did not converge. Last tool result: " + last_tool[:300]}),
                _chunk({}, "stop"),
            ]
        elif "## Summary" in last_tool:
            events = [
                _chunk({"role": "assistant", "content": last_tool}),
                _chunk({}, "stop"),
            ]
        elif '"evidence_id"' in last_tool:
            match = re.search(r'"evidence_id"\s*:\s*"(ev_\d+)"', last_tool)
            evidence_id = match.group(1) if match else "ev_1"
            diagnosis = {
                "route": "storageops-network-endpoint-access",
                "provider": "unknown",
                "confidence": 0.71,
                "primary": {
                    "root_cause_type": "tcp",
                    "affected_layer": "network-path",
                    "mechanism": "The endpoint answered the probe, so the remaining failure is in the path or the client's connection handling.",
                },
                "evidence": [{"id": evidence_id, "claim": "Endpoint probe returned DNS, TCP, and HTTP measurements"}],
                "remediation": [
                    {"action": "Compare the probe result with the failing client's connect timeout", "risk": "none", "reversible": True, "apply_by": "human"}
                ],
                "falsifiers": ["The same client succeeds from another network path"],
            }
            events = [
                _chunk(
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call_2",
                                "type": "function",
                                "function": {"name": "submit_diagnosis", "arguments": json.dumps(diagnosis)},
                            }
                        ],
                    }
                ),
                _chunk({}, "tool_calls"),
            ]
        elif last_tool:
            events = [
                _chunk({"role": "assistant", "content": "TOOL ERROR: " + last_tool[:400]}),
                _chunk({}, "stop"),
            ]
        else:
            events = [
                _chunk(
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call_1",
                                "type": "function",
                                "function": {"name": "probe_endpoint", "arguments": json.dumps({"target": self.target})},
                            }
                        ],
                    }
                ),
                _chunk({}, "tool_calls"),
            ]

        events[-1]["usage"] = {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20}
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.end_headers()
        for event in events:
            self.wfile.write(f"data: {json.dumps(event)}\n\n".encode())
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=18080)
    parser.add_argument("--log", type=Path, required=True)
    args = parser.parse_args()
    target = f"http://127.0.0.1:{args.port}/"
    handler = type("BoundHandler", (Handler,), {"log_path": args.log, "target": target})
    HTTPServer(("127.0.0.1", args.port), handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
