"""
Estimate metadata amplification cost for mount/workspace scenarios.

Given syscall profile and RTT, estimates per-operation latency and total
overhead compared to local SSD.

Usage:
    python -m storageops-core.analyzers.analyze_metadata_amplification syscalls.json
"""
import json
import sys
from pathlib import Path


# Typical per-syscall API translation for FUSE mounts
SYSCALL_API_MAP = {
    'stat': 'HeadObject',
    'lstat': 'HeadObject',
    'fstat': None,  # Already have fd
    'open': 'HeadObject (+ optional GetObject)',
    'read': 'GetObject (range)',
    'write': 'PutObject (on close/fsync)',
    'readdir': 'ListObjectsV2',
    'getdents': 'ListObjectsV2',
    'rename': 'CopyObject + DeleteObject',
    'unlink': 'DeleteObject',
    'fsync': 'PutObject (flush)',
    'truncate': 'GetObject + PutObject',
}

LOCAL_SSD_LATENCY_US = {
    'stat': 1,
    'open': 2,
    'read': 10,      # per 4KB block
    'write': 10,     # per 4KB block (cached)
    'readdir': 50,
    'rename': 5,
    'unlink': 5,
    'fsync': 1000,   # HDD: up to 10ms
}


def analyze(data: dict) -> dict:
    """
    Expected input:
    {
        "rtt_ms": 50,
        "syscalls": {
            "stat": 10000,
            "open": 2000,
            "read": 5000,
            "readdir": 200,
        },
        "operation_name": "git status"
    }
    """
    rtt_ms = data.get('rtt_ms', 0)
    syscalls = data.get('syscalls', {})
    operation_name = data.get('operation_name', 'unknown operation')

    # Per-syscall cost analysis
    syscall_analysis = []
    total_mount_ms = 0
    total_local_ms = 0

    for syscall, count in syscalls.items():
        api = SYSCALL_API_MAP.get(syscall, 'unknown')
        local_us = LOCAL_SSD_LATENCY_US.get(syscall, 10)

        # Mount cost: each syscall = 1 API call (optimistic)
        # Read/write have more complex cost, but for estimation: RTT per call
        mount_ms_per_call = rtt_ms * (2 if syscall in ('rename', 'truncate') else 1)
        mount_total = count * mount_ms_per_call
        local_total = count * local_us / 1000  # Convert to ms

        total_mount_ms += mount_total
        total_local_ms += local_total

        syscall_analysis.append({
            "syscall": syscall,
            "count": count,
            "api_call": api,
            "mount_latency_per_call_ms": round(mount_ms_per_call, 1),
            "mount_total_ms": round(mount_total, 1),
            "local_total_ms": round(local_total, 2),
            "amplification": round(mount_total / local_total, 1) if local_total > 0 else None,
        })

    total_mount_s = total_mount_ms / 1000
    total_local_s = total_local_ms / 1000

    # Severity
    if total_mount_s < 5:
        severity = "low"
    elif total_mount_s < 60:
        severity = "medium"
    else:
        severity = "high"

    return {
        "operation": operation_name,
        "rtt_ms": rtt_ms,
        "total_calls": sum(syscalls.values()),
        "estimated_mount_time_seconds": round(total_mount_s, 1),
        "estimated_local_time_seconds": round(total_local_s, 2),
        "amplification_factor": round(total_mount_s / total_local_s, 0) if total_local_s > 0 else None,
        "severity": severity,
        "syscall_breakdown": syscall_analysis,
        "conclusion": (
            f"Object storage mount adds approximately {round(total_mount_s, 1)}s latency "
            f"for '{operation_name}' at {rtt_ms}ms RTT, compared to ~{round(total_local_s, 2)}s on local SSD. "
            f"This is a {round(total_mount_s / total_local_s, 0)}x amplification."
        ) if total_local_s > 0 else "",
        "recommendation": (
            "Use local SSD for this workload. Object storage mount is not suitable "
            "for hot workspaces with high metadata operation counts."
        ) if severity in ('high', 'medium') else (
            "Metadata amplification is manageable at current RTT and operation count."
        ),
    }


def main():
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
        data = json.loads(path.read_text())
    else:
        data = json.loads(sys.stdin.read())

    result = analyze(data)
    result["ok"] = True
    result["module"] = "analyze_metadata_amplification"
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
