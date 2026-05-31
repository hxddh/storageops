"""
Diagnose why S3 CRR/SRR replication is failing.

Input: output from parse_replication_status.
Output: likely cause, diagnosis, recommendations, and verification commands.

Usage:
    python analyze_replication.py replication_parsed.json
"""
import json
import sys
from pathlib import Path


# Failure reason patterns mapped to likely causes
_REASON_CAUSE_MAP = [
    (["kms", "decrypt", "encrypt", "key"], "kms"),
    (["iam", "permission", "access denied", "not authorized", "403"], "iam_permission"),
    (["destination", "bucket", "does not exist", "nosuchbucket"], "destination_bucket"),
    (["filter", "prefix", "tag", "rule"], "rule_filter"),
    (["versioning", "version", "suspend"], "versioning_disabled"),
    (["object lock", "locked", "worm"], "object_lock"),
]


def _classify_cause(failure_reasons: list, status_counts: dict, rules: list) -> str:
    """Determine the most likely replication failure cause."""
    text = " ".join(failure_reasons).lower()

    for keywords, cause in _REASON_CAUSE_MAP:
        if any(k in text for k in keywords):
            return cause

    # Heuristic: disabled rules with failures → rule_filter
    disabled_rules = [r for r in rules if r.get("status", "").lower() == "disabled"]
    if disabled_rules and status_counts.get("FAILED", 0) > 0:
        return "rule_filter"

    # Pending-heavy → likely IAM (replication role lacks permission)
    pending = status_counts.get("PENDING", 0)
    failed = status_counts.get("FAILED", 0)
    if pending > 0 and failed == 0:
        return "iam_permission"

    if failed > 0:
        return "iam_permission"  # most common default

    return "unknown"


def _build_diagnosis(cause: str, failure_reasons: list, rules: list) -> str:
    diagnoses = {
        "iam_permission": (
            "The replication IAM role lacks the required permissions. "
            "The role must have s3:GetObject, s3:GetObjectVersionForReplication, "
            "s3:ReplicateObject, s3:ReplicateDelete, and s3:GetBucketVersioning on both "
            "source and destination buckets. Check the trust policy allows s3.amazonaws.com."
        ),
        "kms": (
            "KMS key policy prevents the replication role from using the encryption key. "
            "The destination KMS key must grant the replication role kms:GenerateDataKey "
            "and kms:Encrypt. The source KMS key must grant kms:Decrypt."
        ),
        "destination_bucket": (
            "The destination bucket may not exist, is in the wrong region, "
            "or does not have versioning enabled. Replication requires versioning on both "
            "source and destination buckets."
        ),
        "rule_filter": (
            "The replication rule filter (prefix or tag) does not match the objects "
            "that need to be replicated, or the rule is disabled. "
            "Verify rule prefix/tag filters and rule Status is Enabled."
        ),
        "versioning_disabled": (
            "Versioning must be enabled on both source and destination buckets. "
            "If versioning was suspended on the source, existing objects will not replicate."
        ),
        "object_lock": (
            "Object Lock (WORM) on the destination bucket may be preventing replication. "
            "Ensure the destination bucket Object Lock mode is compatible with the source."
        ),
        "unknown": (
            "Unable to determine failure cause from available data. "
            "Collect detailed failure reasons from aws s3api get-bucket-replication "
            "and CloudTrail logs for the replication role."
        ),
    }
    base = diagnoses.get(cause, diagnoses["unknown"])
    if failure_reasons:
        base += f" Observed failure reason(s): {'; '.join(failure_reasons[:3])}."
    return base


