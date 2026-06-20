#!/usr/bin/env python3
"""Compute / verify / reverse-engineer S3-style multipart ETags, offline.

The #1 cause of a post-migration "ETag changed but the bytes are identical"
surprise is re-chunking: the source uploaded an object in N parts and the
destination re-multiparted it with a different part size, so the part-MD5
concatenation differs and the ETag differs even though the object content is
byte-for-byte identical. This tool makes that deterministic to confirm.

Two analysis paths, both pure arithmetic / hashlib, never any network:

1. Compute from part MD5s (`--part-md5s`): the canonical AWS/MinIO/BOS algorithm
   = MD5 of the concatenated binary part MD5s, formatted `<hex>-N` (aws) or
   `-<hex>` (bos). Optionally verify against an `--expected` ETag.

2. Derive part size from total size + observed ETag (`--total-size` +
   `--observed-etag <hex>-N`): no part MD5s needed — recover the part-size band
   that yields N parts, list standard part sizes that match, and (with
   `--other-part-size`) show whether a different chunking reproduces the ETag.

Per the canonical matrix in references/checksum-etag.md, this AWS computation is
verified for AWS S3 and MinIO (unencrypted) and matches BOS's underlying hash.
OSS and COS do NOT use this computation, so this tool refuses to claim a match
for them; it reports shape only.

Emits a single JSON object. On bad/empty input it emits {"ok": false, ...}.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Providers whose multipart ETag is the AWS computation (MD5 of concatenated
# part MD5s). OSS/COS deliberately excluded — their computation is unverified.
_AWS_ALGO_PROVIDERS = ("aws", "minio", "bos")

# Standard multipart part sizes seen in the wild, in bytes. Both decimal (MB)
# and binary (MiB) because clients disagree; 5 MiB is the S3 minimum part size.
_STANDARD_PART_SIZES = {
    "5MiB": 5 * 1024 ** 2,
    "8MiB": 8 * 1024 ** 2,
    "10MiB": 10 * 1024 ** 2,
    "15MiB": 15 * 1024 ** 2,
    "16MiB": 16 * 1024 ** 2,
    "32MiB": 32 * 1024 ** 2,
    "64MiB": 64 * 1024 ** 2,
    "100MiB": 100 * 1024 ** 2,
    "128MiB": 128 * 1024 ** 2,
    "5MB": 5 * 1000 ** 2,
    "8MB": 8 * 1000 ** 2,
    "16MB": 16 * 1000 ** 2,
    "64MB": 64 * 1000 ** 2,
    "100MB": 100 * 1000 ** 2,
}

_HEX32 = re.compile(r"^[0-9a-fA-F]{32}$")
_MULTIPART_ETAG = re.compile(r'^"?([0-9a-fA-F]{32})-(\d+)"?$')
_BOS_ETAG = re.compile(r'^"?-([0-9a-fA-F]{32})"?$')


def parse_size(value: Optional[str]) -> Optional[int]:
    """Parse a byte count or human size like '64MB', '5 MiB' into bytes."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    m = re.fullmatch(r"\s*([0-9]*\.?[0-9]+)\s*([kKmMgGtT]?)([iI]?)[bB]?\s*", text)
    if not m:
        raise ValueError(f"unparseable size: {value!r}")
    num = float(m.group(1))
    unit = m.group(2).lower()
    binary = bool(m.group(3))
    if unit == "":
        return int(num)
    factor = {"k": 1, "m": 2, "g": 3, "t": 4}[unit]
    base = 1024 if binary else 1000
    return int(num * (base ** factor))


def compute_multipart_etag(part_md5s: List[str], fmt: str = "aws") -> Dict[str, Any]:
    """Compute the AWS-algorithm multipart ETag from per-part hex MD5s."""
    cleaned: List[str] = []
    for raw in part_md5s:
        token = raw.strip().strip('"')
        if not token:
            continue
        if not _HEX32.match(token):
            raise ValueError(f"not a 32-hex MD5: {raw!r}")
        cleaned.append(token.lower())
    if not cleaned:
        raise ValueError("no part MD5s provided")

    concat = b"".join(bytes.fromhex(h) for h in cleaned)
    digest = hashlib.md5(concat).hexdigest()
    n = len(cleaned)
    if fmt == "bos":
        etag = f"-{digest}"
    else:
        etag = f"{digest}-{n}"
    return {"etag": etag, "combined_md5": digest, "part_count": n, "format": fmt}


def _normalize_etag(etag: str) -> str:
    return etag.strip().strip('"')


