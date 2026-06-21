#!/usr/bin/env python3
"""Parse SigV4 SignatureDoesNotMatch evidence from XML or debug logs."""

from __future__ import annotations

import argparse
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


TAG_NAMES = {
    "Code",
    "Message",
    "StringToSign",
    "CanonicalRequest",
    "StringToSignBytes",
    "CanonicalRequestBytes",
}


def _strip_namespace(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _parse_xml_fields(text: str) -> tuple[dict[str, str], bool]:
    """Return (fields, used_regex_fallback). Fallback is lossy regex parsing."""
    fields: dict[str, str] = {}
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        for tag in TAG_NAMES:
            match = re.search(rf"<{tag}>(.*?)</{tag}>", text, re.S)
            if match:
                fields[tag] = match.group(1).strip()
        return fields, True
    for element in root.iter():
        tag = _strip_namespace(element.tag)
        if tag in TAG_NAMES and element.text:
            fields[tag] = element.text.strip()
    return fields, False


def _extract_block(lines: list[str], start_index: int) -> str:
    block: list[str] = []
    for raw in lines[start_index + 1 :]:
        line = raw.rstrip("\n")
        if not line:
            block.append("")
            continue
        if re.search(r"\b(?:DEBUG|INFO|WARN|ERROR)\b", line) and block:
            break
        if re.match(r"^\d{4}-\d{2}-\d{2}|\S+ - \S+ - \S+ -", line) and block:
            break
        block.append(line)
    return "\n".join(block).strip()


def _parse_debug_blocks(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if re.search(r"\bCanonicalRequest\s*:\s*$", line):
            fields.setdefault("ClientCanonicalRequest", _extract_block(lines, index))
        elif re.search(r"\bStringToSign\s*:\s*$", line):
            fields.setdefault("ClientStringToSign", _extract_block(lines, index))
    return fields


def _credential_scope(string_to_sign: str) -> dict[str, str]:
    lines = [line.strip() for line in string_to_sign.splitlines() if line.strip()]
    if len(lines) < 3:
        return {}
    scope = lines[2]
    parts = scope.split("/")
    result = {"credential_scope": scope}
    if len(parts) >= 4:
        result.update({"date": parts[0], "region": parts[1], "service": parts[2], "terminal": parts[3]})
    return result


def _canonical_summary(canonical_request: str) -> dict[str, Any]:
    lines = canonical_request.splitlines()
    if not lines:
        return {}
    summary: dict[str, Any] = {"method": lines[0]}
    if len(lines) > 1:
        summary["path"] = lines[1]
    if len(lines) > 2:
        summary["query"] = lines[2]
    # The payload hash is the last line of a *complete* canonical request (method,
    # path, query, headers, blank, signed-headers, hash = >= 6 lines). On a short
    # fragment lines[-1] is the path/query, not the hash — don't mislabel it.
    if len(lines) >= 6:
        summary["payload_hash"] = lines[-1]
    signed_headers_index = None
    for index, line in enumerate(lines):
        if ";" in line and re.fullmatch(r"[a-z0-9-]+(?:;[a-z0-9-]+)+", line):
            signed_headers_index = index
    if signed_headers_index is not None:
        summary["signed_headers"] = lines[signed_headers_index].split(";")
    return summary


def _likely_causes(fields: dict[str, str], canonical: dict[str, Any], scope: dict[str, str]) -> list[str]:
    causes: list[str] = []
    if scope.get("region"):
        causes.append("verify credential-scope region matches the endpoint region")
    if canonical.get("signed_headers"):
        causes.append("verify all signed headers are sent unchanged by proxies and SDK middleware")
    payload_hash = str(canonical.get("payload_hash", ""))
    if payload_hash and payload_hash not in {"UNSIGNED-PAYLOAD", "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"}:
        causes.append("verify payload hash matches the exact request body")
    if fields.get("ClientStringToSign") and fields.get("StringToSign") and fields["ClientStringToSign"] != fields["StringToSign"]:
        causes.append("client and service StringToSign differ; compare timestamp, scope, and canonical request hash")
    if not causes:
        causes.append("compare CanonicalRequest and StringToSign against the client debug trace")
    return causes


def parse_sigv4_evidence(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    fields, xml_parse_fallback = _parse_xml_fields(text)
    fields.update(_parse_debug_blocks(text))
    canonical_text = fields.get("CanonicalRequest") or fields.get("ClientCanonicalRequest", "")
    string_to_sign = fields.get("StringToSign") or fields.get("ClientStringToSign", "")
    scope = _credential_scope(string_to_sign)
    canonical = _canonical_summary(canonical_text)
    return {
        "ok": bool(fields),
        "input": str(path),
        "code": fields.get("Code"),
        "message": fields.get("Message"),
        "string_to_sign": string_to_sign or None,
        "canonical_request": canonical_text or None,
        "client_string_to_sign": fields.get("ClientStringToSign"),
        "client_canonical_request": fields.get("ClientCanonicalRequest"),
        "credential_scope": scope,
        "canonical_summary": canonical,
        "xml_parse_fallback": xml_parse_fallback,
        "likely_causes": _likely_causes(fields, canonical, scope),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="SignatureDoesNotMatch XML response or debug log")
    parser.add_argument("--json", action="store_true", help="Emit JSON report")
    args = parser.parse_args()

    result = parse_sigv4_evidence(args.input)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"Code: {result.get('code') or 'unknown'}")
        print(f"Credential scope: {result['credential_scope'].get('credential_scope', 'unknown')}")
        summary = result["canonical_summary"]
        if summary:
            print(f"Method: {summary.get('method', 'unknown')}")
            print(f"Path: {summary.get('path', 'unknown')}")
            print(f"Signed headers: {', '.join(summary.get('signed_headers', [])) or 'unknown'}")
        print("Likely causes:")
        for cause in result["likely_causes"]:
            print(f"- {cause}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
