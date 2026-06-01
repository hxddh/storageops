#!/usr/bin/env python3
"""
policy_analyzer.py – Parse IAM policy JSON and produce a security diagnostic report.

Usage:
  policy_analyzer.py --file policy.json
  cat policy.json | policy_analyzer.py --stdin

Output: JSON document { ok, summary, details } to stdout.
"""

import argparse
import json
import sys
from collections import defaultdict
from typing import Any, Dict, List

PUBLIC_RISK = {"AWS", "*"}
BROAD_ACTIONS = {"*", "s3:*", "ec2:*", "iam:*", "lambda:*",
                 "dynamodb:*", "kms:*", "rds:*", "sqs:*", "sns:*"}


def _flatten_statements(doc: dict) -> List[dict]:
    """Return a flat list of statement dicts; handle single-statement policies."""
    stmts = doc.get("Statement", [])
    if isinstance(stmts, dict):
        stmts = [stmts]
    return stmts


def _is_public(principal: Any) -> bool:
    if isinstance(principal, str):
        return principal in PUBLIC_RISK
    if isinstance(principal, dict):
        return principal.get("AWS") == "*" or principal.get("*") is not None
    return False


def _action_set(actions: Any) -> List[str]:
    if isinstance(actions, str):
        return [actions]
    if isinstance(actions, list):
        return actions
    return []


def analyze(doc: dict) -> dict:
    details: Dict[str, List[str]] = defaultdict(list)
    issues = 0
    stmts = _flatten_statements(doc)

    for i, stmt in enumerate(stmts, start=1):
        prefix = f"s{i} –"

        effect = str(stmt.get("Effect", "")).lower()
        action = stmt.get("Action", [])
        resource = stmt.get("Resource", "*")
        principal = stmt.get("Principal", "")
        condition = stmt.get("Condition")

        # --- Explicit Deny --------------------------------------------------
        if effect == "deny":
            reasons = []
            for a in _action_set(action):
                if a in BROAD_ACTIONS:
                    reasons.append(f"broad action {a}")
                else:
                    reasons.append(f"action {a}")
            def_res = resource if isinstance(resource, str) else "multiple"
            details["explicit_denies"].append(
                f"{prefix} Deny on {def_res} ({', '.join(reasons)})")
            issues += 1

        # --- Missing Allow --------------------------------------------------
        if effect == "allow" and not action:
            details["missing_allow"].append(
                f"{prefix} Allow statement has no Action")
            issues += 1

        # --- Public-access risk (Principal: *) ------------------------------
        if effect == "allow" and _is_public(principal):
            details["public_access_risk"].append(
                f"{prefix} Principal is * (or AWS:*) – public access")
            issues += 1

        # --- Overly-broad actions -------------------------------------------
        for a in _action_set(action):
            if effect == "allow" and a in BROAD_ACTIONS:
                details["overly_broad_actions"].append(
                    f"{prefix} {a} – grants full control on "
                    f"{resource if isinstance(resource, str) else 'multiple'}")
                issues += 1

        # --- Condition keys ------------------------------------------------
        if condition:
            if effect == "allow":
                for cond_op, cond_map in condition.items():
                    if isinstance(cond_map, dict):
                        for key in cond_map:
                            details["condition_keys"].append(
                                f"{prefix} {cond_op}/{key} – may restrict "
                                f"access on {action}")
            elif effect == "deny":
                for cond_op, cond_map in condition.items():
                    if isinstance(cond_map, dict):
                        for key in cond_map:
                            details["condition_keys"].append(
                                f"{prefix} Deny+Condition {cond_op}/{key} – "
                                f"conditional block on {action}")

        # --- Least-privilege violation -------------------------------------
        if effect == "allow" and not condition and any(
                a in BROAD_ACTIONS for a in _action_set(action)):
            details["least_privilege_violations"].append(
                f"{prefix} Broad action without condition on {resource}")

    ok = issues == 0
    summary_lines = []
    for cat, items in sorted(details.items()):
        if items:
            summary_lines.append(f"{len(items)} {cat.replace('_', ' ')}")
    summary = "; ".join(summary_lines) if summary_lines else "policy is clean"

    return {
        "ok": ok,
        "summary": summary,
        "details": {k: v for k, v in sorted(details.items())},
    }


def main():
    parser = argparse.ArgumentParser(
        description="IAM policy security analyzer")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", "-f", help="Path to JSON policy file")
    group.add_argument("--stdin", action="store_true", help="Read JSON from stdin")
    args = parser.parse_args()

    if args.stdin:
        raw = sys.stdin.read()
    else:
        with open(args.file, "r") as fh:
            raw = fh.read()

    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(1)

    result = analyze(doc)
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