def _build_recommendations(cause: str, rules: list) -> list:
    recs_map = {
        "iam_permission": [
            "Verify the replication role has s3:GetObject, s3:GetObjectVersionForReplication on source bucket.",
            "Verify the replication role has s3:ReplicateObject, s3:ReplicateDelete on destination bucket.",
            "Check the IAM role trust policy allows principal: s3.amazonaws.com.",
            "If using KMS encryption, grant kms:Decrypt (source key) and kms:GenerateDataKey (destination key) to the replication role.",
        ],
        "kms": [
            "Add kms:GenerateDataKey and kms:Encrypt permissions for the replication role in the destination KMS key policy.",
            "Add kms:Decrypt permission for the replication role in the source KMS key policy.",
            "Verify the destination bucket's default encryption key is accessible to the replication role.",
        ],
        "destination_bucket": [
            "Verify the destination bucket exists and is in the expected region.",
            "Enable versioning on the destination bucket: aws s3api put-bucket-versioning --bucket <dest> --versioning-configuration Status=Enabled",
            "Check the replication rule ARN matches the actual destination bucket ARN.",
        ],
        "rule_filter": [
            "Review rule prefix/tag filters — they must match the objects intended for replication.",
            "Set rule Status to Enabled for all rules that should be active.",
            "Check for overlapping rules that may cause conflicts.",
        ],
        "versioning_disabled": [
            "Enable versioning on source bucket: aws s3api put-bucket-versioning --bucket <source> --versioning-configuration Status=Enabled",
            "Enable versioning on destination bucket: aws s3api put-bucket-versioning --bucket <dest> --versioning-configuration Status=Enabled",
        ],
        "object_lock": [
            "Check destination Object Lock mode: aws s3api get-object-lock-configuration --bucket <dest>",
            "Ensure the replication role has s3:PutObjectLegalHold and s3:PutObjectRetention if replicating locked objects.",
        ],
        "unknown": [
            "Run aws s3api get-bucket-replication --bucket <source> to see the full replication configuration.",
            "Check CloudTrail for replication role API call failures.",
            "Enable S3 server access logging on both buckets to trace replication activity.",
        ],
    }
    return recs_map.get(cause, recs_map["unknown"])


def _build_verification_commands(cause: str) -> list:
    base = [
        "# manual-only: aws s3api get-bucket-replication --bucket <source-bucket>",
        "# manual-only: aws s3api get-bucket-versioning --bucket <source-bucket>",
        "# manual-only: aws s3api get-bucket-versioning --bucket <destination-bucket>",
        "# manual-only: aws iam get-role --role-name <replication-role-name>",
        "# manual-only: aws iam simulate-principal-policy --policy-source-arn <role-arn> "
        "--action-names s3:ReplicateObject --resource-arns arn:aws:s3:::<dest-bucket>/*",
    ]
    if cause == "kms":
        base.append(
            "# manual-only: aws kms get-key-policy --key-id <key-id> --policy-name default"
        )
    if cause == "destination_bucket":
        base.append(
            "# manual-only: aws s3api head-bucket --bucket <destination-bucket>"
        )
    return base


def analyze(data: dict) -> dict:
    """
    Diagnose replication failures from parse_replication_status output.

    Returns:
        {
            "likely_cause": str,
            "diagnosis": str,
            "recommendations": [str],
            "verification_commands": [str]
        }
    """
    status_counts = data.get("status_counts", {"FAILED": 0, "PENDING": 0, "COMPLETED": 0})
    failure_reasons = data.get("failure_reasons", [])
    has_failures = data.get("has_failures", False)
    rules = data.get("rules", [])
    summary = data.get("summary", {})

    # If no failures detected, return a clean status
    if not has_failures and status_counts.get("FAILED", 0) == 0:
        return {
            "likely_cause": "none",
            "diagnosis": (
                "No replication failures detected. "
                f"Status: COMPLETED={status_counts.get('COMPLETED', 0)}, "
                f"PENDING={status_counts.get('PENDING', 0)}."
            ),
            "recommendations": ["Monitor replication lag. If objects remain PENDING, check IAM permissions."],
            "verification_commands": [
                "# manual-only: aws s3api head-object --bucket <source-bucket> --key <object-key>",
            ],
        }

    cause = _classify_cause(failure_reasons, status_counts, rules)
    diagnosis = _build_diagnosis(cause, failure_reasons, rules)
    recommendations = _build_recommendations(cause, rules)
    verification_commands = _build_verification_commands(cause)

    return {
        "likely_cause": cause,
        "diagnosis": diagnosis,
        "recommendations": recommendations,
        "verification_commands": verification_commands,
    }


def main():
    if len(sys.argv) > 1:
        data = json.loads(Path(sys.argv[1]).read_text())
    else:
        data = json.loads(sys.stdin.read())

    result = analyze(data)
    result["ok"] = True
    result["module"] = "analyze_replication"
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
