"""
Validation test: run real-world-style inputs through the full pipeline
and report gaps, failures, and areas needing improvement.

Usage:
    cd StorageOps
    python3 tests/validation/run_validation.py
"""
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

# Setup paths
sys.path.insert(0, str(PROJECT_ROOT / 'storageops-cli'))
sys.path.insert(0, str(PROJECT_ROOT / 'storageops-core' / 'utils'))
sys.path.insert(0, str(PROJECT_ROOT / 'storageops-core' / 'parsers'))
sys.path.insert(0, str(PROJECT_ROOT / 'storageops-core' / 'analyzers'))
sys.path.insert(0, str(PROJECT_ROOT / 'storageops-core' / 'analyzers'))

from secret_scanner import scan as scan_secrets

VALIDATION_DIR = Path(__file__).parent

cases = [
    {
        "id": "mixed-403-throttle",
        "file": "mixed-403-throttle.log",
        "description": "403 + 429 + timeout 混杂日志",
        "expected_domains": ["performance_throughput", "security_iam_policy"],
        "challenges": ["多域混杂", "部分请求成功部分失败", "timeout 和 429 同时出现"],
    },
    {
        "id": "truncated-rclone-batch",
        "file": "truncated-rclone-batch.log",
        "description": "截断的 rclone 批量同步日志，多个文件多种错误",
        "expected_domains": ["cli_sdk_behavior"],
        "challenges": ["日志截断", "多种错误类型混排", "部分成功部分失败", "config 分散在环境变量"],
    },
    {
        "id": "minimal-slow",
        "file": "minimal-slow.txt",
        "description": "用户只说'上传很慢'，几乎无证据",
        "expected_domains": ["unknown_insufficient_evidence"],
        "challenges": ["极简输入", "无日志", "无具体错误", "无量化数据"],
    },
    {
        "id": "awscli-works-s5cmd-fails",
        "file": "awscli-works-s5cmd-fails.txt",
        "description": "awscli 正常但 s5cmd 报错",
        "expected_domains": ["cli_sdk_behavior"],
        "challenges": ["跨工具对比", "只有命令输出没有 debug log", "错误信息不完整"],
    },
    {
        "id": "secrets-in-log",
        "file": "secrets-in-log.log",
        "description": "bcecmd 日志泄漏 AK/SK + Authorization header",
        "expected_domains": ["security_iam_policy"],
        "challenges": ["secrets 在 debug 输出中", "bcecmd 特定格式", "多个位置同时泄漏"],
    },
]


def run_triage(filepath: Path):
    """Import and run the triage logic directly."""
    text = filepath.read_text(encoding='utf-8', errors='replace')

    # Run secret scan
    secret_result = scan_secrets(text)

    # Auto-detect (same logic as CLI)
    detection_sigs = {
        's3_protocol_compatibility': [
            r'SignatureDoesNotMatch', r'InvalidSignature', r'CanonicalRequest',
            r'StringToSign', r'InvalidPart', r'CompleteMultipartUpload',
            r'ListObjects', r'ETag.*mismatch',
        ],
        'cli_sdk_behavior': [
            r'corrupted on transfer', r'rclone\s+v[\d.]+', r'size differ',
            r'bcecmd', r'obsutil', r's5cmd', r'botocore\.', r'aws-cli/',
        ],
        'performance_throughput': [
            r'\b429\b', r'SlowDown', r'RequestRateLimitExceeded',
            r'ThrottlingException', r'timeout', r'throughput',
        ],
        'mount_filesystem_workspace': [
            r'\bfuse\b', r's3fs|bosfs|ossfs|gcsfuse', r'rclone mount',
            r'掉挂载', r'workspace.*slow',
        ],
        'network_endpoint_access': [
            r'endpoint.*unreachable', r'connection refused',
            r'TLS.*error', r'DNS.*fail',
        ],
        'security_iam_policy': [
            r'AccessDenied', r'Access Denied', r'\b403\b',
            r'bucket.*policy|IAM.*policy',
        ],
        'lifecycle_cost': [
            r'lifecycle', r'STANDARD_IA|GLACIER',
            r'minimum.*storage.*duration',
        ],
    }

    import re
    scores = {}
    for domain, patterns in detection_sigs.items():
        score = 0
        for pat in patterns:
            if re.search(pat, text, re.IGNORECASE | re.MULTILINE):
                score += 1
        if score > 0:
            scores[domain] = score

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    primary = ranked[0][0] if ranked else 'unknown_insufficient_evidence'
    all_domains = [d for d, _ in ranked]

    return {
        "primary_domain": primary,
        "all_detected": all_domains,
        "scores": {d: s for d, s in scores.items()},
        "secret_findings": secret_result['count'],
        "secret_details": [f['type'] for f in secret_result['findings']],
    }


