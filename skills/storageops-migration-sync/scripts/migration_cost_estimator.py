#!/usr/bin/env python3
"""Estimate time and cost for object-storage migration.

Input (JSON or CSV) fields:
  object_count          – number of objects
  total_size_bytes      – total bytes (or total_size_gb / total_size_tb)
  bandwidth_mbps        – available bandwidth in Mbps
  source_provider       – e.g. aws_s3, gcs, azure_blob, ali_oss, tencent_cos,
                          baidu_bos, minio, custom
  dest_provider         – same enum as above
  source_egress_per_gb  – override source egress cost (USD / GB)
  dest_ingress_per_gb   – override dest ingress cost (USD / GB)
  put_cost_per_1000     – override dest PUT cost per 1000 requests
  get_cost_per_1000     – override source GET/LIST cost per 1000 requests
  overhead_factor       – multiplier for TCP / TLS overhead (default 1.05)

Output JSON:  {ok, summary: {total_time_hours, total_cost_usd, ...}, details: {...}}
"""

import argparse
import json
import sys
import csv

# Provider defaults – source egress, dest ingress, PUT/1K, GET-LIST/1K  (USD).
# Public-cloud transfer prices vary by region, tier, date, and contract. Keep
# egress unknown unless the user supplies source_egress_per_gb explicitly.
PROVIDERS: dict[str, dict[str, float | None]] = {
    "aws_s3":     {"egress": None,  "ingress": 0.0, "put": 0.005,  "get": 0.0004},
    "gcs":        {"egress": None,  "ingress": 0.0, "put": 0.005,  "get": 0.0004},
    "azure_blob": {"egress": None,  "ingress": 0.0, "put": 0.005,  "get": 0.0004},
    "ali_oss":    {"egress": None,  "ingress": 0.0, "put": 0.0015, "get": 0.00015},
    "tencent_cos":{"egress": None,  "ingress": 0.0, "put": 0.0015, "get": 0.00015},
    "baidu_bos":  {"egress": None,  "ingress": 0.0, "put": 0.0015, "get": 0.00015},
    "minio":      {"egress": 0.0,   "ingress": 0.0, "put": 0.0,    "get": 0.0},
    "custom":     {"egress": None,  "ingress": 0.0, "put": 0.0,    "get": 0.0},
}


def _resolve_total_bytes(row: dict) -> float:
    """Byte-priority: total_size_bytes > total_size_gb > total_size_tb."""
    if row.get("total_size_bytes"):
        return float(row["total_size_bytes"])
    if row.get("total_size_gb"):
        return float(row["total_size_gb"]) * 1e9
    if row.get("total_size_tb"):
        return float(row["total_size_tb"]) * 1e12
    raise ValueError("missing one of: total_size_bytes, total_size_gb, total_size_tb")


def _optional_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _cost_for(provider: str | None, field: str, override: object) -> float | None:
    """Resolve a cost field: explicit override > provider table > unknown."""
    parsed_override = _optional_float(override)
    if parsed_override is not None:
        return parsed_override
    return PROVIDERS.get(provider or "custom", PROVIDERS["custom"]).get(field, 0.0)


def estimate(row: dict) -> dict:
    """Return {ok, summary, details} for a single migration estimate."""
    obj_count = int(row.get("object_count", 0))
    total_bytes = _resolve_total_bytes(row)
    total_gb = total_bytes / 1e9
    bw_mbps = float(row.get("bandwidth_mbps", 1000))
    overhead = float(row.get("overhead_factor", 1.05))
    src = row.get("source_provider") or "custom"
    dst = row.get("dest_provider") or "custom"

    src_egress = _cost_for(src, "egress", row.get("source_egress_per_gb"))
    dst_ingress = _cost_for(dst, "ingress", row.get("dest_ingress_per_gb"))
    put_per_1k = _cost_for(dst, "put", row.get("put_cost_per_1000"))
    get_per_1k = _cost_for(src, "get", row.get("get_cost_per_1000"))

    eff_bw_mbps = bw_mbps / overhead
    transfer_sec = total_bytes * 8 / (eff_bw_mbps * 1e6)  # seconds
    transfer_h = transfer_sec / 3600

    # Request estimates: one GET/LIST per object on source, one PUT per object
    get_cost = (obj_count / 1000) * get_per_1k
    put_cost = (obj_count / 1000) * put_per_1k

    warnings: list[str] = []
    if src_egress is None:
        warnings.append(
            "source egress price is unknown; pass source_egress_per_gb for complete cost"
        )
    if dst_ingress is None:
        warnings.append(
            "destination ingress price is unknown; pass dest_ingress_per_gb for complete cost"
        )

    egress_cost = None if src_egress is None else total_gb * src_egress
    ingress_cost = None if dst_ingress is None else total_gb * dst_ingress
    request_cost = get_cost + put_cost
    known_transfer_cost = (egress_cost or 0.0) + (ingress_cost or 0.0)
    total_cost = known_transfer_cost + request_cost
    cost_complete = not warnings

    return {
        "ok": True,
        "summary": {
            "total_time_hours": round(transfer_h, 3),
            "total_time_days": round(transfer_h / 24, 2),
            "total_cost_usd": round(total_cost, 4),
            "cost_complete": cost_complete,
            "pricing_warnings": warnings,
        },
        "details": {
            "object_count": obj_count,
            "total_size_bytes": total_bytes,
            "total_size_gb": round(total_gb, 2),
            "total_size_tb": round(total_gb / 1000, 4),
            "bandwidth_mbps": bw_mbps,
            "overhead_factor": overhead,
            "effective_bandwidth_mbps": round(eff_bw_mbps, 2),
            "data_transfer_seconds": round(transfer_sec, 1),
            "data_transfer_hours": round(transfer_h, 3),
            "data_transfer_days": round(transfer_h / 24, 2),
            "source_provider": src,
            "dest_provider": dst,
            "source_egress_per_gb": src_egress,
            "dest_ingress_per_gb": dst_ingress,
            "source_egress_cost": None if egress_cost is None else round(egress_cost, 4),
            "dest_ingress_cost": None if ingress_cost is None else round(ingress_cost, 4),
            "request_estimates": {
                "get_list_requests": obj_count,
                "put_requests": obj_count,
                "get_list_cost_per_1000": get_per_1k,
                "put_cost_per_1000": put_per_1k,
                "get_list_cost": round(get_cost, 4),
                "put_cost": round(put_cost, 4),
                "total_requests_cost": round(request_cost, 4),
            },
        },
    }


def _parse_stdin() -> dict | list[dict]:
    raw = sys.stdin.read().strip()
    if not raw:
        raise SystemExit("no input on stdin")
    data = json.loads(raw)
    return data if isinstance(data, list) else [data]


def _parse_csv(path: str) -> list[dict]:
    with open(path) as fh:
        reader = csv.DictReader(fh)
        return [row for row in reader]


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Estimate time and cost for object-storage migration"
    )
    ap.add_argument("--file", help="Path to CSV file with migration parameters")
    ap.add_argument("--stdin", action="store_true", help="Read JSON from stdin")
    ap.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    args = ap.parse_args()

    inputs: list[dict] = []
    if args.stdin:
        inputs = _parse_stdin()
    elif args.file:
        inputs = _parse_csv(args.file)
    else:
        ap.print_help()
        raise SystemExit("specify --file or --stdin")

    results = [estimate(row) for row in inputs]
    out = results[0] if len(results) == 1 else results
    indent = 2 if args.pretty else None
    print(json.dumps(out, indent=indent))


if __name__ == "__main__":
    main()
