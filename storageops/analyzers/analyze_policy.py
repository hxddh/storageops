"""
Analyze IAM and bucket policies to trace why access was denied.

Given a 403 error context, IAM policy, and optionally bucket policy,
traces the policy evaluation logic to identify the denial source.

Usage:
    python -m storageops-core.analyzers.analyze_policy context.json
"""
import json
import sys
from pathlib import Path


def _find_action_match(statement: dict, target_action: str) -> bool:
    """Check if a statement's Action covers the target action."""
    actions = statement.get('Action', [])
    if isinstance(actions, str):
        actions = [actions]
    for a in actions:
        if a == target_action or a == 's3:*' or a == '*':
            return True
        # Prefix wildcard: "s3:Get*" matches "s3:GetObject", "s3:GetBucketPolicy", etc.
        if a.endswith('*'):
            prefix = a[:-1]
            if target_action.startswith(prefix):
                return True
    return False


def _find_resource_match(statement: dict, target_resource: str) -> bool:
    """Check if a statement's Resource covers the target resource."""
    resources = statement.get('Resource', [])
    if isinstance(resources, str):
        resources = [resources]
    for r in resources:
        if r == target_resource or r == '*':
            return True
        # Simple wildcard match: "arn:aws:s3:::bucket/*" matches "arn:aws:s3:::bucket/key"
        if r.endswith('/*') and target_resource.startswith(r[:-2]):
            return True
    return False


def _find_condition_match(statement: dict, context: dict) -> list:
    """Check condition keys and report potential mismatches."""
    conditions = statement.get('Condition', {})
    issues = []
    for op, conds in conditions.items():
        for key, values in conds.items():
            if isinstance(values, list):
                values_str = ', '.join(values)
            else:
                values_str = str(values)
            issues.append({
                "condition_key": key,
                "operator": op,
                "required_values": str(values),
                "note": f"Condition {op} {key} = {values_str}. Verify this matches the request context.",
            })
    return issues


def analyze(data: dict) -> dict:
    """
    Analyze policies against an access context.

    Expected input:
    {
        "principal": "arn:aws:iam::111111111111:user/alice",
        "action": "s3:GetObject",
        "resource": "arn:aws:s3:::shared-data/report.pdf",
        "iam_policy": { ... },
        "bucket_policy": { ... },
    }
    """
    principal = data.get('principal', '')
    action = data.get('action', '')
    resource = data.get('resource', '')
    iam_policy = data.get('iam_policy', {})
    bucket_policy = data.get('bucket_policy', {})

    findings = []

    # ── Evaluate IAM Policy ──
    iam_statements = iam_policy.get('Statement', [])
    iam_allow = False
    iam_explicit_deny = False

    for stmt in iam_statements:
        effect = stmt.get('Effect', '')
        action_match = _find_action_match(stmt, action)
        resource_match = _find_resource_match(stmt, resource)

        if not (action_match and resource_match):
            continue

        condition_issues = _find_condition_match(stmt, data)
        condition_block = len(condition_issues) > 0

        if effect == 'Deny':
            iam_explicit_deny = True
            findings.append({
                "source": "iam_policy",
                "type": "explicit_deny",
                "sid": stmt.get('Sid', ''),
                "effect": "Deny",
                "action_match": action_match,
                "resource_match": resource_match,
                "condition_issues": condition_issues,
            })
        elif effect == 'Allow' and not condition_block:
            iam_allow = True

    # ── Evaluate Bucket Policy ──
    bucket_statements = bucket_policy.get('Statement', [])
    bucket_allow = False
    bucket_explicit_deny = False
    cross_account = False

    for stmt in bucket_statements:
        effect = stmt.get('Effect', '')
        action_match = _find_action_match(stmt, action)
        resource_match = _find_resource_match(stmt, resource)

        if not (action_match and resource_match):
            continue

        principal_obj = stmt.get('Principal', {})
        if isinstance(principal_obj, dict):
            aws_principal = principal_obj.get('AWS', '')
            if aws_principal == '*':
                cross_account = True  # Public
                findings.append({
                    "source": "bucket_policy",
                    "type": "public_access_granted",
                    "sid": stmt.get('Sid', ''),
                    "note": "Principal is '*'. This bucket is or may be publicly accessible.",
                })

        condition_issues = _find_condition_match(stmt, data)
        condition_block = len(condition_issues) > 0

        if effect == 'Deny':
            bucket_explicit_deny = True
            findings.append({
                "source": "bucket_policy",
                "type": "explicit_deny",
                "sid": stmt.get('Sid', ''),
                "effect": "Deny",
                "condition_issues": condition_issues,
            })
        elif effect == 'Allow' and not condition_block:
            bucket_allow = True
            # Check if the principals match
            if isinstance(principal_obj, dict):
                aws_principal = principal_obj.get('AWS', '')
                if isinstance(aws_principal, str):
                    if principal.startswith(aws_principal.rstrip(':root')):
                        cross_account = True

    # ── Determine Denial Source ──
    denial_source = "unknown"
    if iam_explicit_deny:
        denial_source = "iam_policy_explicit_deny"
    elif bucket_explicit_deny:
        denial_source = "bucket_policy_explicit_deny"
    elif cross_account and not iam_allow:
        denial_source = "cross_account_missing_iam_allow"
        findings.append({
            "source": "analysis",
            "type": "cross_account_missing_iam_allow",
            "note": "Bucket policy allows cross-account access, but the IAM policy in the requesting account does not grant this action. Both sides must Allow for cross-account access.",
        })
    elif not iam_allow and not bucket_allow:
        denial_source = "no_allow_statement"
    elif not iam_allow:
        denial_source = "iam_policy_missing_allow"
    elif not bucket_allow:
        denial_source = "bucket_policy_missing_allow"

    # ── Cross-Account Detection ──
    if principal and resource:
        principal_account = principal.split(':')[4] if ':' in principal else ''
        resource_account = resource.split(':')[4] if ':' in resource else ''
        if principal_account and resource_account and principal_account != resource_account:
            cross_account = True
            if not findings:
                findings.append({
                    "source": "analysis",
                    "type": "cross_account_detected",
                    "note": f"Principal account {principal_account} differs from resource account {resource_account}.",
                })

    return {
        "denial_source": denial_source,
        "findings": findings,
        "cross_account": cross_account,
        "iam_evaluation": {
            "has_explicit_deny": iam_explicit_deny,
            "has_allow": iam_allow,
        },
        "bucket_evaluation": {
            "has_explicit_deny": bucket_explicit_deny,
            "has_allow": bucket_allow,
        },
        "recommendation": {
            "iam_policy_explicit_deny": "Remove or modify the IAM policy Deny statement. manual-only.",
            "bucket_policy_explicit_deny": "Remove or modify the bucket policy Deny statement. manual-only.",
            "cross_account_missing_iam_allow": "Add an Allow statement in the IAM policy for the required S3 actions on the cross-account resource. manual-only.",
            "iam_policy_missing_allow": "Add an Allow statement in the IAM policy. manual-only.",
            "bucket_policy_missing_allow": "Add an Allow statement in the bucket policy. manual-only.",
            "no_allow_statement": "Add Allow statements in both IAM and bucket policies as needed. manual-only.",
        }.get(denial_source, "Further investigation needed."),
    }


