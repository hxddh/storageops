#!/usr/bin/env python3
"""Offline validator for an event-notification TARGET resource policy.

Answers the #1 cause of silently-undelivered S3 events: does the target's
resource policy (Lambda get-policy / SQS get-queue-attributes Policy / SNS
get-topic-attributes Policy) actually allow S3 to deliver events? S3 returns NO
error to the caller when the target rejects the delivery, so this check is the
deterministic way to catch a missing or wrong allow statement.

Deterministic and offline: parses the policy JSON, never contacts AWS.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

S3_SERVICE = "s3.amazonaws.com"

# Per-target requirements: the action S3 needs and the kind of resource the
# statement targets.
TARGET_SPEC = {
    "lambda": {"action": "lambda:InvokeFunction", "service": "lambda"},
    "sqs": {"action": "sqs:SendMessage", "service": "sqs"},
    "sns": {"action": "sns:Publish", "service": "sns"},
}


def _as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _load_policy(raw: str) -> dict:
    """Parse a policy document.

    Lambda get-policy returns {"Policy": "<json string>"}; SQS/SNS attribute
    calls return the policy as a JSON string too. Accept either the already
    parsed document or the wrapper, and a stringified inner policy.
    """
    data = json.loads(raw)
    if isinstance(data, dict) and "Policy" in data and isinstance(data["Policy"], str):
        data = json.loads(data["Policy"])
    if isinstance(data, dict) and "Policy" in data and isinstance(data["Policy"], dict):
        data = data["Policy"]
    if not isinstance(data, dict):
        raise ValueError("policy must be a JSON object")
    return data


def _statements(policy: dict) -> list:
    return [s for s in _as_list(policy.get("Statement")) if isinstance(s, dict)]


def _principal_is_s3(stmt: dict) -> bool:
    principal = stmt.get("Principal")
    if principal == "*":
        return False
    if isinstance(principal, str):
        return principal == S3_SERVICE
    if isinstance(principal, dict):
        service = principal.get("Service")
        return S3_SERVICE in _as_list(service)
    return False


def _action_present(stmt: dict, action: str) -> bool:
    actions = [str(a) for a in _as_list(stmt.get("Action"))]
    service = action.split(":", 1)[0]
    for a in actions:
        if a == action or a == f"{service}:*" or a == "*":
            return True
    return False


def _source_arn_values(stmt: dict) -> List[str]:
    cond = stmt.get("Condition")
    values: List[str] = []
    if isinstance(cond, dict):
        for operator, mapping in cond.items():
            if not isinstance(mapping, dict):
                continue
            for key, val in mapping.items():
                if str(key).lower() == "aws:sourcearn":
                    values.extend(str(v) for v in _as_list(val))
    return values


def _detect_target_type(policy: dict) -> Optional[str]:
    """Infer target type from the actions present in the policy statements."""
    for stmt in _statements(policy):
        actions = [str(a).lower() for a in _as_list(stmt.get("Action"))]
        for a in actions:
            svc = a.split(":", 1)[0]
            if svc in TARGET_SPEC:
                return svc
    return None


def _arc_matches(source_arn_cond: str, bucket_arn: str) -> bool:
    """Match an aws:SourceArn condition value against a bucket ARN.

    Conditions commonly use ArnLike with a trailing wildcard; treat a single
    trailing '*' as a prefix match, otherwise require equality.
    """
    if source_arn_cond == bucket_arn:
        return True
    if source_arn_cond.endswith("*"):
        return bucket_arn.startswith(source_arn_cond[:-1])
    return False


def _suggested_statement(target_type: str, bucket_arn: Optional[str]) -> dict:
    spec = TARGET_SPEC[target_type]
    stmt = {
        "Effect": "Allow",
        "Principal": {"Service": S3_SERVICE},
        "Action": spec["action"],
    }
    if target_type == "lambda":
        stmt["Sid"] = "AllowS3Invoke"
    else:
        stmt["Sid"] = "AllowS3Delivery"
        stmt["Resource"] = "<target-arn>"
    if bucket_arn:
        stmt["Condition"] = {"ArnLike": {"aws:SourceArn": bucket_arn}}
    return stmt


def validate(policy: dict, target_type: Optional[str], bucket_arn: Optional[str]) -> dict:
    target_type = (target_type or "").strip().lower() or None
    if target_type not in (None, *TARGET_SPEC):
        target_type = None
    if target_type is None:
        target_type = _detect_target_type(policy)
    if target_type is None:
        return {
            "ok": False,
            "target_type": "unknown",
            "policy_ok": False,
            "missing": ["target_type"],
            "summary": "Could not determine the target type (lambda/sqs/sns) from the policy; "
                       "no recognizable S3-delivery action found.",
            "recommendation": "Pass --target-type {lambda,sqs,sns}, or supply the correct target "
                              "resource policy (Lambda get-policy / SQS or SNS Policy attribute).",
            "suggested_statement": {},
        }

    spec = TARGET_SPEC[target_type]
    action = spec["action"]
    statements = _statements(policy)

    s3_stmts = [s for s in statements if s.get("Effect", "Allow") == "Allow" and _principal_is_s3(s)]
    action_stmts = [s for s in s3_stmts if _action_present(s, action)]

    missing: List[str] = []
    if not s3_stmts:
        missing.append(f"Allow statement with Principal Service {S3_SERVICE}")
    if not action_stmts:
        missing.append(f"Action {action} for Principal {S3_SERVICE}")

    # SourceArn check only when a bucket ARN is supplied and a condition exists.
    sourcearn_mismatch = False
    if action_stmts and bucket_arn:
        conditioned = [s for s in action_stmts if _source_arn_values(s)]
        if conditioned:
            ok_arn = any(
                any(_arc_matches(v, bucket_arn) for v in _source_arn_values(s))
                for s in conditioned
            )
            # An unconditioned allow also satisfies delivery (broader, but valid).
            unconditioned = any(not _source_arn_values(s) for s in action_stmts)
            if not ok_arn and not unconditioned:
                sourcearn_mismatch = True
                missing.append(
                    f"Condition aws:SourceArn matching the source bucket {bucket_arn}"
                )

    policy_ok = not missing

    if policy_ok:
        summary = (
            f"Target resource policy permits S3 delivery: an Allow statement grants "
            f"{action} to Principal {S3_SERVICE}"
            + (f" scoped to {bucket_arn}." if bucket_arn else ".")
        )
        recommendation = (
            "Policy is correct. If events still are not delivered, the target policy is not "
            "the cause — check the bucket notification rule (event type + prefix/suffix filter) "
            "with notification_config_analyzer.py, and confirm CloudTrail shows the event was emitted."
        )
    elif sourcearn_mismatch:
        summary = (
            f"Target policy allows {action} for S3, but its aws:SourceArn condition does not match "
            f"the source bucket {bucket_arn}; S3 deliveries from this bucket are silently denied."
        )
        recommendation = (
            f"Update the aws:SourceArn condition to match {bucket_arn} (use ArnLike with the bucket "
            f"ARN), or add a statement allowing {action} from {S3_SERVICE} scoped to this bucket."
        )
    else:
        summary = (
            f"Target resource policy does NOT permit S3 delivery: missing {', '.join(missing)}. "
            f"S3 silently drops events when the {target_type} target rejects them — no error is returned."
        )
        recommendation = (
            f"Add an Allow statement: Principal Service {S3_SERVICE}, Action {action}"
            + (f", Condition aws:SourceArn {bucket_arn}." if bucket_arn else ", and scope it with "
               "aws:SourceArn to the source bucket ARN.")
        )

    return {
        "ok": True,
        "target_type": target_type,
        "policy_ok": policy_ok,
        "missing": missing,
        "summary": summary,
        "recommendation": recommendation,
        "suggested_statement": {} if policy_ok else _suggested_statement(target_type, bucket_arn),
    }


def _read_input(args) -> str:
    if args.stdin:
        return sys.stdin.read()
    return args.file.read_text(encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--file", type=Path, help="Target resource policy JSON file")
    src.add_argument("--stdin", action="store_true", help="Read policy JSON from stdin")
    ap.add_argument("--target-type", choices=sorted(TARGET_SPEC), default=None,
                    help="Target type (auto-detected from policy if omitted)")
    ap.add_argument("--source-bucket-arn", default=None,
                    help="Source bucket ARN, e.g. arn:aws:s3:::my-bucket")
    ap.add_argument("--json", action="store_true", help="Emit JSON (default)")
    args = ap.parse_args(argv)

    try:
        raw = _read_input(args)
        policy = _load_policy(raw)
    except Exception as exc:
        result = {
            "ok": False,
            "target_type": (args.target_type or "unknown"),
            "policy_ok": False,
            "missing": ["valid_policy_json"],
            "summary": f"Could not parse the target resource policy: {exc}",
            "recommendation": "Provide the raw resource policy JSON (Lambda get-policy output, or the "
                              "SQS/SNS Policy attribute value).",
            "suggested_statement": {},
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    result = validate(policy, args.target_type, args.source_bucket_arn)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
