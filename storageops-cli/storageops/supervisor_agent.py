"""
Supervisor agent: triage-first multi-agent orchestration.

Architecture:
  1. Fast rule-based triage (no LLM) classifies evidence into domains.
  2. Primary specialist LLM agent runs for the top domain.
  3. If multi-domain evidence detected (e.g., both IAM error AND rclone log),
     a secondary specialist runs with a reduced turn budget.
  4. Results are merged into a single output dict.

This decouples routing from diagnosis: the supervisor uses deterministic
rules, each specialist has a focused system prompt and tool set.
"""
from __future__ import annotations

import sys
from pathlib import Path

_CLI_DIR = Path(__file__).parent.parent
_CORE_DIR = _CLI_DIR.parent / "storageops-core"
for _sub in ("utils", "parsers", "analyzers"):
    _p = str(_CORE_DIR / _sub)
    if _p not in sys.path:
        sys.path.insert(0, _p)


# Domain-specific tool allowlists — each specialist only sees relevant tools
_DOMAIN_TOOLS: dict[str, list[str]] = {
    "cli_sdk_behavior": [
        "search_memory", "scan_secrets", "parse_rclone_log", "parse_awscli_debug",
        "detect_throttling", "analyze_throughput", "save_diagnosis",
        "generate_lifecycle_fix",
    ],
    "s3_protocol_compatibility": [
        "search_memory", "scan_secrets", "parse_sigv4_error", "parse_awscli_debug",
        "save_diagnosis",
    ],
    "performance_throughput": [
        "search_memory", "scan_secrets", "detect_throttling", "analyze_throughput",
        "parse_awscli_debug", "parse_rclone_log", "save_diagnosis",
    ],
    "security_iam_policy": [
        "search_memory", "scan_secrets", "analyze_policy", "parse_awscli_debug",
        "generate_policy_fix", "save_diagnosis",
    ],
    "lifecycle_cost": [
        "search_memory", "scan_secrets", "parse_lifecycle_xml", "analyze_cost",
        "generate_lifecycle_fix", "save_diagnosis",
    ],
    "mount_filesystem_workspace": [
        "search_memory", "scan_secrets", "parse_awscli_debug", "analyze_throughput",
        "save_diagnosis",
    ],
    "network_endpoint_access": [
        "search_memory", "scan_secrets", "parse_awscli_debug", "save_diagnosis",
    ],
}
_DEFAULT_TOOLS = [
    "search_memory", "scan_secrets", "parse_rclone_log", "parse_sigv4_error",
    "parse_awscli_debug", "analyze_policy", "detect_throttling", "save_diagnosis",
]


def _filter_tools(tool_definitions: list[dict], allowed: list[str]) -> list[dict]:
    allowed_set = set(allowed)
    return [t for t in tool_definitions if t["name"] in allowed_set]


