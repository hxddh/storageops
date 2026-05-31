"""
Parse Hadoop/Spark/Hive S3A filesystem errors.

Detects: rename failures (HADOOP-13345), staging vs magic committer issues,
AccessDenied on _temporary/, credential expiry, multipart abort failures,
S3AFileSystem errors, EMRFS vs native S3A conflicts.

Usage:
    cat spark-error.log | python parse_hadoop_s3a.py
"""
import re
import sys
import json
from pathlib import Path


_RE_S3A_ERROR = re.compile(
    r'(?:S3AFileSystem|org\.apache\.hadoop\.fs\.s3a)\S*[:\s]+([^\n]+)',
    re.IGNORECASE
)
_RE_RENAME_FAILURE = re.compile(
    r'(?:rename.*fail|fail.*rename|HADOOP-13345|Cannot rename|rename.*not.*support)',
    re.IGNORECASE
)
_RE_RENAME_PATH = re.compile(
    r'rename\s+(\S+)\s+(?:to\s+)?(\S+)',
    re.IGNORECASE
)
_RE_STAGING_COMMITTER = re.compile(
    r'(?:staging.*committer|StagingCommitter|FileOutputCommitter)',
    re.IGNORECASE
)
_RE_MAGIC_COMMITTER = re.compile(
    r'(?:magic.*committer|MagicS3GuardCommitter|Magic.*Commit)',
    re.IGNORECASE
)
_RE_COMMITTER_CONFIG = re.compile(
    r'spark\.hadoop\.fs\.s3a\.committer\.name\s*[=:\s]+(\S+)',
    re.IGNORECASE
)
_RE_TEMP_PATH = re.compile(
    r'(?:_temporary/|__spark_staging/|_SUCCESS)\S*',
    re.IGNORECASE
)
_RE_ACCESS_DENIED = re.compile(
    r'(?:AccessDenied|Access Denied|403)[^:]*(?:_temporary|staging)',
    re.IGNORECASE
)
_RE_CREDENTIAL_ERROR = re.compile(
    r'(?:credential.*expir|token.*expir|ExpiredToken|InvalidClientTokenId'
    r'|NoCredentialsError|credential.*fail|AWSCredentials)',
    re.IGNORECASE
)
_RE_MULTIPART_ABORT = re.compile(
    r'(?:abort.*multipart|multipart.*abort|AbortMultipartUpload.*fail)',
    re.IGNORECASE
)
_RE_EMRFS = re.compile(r'(?:EmrFileSystem|EMRFS|emr\.fs\.s3)', re.IGNORECASE)
_RE_S3A_PATH = re.compile(r's3a://[^\s<>"\']+', re.IGNORECASE)
_RE_SPARK_VERSION = re.compile(
    r'(?:spark[/ ])([\d.]+)',
    re.IGNORECASE
)
_RE_HADOOP_VERSION = re.compile(
    r'(?:hadoop[/ ]|hadoop-)([\d.]+)',
    re.IGNORECASE
)
_RE_HADOOP_ISSUE = re.compile(r'HADOOP-(\d+)', re.IGNORECASE)
_RE_EXCEPTION_LINE = re.compile(
    r'(?:Exception|Error)[:\s]+([^\n]+)',
    re.IGNORECASE
)


def _detect_committer_type(text: str):
    if _RE_MAGIC_COMMITTER.search(text):
        return "magic"
    if _RE_STAGING_COMMITTER.search(text):
        return "staging"
    m = _RE_COMMITTER_CONFIG.search(text)
    if m:
        val = m.group(1).lower()
        if 'magic' in val:
            return "magic"
        if 'staging' in val:
            return "staging"
        return val
    return None