def _parse_observed_etag(etag: str) -> Dict[str, Any]:
    s = _normalize_etag(etag)
    m = _MULTIPART_ETAG.match(s)
    if m:
        return {"shape": "aws-multipart", "md5": m.group(1).lower(), "part_count": int(m.group(2))}
    b = _BOS_ETAG.match(s)
    if b:
        return {"shape": "bos-multipart", "md5": b.group(1).lower(), "part_count": None}
    if _HEX32.match(s):
        return {"shape": "single-md5", "md5": s.lower(), "part_count": 1}
    return {"shape": "unknown", "md5": None, "part_count": None}


def derive_part_size(total_size: int, part_count: int) -> Dict[str, Any]:
    """Recover the uniform part-size band that yields ``part_count`` parts.

    A uniform upload of S bytes with part size P produces N = ceil(S/P) parts, so
    N parts ⟺ S/N ≤ P < S/(N-1). Returns inclusive integer [min, max] bounds
    (max is None for a single-part object) plus matching standard sizes.
    """
    if total_size <= 0:
        raise ValueError("total size must be > 0")
    if part_count < 1:
        raise ValueError("part count must be >= 1")

    p_min = math.ceil(total_size / part_count)
    if part_count == 1:
        p_max: Optional[int] = None
    else:
        # P < S/(N-1)  ⟹  largest integer P is ceil(S/(N-1)) - 1.
        p_max = math.ceil(total_size / (part_count - 1)) - 1
        if p_max < p_min:
            # No integer part size produces exactly this many parts.
            return {
                "part_size_min": p_min,
                "part_size_max": p_max,
                "feasible": False,
                "matching_standard_sizes": [],
            }

    matches = []
    for label, size in _STANDARD_PART_SIZES.items():
        if size >= p_min and (p_max is None or size <= p_max):
            matches.append({"label": label, "bytes": size})
    matches.sort(key=lambda d: d["bytes"])
    return {
        "part_size_min": p_min,
        "part_size_max": p_max,
        "feasible": True,
        "matching_standard_sizes": matches,
    }


def analyze_rechunk(total_size: int, observed_part_count: int, other_part_size: int) -> Dict[str, Any]:
    """Does re-chunking ``total_size`` at ``other_part_size`` reproduce the ETag?

    A uniform multipart ETag is reproduced only when the part *boundaries* are
    identical, i.e. the same part size. Two different part sizes that happen to
    yield the same part count still place the boundaries differently, so their
    ETags differ. We know only the part-size *band* the source used, so unless
    that band collapses to a single value we cannot confirm a match — we report
    the conditional honestly rather than overclaiming.
    """
    if other_part_size <= 0:
        raise ValueError("other part size must be > 0")
    other_count = math.ceil(total_size / other_part_size)
    band = derive_part_size(total_size, observed_part_count)
    in_band = (
        band.get("feasible")
        and other_part_size >= band["part_size_min"]
        and (band["part_size_max"] is None or other_part_size <= band["part_size_max"])
    )
    band_is_unique = band.get("feasible") and band["part_size_max"] == band["part_size_min"]

    if other_count != observed_part_count:
        verdict = "etag_differs"
        explanation = (
            f"Re-chunking {total_size} B at {other_part_size} B yields {other_count} parts, "
            f"not {observed_part_count}; the part-MD5 concatenation differs, so the multipart "
            f"ETag differs even though the object bytes are identical."
        )
    elif not in_band:
        verdict = "etag_differs"
        explanation = (
            f"{other_part_size} B falls outside the part-size band that produced the observed "
            f"ETag; the part boundaries differ, so the ETag differs."
        )
    elif band_is_unique:
        verdict = "etag_matches"
        explanation = (
            f"Re-chunking at {other_part_size} B is the only part size that yields "
            f"{observed_part_count} parts for this object, so the part boundaries — and the "
            f"multipart ETag — are reproduced (bytes unchanged)."
        )
    else:
        verdict = "etag_matches_iff_same_part_size"
        explanation = (
            f"{other_part_size} B also yields {observed_part_count} parts and is within the "
            f"plausible band [{band['part_size_min']}, {band['part_size_max']}] B, but other part "
            f"sizes in that band give the same count with different boundaries. The ETag is "
            f"reproduced only if the source used exactly {other_part_size} B parts; confirm the "
            f"source part size (aws s3api list-parts) to be certain."
        )
    return {
        "other_part_size": other_part_size,
        "other_part_count": other_count,
        "verdict": verdict,
        "explanation": explanation,
    }


def _read_lines(file: Optional[Path], use_stdin: bool) -> List[str]:
    if use_stdin:
        return sys.stdin.read().splitlines()
    if file:
        return file.read_text(encoding="utf-8").splitlines()
    return []


