"""Canonical domain signatures for triage auto-detection.

Single source of truth for pattern-to-domain mapping.
Imported by storageops-cli and storageops-core.
"""
from __future__ import annotations

import re

# Each domain maps to a list of (pattern, subdomain) tuples.
SIGNATURES: dict[str, list[tuple[str, str]]] = {
    's3_protocol_compatibility': [
        (r'SignatureDoesNotMatch', 'sigv4'),
        (r'InvalidSignature', 'sigv4'),
        (r'CanonicalRequest', 'sigv4'),
        (r'StringToSign', 'sigv4'),
        (r'<Code>InvalidPart</Code>', 'multipart_upload'),
        (r'CompleteMultipartUpload', 'multipart_upload'),
        (r'ListObjects', 'list_objects'),
        (r'ETag.*mismatch', 'checksum_etag'),
        (r'Access-Control-Allow-Origin|NoSuchCORSConfiguration|CORS.*policy|preflight', 'cors'),
        (r'ReplicationStatus|ReplicationConfiguration|ReplicateObject|DeleteMarkerReplication',
         'replication'),
        (r'IsDeleteMarker|ListObjectVersions|VersionId.*null|NoncurrentVersion', 'versioning'),
        (r'XMinioStorageFull|XMinioInvalidObjectName', 'minio'),
        (r'InvalidBucketName.*r2|r2.*region', 'r2'),
    ],
    'cli_sdk_behavior': [
        (r'corrupted on transfer', 'rclone'),
        (r'rclone\s+v[\d.]+', 'rclone'),
        (r'size differ', 'rclone'),
        (r'bcecmd', 'bcecmd'),
        (r'obsutil', 'obsutil'),
        (r's5cmd', 's5cmd'),
        (r'botocore\.', 'boto3'),
        (r'aws-cli/', 'awscli'),
        (r'obsutil|huaweicloud|OBS', 'obsutil'),
        (r'rclone.*r2|cloudflare.*r2', 'r2'),
    ],
    'performance_throughput': [
        (r'\b429\b', 'throttling'),
        (r'SlowDown', 'throttling'),
        (r'RequestRateLimitExceeded', 'throttling'),
        (r'ThrottlingException', 'throttling'),
        (r'timeout', 'timeout'),
        (r'throughput', 'throughput'),
        (r'MB/s', 'throughput'),
        (r'MiB/s', 'throughput'),
    ],
    'mount_filesystem_workspace': [
        (r'\bfuse\b', 'mount'),
        (r's3fs|bosfs|ossfs|gcsfuse', 'mount'),
        (r'rclone mount', 'mount'),
        (r'掉挂载|mount.*disconnect', 'mount'),
        (r'stat.*storm|metadata.*amplif', 'mount'),
        (r'workspace.*slow', 'mount'),
    ],
    'network_endpoint_access': [
        (r'endpoint.*unreachable|connection refused', 'network'),
        (r'TLS.*error|certificate.*error', 'network'),
        (r'DNS.*fail|NXDOMAIN', 'network'),
        (r'VPC.*endpoint|PrivateLink', 'network'),
        (r'MTU', 'network'),
        (r'minio.*server|MinIO', 'minio'),
        (r'r2\.cloudflarestorage', 'r2'),
    ],
    'security_iam_policy': [
        (r'AccessDenied', 'security'),
        (r'Access Denied', 'security'),
        (r'\b403\b', 'security'),
        (r'bucket.*policy|IAM.*policy', 'security'),
        (r'STS.*expir|session.*token.*expir', 'security'),
        (r'KMS.*denied|kms:Decrypt', 'security'),
    ],
    'lifecycle_cost': [
        (r'lifecycle.*rule|LifecycleConfiguration', 'lifecycle'),
        (r'STANDARD_IA|GLACIER|DEEP_ARCHIVE', 'lifecycle'),
        (r'minimum.*storage.*duration', 'lifecycle'),
        (r'retrieval.*cost|request.*cost', 'lifecycle'),
        (r'Intelligent.*Tiering', 'lifecycle'),
    ],
    'cors_configuration': [
        (r'NoSuchCORSConfiguration', 'cors'),
        (r'CORSForbidden', 'cors'),
        (r'Access-Control-Allow-Origin', 'cors'),
        (r'preflight.*fail|OPTIONS.*403', 'cors'),
        (r'AllowedOrigin|AllowedMethod|AllowedHeader|ExposeHeader', 'cors'),
    ],
    'replication_versioning': [
        (r'ReplicationStatus.*FAILED|PENDING.*replication', 'replication'),
        (r'ReplicationConfiguration|ReplicateObject', 'replication'),
        (r'DeleteMarkerReplication|delete.*marker.*replicate', 'versioning'),
        (r'CRR|SRR|cross.region.replication|same.region.replication', 'replication'),
        (r'IsDeleteMarker.*true|ListObjectVersions', 'versioning'),
        (r'NoncurrentVersionTransition|VersionId.*null', 'versioning'),
    ],
    'bigdata_pipeline': [
        (r'S3AFileSystem|s3a://', 'hadoop_s3a'),
        (r'staging.*committer|magic.*committer|MagicS3GuardCommitter', 'committer'),
        (r'HADOOP-\d+|hadoop.*rename', 'hadoop'),
        (r'spark.*s3|pyspark.*s3|hive.*s3', 'spark_hive'),
        (r'_temporary/|__spark_staging', 'committer'),
        (r'EmrFileSystem|EMRFS', 'emrfs'),
    ],
}


def auto_detect(text: str) -> list[dict]:
    """Auto-detect issue domain from evidence text. Returns ranked detections."""
    scores: dict[str, dict] = {}
    for domain, patterns in SIGNATURES.items():
        score = 0
        matches: list[str] = []
        for pattern, subdomain in patterns:
            if re.search(pattern, text, re.IGNORECASE | re.MULTILINE):
                score += 1
                matches.append(subdomain)
        if score > 0:
            scores[domain] = {'score': score, 'subdomains': list(set(matches))}

    results = [
        {
            'domain': domain,
            'confidence': min(round(info['score'] / max(1, len(SIGNATURES[domain])), 2), 0.95),
            'subdomains': info['subdomains'],
        }
        for domain, info in scores.items()
    ]
    return sorted(results, key=lambda x: x['confidence'], reverse=True)