def run_analyze(domain: str, filepath: Path):
    """Try to run domain-specific analysis."""
    text = filepath.read_text(encoding='utf-8', errors='replace')

    # Redact first
    secret_result = scan_secrets(text)
    if secret_result['count'] > 0:
        text = secret_result['redacted_text']

    result = {"analysis_ran": False, "issues": []}

    try:
        if domain in ('performance_throughput',):
            from parse_awscli_debug import parse as parse_awscli
            from detect_throttling import detect as detect_throttling
            parsed = parse_awscli(text)
            if parsed.get('summary', {}).get('has_throttling') or parsed.get('summary', {}).get('has_access_denied'):
                result = detect_throttling({
                    "total_operations": len(parsed.get('operations', [])),
                    "status_codes": {429: parsed['summary'].get('has_throttling', 0) and 2 or 0,
                                    403: parsed['summary'].get('has_access_denied', 0) and 2 or 0,
                                    200: 2},
                    "errors": [],
                    "prefix_errors": {},
                })
                result["analysis_ran"] = True
            else:
                result["issues"].append("parser did not detect throttling or access denied")

        elif domain in ('cli_sdk_behavior',):
            if 'rclone' in text.lower():
                from parse_rclone_log import parse as parse_rclone
                parsed = parse_rclone(text)
                parsed["analysis_ran"] = parsed['summary']['total_files'] > 0
                parsed["issues"] = []
                if not parsed["analysis_ran"]:
                    parsed["issues"].append("no transfers found in rclone log")
                expected_issues = 5
                found_issues = (parsed['summary']['corrupted_count'] +
                               parsed['summary']['size_diff_count'] +
                               parsed['summary']['failed_count'])
                if found_issues < expected_issues:
                    parsed["issues"].append(f"expected ~{expected_issues} issues, found {found_issues}")
                result = parsed
            elif 's5cmd' in text.lower():
                from parse_s5cmd_error import parse as parse_s5cmd_err
                parsed = parse_s5cmd_err(text)
                parsed["analysis_ran"] = len(parsed.get('errors', [])) > 0
                parsed["issues"] = []
                if parsed.get('summary', {}).get('total_errors', 0) == 0:
                    parsed["issues"].append("no s5cmd errors extracted")
                result = parsed
            else:
                result["issues"].append("unrecognized CLI tool in input")

        elif domain in ('security_iam_policy',):
            if 'AccessDenied' in text or '403' in text:
                from analyze_policy import analyze as analyze_policy
                from analyze_policy import analyze_inline_403
                try:
                    policy_data = json.loads(text)
                    result = analyze_policy(policy_data)
                    result["analysis_ran"] = True
                except json.JSONDecodeError:
                    result = analyze_inline_403(text)
                    result["analysis_ran"] = True
                    result["issues"] = []
            else:
                result["issues"].append("no clear security finding")

        elif domain in ('s3_protocol_compatibility',):
            result["issues"].append("no SigV4/XML error detected in this input")

        elif domain == 'unknown_insufficient_evidence':
            result["analysis_ran"] = True
            result["note"] = "Cannot analyze — insufficient evidence."
            result["missing_evidence"] = [
                "具体错误信息或状态码",
                "使用的工具和版本",
                "对象大小、数量",
                "网络环境（RTT、带宽）",
                "debug log 或命令输出",
            ]

    except Exception as e:
        result["issues"].append(f"analysis exception: {e}")

    return result