def run(args) -> Dict[str, Any]:
    provider = (args.provider or "aws").strip().lower()
    fmt = "bos" if provider == "bos" else "aws"

    # Path 1: compute from part MD5s.
    if args.part_md5s or args.stdin:
        lines = _read_lines(args.part_md5s, args.stdin)
        computed = compute_multipart_etag(lines, fmt=fmt)
        result: Dict[str, Any] = {
            "ok": True,
            "mode": "compute",
            "provider": provider,
            "computed_etag": computed["etag"],
            "combined_md5": computed["combined_md5"],
            "part_count": computed["part_count"],
        }
        if provider in ("oss", "cos"):
            result["provider_warning"] = (
                f"{provider.upper()} does not use the AWS multipart computation; the computed "
                f"value is the AWS/BOS algorithm and will NOT match a real {provider.upper()} "
                f"ETag. See references/checksum-etag.md."
            )
        if args.expected:
            exp = _normalize_etag(args.expected)
            match = exp.lower() == computed["etag"].lower()
            result["expected_etag"] = exp
            result["match"] = match
            result["summary"] = (
                f"Computed {computed['etag']} from {computed['part_count']} part MD5s; "
                + ("matches the expected ETag." if match else "does NOT match the expected ETag.")
            )
            if not match and provider not in ("oss", "cos"):
                result["recommendation"] = (
                    "Bytes/part-MD5s differ from the source, OR the object was re-multiparted with a "
                    "different part size. Confirm the part list (aws s3api list-parts) and part size "
                    "used on each side; re-upload with the source part size to reproduce the ETag."
                )
        else:
            result["summary"] = (
                f"Computed multipart ETag {computed['etag']} from {computed['part_count']} part MD5s "
                f"(MD5 of concatenated part MD5s)."
            )
        return result

    # Path 2: derive part size from total size + observed ETag.
    if args.total_size is not None and args.observed_etag:
        total = parse_size(args.total_size)
        if total is None:
            raise ValueError("invalid total size")
        observed = _parse_observed_etag(args.observed_etag)
        if observed["part_count"] is None:
            raise ValueError(
                "observed ETag has no part count (BOS leading-dash ETags omit it); "
                "supply --part-count, or an AWS-shape '<hex>-N' ETag"
            )
        part_count = args.part_count if args.part_count is not None else observed["part_count"]
        band = derive_part_size(total, part_count)
        result = {
            "ok": True,
            "mode": "derive",
            "provider": provider,
            "total_size": total,
            "observed_etag": _normalize_etag(args.observed_etag),
            "observed_shape": observed["shape"],
            "part_count": part_count,
            "part_size_min": band["part_size_min"],
            "part_size_max": band["part_size_max"],
            "matching_standard_sizes": band["matching_standard_sizes"],
        }
        if not band.get("feasible"):
            result["summary"] = (
                f"No uniform part size produces exactly {part_count} parts for a {total} B object; "
                f"the upload likely used non-uniform parts."
            )
            return result
        std = ", ".join(d["label"] for d in band["matching_standard_sizes"]) or "none of the common sizes"
        pmax = band["part_size_max"]
        result["summary"] = (
            f"A {total} B object split into {part_count} parts used a part size in "
            f"[{band['part_size_min']}, {pmax if pmax is not None else '∞'}] B "
            f"(standard sizes that fit: {std})."
        )
        if args.other_part_size is not None:
            other = parse_size(args.other_part_size)
            if other is None:
                raise ValueError("invalid --other-part-size")
            result["rechunk_analysis"] = analyze_rechunk(total, part_count, other)
        return result

    raise ValueError(
        "nothing to do: provide --part-md5s/--stdin to compute, or --total-size with "
        "--observed-etag to derive the part size"
    )


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Compute/verify/reverse S3-style multipart ETags")
    ap.add_argument("--part-md5s", type=Path, help="File of per-part hex MD5s (one per line)")
    ap.add_argument("--stdin", action="store_true", help="Read per-part hex MD5s from stdin")
    ap.add_argument("--expected", help="Expected ETag to verify the computed value against")
    ap.add_argument("--total-size", help="Object size (bytes or human, e.g. 1GiB) for derive mode")
    ap.add_argument("--observed-etag", help="Observed multipart ETag '<hex>-N' for derive mode")
    ap.add_argument("--part-count", type=int, default=None,
                    help="Override part count (needed for BOS leading-dash ETags)")
    ap.add_argument("--other-part-size", help="Compare a different part size: does it reproduce the ETag?")
    ap.add_argument("--provider", default="aws",
                    help="Provider hint: aws/minio/bos use the AWS algorithm; oss/cos are flagged")
    args = ap.parse_args(argv)

    try:
        result = run(args)
    except (ValueError, TypeError, OSError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 0

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
