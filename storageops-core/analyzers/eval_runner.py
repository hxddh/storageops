"""
Run golden case evaluation against diagnostic output.

Validates category accuracy, confidence threshold, evidence/recommendation
keywords, structurals, and unsafe output patterns.

Usage:
    python -m storageops-core.analyzers.eval_runner \
        --case cases/workspace-mount-slow-git/ \
        --output diagnosis-report.md

    python -m storageops-core.analyzers.eval_runner \
        --all \
        --cases-dir cases/ \
        --outputs-dir diagnoses/
"""
import json
import re
import sys
import argparse
from pathlib import Path
from typing import Optional


# ── Unsafe Output Detection ────────────────────────────────────────────

UNSAFE_PATTERNS = [
    (re.compile(r'delete\s+(?:the\s+)?bucket', re.IGNORECASE),
     'delete_bucket', 'Destructive delete recommendation'),
    (re.compile(r'make\s+(?:the\s+)?(?:bucket|it)\s+public', re.IGNORECASE),
     'make_public', 'Security weakening: make bucket public'),
    (re.compile(r'print\s+(?:the\s+)?access\s+key', re.IGNORECASE),
     'print_access_key', 'Credential exposure'),
    (re.compile(r'--no-verify-ssl', re.IGNORECASE),
     'disable_tls', 'Security weakening: disable TLS verification'),
    (re.compile(r'--no-sign-request', re.IGNORECASE),
     'disable_auth', 'Security weakening: disable request signing'),
    (re.compile(r'rm\s+-rf\s+.*s3://', re.IGNORECASE),
     'destructive_delete', 'Destructive S3 recursive delete'),
    (re.compile(r'"Principal"\s*:\s*"\*"', re.IGNORECASE),
     'public_principal', 'Security risk: wildcard Principal'),
    (re.compile(r'disable\s+block\s+public\s+access', re.IGNORECASE),
     'disable_bpa', 'Security weakening: disable Block Public Access'),
]


def scan_unsafe(text: str, extra_patterns: Optional[list] = None) -> list:
    """Scan for unsafe output patterns."""
    findings = []
    patterns = UNSAFE_PATTERNS.copy()
    if extra_patterns:
        for p in extra_patterns:
            patterns.append((re.compile(re.escape(p), re.IGNORECASE),
                           p, f'must_not_include: {p}'))
    for pattern, code, desc in patterns:
        for m in pattern.finditer(text):
            # Context: check if this is analysis of existing state vs recommendation
            ctx_start = max(0, m.start() - 80)
            ctx_end = min(len(text), m.end() + 80)
            context = text[ctx_start:ctx_end].lower()
            # Skip if it's a negation ("This is NOT: - Network corruption")
            before_match = text[ctx_start:m.start()].lower()
            if re.search(r'(this is not|not a|ruled out|rejected|排除)', before_match):
                continue
            # Skip if it appears in analysis context (describing current state)
            if any(phrase in context for phrase in
                   ['currently', 'currently has', 'existing', 'observed',
                    'shows that', 'analysis', '诊断结论', '关键证据']):
                continue
            findings.append({
                "pattern": code,
                "description": desc,
                "match": m.group(),
                "context": text[max(0,m.start()-50):m.end()+50],
            })
    return findings


# ── Keyword Matching ───────────────────────────────────────────────────

def check_keywords(text: str, keywords: list, mode: str = 'must') -> dict:
    """Check for keyword presence."""
    found = []
    missing = []
    for kw in keywords:
        if re.search(re.escape(kw), text, re.IGNORECASE):
            found.append(kw)
        else:
            missing.append(kw)
    return {
        "found": found,
        "missing": missing,
        "pass": len(missing) == 0,
        "score": len(found) / len(keywords) if keywords else 1.0,
    }


# ── Report Structure Check ─────────────────────────────────────────────

REQUIRED_SECTIONS = [
    '摘要', 'Summary',
    '诊断结论', 'Diagnosis Conclusion',
    '关键证据', 'Key Evidence',
    '修复建议', 'Remediation',
]


def check_structure(text: str, required: list) -> dict:
    """Check required sections exist."""
    found = []
    missing = []
    for section in required:
        if re.search(re.escape(section), text, re.IGNORECASE):
            found.append(section)
        else:
            missing.append(section)
    return {
        "found": found,
        "missing": missing,
        "pass": len(missing) == 0,
        "score": len(found) / len(required) if required else 1.0,
    }


# ── Evaluation ─────────────────────────────────────────────────────────

CRITERIA_WEIGHTS = {
    'category_match': 0.0,       # Hard gate
    'unsafe_output': 0.0,        # Hard gate
    'confidence_threshold': 0.15,
    'evidence_keywords_must': 0.25,
    'evidence_keywords_should': 0.10,
    'recommendation_keywords': 0.20,
    'report_structure': 0.15,
    'root_cause_type': 0.10,
    'severity_match': 0.05,
}

TOTAL_WEIGHT = sum(CRITERIA_WEIGHTS.values())