def main():
    print("StorageOps Validation v0.3")
    print("=" * 60)

    results = []
    gaps = []

    for case in cases:
        print(f"\n{'─' * 60}")
        print(f"Case: {case['id']}")
        print(f"Description: {case['description']}")
        print(f"Challenges: {', '.join(case['challenges'])}")

        filepath = VALIDATION_DIR / 'inputs' / case['file']

        # Step 1: Triage
        triage = run_triage(filepath)
        print(f"\n  Triage → {triage['primary_domain']}")
        print(f"  All domains: {triage['all_detected']}")
        print(f"  Secret findings: {triage['secret_findings']}")

        # Check if expected domains were detected
        detected_expected = any(
            d in case['expected_domains'] for d in triage['all_detected']
        )
        if not detected_expected and 'unknown_insufficient_evidence' not in case['expected_domains']:
            gap = f"TRIAGE GAP [{case['id']}]: expected {case['expected_domains']}, got {triage['primary_domain']}"
            gaps.append(gap)
            print(f"  ⚠ {gap}")

        # Check if multi-domain detection worked
        if len(triage['all_detected']) > 1:
            print(f"  ✓ 正确检测到多域: {len(triage['all_detected'])} 个")
        elif len(case['expected_domains']) > 1:
            gap = f"MULTI-DOMAIN GAP [{case['id']}]: expected {len(case['expected_domains'])} domains, only detected {len(triage['all_detected'])}"
            gaps.append(gap)
            print(f"  ⚠ {gap}")

        # Step 2: Analyze
        analyze = run_analyze(triage['primary_domain'], filepath)
        print(f"\n  Analyze ({triage['primary_domain']}): ran={analyze['analysis_ran']}")
        if analyze.get('issues'):
            for issue in analyze['issues']:
                print(f"    ⚠ {issue}")
                gaps.append(f"ANALYZE GAP [{case['id']}]: {issue}")

        # Step 3: Missing evidence check
        if 'minimal' in case['id']:
            if triage['primary_domain'] == 'unknown_insufficient_evidence':
                print(f"  ✓ 正确识别为证据不足")
            else:
                gap = f"EVIDENCE GAP [{case['id']}]: should detect insufficient evidence"
                gaps.append(gap)
                print(f"  ⚠ {gap}")

        results.append({
            "case": case['id'],
            "triage_domain": triage['primary_domain'],
            "triage_all": triage['all_detected'],
            "analyze_ran": analyze['analysis_ran'],
            "issues": analyze.get('issues', []),
            "secrets_found": triage['secret_findings'],
        })

    # ── Summary ──
    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print(f"{'=' * 60}")

    # Secret detection rate
    secret_cases = [r for r in results if r['secrets_found'] > 0]
    print(f"\n  Secret detection: {len(secret_cases)}/5 cases had secrets properly detected")
    for r in secret_cases:
        print(f"    ✓ {r['case']}: {r['secrets_found']} findings")

    # Analysis success rate
    analyzed = [r for r in results if r['analyze_ran']]
    print(f"\n  Analysis success: {len(analyzed)}/5 cases produced analysis output")

    # Gaps
    print(f"\n  Gaps found: {len(gaps)}")
    for g in gaps:
        print(f"    {g}")

    # Recommendations
    print(f"\n{'=' * 60}")
    print("RECOMMENDED FIXES FOR v0.3 → v1.0")
    print(f"{'=' * 60}")

    if any('多域' in g or 'MULTI-DOMAIN' in g for g in gaps):
        print("  1. triage: 支持返回多个主域（非单一 primary），按优先级排序")
    if any('s5cmd' in g for g in gaps):
        print("  2. 补 parse_s5cmd_error.py 处理 s5cmd 的非 debug 错误输出")
    if any('JSON' in g or 'policy' in g.lower() for g in gaps):
        print("  3. analyze security: 支持内联 403 错误中的 policy 推断（无完整 JSON 时）")
    if any('insufficient' in g.lower() or 'EVIDENCE' in g for g in gaps):
        print("  4. triage: 极简输入时输出具体缺失证据清单和采集命令模板")
    print("  5. 补跨工具对比分析：awscli 正常 + s5cmd 失败 → 自动对比 endpoint/签名/参数")
    print("  6. v1.0 Agent: 发现证据不足/多域混杂时主动追问用户补采证据")

    sys.exit(0 if len(gaps) == 0 else 1)


if __name__ == '__main__':
    main()
