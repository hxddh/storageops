"""
Analyze inventory data for per-prefix cost attribution and small-object penalties.

Identifies prefixes with disproportionate costs due to minimum billable size,
minimum storage duration penalties, or lifecycle transition issues.

Usage:
    python -m storageops-core.analyzers.analyze_cost inventory.json
"""
import json
import sys
from pathlib import Path


# Pricing is parameterized — no hardcoded rates
MIN_BILLABLE_SIZE_KB = {
    'STANDARD': 0,
    'STANDARD_IA': 128,
    'ONEZONE_IA': 128,
    'GLACIER': 0,  # 40KB overhead but not minimum billable
    'DEEP_ARCHIVE': 0,
}

MIN_STORAGE_DAYS = {
    'STANDARD': 0,
    'STANDARD_IA': 30,
    'ONEZONE_IA': 30,
    'GLACIER': 90,
    'DEEP_ARCHIVE': 180,
}


def analyze(data: dict) -> dict:
    """
    Expected input:
    {
        "storage_price_per_gb": {"STANDARD": 0.023, "STANDARD_IA": 0.0125, ...},
        "prefixes": [
            {
                "prefix": "logs/",
                "storage_class": "STANDARD_IA",
                "object_count": 1000000,
                "total_size_bytes": 1073741824,
                "avg_object_age_days": 45,
            },
            ...
        ]
    }
    """
    prices = data.get('storage_price_per_gb', {})
    prefixes = data.get('prefixes', [])

    results = []
    total_actual_cost = 0
    total_billable_cost = 0
    total_penalty_cost = 0
    issues = []

    for p in prefixes:
        prefix = p['prefix']
        storage_class = p.get('storage_class', 'STANDARD').upper()
        count = p['object_count']
        total_bytes = p['total_size_bytes']
        age_days = p.get('avg_object_age_days', 0)

        actual_gb = total_bytes / (1024 ** 3)
        price_per_gb = prices.get(storage_class, 0)

        # Actual cost
        actual_cost = actual_gb * price_per_gb

        # Minimum billable size penalty
        min_size_kb = MIN_BILLABLE_SIZE_KB.get(storage_class, 0)
        penalty_bytes = 0
        if min_size_kb > 0:
            avg_size_kb = total_bytes / count / 1024 if count > 0 else 0
            if avg_size_kb < min_size_kb:
                penalty_bytes = count * (min_size_kb * 1024)
                penalty_gb = penalty_bytes / (1024 ** 3)
                penalty_cost = penalty_gb * price_per_gb
            else:
                penalty_gb = 0
                penalty_cost = 0
        else:
            penalty_gb = 0
            penalty_cost = 0

        billable_gb = max(actual_gb, penalty_gb) if penalty_gb > 0 else actual_gb
        billable_cost = billable_gb * price_per_gb

        # Minimum storage duration check
        min_days = MIN_STORAGE_DAYS.get(storage_class, 0)
        duration_risk = False
        if min_days > 0 and age_days < min_days:
            duration_risk = True
            issues.append({
                "prefix": prefix,
                "type": "minimum_duration_at_risk",
                "storage_class": storage_class,
                "current_age_days": age_days,
                "required_min_days": min_days,
                "note": f"Objects may incur minimum duration charge if deleted before {min_days} days.",
            })

        # Small object issue
        if penalty_cost > 0:
            issues.append({
                "prefix": prefix,
                "type": "minimum_billable_size_penalty",
                "storage_class": storage_class,
                "object_count": count,
                "actual_gb": round(actual_gb, 4),
                "billable_gb": round(billable_gb, 4),
                "penalty_multiplier": round(billable_gb / actual_gb, 1) if actual_gb > 0 else 0,
                "penalty_cost": round(penalty_cost, 2),
            })

        total_actual_cost += actual_cost
        total_billable_cost += billable_cost
        total_penalty_cost += penalty_cost

        results.append({
            "prefix": prefix,
            "storage_class": storage_class,
            "object_count": count,
            "actual_gb": round(actual_gb, 4),
            "billable_gb": round(billable_gb, 4),
            "actual_monthly_cost": round(actual_cost, 2),
            "billable_monthly_cost": round(billable_cost, 2),
            "penalty_multiplier": round(billable_cost / actual_cost, 1) if actual_cost > 0 else 0,
            "has_min_size_penalty": penalty_cost > 0,
            "has_duration_risk": duration_risk,
        })

    # Sort by cost (highest first)
    results.sort(key=lambda r: r['billable_monthly_cost'], reverse=True)

    return {
        "prefix_analysis": results,
        "issues": issues,
        "issue_count": len(issues),
        "totals": {
            "actual_monthly_cost": round(total_actual_cost, 2),
            "billable_monthly_cost": round(total_billable_cost, 2),
            "penalty_cost": round(total_penalty_cost, 2),
            "penalty_percent": round(total_penalty_cost / total_billable_cost * 100, 1)
            if total_billable_cost > 0 else 0,
        },
        "recommendations": [
            "Move small objects (<128KB) from Standard-IA to Standard to avoid minimum billable size penalty.",
            "Use lifecycle filter to exclude objects below 128KB from IA transition.",
            "Aggregate small objects (tar/zip) before transition to infrequent access tiers.",
            "Review minimum storage duration before deleting objects in IA or Archive tiers.",
        ] if issues else [],
    }


def main():
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
        data = json.loads(path.read_text())
    else:
        data = json.loads(sys.stdin.read())

    result = analyze(data)
    result["ok"] = True
    result["module"] = "analyze_cost"
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
