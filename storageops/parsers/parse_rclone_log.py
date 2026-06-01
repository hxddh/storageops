"""
Parse rclone -vv --dump headers output into structured transfer records.

Extracts transfer status, MD5/ETag comparisons, retry events, and errors
like "corrupted on transfer" and "size differ".

Usage:
    cat rclone.log | python -m storageops-core.parsers.parse_rclone_log
    python -m storageops-core.parsers.parse_rclone_log rclone.log
"""
import re
import sys
import json
from pathlib import Path

PATTERNS = {
    'version': re.compile(r'rclone\s+v([\d.]+)'),
    'transfer_start': re.compile(
        r'(\S+):\s+(Need to transfer|Sizes differ|Copied)'
    ),
    'server_side_copy': re.compile(
        r'(\S+):\s+Copied \(server-(?:side|side) copy\)', re.IGNORECASE
    ),
    'md5_source': re.compile(
        r'(\S+):\s+MD5\s*=\s*([0-9a-f]{12,}(?:-\d+)?)\s+from\s+(source|src)',
        re.IGNORECASE
    ),
    'md5_dest': re.compile(
        r'(\S+):\s+MD5\s*=\s*([0-9a-f]{12,}(?:-\d+)?)\s+from\s+(destination|dest)',
        re.IGNORECASE
    ),
    'corrupted': re.compile(
        r"(\S+):\s+corrupted on transfer:\s*(.*?)(?=\n\s*\n?\d{4}|\n\s*\n?\S+:|$)",
        re.IGNORECASE
    ),
    'corrupted_md5_inline': re.compile(
        r'(\S+):\s+corrupted on transfer:\s+md5 hash differ\s+"([^"]+)"\s+vs\s+"([^"]+)"',
        re.IGNORECASE
    ),
    'size_diff': re.compile(
        r"(\S+):\s+(?:Sizes differ|size differ|cannot check size)"
    ),
    'size_diff_detail': re.compile(
        r'(\S+):\s+Sizes differ\s+\(src=(\d+),\s+dst=(\d+)\)',
        re.IGNORECASE
    ),
    'failed_copy': re.compile(
        r"(\S+):\s+Removing failed copy"
    ),
    'timeout_error': re.compile(
        r"(\S+):\s+(?:Failed to copy|error):\s*(.*?)(?=\n|$)",
        re.IGNORECASE
    ),
    'retry': re.compile(
        r'Attempt\s+(\d+)/(\d+)\s+failed.*?(\d+)\s+errors',
        re.IGNORECASE
    ),
    'transfer_ok': re.compile(
        r'(\S+):\s+Copied \(new\)'
    ),
}


def etag_type(etag: str) -> str:
    """Classify ETag format."""
    etag = etag.strip('"').strip("'")
    if re.match(r'^[0-9a-f]{32}$', etag):
        return "single_put_md5"
    if re.match(r'^[0-9a-f]{32}-\d+$', etag):
        return "multipart_etag"
    return "unknown"