def run_supervisor_agent(
    evidence_text: str,
    provider_name: str,
    api_key: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    max_turns: int = 10,
    verbose: bool = False,
    stream: bool = False,
) -> dict:
    """
    Triage evidence, route to specialist(s), merge results.

    Returns the primary result dict with optional 'secondary_report' added.
    """
    from storageops.llm_agent import run_llm_agent
    from storageops.tool_registry import TOOL_DEFINITIONS

    # ── Step 1: Rule-based triage (no LLM) ──────────────────────────
    domains = _triage(evidence_text)

    if not domains:
        primary_domain = "unknown"
        secondary_domains: list[str] = []
    else:
        primary_domain = domains[0]["domain"]
        # Only spawn secondary if confidence is meaningful
        secondary_domains = [
            d["domain"] for d in domains[1:2]
            if d["confidence"] >= 0.3 and d["domain"] != primary_domain
        ]

    if verbose:
        conf = domains[0]["confidence"] if domains else 0.0
        print(
            f"\n  [Supervisor] Primary: {primary_domain} ({conf:.0%})",
            file=sys.stderr,
        )
        if secondary_domains:
            print(f"  [Supervisor] Secondary: {secondary_domains[0]}", file=sys.stderr)

    # ── Step 2: Primary specialist ───────────────────────────────────
    primary_tools = _filter_tools(
        TOOL_DEFINITIONS, _DOMAIN_TOOLS.get(primary_domain, _DEFAULT_TOOLS)
    )

    primary_result = run_llm_agent(
        evidence_text=evidence_text,
        domain=primary_domain,
        provider_name=provider_name,
        api_key=api_key,
        model=model,
        base_url=base_url,
        max_turns=max_turns,
        verbose=verbose,
        stream=stream,
        _tool_override=primary_tools,
    )

    result = {
        **primary_result,
        "all_domains": [d["domain"] for d in domains],
        "routing": {
            "primary": primary_domain,
            "secondary": secondary_domains,
            "triage_scores": {d["domain"]: d["confidence"] for d in domains},
        },
    }

    # ── Step 3: Secondary specialist (optional) ───────────────────────
    if secondary_domains and primary_result.get("ok"):
        sec_domain = secondary_domains[0]
        sec_tools = _filter_tools(
            TOOL_DEFINITIONS, _DOMAIN_TOOLS.get(sec_domain, _DEFAULT_TOOLS)
        )
        if verbose:
            print(f"\n  [Supervisor] Running secondary specialist: {sec_domain}", file=sys.stderr)

        secondary_result = run_llm_agent(
            evidence_text=evidence_text,
            domain=sec_domain,
            provider_name=provider_name,
            api_key=api_key,
            model=model,
            base_url=base_url,
            max_turns=max(3, max_turns // 2),
            verbose=verbose,
            stream=False,  # Don't stream secondary
            _tool_override=sec_tools,
        )
        if secondary_result.get("ok"):
            result["secondary_domain"] = sec_domain
            result["secondary_report"] = secondary_result.get("report", "")
            result["secondary_root_cause"] = secondary_result.get("root_cause", "unknown")

    return result


def _triage(text: str) -> list[dict]:
    """Rule-based domain detection — same logic as cli.py auto_detect."""
    import re

    SIGNATURES = {
        "s3_protocol_compatibility": [
            r"SignatureDoesNotMatch", r"InvalidSignature",
            r"CanonicalRequest", r"StringToSign",
        ],
        "cli_sdk_behavior": [
            r"corrupted on transfer", r"rclone\s+v[\d.]+",
            r"size differ", r"aws-cli/", r"botocore\.",
        ],
        "performance_throughput": [
            r"\b429\b", r"SlowDown", r"RequestRateLimitExceeded",
            r"ThrottlingException", r"throughput", r"MB/s",
        ],
        "mount_filesystem_workspace": [
            r"\bfuse\b", r"s3fs|bosfs|ossfs", r"rclone mount",
        ],
        "network_endpoint_access": [
            r"endpoint.*unreachable|connection refused",
            r"TLS.*error|certificate.*error", r"DNS.*fail|NXDOMAIN",
        ],
        "security_iam_policy": [
            r"AccessDenied", r"Access Denied", r"\b403\b",
            r"bucket.*policy|IAM.*policy", r"KMS.*denied",
        ],
        "lifecycle_cost": [
            r"lifecycle.*rule|LifecycleConfiguration",
            r"STANDARD_IA|GLACIER|DEEP_ARCHIVE",
            r"minimum.*storage.*duration",
        ],
    }

    scores: dict[str, dict] = {}
    for domain, patterns in SIGNATURES.items():
        hits = sum(1 for p in patterns if re.search(p, text, re.IGNORECASE))
        if hits:
            scores[domain] = {
                "domain": domain,
                "confidence": min(round(hits / len(patterns), 2), 0.95),
            }

    ranked = sorted(scores.values(), key=lambda x: x["confidence"], reverse=True)
    return ranked
