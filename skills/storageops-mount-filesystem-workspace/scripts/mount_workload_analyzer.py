#!/usr/bin/env python3
"""Offline analyzer for object-storage mount/workspace suitability.

Given a mount tool, a workload type, and (optionally) a file count and RTT, it
estimates metadata amplification, lists the POSIX features the workload needs
that an object-storage mount cannot provide, flags stale-cache risk, and gives a
suitability verdict.

Offline-only: no mounting, no network. Facts mirror
``references/posix-semantics.md`` and ``references/object-storage-as-filesystem.md``
(stat()->HeadObject ~RTT, rename()->Copy+Delete ~2xRTT non-atomic, no
flock/fcntl, no mmap, no partial writes).
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Dict, List, Optional

# Per-workload profile grounded in references/posix-semantics.md.
# stat: relative HeadObject intensity; needs_*: POSIX features the workload relies on.
WORKLOADS: Dict[str, dict] = {
    "git":       {"stat": "very-high", "needs_atomic_rename": True,  "needs_locking": True,  "needs_mmap": True,  "factor": 3.0},
    "npm":       {"stat": "high",      "needs_atomic_rename": True,  "needs_locking": False, "needs_mmap": False, "factor": 2.0},
    "build":     {"stat": "high",      "needs_atomic_rename": True,  "needs_locking": False, "needs_mmap": False, "factor": 2.0},
    "ide":       {"stat": "very-high", "needs_atomic_rename": True,  "needs_locking": False, "needs_mmap": False, "factor": 4.0},
    "database":  {"stat": "moderate",  "needs_atomic_rename": True,  "needs_locking": True,  "needs_mmap": True,  "factor": 1.5},
    "ls-find":   {"stat": "high",      "needs_atomic_rename": False, "needs_locking": False, "needs_mmap": False, "factor": 1.0},
    "read-only": {"stat": "low",       "needs_atomic_rename": False, "needs_locking": False, "needs_mmap": False, "factor": 0.2},
    "generic":   {"stat": "moderate",  "needs_atomic_rename": False, "needs_locking": False, "needs_mmap": False, "factor": 1.0},
}

# Tools with a local metadata/read cache (mitigates stat amplification but adds staleness).
CACHING_TOOLS = {"s3fs", "juicefs", "rclone", "mountpoint"}


def analyze(tool: str, workload: str, files: Optional[int], rtt_ms: Optional[float]) -> dict:
    tool = (tool or "generic").strip().lower()
    workload = (workload or "generic").strip().lower()
    profile = WORKLOADS.get(workload, WORKLOADS["generic"])

    # POSIX features the workload needs that an object mount cannot provide.
    unsupported: List[str] = []
    if profile["needs_atomic_rename"]:
        unsupported.append("atomic rename (rename = CopyObject + DeleteObject, ~2xRTT, not atomic)")
    if profile["needs_locking"]:
        unsupported.append("file locking (flock/fcntl unsupported on object mounts)")
    if profile["needs_mmap"]:
        unsupported.append("mmap (object not in the page cache)")

    # Metadata amplification: stat() -> HeadObject per file, repeated by workload.
    amplification = profile["stat"]
    est_head_ops = int(files * profile["factor"]) if isinstance(files, int) and files > 0 else None
    est_serialized_seconds = None
    if est_head_ops is not None and isinstance(rtt_ms, (int, float)) and rtt_ms > 0:
        # Worst-case upper bound if metadata ops are serialized (no cache hit).
        est_serialized_seconds = round(est_head_ops * rtt_ms / 1000.0, 1)

    caches = tool in CACHING_TOOLS
    # Increasing stat-cache TTL is the usual mitigation, but it trades freshness.
    stale_cache_risk = "elevated (raising stat-cache TTL to cut HeadObject load trades metadata freshness)" if caches else "n/a (no local metadata cache)"

    suitable = not unsupported and amplification in {"low", "moderate"}
    if suitable:
        recommendation = (
            "Mount is acceptable for this read-heavy/low-metadata workload. Enable read and metadata caching; "
            "treat data as effectively read-mostly."
        )
    else:
        reasons = []
        if unsupported:
            reasons.append("it depends on POSIX semantics object mounts do not provide")
        if amplification in {"high", "very-high"}:
            reasons.append("its stat()/HeadObject load amplifies badly over the network")
        recommendation = (
            "Do not run this workload directly on an object-storage mount because " + " and ".join(reasons) + ". "
            "Work on local disk (clone/build/run locally) and sync results to object storage, or use a POSIX filesystem. "
            "If a mount is unavoidable, enable local read+write caching and raise the stat-cache TTL (accepting staleness)."
        )

    return {
        "ok": True,
        "tool": tool,
        "workload": workload,
        "file_count": files,
        "metadata_amplification": amplification,
        "estimated_head_ops": est_head_ops,
        "estimated_serialized_seconds_worst_case": est_serialized_seconds,
        "unsupported_posix": unsupported,
        "stale_cache_risk": stale_cache_risk,
        "suitable": suitable,
        "recommendation": recommendation,
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tool", default="generic", help="s3fs/goofys/juicefs/mountpoint/rclone")
    ap.add_argument("--workload", default="generic", help=", ".join(sorted(WORKLOADS)))
    ap.add_argument("--files", type=int, default=None, help="Number of files/objects in the workload")
    ap.add_argument("--rtt-ms", type=float, default=None, help="Observed round-trip latency in ms")
    ap.add_argument("--json", action="store_true", help="Emit JSON")
    args = ap.parse_args(argv)

    result = analyze(args.tool, args.workload, args.files, args.rtt_ms)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"tool / workload : {result['tool']} / {result['workload']}")
        print(f"metadata amp.   : {result['metadata_amplification']}"
              + (f" (~{result['estimated_head_ops']} HeadObject ops)" if result["estimated_head_ops"] else ""))
        if result["estimated_serialized_seconds_worst_case"] is not None:
            print(f"worst-case wall : ~{result['estimated_serialized_seconds_worst_case']}s if serialized")
        if result["unsupported_posix"]:
            print("unsupported     :")
            for u in result["unsupported_posix"]:
                print(f"  - {u}")
        print(f"stale cache     : {result['stale_cache_risk']}")
        print(f"suitable        : {result['suitable']}")
        print(f"recommendation  : {result['recommendation']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
