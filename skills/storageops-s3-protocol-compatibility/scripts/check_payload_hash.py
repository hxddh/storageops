#!/usr/bin/env python3
"""Offline check: is x-amz-content-sha256 computed over the wrong bytes?

Diagnoses the BadDigest / BadDigestSHA256 class where a client computes the SigV4
payload hash over the *pre-encoding* bytes (e.g. the uncompressed file) while
sending an encoded body (e.g. gzip with `Content-Encoding: gzip`). The server
hashes the body it actually received, so the digests differ.

Offline-only: reads local files, computes SHA-256, never signs, never contacts a
cloud endpoint. This is an optional falsifier — it confirms or refutes the
mechanism; it does not route.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def analyze(
    raw_bytes: bytes,
    declared_sha256: str,
    content_encoding: str | None,
    sent_bytes: bytes | None,
) -> dict:
    raw_sha = _sha256(raw_bytes)
    sent_sha = _sha256(sent_bytes) if sent_bytes is not None else None
    declared = (declared_sha256 or "").strip().lower()
    encoding = (content_encoding or "").strip().lower() or None
    transform_present = bool(encoding) or (sent_sha is not None and sent_sha != raw_sha)

    if declared and declared == raw_sha:
        matches = "raw"
    elif sent_sha is not None and declared == sent_sha:
        matches = "sent"
    else:
        matches = "none"

    notes: list[str] = []
    if encoding and sent_sha is None:
        notes.append(
            "compressed hash is implementation-dependent (gzip embeds mtime/OS); "
            "capture the exact sent body with --sent-file for a byte-exact match"
        )

    if matches == "sent":
        verdict = "ok"
        likely_cause = (
            "declared x-amz-content-sha256 matches the bytes actually sent; "
            "the payload hash is not the problem — look elsewhere "
            "(clock skew, signed headers, proxy re-encoding)"
        )
        fix = "No payload-hash change needed."
    elif matches == "raw" and transform_present:
        verdict = "payload_hash_over_pre_encoding"
        likely_cause = (
            "x-amz-content-sha256 was computed over the pre-encoding (raw) bytes, "
            "but the body on the wire is encoded/transformed; the server hashes the "
            "received body, so the digests differ (BadDigest / BadDigestSHA256)"
        )
        fix = (
            "Compute x-amz-content-sha256 over the bytes actually transmitted "
            "(e.g. sha256 of the gzip-compressed body), or let the SDK compute the "
            "payload hash after compression."
        )
    elif matches == "raw":
        verdict = "declared_matches_raw_no_transform_evidence"
        likely_cause = (
            "declared hash matches the raw file and no body transform was provided; "
            "if a Content-Encoding/compression is applied at send time this is the "
            "bug, otherwise the digest matches and the problem is elsewhere"
        )
        fix = "Provide --content-encoding or --sent-file to confirm the mechanism."
    else:
        verdict = "unknown"
        likely_cause = (
            "declared hash matches neither the raw file nor the provided sent body; "
            "the hashed bytes differ from both (different object, different transform, "
            "or wrong sample)"
        )
        fix = "Provide the exact bytes sent (--sent-file) to localize."

    return {
        "raw_sha256": raw_sha,
        "sent_sha256": sent_sha,
        "declared_sha256": declared,
        "content_encoding": encoding,
        "declared_matches": matches,
        "verdict": verdict,
        "likely_cause": likely_cause,
        "fix": fix,
        "notes": notes,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-file", required=True, type=Path, help="The original (pre-encoding) object bytes")
    parser.add_argument("--declared-sha256", required=True, help="The x-amz-content-sha256 value the client sent")
    parser.add_argument("--content-encoding", default=None, help="Content-Encoding applied to the body (e.g. gzip)")
    parser.add_argument("--sent-file", default=None, type=Path, help="The exact bytes sent on the wire, if captured")
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    args = parser.parse_args(argv)

    declared = (args.declared_sha256 or "").strip().lower()
    if len(declared) != 64 or any(c not in "0123456789abcdef" for c in declared):
        print("error: --declared-sha256 must be a 64-character hex digest", file=sys.stderr)
        return 2

    raw_bytes = args.raw_file.read_bytes()
    sent_bytes = args.sent_file.read_bytes() if args.sent_file else None
    result = analyze(raw_bytes, declared, args.content_encoding, sent_bytes)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"declared_matches : {result['declared_matches']}")
        print(f"verdict          : {result['verdict']}")
        print(f"likely_cause     : {result['likely_cause']}")
        print(f"fix              : {result['fix']}")
        for note in result["notes"]:
            print(f"note             : {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
