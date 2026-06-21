#!/usr/bin/env python3
"""Offline analyzer for an S3 bucket notification configuration.

Answers the event-notification skill's first failure class ("no events at all"):
does a notification rule actually match a given object event, or is it excluded by
event type or prefix/suffix filter? Deterministic and offline — parses the
notification JSON (e.g. `aws s3api get-bucket-notification-configuration` output),
never contacts a bucket.

AWS-specific: this models AWS S3 event-notification configuration (event types,
prefix/suffix filters, destination ARNs). BOS/OSS/COS expose similar but not
identical event taxonomies — see
storageops-event-notification/references/notification-configuration.md. Results
carry "model": "aws" to make the scope explicit.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

CONFIG_KEYS = {
    "LambdaFunctionConfigurations": ("lambda", "LambdaFunctionArn"),
    "QueueConfigurations": ("sqs", "QueueArn"),
    "TopicConfigurations": ("sns", "TopicArn"),
}
POLICY_HINT = {
    "lambda": "Lambda resource policy must allow principal s3.amazonaws.com + lambda:InvokeFunction + the source bucket ARN.",
    "sqs": "SQS queue policy must allow principal s3.amazonaws.com + sqs:SendMessage.",
    "sns": "SNS topic policy must allow principal s3.amazonaws.com + sns:Publish.",
}


def _normalize_event(event: str) -> str:
    e = (event or "").strip()
    if e and not e.startswith("s3:"):
        e = "s3:" + e
    return e


def _event_matches(rule_events: List[str], event: str) -> bool:
    if not event:
        return True
    for re_ in rule_events:
        if re_ == event:
            return True
        # wildcard: "s3:ObjectCreated:*" matches "s3:ObjectCreated:Put"
        if re_.endswith(":*") and event.startswith(re_[:-1]):
            return True
    return False


def _filter_excludes(prefix: str, suffix: str, key: Optional[str]) -> Optional[str]:
    if key is None:
        return None
    if prefix and not key.startswith(prefix):
        return f"prefix={prefix!r} does not match key {key!r}"
    if suffix and not key.endswith(suffix):
        return f"suffix={suffix!r} does not match key {key!r}"
    return None


def _rules(config: dict) -> list[dict]:
    rules = []
    for cfg_key, (target_type, arn_field) in CONFIG_KEYS.items():
        for r in config.get(cfg_key, []) or []:
            fr = (((r.get("Filter") or {}).get("Key") or {}).get("FilterRules")) or []
            prefix = suffix = ""
            for f in fr:
                if str(f.get("Name", "")).lower() == "prefix":
                    prefix = f.get("Value", "")
                elif str(f.get("Name", "")).lower() == "suffix":
                    suffix = f.get("Value", "")
            rules.append({
                "id": r.get("Id", ""),
                "target_type": target_type,
                "target": r.get(arn_field, ""),
                "events": r.get("Events", []) or [],
                "prefix": prefix,
                "suffix": suffix,
            })
    return rules


def analyze(config: dict, key: Optional[str], event: str) -> dict:
    event = _normalize_event(event)
    rules = _rules(config)
    if not rules:
        return {
            "ok": True, "rule_count": 0, "verdict": "no_notification_config",
            "likely_cause": "No bucket notification configuration found — no events will be delivered.",
            "recommendation": "Configure a notification rule (event type + optional prefix/suffix filter + target).",
            "matching_rules": [],
        }

    event_matched = [r for r in rules if _event_matches(r["events"], event)]
    matching = []
    filter_reasons = []
    for r in event_matched:
        reason = _filter_excludes(r["prefix"], r["suffix"], key)
        if reason is None:
            matching.append(r)
        else:
            filter_reasons.append(f"rule {r['id'] or r['target']}: {reason}")

    if not event_matched:
        configured = sorted({e for r in rules for e in r["events"]})
        verdict, cause = "event_type_mismatch", (
            f"No rule matches event {event or '(unspecified)'}; configured events are {configured}. "
            "Note ObjectCreated:Put does not fire on multipart completion (needs CompleteMultipartUpload or ObjectCreated:*)."
        )
        rec = "Add the missing event type (or use s3:ObjectCreated:* to cover all creates)."
    elif not matching:
        verdict, cause = "filter_mismatch", "Event type matches, but the prefix/suffix filter excludes the object: " + "; ".join(filter_reasons)
        rec = "Fix the prefix/suffix filter so it matches the object key (empty filter matches all)."
    else:
        targets = ", ".join(f"{r['target_type']}:{r['target'] or '(arn)'}" for r in matching)
        verdict, cause = "would_fire", f"{len(matching)} rule(s) would fire to {targets}."
        hints = sorted({POLICY_HINT[r["target_type"]] for r in matching})
        rec = "If events still are not delivered, the config is fine — check the target side: " + " ".join(hints)

    return {
        "ok": True, "rule_count": len(rules), "verdict": verdict,
        "likely_cause": cause, "recommendation": rec,
        "matching_rules": [{"id": r["id"], "target_type": r["target_type"], "events": r["events"],
                            "prefix": r["prefix"], "suffix": r["suffix"]} for r in matching],
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", required=True, type=Path, help="Notification configuration JSON")
    ap.add_argument("--key", default=None, help="Object key that should have triggered an event")
    ap.add_argument("--event", default="", help="Event, e.g. s3:ObjectCreated:CompleteMultipartUpload")
    ap.add_argument("--json", action="store_true", help="Emit JSON")
    args = ap.parse_args(argv)

    try:
        config = json.loads(args.config.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"error: cannot parse notification JSON: {exc}", file=sys.stderr)
        return 2
    if not isinstance(config, dict):
        print("error: notification configuration must be a JSON object", file=sys.stderr)
        return 2

    result = analyze(config, args.key, args.event)
    result["model"] = "aws"
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"rules          : {result['rule_count']}")
        print(f"verdict        : {result['verdict']}")
        print(f"likely_cause   : {result['likely_cause']}")
        print(f"recommendation : {result['recommendation']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