def parse(text: str) -> dict:
    """Parse rclone verbose log into structured records."""
    transfers = {}
    corrupted = []
    failed = []
    size_diffs = []
    retries = []
    version = None

    # Extract version
    vm = PATTERNS['version'].search(text)
    if vm:
        version = vm.group(1)

    # Extract MD5s
    for m in PATTERNS['md5_source'].finditer(text):
        fname = m.group(1)
        if fname not in transfers:
            transfers[fname] = {}
        transfers[fname]['md5_source'] = m.group(2)
        transfers[fname]['source_etag_type'] = etag_type(m.group(2))

    for m in PATTERNS['md5_dest'].finditer(text):
        fname = m.group(1)
        if fname not in transfers:
            transfers[fname] = {}
        transfers[fname]['md5_dest'] = m.group(2)
        transfers[fname]['dest_etag_type'] = etag_type(m.group(2))

    # Extract corrupted (full reason line)
    for m in PATTERNS['corrupted'].finditer(text):
        fname = m.group(1)
        reason = m.group(2).strip()
        corrupted.append({
            "file": fname,
            "reason": reason,
            "md5_source": transfers.get(fname, {}).get('md5_source'),
            "md5_dest": transfers.get(fname, {}).get('md5_dest'),
        })
        if fname in transfers:
            transfers[fname]['status'] = 'corrupted'

    # Extract corrupted MD5 inline ("md5 hash differ "a" vs "b"")
    for m in PATTERNS['corrupted_md5_inline'].finditer(text):
        fname = m.group(1)
        src_md5 = m.group(2)
        dst_md5 = m.group(3)
        if fname not in transfers:
            transfers[fname] = {}
        transfers[fname]['md5_source'] = src_md5
        transfers[fname]['source_etag_type'] = etag_type(src_md5)
        transfers[fname]['md5_dest'] = dst_md5
        transfers[fname]['dest_etag_type'] = etag_type(dst_md5)
        transfers[fname]['status'] = 'corrupted'
        # Only add if not already in corrupted list
        if not any(c['file'] == fname for c in corrupted):
            corrupted.append({
                "file": fname,
                "reason": f"md5 hash differ \"{src_md5}\" vs \"{dst_md5}\"",
                "md5_source": src_md5,
                "md5_dest": dst_md5,
            })

    # Extract failed copies
    for m in PATTERNS['failed_copy'].finditer(text):
        fname = m.group(1)
        failed.append(fname)
        if fname in transfers:
            transfers[fname]['status'] = 'failed'

    # Extract size diffs
    for m in PATTERNS['size_diff'].finditer(text):
        fname = m.group(1)
        size_diffs.append(fname)
        if fname in transfers:
            transfers[fname]['status'] = 'size_diff'

    # Extract size diff with detail (src=X, dst=Y)
    for m in PATTERNS['size_diff_detail'].finditer(text):
        fname = m.group(1)
        if fname not in transfers:
            transfers[fname] = {}
        transfers[fname]['size_src'] = int(m.group(2))
        transfers[fname]['size_dst'] = int(m.group(3))
        transfers[fname]['status'] = 'size_diff'
        if fname not in size_diffs:
            size_diffs.append(fname)

    # Extract timeout / deadline errors
    timeouts = []
    for m in PATTERNS['timeout_error'].finditer(text):
        fname = m.group(1)
        error_msg = m.group(2).strip()
        if fname not in transfers:
            transfers[fname] = {}
        transfers[fname]['status'] = 'timeout'
        timeouts.append({"file": fname, "error": error_msg})
        failed.append(fname)

    # Extract successful
    for m in PATTERNS['transfer_ok'].finditer(text):
        fname = m.group(1)
        if fname in transfers:
            transfers[fname]['status'] = 'ok'

    # Extract server-side copies
    for m in PATTERNS['server_side_copy'].finditer(text):
        fname = m.group(1)
        if fname in transfers:
            transfers[fname]['transfer_type'] = 'server_side'

    # Retries
    for m in PATTERNS['retry'].finditer(text):
        retries.append({
            "attempt": int(m.group(1)),
            "max_attempts": int(m.group(2)),
            "error_count": int(m.group(3)),
        })

    # Classify issues
    etag_format_mismatch = any(
        t.get('source_etag_type') == 'single_put_md5' and
        t.get('dest_etag_type') == 'multipart_etag'
        for t in transfers.values()
    )

    return {
        "version": version,
        "transfers": {k: v for k, v in transfers.items()},
        "corrupted": corrupted,
        "failed": failed,
        "size_diffs": size_diffs,
        "timeouts": timeouts,
        "retries": retries,
        "summary": {
            "total_files": len(transfers),
            "corrupted_count": len(corrupted),
            "failed_count": len(failed),
            "size_diff_count": len(size_diffs),
            "timeout_count": len(timeouts),
            "success_count": sum(1 for t in transfers.values() if t.get('status') == 'ok'),
            "server_side_count": sum(
                1 for t in transfers.values() if t.get('transfer_type') == 'server_side'
            ),
            "etag_format_mismatch_detected": etag_format_mismatch,
            "root_cause_likely": (
                "multipart_etag_format_mismatch" if etag_format_mismatch and corrupted
                else "unknown"
            ),
        },
    }


def main():
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
        text = path.read_text(encoding='utf-8', errors='replace')
    else:
        text = sys.stdin.read()

    result = parse(text)
    result["ok"] = True
    result["module"] = "parse_rclone_log"
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))


if __name__ == '__main__':
    main()
