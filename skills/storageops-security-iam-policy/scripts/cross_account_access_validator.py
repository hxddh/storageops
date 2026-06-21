#!/usr/bin/env python3
"""Evaluate a cross-account S3 access chain offline and report the broken link.

Cross-account access is an AND of independent grants: the caller's identity
(IAM) policy in account A must Allow the action, AND the resource owner's bucket
policy in account B must Allow the caller principal, AND no explicit Deny may
match anywhere (Deny always wins), AND — when SSE-KMS is involved — the KMS key
policy must grant the caller the needed key action. The #1 cross-account failure
is fixing one link and staying blocked because another link is still missing.

This validator takes the principal, action, resource ARN and the relevant policy
documents and deterministically reports which link breaks. It is a deliberately
conservative model of AWS evaluation (explicit Deny > explicit Allow > implicit
Deny); it does NOT resolve SCPs, permission boundaries, session policies, ABAC
condition values, or wildcards beyond simple ARN prefixes — those are surfaced as
open questions rather than silently assumed. Offline; never contacts AWS.

AWS-specific: this models the AWS IAM evaluation chain. Alibaba OSS (RAM), Tencent
COS (CAM) and Baidu BOS use different identity systems and policy semantics — see
storageops-security-iam-policy/references/provider-differences.md. Every result
carries "model": "aws" to make that scope explicit.

Emits a single JSON object. On bad/empty input it emits {"ok": false, ...}.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_ARN_ACCOUNT = re.compile(r"^arn:[^:]*:[^:]*:[^:]*:(\d+):")


def _as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _load_policy(path: Optional[Path]) -> Optional[dict]:
    if path is None:
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and isinstance(data.get("Policy"), str):
        data = json.loads(data["Policy"])
    if not isinstance(data, dict):
        raise ValueError("policy must be a JSON object")
    return data


def _statements(policy: Optional[dict]) -> List[dict]:
    if not policy:
        return []
    return [s for s in _as_list(policy.get("Statement")) if isinstance(s, dict)]


def _account_of(arn: str) -> Optional[str]:
    m = _ARN_ACCOUNT.match(arn or "")
    return m.group(1) if m else None


def _glob_match(pattern: str, value: str) -> bool:
    """Match an IAM-style pattern with '*' and '?' wildcards against a value."""
    if pattern == "*":
        return True
    regex = "^" + re.escape(pattern).replace(r"\*", ".*").replace(r"\?", ".") + "$"
    return re.match(regex, value) is not None


def _action_matches(stmt_actions: Any, action: str) -> bool:
    for a in _as_list(stmt_actions):
        if _glob_match(str(a), action):
            return True
    return False


def _resource_matches(stmt_resources: Any, resource: str) -> bool:
    resources = _as_list(stmt_resources)
    if not resources:
        # Identity policies always carry Resource; resource policies may omit it
        # (meaning "this resource"). Treat an absent Resource as a match.
        return True
    return any(_glob_match(str(r), resource) for r in resources)


def _principal_matches(stmt_principal: Any, principal_arn: str) -> bool:
    """Does a resource-policy Principal grant the given caller principal ARN?"""
    if stmt_principal == "*":
        return True
    values: List[str] = []
    if isinstance(stmt_principal, str):
        values = [stmt_principal]
    elif isinstance(stmt_principal, dict):
        if "*" in stmt_principal.values():
            return True
        values = [str(v) for v in _as_list(stmt_principal.get("AWS"))]
    account = _account_of(principal_arn)
    for v in values:
        if v == "*":
            return True
        if v == principal_arn:
            return True
        # Account-root principal grants every identity in that account (the
        # identity still needs its own IAM allow, evaluated as a separate link).
        if account and v in (account, f"arn:aws:iam::{account}:root"):
            return True
        if _glob_match(v, principal_arn):
            return True
    return False


def _has_condition(stmt: dict) -> bool:
    return isinstance(stmt.get("Condition"), dict) and bool(stmt.get("Condition"))


def evaluate_link(
    statements: List[dict],
    action: str,
    resource: str,
    principal_arn: Optional[str] = None,
    match_principal: bool = False,
) -> Dict[str, Any]:
    """Evaluate one policy: explicit Deny > explicit Allow > implicit Deny."""
    allow_hit: Optional[str] = None
    conditional = False
    for i, stmt in enumerate(statements, start=1):
        effect = str(stmt.get("Effect", "")).lower()
        if not _action_matches(stmt.get("Action"), action):
            continue
        if not _resource_matches(stmt.get("Resource"), resource):
            continue
        if match_principal and not _principal_matches(stmt.get("Principal"), principal_arn or ""):
            continue
        sid = stmt.get("Sid", f"statement#{i}")
        if effect == "deny":
            return {"result": "explicit_deny", "matched_sid": sid, "conditional": _has_condition(stmt)}
        if effect == "allow" and allow_hit is None:
            allow_hit = sid
            conditional = _has_condition(stmt)
    if allow_hit is not None:
        return {"result": "allow", "matched_sid": allow_hit, "conditional": conditional}
    return {"result": "implicit_deny", "matched_sid": None, "conditional": False}


def _kms_action_for(action: str) -> Optional[str]:
    a = action.lower()
    if a in ("s3:getobject", "s3:headobject", "s3:copyobject"):
        return "kms:Decrypt"
    if a in ("s3:putobject", "s3:copyobject", "s3:createmultipartupload", "s3:uploadpart"):
        return "kms:GenerateDataKey"
    return "kms:Decrypt"


def validate(
    principal_arn: str,
    action: str,
    resource: str,
    identity_policy: Optional[dict],
    bucket_policy: Optional[dict],
    kms_key_policy: Optional[dict] = None,
    resource_account: Optional[str] = None,
) -> Dict[str, Any]:
    caller_account = _account_of(principal_arn)
    # S3 bucket/object ARNs carry no account id, so prefer an explicit owner
    # account; fall back to any account embedded in the resource ARN.
    resource_account = resource_account or _account_of(resource)
    cross_account = bool(caller_account and resource_account and caller_account != resource_account)

    links: List[Dict[str, Any]] = []
    blocked_at: Optional[str] = None

    # Link 1 — caller identity (IAM) policy in the caller's account.
    if identity_policy is None:
        identity = {"link": "identity_policy", "account": caller_account, "result": "not_provided",
                    "reason": "Caller IAM policy not supplied; cannot confirm the identity-side allow."}
    else:
        ev = evaluate_link(_statements(identity_policy), action, resource)
        identity = {"link": "identity_policy", "account": caller_account, **ev}
        if ev["result"] == "allow":
            identity["reason"] = f"IAM policy allows {action} on the resource (Sid {ev['matched_sid']})."
        elif ev["result"] == "explicit_deny":
            identity["reason"] = f"IAM policy explicitly denies {action} (Sid {ev['matched_sid']}); Deny wins."
        else:
            identity["reason"] = f"IAM policy has no statement allowing {action} on the resource."
    links.append(identity)

    # Link 2 — resource (bucket) policy in the owner account.
    if bucket_policy is None:
        bucket = {"link": "resource_policy", "account": resource_account, "result": "not_provided",
                  "reason": "Bucket policy not supplied; cannot confirm the resource-side allow."}
    else:
        ev = evaluate_link(_statements(bucket_policy), action, resource,
                           principal_arn=principal_arn, match_principal=True)
        bucket = {"link": "resource_policy", "account": resource_account, **ev}
        if ev["result"] == "allow":
            bucket["reason"] = (f"Bucket policy allows {action} for principal {principal_arn} "
                                f"(Sid {ev['matched_sid']}).")
        elif ev["result"] == "explicit_deny":
            bucket["reason"] = (f"Bucket policy explicitly denies {action} for this principal "
                                f"(Sid {ev['matched_sid']}); Deny wins.")
        else:
            bucket["reason"] = (f"Bucket policy has no statement granting {action} to principal "
                                f"{principal_arn} (nor its account root).")
    links.append(bucket)

    # Link 3 — KMS key policy, only when one is supplied.
    if kms_key_policy is not None:
        kms_action = _kms_action_for(action)
        ev = evaluate_link(_statements(kms_key_policy), kms_action, "*",
                           principal_arn=principal_arn, match_principal=True)
        kms = {"link": "kms_key_policy", "result": ev["result"], "matched_sid": ev["matched_sid"],
               "conditional": ev["conditional"], "kms_action": kms_action}
        if ev["result"] == "allow":
            kms["reason"] = f"KMS key policy allows {kms_action} for the principal (Sid {ev['matched_sid']})."
        elif ev["result"] == "explicit_deny":
            kms["reason"] = f"KMS key policy explicitly denies {kms_action}; Deny wins."
        else:
            kms["reason"] = f"KMS key policy does not grant {kms_action} to the principal."
        links.append(kms)

    # Decide the chain. Explicit deny anywhere blocks; otherwise every provided
    # link must allow. A not_provided link is reported as unknown, not allow.
    decision = "allow"
    for link in links:
        if link["result"] == "explicit_deny":
            decision = "deny"
            blocked_at = link["link"]
            break
    if decision == "allow":
        for link in links:
            if link["result"] in ("implicit_deny",):
                decision = "deny"
                blocked_at = link["link"]
                break
    unknown_links = [l["link"] for l in links if l["result"] == "not_provided"]
    if decision == "allow" and unknown_links:
        decision = "indeterminate"

    if decision == "allow":
        summary = (f"All evaluated links allow {action}: the cross-account chain is satisfied."
                   if cross_account else f"All evaluated links allow {action}.")
        recommendation = (
            "Policies permit the action. If access still fails, the gap is outside these documents: "
            "check SCPs/permission boundaries, VPC endpoint policy, Block Public Access, object "
            "ownership/ACLs, or a Condition value (e.g. aws:SourceVpce, encryption header) that this "
            "validator does not resolve."
        )
    elif decision == "indeterminate":
        summary = (f"Cannot fully confirm the chain for {action}: missing "
                   f"{', '.join(unknown_links)}. No provided link blocks, but the unsupplied "
                   f"policy(ies) could.")
        recommendation = (f"Supply the {', '.join(unknown_links)} document(s) to complete the "
                          f"evaluation; both the caller IAM policy and the bucket policy must "
                          f"independently allow {action}.")
    else:
        broken = next(l for l in links if l["link"] == blocked_at)
        summary = f"Access to {action} is denied — blocked at {blocked_at}: {broken['reason']}"
        if blocked_at == "identity_policy":
            recommendation = (f"Add an IAM Allow for {action} on {resource} to the caller "
                              f"({principal_arn}). A bucket-policy grant alone is not enough in "
                              f"cross-account access — the identity also needs its own allow.")
        elif blocked_at == "resource_policy":
            recommendation = (f"Add a bucket-policy Allow for {action} naming principal "
                              f"{principal_arn} (or its account root arn:aws:iam::{caller_account}:root) "
                              f"on {resource}. The caller's IAM allow alone cannot grant access to "
                              f"another account's bucket.")
        elif blocked_at == "kms_key_policy":
            recommendation = (f"Grant {broken.get('kms_action', 'the KMS action')} on the SSE-KMS key "
                              f"to {principal_arn} in the key policy; an SSE-KMS object needs both the "
                              f"S3 allow and the key allow.")
        else:
            recommendation = f"Resolve the explicit Deny at {blocked_at}; an explicit Deny overrides every Allow."

    open_questions: List[str] = []
    if any(l.get("conditional") for l in links):
        open_questions.append(
            "One or more matched statements carry a Condition; this validator matches the "
            "statement but does not evaluate Condition values — confirm the request meets them."
        )
    if cross_account and bucket_policy is not None and identity_policy is None:
        open_questions.append("Caller IAM policy was not supplied; the identity-side allow is assumed unknown.")

    return {
        "ok": decision == "allow",
        "decision": decision,
        "cross_account": cross_account,
        "principal": principal_arn,
        "action": action,
        "resource": resource,
        "caller_account": caller_account,
        "resource_account": resource_account,
        "links": links,
        "blocked_at": blocked_at,
        "summary": summary,
        "recommendation": recommendation,
        "open_questions": open_questions,
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Validate a cross-account S3 access chain offline")
    ap.add_argument("--principal-arn", required=True, help="Caller identity ARN (user/role)")
    ap.add_argument("--action", required=True, help="S3 action, e.g. s3:GetObject")
    ap.add_argument("--resource", required=True, help="Resource ARN, e.g. arn:aws:s3:::bucket/key")
    ap.add_argument("--identity-policy", type=Path, help="Caller IAM policy JSON (account A)")
    ap.add_argument("--bucket-policy", type=Path, help="Bucket/resource policy JSON (account B)")
    ap.add_argument("--kms-key-policy", type=Path, help="KMS key policy JSON (if SSE-KMS)")
    ap.add_argument("--resource-account", default=None,
                    help="Owner account id of the resource (S3 ARNs omit it; sets cross-account)")
    args = ap.parse_args(argv)

    try:
        identity_policy = _load_policy(args.identity_policy)
        bucket_policy = _load_policy(args.bucket_policy)
        kms_key_policy = _load_policy(args.kms_key_policy)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "model": "aws", "error": f"could not load policy: {exc}"}, indent=2))
        return 0

    result = validate(
        principal_arn=args.principal_arn,
        action=args.action,
        resource=args.resource,
        identity_policy=identity_policy,
        bucket_policy=bucket_policy,
        kms_key_policy=kms_key_policy,
        resource_account=args.resource_account,
    )
    result["model"] = "aws"
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
