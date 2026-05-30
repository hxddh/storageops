"""
StorageOps Agent — diagnostic orchestrator.

Two modes:
  1. Rule-based (default, offline): deterministic parsers + analyzers.
     storageops agent <file>

  2. LLM-powered (requires --llm-provider + API key): ReAct loop with
     tool-calling, SKILL.md system prompt, and unsafe output gate.
     storageops agent <file> --llm-provider anthropic

API keys are NEVER hardcoded. Provide via:
  - ANTHROPIC_API_KEY environment variable
  - STORAGEOPS_LLM_KEY environment variable
  - ~/.storageops/config.yaml
  - --llm-key flag (not recommended for scripts)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


# Resolve storageops-core
CLI_DIR = Path(__file__).parent.parent
PROJECT_ROOT = CLI_DIR.parent
CORE_DIR = PROJECT_ROOT / 'storageops-core'
for sub in ['utils', 'parsers', 'analyzers']:
    p = str(CORE_DIR / sub)
    if p not in sys.path:
        sys.path.insert(0, p)

from secret_scanner import scan as scan_secrets


# ── Evidence Requirements per Domain ──────────────────────────────────

EVIDENCE_CHECKLIST = {
    's3_protocol_compatibility': {
        'required': [
            'Error code or message (SignatureDoesNotMatch, InvalidPart, etc.)',
            'Provider name and endpoint',
            'SDK or tool name and version',
        ],
        'helpful': [
            'Debug log with canonical request and string-to-sign',
            'Client region configuration',
            'Whether path-style or virtual-hosted-style is used',
        ],
    },
    'cli_sdk_behavior': {
        'required': [
            'Tool name and exact version',
            'The command that was run (redact secrets)',
            'Error output or debug log',
        ],
        'helpful': [
            'Configuration file (endpoint, region, concurrency settings)',
            'Whether the same operation works with a different tool',
            'Object size and count',
        ],
    },
    'performance_throughput': {
        'required': [
            'Tool and version used',
            'Observed throughput or timing data',
            'Object sizes and count',
        ],
        'helpful': [
            'Concurrency and part size settings',
            'RTT to endpoint (ping result)',
            'Client machine specs (CPU, memory, disk type)',
            'Any 429/503/5xx errors in logs',
        ],
    },
    'mount_filesystem_workspace': {
        'required': [
            'Mount type and version (s3fs, rclone mount, bosfs, etc.)',
            'Mount options (command line or fstab)',
            'Workspace description (git repos, node_modules, venv, etc.)',
        ],
        'helpful': [
            'Timing comparison: local SSD vs mount for same operation',
            'Kernel log FUSE errors: dmesg | grep -i fuse',
            'Concurrency: number of simultaneous users/processes',
        ],
    },
    'network_endpoint_access': {
        'required': [
            'Endpoint URL or hostname',
            'Access path type (public, VPC, PrivateLink, 专线)',
        ],
        'helpful': [
            'DNS resolution output: dig <endpoint-hostname>',
            'Ping/traceroute to endpoint',
            'TLS certificate details',
            'Proxy configuration',
        ],
    },
    'security_iam_policy': {
        'required': [
            'Full error message with request ID',
            'Bucket name and object key (if applicable)',
            'Action being attempted (GetObject, PutObject, ListBucket, etc.)',
        ],
        'helpful': [
            'IAM policy JSON for the principal (redact account IDs if needed)',
            'Bucket policy JSON',
            'Whether STS/temporary credentials are in use',
        ],
    },
    'lifecycle_cost': {
        'required': [
            'Lifecycle configuration (XML or description)',
            'Storage class of objects in question',
            'Object sizes and count per prefix',
        ],
        'helpful': [
            'Access frequency patterns (how often are objects read?)',
            'Current monthly cost breakdown if available',
            'Region and pricing tier',
        ],
    },
}


# ── Triage (inline, same logic as CLI) ───────────────────────────────

SIGNATURES = {
    's3_protocol_compatibility': [
        r'SignatureDoesNotMatch', r'InvalidSignature', r'CanonicalRequest',
        r'StringToSign', r'InvalidPart', r'CompleteMultipartUpload',
        r'ListObjectsV\d', r'ETag.*(?:mismatch|differ)',
    ],
    'cli_sdk_behavior': [
        r'corrupted on transfer', r'rclone\s+v[\d.]+', r'size differ',
        r'bcecmd', r'obsutil', r's5cmd\s+(?:cp|ls|sync)',
        r'botocore\.', r'aws-cli/',
    ],
    'performance_throughput': [
        r'\b429\b', r'SlowDown', r'RequestRateLimitExceeded',
        r'ThrottlingException', r'(?:upload|download|transfer).*slow',
        r'time(?:d\s+)?out', r'throughput', r'MB/s', r'MiB/s',
    ],
    'mount_filesystem_workspace': [
        r'\bfuse\b', r's3fs|bosfs|ossfs|gcsfuse', r'rclone mount',
        r'掉挂载|mount.*disconnect', r'workspace.*slow',
        r'stat.*storm|metadata.*amplif', r'OpenClaw',
    ],
    'network_endpoint_access': [
        r'endpoint.*unreachable', r'connection refused',
        r'TLS.*error|certificate.*error', r'DNS.*fail|NXDOMAIN',
        r'VPC.*endpoint|PrivateLink', r'MTU',
    ],
    'security_iam_policy': [
        r'AccessDenied', r'Access Denied', r'\b403\b',
        r'bucket.*policy|IAM.*policy', r'KMS.*denied',
        r'STS.*expir|session.*token.*expir',
    ],
    'lifecycle_cost': [
        r'lifecycle.*rule|LifecycleConfiguration',
        r'STANDARD_IA|GLACIER|DEEP_ARCHIVE',
        r'(?:storage|request|retrieval).*cost',
        r'Intelligent.*Tiering', r'minimum.*storage.*duration',
    ],
}


def classify_evidence(text: str) -> dict:
    """Classify evidence and assess completeness."""
    scores = {}
    for domain, patterns in SIGNATURES.items():
        score = sum(1 for p in patterns if re.search(p, text, re.IGNORECASE))
        if score > 0:
            scores[domain] = score

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    primary = ranked[0][0] if ranked else 'unknown'

    # Assess evidence quality
    if primary == 'unknown':
        quality = 'insufficient'
    else:
        checklist = EVIDENCE_CHECKLIST.get(primary, {})
        required = checklist.get('required', [])
        required_count = len(required)
        quality = 'partial' if required_count > 0 else 'sufficient'

    return {
        'primary_domain': primary,
        'all_domains': [d for d, _ in ranked],
        'scores': dict(scores),
        'evidence_quality': quality,
    }


def assess_evidence(text: str, domain: str) -> dict:
    """Check what evidence is present vs missing for a domain."""
    checklist = EVIDENCE_CHECKLIST.get(domain, {})
    if not checklist:
        return {'quality': 'unknown', 'missing': []}

    # Simple heuristic: check for key indicators
    missing_required = []
    missing_helpful = []

    has_debug = bool(re.search(
        r'\d{4}-\d{2}-\d{2}.*(?:DEBUG|ERROR|INFO|WARN)', text
    ))
    has_error = bool(re.search(
        r'(?:Error|ERROR|AccessDenied|SignatureDoesNotMatch|corrupted|failed)',
        text
    ))
    for req in checklist.get('required', []):
        indicator = _indicator_for(req)
        if indicator and not indicator(text):
            missing_required.append(req)

    for help_item in checklist.get('helpful', []):
        indicator = _indicator_for(help_item)
        if indicator and not indicator(text):
            missing_helpful.append(help_item)

    quality = 'sufficient' if not missing_required else 'partial'
    if not has_error and not has_debug:
        quality = 'insufficient'

    return {
        'quality': quality,
        'missing_required': missing_required,
        'missing_helpful': missing_helpful,
    }


def _indicator_for(item: str):
    """Return a lambda that checks if an evidence item is present."""
    indicators = {
        'error': lambda t: bool(re.search(r'(?:Error|ERROR|fail|denied)', t)),
        'tool': lambda t: bool(re.search(
            r'(?:aws-cli|rclone|s5cmd|bcecmd|obsutil|boto3|aws\s+s3)', t, re.IGNORECASE
        )),
        'debug': lambda t: bool(re.search(r'(?:DEBUG|--debug|-vv)', t)),
        'config': lambda t: bool(re.search(
            r'(?:endpoint|region|concurrency|part.size|chunk.size)', t, re.IGNORECASE
        )),
        'timing': lambda t: bool(re.search(
            r'(?:\d+\s*(?:ms|s|MB/s)|RTT|latency|ping|elapsed)', t, re.IGNORECASE
        )),
        'mount': lambda t: bool(re.search(
            r'(?:s3fs|bosfs|rclone mount|fuse|mount\s+-[a-zA-Z])', t, re.IGNORECASE
        )),
        'policy': lambda t: bool(re.search(
            r'(?:Statement|Effect|Principal|Action|Resource|bucket.*policy)', t
        )),
    }
    for key, fn in indicators.items():
        if key in item.lower():
            return fn
    return None


# ── Follow-up Question Generation ─────────────────────────────────────

def generate_questions(domain: str, evidence: dict) -> list[str]:
    """Generate specific follow-up questions for missing evidence."""
    questions = []
    missing = evidence.get('missing_required', [])
    helpful = evidence.get('missing_helpful', [])

    for item in missing[:3]:  # Max 3 questions per turn
        if 'error' in item.lower() or 'message' in item.lower():
            questions.append("请提供完整的错误消息或 debug 日志。")
        elif 'tool' in item.lower() or 'version' in item.lower():
            questions.append("你使用的是什么工具？请提供版本号（如 `aws --version`、`rclone version`）。")
        elif 'endpoint' in item.lower():
            questions.append("你连接的 endpoint URL 是什么？是公网、内网还是 VPC endpoint？")
        elif 'mount' in item.lower():
            questions.append("你用的挂载工具和版本是什么？请提供挂载命令或 fstab 配置（脱敏后）。")
        elif 'policy' in item.lower():
            questions.append("你有 IAM policy 或 bucket policy 的 JSON 吗？如果有请提供（脱敏后）。")
        elif 'config' in item.lower() or 'lifecycle' in item.lower():
            questions.append("请提供相关的配置文件内容（lifecycle XML、工具配置等，脱敏后）。")
        elif 'throughput' in item.lower() or 'timing' in item.lower():
            questions.append("请提供性能数据：上传/下载速度（MB/s）、操作耗时、是否有限流错误。")
        elif 'object' in item.lower() or 'size' in item.lower():
            questions.append("文件的大小和数量是多少？是单大文件还是很多小文件？")
        elif 'access' in item.lower() or 'principal' in item.lower():
            questions.append("是哪个用户/角色在操作？要执行什么操作（GetObject、PutObject）？对哪个 bucket？")
        else:
            questions.append(f"请提供更多信息：{item}")

    # If a helpful item would really help, add it
    if not questions and helpful:
        for item in helpful[:1]:
            questions.append(f"如果有的话，请提供：{item}")

    if not questions:
        questions.append("请提供更多上下文：使用的工具、endpoint、具体的错误消息。")

    return questions


# ── Analysis Pipeline ─────────────────────────────────────────────────

def run_analysis(domain: str, text: str) -> dict:
    """Run domain analysis. Returns structured result."""
    # Redact first
    secret_result = scan_secrets(text)
    if secret_result['count'] > 0:
        text = secret_result['redacted_text']

    result = {}
    try:
        if domain == 's3_protocol_compatibility':
            from parse_sigv4_error import parse_xml_error, diagnose as diagnose_sigv4
            if '<Code>SignatureDoesNotMatch</Code>' in text:
                result = diagnose_sigv4(parse_xml_error(text))
            elif '<Code>' in text:
                result = diagnose_sigv4(parse_xml_error(text))
            else:
                from parse_awscli_debug import parse as parse_awscli
                result = parse_awscli(text)

        elif domain == 'cli_sdk_behavior':
            if 'rclone' in text.lower():
                from parse_rclone_log import parse as parse_rclone
                result = parse_rclone(text)
            elif 's5cmd' in text.lower():
                from parse_s5cmd_error import parse as parse_s5cmd_err
                result = parse_s5cmd_err(text)
            else:
                from parse_awscli_debug import parse as parse_awscli
                result = parse_awscli(text)

        elif domain == 'performance_throughput':
            from parse_awscli_debug import parse as parse_awscli
            from detect_throttling import detect as detect_throttling
            parsed = parse_awscli(text)
            if parsed.get('summary', {}).get('has_throttling'):
                result = detect_throttling(parsed)
            else:
                result = parsed

        elif domain == 'mount_filesystem_workspace':
            from analyze_metadata_amplification import analyze as analyze_amp
            # Default profile for git status on mount
            result = analyze_amp({
                "rtt_ms": 50,
                "syscalls": {"stat": 10000, "open": 2000, "readdir": 200, "read": 5000},
                "operation_name": "git status (estimated)",
                "note": "Default estimation. Provide strace output for accurate analysis.",
            })

        elif domain == 'security_iam_policy':
            from analyze_policy import analyze as analyze_policy
            from analyze_policy import analyze_inline_403
            try:
                result = analyze_policy(json.loads(text))
            except json.JSONDecodeError:
                result = analyze_inline_403(text)

        elif domain == 'lifecycle_cost':
            from analyze_cost import analyze as analyze_cost
            try:
                result = analyze_cost(json.loads(text))
            except json.JSONDecodeError:
                from parse_lifecycle_xml import parse as parse_lifecycle
                result = parse_lifecycle(text)

        elif domain == 'network_endpoint_access':
            result = {
                "note": "Network diagnosis requires interactive tools. Run: "
                        "dig <hostname>, curl -v <endpoint>, mtr <hostname>",
                "recommendations": [
                    "Check DNS: dig <endpoint-hostname>",
                    "Check TCP: curl -v --connect-timeout 5 https://<endpoint>",
                    "Check path: mtr -r -c 10 <endpoint-hostname>",
                ],
            }
    except Exception as e:
        result = {"error": str(e), "note": "Analysis encountered an error. More evidence may be needed."}

    result['_secret_scan'] = {
        'findings': secret_result['count'],
        'redacted': secret_result['count'] > 0,
    }
    return result


# ── Report Generation ─────────────────────────────────────────────────

def generate_report(domain: str, analysis: dict, evidence_quality: str) -> str:
    """Generate a structured markdown report from analysis results."""
    secret_info = analysis.pop('_secret_scan', {})
    redacted_note = "\n> ⚠️ 此报告中的密钥和凭据已脱敏处理。\n" if secret_info.get('redacted') else ''

    report = f"""# 诊断报告