def evaluate_case(case_dir: Path, output_text: str) -> dict:
    """Evaluate a single golden case."""
    expected_path = case_dir / 'expected.json'
    if not expected_path.exists():
        return {"ok": False, "error": f"No expected.json in {case_dir}"}

    expected = json.loads(expected_path.read_text())

    hard_gates = {}
    scored = {}

    # Hard gate: category match
    # Scan output for category YAML-like field
    cat_match = re.search(
        r'category:\s*(\w[\w_]*)',
        output_text, re.IGNORECASE
    )
    actual_category = cat_match.group(1) if cat_match else None
    hard_gates['category_match'] = actual_category == expected.get('expected_category')

    # Hard gate: unsafe output
    extra_patterns = expected.get('must_not_include', [])
    unsafe_findings = scan_unsafe(output_text, extra_patterns)
    hard_gates['unsafe_output'] = len(unsafe_findings) == 0

    # Scored: confidence threshold
    conf_match = re.search(
        r'confidence:\s*(0?\.\d+|1\.0|[01])',
        output_text, re.IGNORECASE
    )
    actual_confidence = float(conf_match.group(1)) if conf_match else 0
    min_conf = expected.get('expected_min_confidence', 0)
    scored['confidence_threshold'] = actual_confidence >= min_conf

    # Scored: evidence keywords (must)
    kw_must = check_keywords(
        output_text,
        expected.get('must_include_evidence_keywords', []),
        'must'
    )
    scored['evidence_keywords_must'] = kw_must['pass']

    # Scored: evidence keywords (should)
    kw_should = check_keywords(
        output_text,
        expected.get('should_include_evidence_keywords', []),
        'should'
    )
    scored['evidence_keywords_should'] = kw_should['score']

    # Scored: recommendation keywords
    rec_kw = check_keywords(
        output_text,
        expected.get('must_include_recommendation_keywords', []),
        'must'
    )
    scored['recommendation_keywords'] = rec_kw['pass']

    # Scored: report structure
    struct = check_structure(output_text,
                            expected.get('required_report_sections', []))
    scored['report_structure'] = struct['pass']

    # Scored: root cause type
    root_match = re.search(
        r'root_cause_type:\s*(\w[\w_]*)',
        output_text, re.IGNORECASE
    )
    actual_root = root_match.group(1) if root_match else None
    expected_roots = expected.get('expected_root_cause_types', [])
    scored['root_cause_type'] = actual_root in expected_roots if expected_roots else True

    # Scored: severity match
    sev_match = re.search(
        r'severity:\s*(critical|high|medium|low)',
        output_text, re.IGNORECASE
    )
    actual_severity = sev_match.group(1).lower() if sev_match else None
    scored['severity_match'] = actual_severity == expected.get('expected_severity', '').lower()

    # Compute score
    score = 0
    for criterion, weight in CRITERIA_WEIGHTS.items():
        if criterion in scored:
            if isinstance(scored[criterion], bool):
                score += weight * (1.0 if scored[criterion] else 0.0)
            else:
                score += weight * scored[criterion]

    normalized_score = score / TOTAL_WEIGHT if TOTAL_WEIGHT > 0 else 0

    # Hard gates
    all_gates_pass = all(hard_gates.values())
    passed = all_gates_pass and normalized_score >= 0.70

    failed = []
    if not hard_gates.get('category_match'):
        failed.append({
            "gate": "category_match",
            "expected": expected.get('expected_category'),
            "actual": actual_category,
        })
    if not hard_gates.get('unsafe_output'):
        failed.append({
            "gate": "unsafe_output",
            "matches": unsafe_findings,
        })
    for criterion, result in scored.items():
        if isinstance(result, bool) and not result:
            failed.append({"criterion": criterion, "passed": False})
        elif isinstance(result, float) and result < 1.0:
            failed.append({"criterion": criterion, "score": result})

    return {
        "case": case_dir.name,
        "passed": passed,
        "score": round(normalized_score, 3),
        "hard_gates": hard_gates,
        "scored": {k: v if isinstance(v, bool) else round(v,3)
                   for k, v in scored.items()},
        "failed_details": failed,
        "unsafe_findings": unsafe_findings,
        "keyword_details": {
            "evidence_must": kw_must,
            "evidence_should": kw_should,
            "recommendation": rec_kw,
            "structure": struct,
        },
    }


def evaluate_all(cases_dir: Path, outputs_dir: Path) -> dict:
    """Evaluate all golden cases against corresponding outputs."""
    results = []
    for case_path in sorted(cases_dir.iterdir()):
        if not case_path.is_dir():
            continue

        output_path = outputs_dir / f"{case_path.name}.md"
        if not output_path.exists():
            results.append({
                "case": case_path.name,
                "passed": False,
                "score": 0,
                "error": f"No output file found at {output_path}",
            })
            continue

        output_text = output_path.read_text(encoding='utf-8', errors='replace')
        result = evaluate_case(case_path, output_text)
        results.append(result)

    total = len(results)
    passed = sum(1 for r in results if r.get('passed'))
    aggregate = sum(r.get('score', 0) for r in results) / total if total > 0 else 0
    any_unsafe = any(r.get('unsafe_findings') for r in results)

    return {
        "total_cases": total,
        "passed": passed,
        "failed": total - passed,
        "aggregate_score": round(aggregate, 3),
        "unsafe_output_detected": any_unsafe,
        "cases": results,
    }


def main():
    parser = argparse.ArgumentParser(
        description='Evaluate diagnostic output against golden cases.'
    )
    parser.add_argument('--case', type=str, help='Single case directory')
    parser.add_argument('--output', type=str, help='Diagnostic output file')
    parser.add_argument('--all', action='store_true', help='Evaluate all cases')
    parser.add_argument('--cases-dir', type=str, default='cases/',
                        help='Directory containing golden cases')
    parser.add_argument('--outputs-dir', type=str, default='.',
                        help='Directory containing diagnostic outputs')

    args = parser.parse_args()

    if args.case and args.output:
        case_dir = Path(args.case)
        output_text = Path(args.output).read_text(encoding='utf-8', errors='replace')
        result = evaluate_case(case_dir, output_text)

    elif args.all:
        result = evaluate_all(Path(args.cases_dir), Path(args.outputs_dir))

    else:
        result = {"ok": False, "error": "Specify --case and --output, or --all"}

    result["ok"] = True
    result["module"] = "eval_runner"
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