def _extract_errors(text: str) -> list:
    errors = []

    # S3AFileSystem errors
    for m in _RE_S3A_ERROR.finditer(text):
        msg = m.group(1).strip()
        # Find associated path
        path_m = _RE_S3A_PATH.search(text[max(0, m.start()-100):m.end()+100])
        errors.append({
            "type": "S3AFileSystem",
            "path": path_m.group(0) if path_m else "",
            "message": msg[:200],
        })

    # Rename failures
    if _RE_RENAME_FAILURE.search(text):
        path = ""
        path_m = _RE_RENAME_PATH.search(text)
        if path_m:
            path = path_m.group(1)
        elif _RE_S3A_PATH.search(text):
            path = _RE_S3A_PATH.search(text).group(0)
        errors.append({
            "type": "rename_failure",
            "path": path,
            "message": "Rename operation failed — S3 does not support atomic rename",
        })

    # AccessDenied on _temporary/
    if _RE_ACCESS_DENIED.search(text):
        path_m = _RE_TEMP_PATH.search(text)
        errors.append({
            "type": "access_denied_staging",
            "path": path_m.group(0) if path_m else "_temporary/",
            "message": "AccessDenied on staging/temporary path",
        })

    # Credential errors
    if _RE_CREDENTIAL_ERROR.search(text):
        errors.append({
            "type": "credential_error",
            "path": "",
            "message": "Credential expiry or invalid credentials detected",
        })

    # Multipart abort failures
    if _RE_MULTIPART_ABORT.search(text):
        errors.append({
            "type": "multipart_abort_failure",
            "path": "",
            "message": "Multipart upload abort failed — orphaned parts may incur storage costs",
        })

    # EMRFS conflict
    if _RE_EMRFS.search(text):
        errors.append({
            "type": "emrfs_conflict",
            "path": "",
            "message": "EMRFS detected alongside S3A — potential conflict in filesystem implementation",
        })

    # Hadoop issue references
    for m in _RE_HADOOP_ISSUE.finditer(text):
        issue_num = m.group(1)
        errors.append({
            "type": f"HADOOP-{issue_num}",
            "path": "",
            "message": f"References HADOOP-{issue_num}",
        })

    return errors


def _extract_affected_paths(text: str) -> list:
    paths = list({m.group(0) for m in _RE_S3A_PATH.finditer(text)})
    temp_paths = list({m.group(0) for m in _RE_TEMP_PATH.finditer(text)})
    all_paths = paths + [p for p in temp_paths if p not in paths]
    return all_paths[:20]  # cap to avoid noise


def _root_cause_hint(errors: list, has_rename: bool, has_cred: bool, committer: str) -> str:
    if has_cred:
        return "credential_expiry"
    if has_rename and committer == "staging":
        return "staging_committer_rename_not_supported"
    if has_rename:
        return "s3_rename_not_atomic"
    if any(e["type"] == "access_denied_staging" for e in errors):
        return "iam_missing_staging_permission"
    if any(e["type"] == "emrfs_conflict" for e in errors):
        return "emrfs_s3a_conflict"
    if any(e["type"] == "multipart_abort_failure" for e in errors):
        return "multipart_abort_iam_or_network"
    if errors:
        return errors[0]["type"]
    return "unknown"


def parse(text: str) -> dict:
    """
    Parse Hadoop/Spark/Hive S3A error log and return structured diagnostics.

    Returns:
        {
            "errors": [{"type": str, "path": str, "message": str}],
            "committer_type": str | None,
            "has_rename_error": bool,
            "has_credential_error": bool,
            "spark_version": str | None,
            "hadoop_version": str | None,
            "affected_paths": [str],
            "summary": {"error_count": int, "root_cause_hint": str}
        }
    """
    errors = _extract_errors(text)

    committer_type = _detect_committer_type(text)
    has_rename_error = bool(_RE_RENAME_FAILURE.search(text))
    has_credential_error = bool(_RE_CREDENTIAL_ERROR.search(text))

    spark_m = _RE_SPARK_VERSION.search(text)
    spark_version = spark_m.group(1) if spark_m else None

    hadoop_m = _RE_HADOOP_VERSION.search(text)
    hadoop_version = hadoop_m.group(1) if hadoop_m else None

    affected_paths = _extract_affected_paths(text)
    root_cause = _root_cause_hint(errors, has_rename_error, has_credential_error, committer_type or "")

    return {
        "errors": errors,
        "committer_type": committer_type,
        "has_rename_error": has_rename_error,
        "has_credential_error": has_credential_error,
        "spark_version": spark_version,
        "hadoop_version": hadoop_version,
        "affected_paths": affected_paths,
        "summary": {
            "error_count": len(errors),
            "root_cause_hint": root_cause,
        },
    }


def main():
    if len(sys.argv) > 1:
        text = Path(sys.argv[1]).read_text(encoding='utf-8', errors='replace')
    else:
        text = sys.stdin.read()
    result = parse(text)
    result["ok"] = True
    result["module"] = "parse_hadoop_s3a"
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