def analyze_inline_403(text: str) -> dict:
    """Analyze an inline 403 error without requiring full policy JSON.

    Extracts what it can from error messages and provides a diagnosis
    with explicit caveats about missing policy documents.
    """
    import re

    findings = []

    # Extract error code
    code_match = re.search(r'<Code>(\w+)</Code>', text)
    msg_match = re.search(r'<Message>([^<]+)</Message>', text)
    req_match = re.search(r'<RequestId>([^<]+)</RequestId>', text)

    error_code = code_match.group(1) if code_match else 'AccessDenied'
    error_msg = msg_match.group(1) if msg_match else 'Access Denied'
    request_id = req_match.group(1) if req_match else 'unknown'

    # Detect auth provider
    is_bce = 'bce-auth' in text.lower() or 'bcebos' in text.lower()

    # Detect bucket/action context
    bucket_match = re.search(r'(?:bucket|bos:)/([\w.-]+)', text)
    action_hint = 'ListBucket' if re.search(r'\bls\b|list', text, re.IGNORECASE) else 'Unknown'

    # Possible causes
    causes = []
    if is_bce:
        causes.append("BOS credential issue: verify AK/SK are correct and not expired")
        causes.append("BOS bucket permission: verify the AK has access to this bucket")
    causes.append("IAM/Bucket policy: the principal lacks Allow for the attempted action")
    causes.append("Block Public Access: the request may be blocked by public access settings")
    causes.append("Condition mismatch: SourceIp, SourceVpc, or other condition fails")
    causes.append("Object does not exist: unauthenticated requests return 403 instead of 404")

    return {
        "denial_source": "inline_403_no_policy_json",
        "error_code": error_code,
        "error_message": error_msg,
        "request_id": request_id,
        "provider_hint": "BOS (Baidu Object Storage)" if is_bce else "S3-compatible",
        "affected_bucket": bucket_match.group(1) if bucket_match else None,
        "suspected_action": action_hint,
        "possible_causes": causes,
        "findings": findings,
        "recommendation": (
            "To trace this AccessDenied, collect:\n"
            "1. IAM policy JSON for the principal.\n"
            "2. Bucket policy JSON (if accessible).\n"
            "3. Confirmation of the exact action and resource being attempted.\n"
            "Then re-run: storageops analyze security_iam_policy <policy-json>"
        ),
        "note": "Full policy tracing requires IAM/bucket policy JSON. "
                "The causes listed above are possible explanations, not confirmed.",
    }


def main():
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
        data = json.loads(path.read_text())
    else:
        data = json.loads(sys.stdin.read())

    result = analyze(data)
    result["ok"] = True
    result["module"] = "analyze_policy"
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
