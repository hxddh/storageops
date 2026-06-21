#!/usr/bin/env python3
"""Flag IA-class objects below 128 KB min-billable-size threshold,
compute penalty, estimate savings from consolidation.

CSV columns (required header): key,size_bytes,storage_class
Output: JSON {ok, summary, class_breakdown, recommendations, details}"""

import argparse, csv, json, re, sys

# Minimum billable object size (bytes) per storage class family
_MIN_BILLABLE = {
    "STANDARD": 0,
    "STANDARD_IA": 128 << 10,
    "ONEZONE_IA": 128 << 10,
    "GLACIER_IR": 128 << 10,
    "GLACIER": 40 << 10,
    "DEEP_ARCHIVE": 40 << 10,
    # Intelligent-Tiering has NO per-object minimum billable size. Objects under
    # 128 KB are simply never auto-tiered (and incur a monitoring/automation fee),
    # so there is no min-size storage penalty to flag here.
    "INTELLIGENT_TIERING": 0,
}


def _min_billable(storage_class: str) -> int:
    # Normalise spelling so "GLACIER IR" / "Glacier Instant Retrieval" / "glacier-ir"
    # all match GLACIER_IR rather than falling through to plain GLACIER.
    upper = re.sub(r"[ \-]+", "_", storage_class.upper())
    if "INSTANT" in upper and "GLACIER" in upper:
        upper = "GLACIER_IR"
    for marker in sorted(_MIN_BILLABLE, key=len, reverse=True):
        if marker in upper:
            return _MIN_BILLABLE[marker]
    return 0


def _read_rows(file_path: str | None, use_stdin: bool) -> dict:
    """Read CSV rows; return {"ok":False,error} or {"ok":True,rows}."""
    if file_path:
        fh = open(file_path, newline="", encoding="utf-8")
    elif use_stdin:
        fh = sys.stdin
    else:
        return {"ok": False, "error": "Provide --file or --stdin"}

    with fh:
        reader = csv.DictReader(fh)
        rows: list[dict] = []
        for i, row in enumerate(reader, start=2):
            try:
                row["size_bytes"] = int(row["size_bytes"])
            except (ValueError, KeyError):
                return {"ok": False, "error": f"Invalid/missing size_bytes at row {i}"}
            row["_line"] = i
            rows.append(row)
    return {"ok": True, "rows": rows}


def run(file_path: str | None = None, use_stdin: bool = False) -> dict:
    result = _read_rows(file_path, use_stdin)
    if not result["ok"]:
        return result
    rows = result["rows"]

    total = len(rows)
    if total == 0:
        return {"ok": True, "summary": {"total_objects": 0, "flagged": 0}, "details": []}

    flagged, total_penalty, ia_count = [], 0, 0
    for r in rows:
        sc = r.get("storage_class", "STANDARD")
        size = int(r["size_bytes"])
        mb = _min_billable(sc)
        if mb > 0:
            ia_count += 1
        if mb > 0 and size < mb:
            penalty = mb - size
            total_penalty += penalty
            flagged.append({
                "key": r.get("key", ""),
                "size_bytes": size,
                "storage_class": sc,
                "min_billable": mb,
                "penalty_bytes": penalty,
                "penalty_kb": round(penalty / 1024, 2),
                "multiplier": round(mb / max(size, 1), 2),
                "line": r.get("_line"),
            })

    fc = len(flagged)
    pct = round(fc / total * 100, 2) if total else 0

    class_bd: dict[str, dict] = {}
    for f in flagged:
        sc = f["storage_class"]
        class_bd.setdefault(sc, {"count": 0, "penalty_bytes": 0})
        class_bd[sc]["count"] += 1
        class_bd[sc]["penalty_bytes"] += f["penalty_bytes"]
    for v in class_bd.values():
        v["penalty_kb"] = round(v["penalty_bytes"] / 1024, 2)

    recs = []
    if fc:
        recs = [
            "Consolidate small IA objects (tar/zip) into >=128 KB bundles",
            "Consider migrating small IA objects to STANDARD if infrequently accessed",
        ]

    return {
        "ok": True,
        "summary": {
            "total_objects": total,
            "ia_objects": ia_count,
            "flagged": fc,
            "flagged_pct": pct,
            "total_penalty_bytes": total_penalty,
            "total_penalty_kb": round(total_penalty / 1024, 2),
            "penalty_gb_months": round(total_penalty / (1024 ** 3), 6),
        },
        "class_breakdown": class_bd,
        "recommendations": recs,
        "details": flagged,
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Small-object penalty analyzer")
    p.add_argument("--file", "-f", help="CSV inventory (key,size_bytes,storage_class)")
    p.add_argument("--stdin", action="store_true", help="Read CSV from stdin")
    p.add_argument("--pretty", "-p", action="store_true", help="Pretty-print JSON")
    args = p.parse_args()
    if not args.file and not args.stdin:
        p.error("Either --file or --stdin is required")
    result = run(file_path=args.file, use_stdin=args.stdin)
    json.dump(result, sys.stdout, indent=2 if args.pretty else None,
              default=str, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
