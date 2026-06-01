"""CLI: eval command."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from storageops.ui.terminal import red, green, yellow, dim

# core eval_runner and signatures are imported lazily to keep CLI fast


def cmd_eval(args: argparse.Namespace) -> None:
    if getattr(args, "regression", False):
        _cmd_eval_regression(args)
        return

    from eval_runner import evaluate_case, evaluate_all
    from signatures import auto_detect

    cases_dir = Path(args.cases_dir)
    outputs_dir_raw = getattr(args, "outputs_dir", None)

    if args.case:
        if outputs_dir_raw:
            output_path = Path(outputs_dir_raw) / f"{args.case}.md"
            if not output_path.exists():
                print(f"{red('✗')} Output not found: {output_path}", file=sys.stderr)
                sys.exit(1)
            output_text = output_path.read_text(encoding="utf-8", errors="replace")
            result = evaluate_case(cases_dir / args.case, output_text)
        else:
            result = _fast_eval_case(cases_dir / args.case)
    elif args.all:
        if outputs_dir_raw:
            result = evaluate_all(cases_dir, Path(outputs_dir_raw))
        else:
            result = _fast_eval_all(cases_dir)
    else:
        print(f"{red('✗')} Specify --case, --all, or --regression", file=sys.stderr)
        sys.exit(1)

    result["ok"] = True
    result["module"] = "eval"
    print(json.dumps(result, indent=2, ensure_ascii=False))

    if result.get("failed", 0) > 0 or not result.get("passed", True):
        sys.exit(1)


def _fast_eval_case(case_path: Path) -> dict:
    from signatures import auto_detect
    import json as _json

    expected_path = case_path / "expected.json"
    if not expected_path.exists():
        return {"case": case_path.name, "passed": False, "error": "No expected.json"}

    expected = _json.loads(expected_path.read_text(encoding="utf-8"))
    input_dir = case_path / "input"
    texts: list[str] = []
    if input_dir.exists():
        for fpath in sorted(input_dir.iterdir()):
            if fpath.is_file():
                texts.append(fpath.read_text(encoding="utf-8", errors="replace"))
    text = "\n\n".join(texts)

    detections = auto_detect(text)
    top_domain = detections[0]["domain"] if detections else None
    top_conf = detections[0]["confidence"] if detections else 0.0
    expected_category = expected.get("expected_category")
    domain_ok = top_domain == expected_category

    return {
        "case": case_path.name, "mode": "fast", "passed": domain_ok,
        "score": round(top_conf, 3), "expected_category": expected_category,
        "actual_category": top_domain, "domain_match": domain_ok,
        "all_detections": [{"domain": d["domain"], "confidence": d["confidence"]}
                           for d in detections[:3]],
    }


def _fast_eval_all(cases_dir: Path) -> dict:
    results = []
    for case_path in sorted(cases_dir.iterdir()):
        if case_path.is_dir():
            results.append(_fast_eval_case(case_path))
    total = len(results)
    passed_count = sum(1 for r in results if r.get("passed"))
    avg_score = round(sum(r.get("score", 0) for r in results) / total, 3) if total else 0
    return {
        "mode": "fast",
        "note": "domain routing check only — does not represent full diagnostic quality",
        "total_cases": total, "passed": passed_count, "failed": total - passed_count,
        "aggregate_score": avg_score, "unsafe_output_detected": False, "cases": results,
    }


def _cmd_eval_regression(args: argparse.Namespace) -> None:
    import json

    metrics_file = Path(
        getattr(args, "metrics_file", None)
        or Path(__file__).parent.parent.parent / "storageops-eval-metrics.json"
    )
    threshold = getattr(args, "threshold", 0.10)

    if not metrics_file.exists():
        print(f"{red('✗')} Metrics file not found: {metrics_file}", file=sys.stderr)
        sys.exit(1)

    try:
        history = json.loads(metrics_file.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        print(f"{red('✗')} Cannot read metrics: {exc}", file=sys.stderr)
        sys.exit(1)

    if len(history) < 2:
        print(json.dumps({
            "ok": True, "regressions": [],
            "message": "Need at least 2 metric snapshots; only 1 found.",
        }))
        return

    prev_conf: dict[str, float] = history[-2].get("confidence", {})
    curr_conf: dict[str, float] = history[-1].get("confidence", {})
    regressions, improvements = [], []

    for case, curr in curr_conf.items():
        prev = prev_conf.get(case)
        if prev is None or prev < 0 or curr < 0:
            continue
        delta = curr - prev
        entry = {"case": case, "prev": round(prev, 4), "curr": round(curr, 4),
                 "delta": round(delta, 4)}
        if delta < -threshold:
            regressions.append(entry)
        elif delta > threshold:
            improvements.append(entry)

    result = {
        "ok": True, "module": "eval_regression",
        "prev_ts": history[-2].get("ts", "?"), "curr_ts": history[-1].get("ts", "?"),
        "threshold": threshold, "regressions": regressions,
        "improvements": improvements, "regression_count": len(regressions),
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if regressions:
        sys.exit(1)