**分类:** {domain}
**证据质量:** {evidence_quality}
**生成方式:** StorageOps Agent v1.0 自动生成
{redacted_note}

## 摘要

{_extract_conclusion(analysis, domain)}

## 诊断结论

```json
{json.dumps(analysis, indent=2, ensure_ascii=False, default=str)[:3000]}
```

## 修复建议

{_extract_recommendations(analysis, domain)}

## 后续排查清单

- [ ] 审查以上诊断结论和证据
- [ ] 执行修复建议中的操作（manual-only：执行前请确认）
- [ ] 验证修复效果
- [ ] 如问题未解决，补充更多证据后重新运行诊断

---
*StorageOps Agent v1.0 | 所有结论应结合实际情况验证*
"""
    # Restore secret scan info
    analysis['_secret_scan'] = secret_info
    return report


def _extract_conclusion(analysis: dict, domain: str) -> str:
    """Extract a human-readable conclusion."""
    if analysis.get('conclusion'):
        return analysis['conclusion']
    if analysis.get('note'):
        return analysis['note']
    summary = analysis.get('summary', {})
    if summary.get('root_cause_likely'):
        return f"可能的根因：{summary['root_cause_likely']}"
    if summary.get('corrupted_count', 0) > 0:
        return f"检测到 {summary['corrupted_count']} 个传输校验失败。"
    if summary.get('has_signature_error'):
        return "检测到 SigV4 签名错误。"
    if analysis.get('denial_source'):
        return f"权限拒绝来源：{analysis['denial_source']}"
    return "详见下方诊断结论。"


def _extract_recommendations(analysis: dict, domain: str) -> str:
    """Extract recommendations."""
    recs = analysis.get('recommendations', [])
    single = analysis.get('recommendation', '')

    if recs and isinstance(recs, list):
        return '\n'.join(f'- {r}' for r in recs)
    if single and isinstance(single, str):
        return f'- {single}'
    if isinstance(single, dict):
        return '\n'.join(f'- {k}: {v}' for k, v in single.items())

    # Domain defaults
    defaults = {
        's3_protocol_compatibility': '- 检查时钟同步（ntp）。\n- 检查 region 配置。',
        'cli_sdk_behavior': '- 检查工具版本和配置。\n- 尝试不同工具对比。',
        'performance_throughput': '- 调整并发数和 part size。\n- 检查是否有限流。',
        'mount_filesystem_workspace': '- 考虑使用本地 SSD 作为 hot workspace。\n- 对象存储仅用于持久化和备份。',
        'security_iam_policy': '- 检查 IAM 和 bucket policy。\n- 确认跨账号时双方都有 Allow。',
        'lifecycle_cost': '- 检查 lifecycle 规则。\n- 小文件避免进入 Standard-IA。',
        'network_endpoint_access': '- 检查 DNS 解析。\n- 测试 TCP 连接和 TLS 握手。',
    }
    return defaults.get(domain, '- 分析结果详见上方 JSON。')


# ── Main Agent Loop ───────────────────────────────────────────────────

def agent_run(
    initial_file: str = None,
    interactive: bool = False,
    llm_provider: str | None = None,
    llm_model: str | None = None,
    llm_key: str | None = None,
    llm_base_url: str | None = None,
    max_turns: int = 8,
    verbose: bool = False,
    stream: bool = False,
    supervisor: bool = False,
) -> int:
    """Run the agent diagnostic loop. Returns exit code.

    If llm_provider is set, delegates to the LLM-powered agent.
    With supervisor=True, uses multi-agent triage-then-specialist routing.
    Otherwise runs the offline rule-based engine.
    """
    if llm_provider:
        return _agent_run_llm(
            initial_file=initial_file,
            provider_name=llm_provider,
            model=llm_model,
            api_key=llm_key,
            base_url=llm_base_url,
            max_turns=max_turns,
            verbose=verbose,
            stream=stream,
            supervisor=supervisor,
        )
    return _agent_run_rules(initial_file=initial_file, interactive=interactive)


def _agent_run_llm(
    initial_file: str | None,
    provider_name: str,
    model: str | None,
    api_key: str | None,
    base_url: str | None,
    max_turns: int,
    verbose: bool,
    stream: bool = False,
    supervisor: bool = False,
) -> int:
    """LLM-powered diagnostic agent."""
    try:
        from storageops.llm_agent import run_llm_agent
        from storageops.supervisor_agent import run_supervisor_agent
    except ImportError as exc:
        print(f"Error: LLM agent unavailable — {exc}")
        print("Install LLM dependencies: pip install 'storageops[llm]'")
        return 1

    if not initial_file:
        print("Error: --llm-provider requires an evidence file argument.")
        return 1

    path = Path(initial_file)
    if not path.exists():
        print(f"Error: file not found: {initial_file}")
        return 1

    evidence = path.read_text(encoding="utf-8", errors="replace")

    if supervisor:
        print(f"\n[StorageOps Supervisor] provider={provider_name}")
        result = run_supervisor_agent(
            evidence_text=evidence,
            provider_name=provider_name,
            api_key=api_key,
            model=model,
            base_url=base_url,
            max_turns=max_turns,
            verbose=verbose,
            stream=stream,
        )
    else:
        classification = classify_evidence(evidence)
        domain = classification["primary_domain"]
        print(f"\n[StorageOps LLM Agent] provider={provider_name} domain={domain}")
        result = run_llm_agent(
            evidence_text=evidence,
            domain=domain,
            provider_name=provider_name,
            api_key=api_key,
            model=model,
            base_url=base_url,
            max_turns=max_turns,
            verbose=verbose,
            stream=stream,
        )

    if not stream:
        print(f"\n{'='*60}")
        print(result["report"])
        print(f"{'='*60}")

    print(
        f"\n[Session {result['session_id']}] "
        f"turns={result['turns_used']} "
        f"tools={result['tool_calls_made']} "
        f"redacted={result.get('secrets_redacted', 0)}"
    )
    if result.get("secondary_report"):
        print(f"\n[Secondary: {result.get('secondary_domain')}]")
        print(result["secondary_report"])
    if result.get("error"):
        print(f"Status: {result['error']}")

    return 0 if result["ok"] else 1


def _agent_run_rules(initial_file: str = None, interactive: bool = False) -> int:
    """Run the agent diagnostic loop. Returns exit code."""
    all_evidence = []
    turn = 0
    max_turns = 5

    if initial_file:
        path = Path(initial_file)
        if not path.exists():
            print(f"错误: 文件不存在: {initial_file}")
            return 1
        all_evidence.append(path.read_text(encoding='utf-8', errors='replace'))

    while turn < max_turns:
        turn += 1
        combined_text = '\n---\n'.join(all_evidence)

        # Secret scan
        secret_result = scan_secrets(combined_text)
        if secret_result['count'] > 0:
            combined_text = secret_result['redacted_text']

        # Classify
        classification = classify_evidence(combined_text)
        domain = classification['primary_domain']

        if domain == 'unknown':
            print(f"\n[Agent turn {turn}] 无法确定问题类型。")
            print("请提供更多信息：错误消息、debug 日志、配置文件。")
            if not interactive:
                return 1
            user_input = input("\n> ").strip()
            if not user_input:
                break
            all_evidence.append(user_input)
            continue

        # Assess evidence
        evidence = assess_evidence(combined_text, domain)

        print(f"\n[Agent turn {turn}] 分类: {domain}")
        print(f"  检测到的域: {', '.join(classification['all_domains'])}")
        print(f"  证据质量: {evidence['quality']}")

        if secret_result['count'] > 0:
            print(f"  ⚠️  检测到 {secret_result['count']} 个疑似密钥，已脱敏")

        # Check if evidence is sufficient
        if evidence['quality'] in ('insufficient', 'partial') and turn < max_turns:
            questions = generate_questions(domain, evidence)
            print("\n  需要补充以下信息：")
            for q in questions[:3]:
                print(f"    • {q}")

            if not interactive:
                print("\n  [非交互模式] 请使用更多证据文件重新运行。")
                missing = evidence.get('missing_required', [])
                for m in missing:
                    print(f"    - 需要: {m}")
                return 1

            user_input = input("\n> ").strip()
            if not user_input:
                break
            all_evidence.append(user_input)
            continue

        # Run analysis
        print("\n  正在分析...")
        analysis = run_analysis(domain, combined_text)
        analysis['domain'] = domain
        analysis['evidence_quality'] = evidence['quality']

        # Generate report
        report = generate_report(domain, analysis, evidence['quality'])
        print(f"\n{'='*60}")
        print(report)
        print(f"{'='*60}")

        # Next steps
        if classification['all_domains'] and len(classification['all_domains']) > 1:
            others = [d for d in classification['all_domains'] if d != domain]
            print(f"\n  还检测到其他可能相关的域: {', '.join(others)}")
            print("  建议分别分析这些域以获得完整诊断。")

        return 0

    print(f"\n已达到最大交互轮次 ({max_turns})。")
    return 1
