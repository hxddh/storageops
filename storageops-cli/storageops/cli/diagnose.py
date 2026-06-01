"""CLI: diagnose command — full Pi agent diagnosis (uses new Agent class)."""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import time
from pathlib import Path

from storageops.core.agent import Agent
from storageops.core.session import Session
from storageops.ui.display import StreamDisplay
from storageops.ui.terminal import c, bold, dim, green, yellow, red, cyan, hr, is_tty

from signatures import auto_detect  # noqa: F401


def cmd_diagnose(args: argparse.Namespace) -> None:
    fmt = getattr(args, "format", "human")
    file_arg = args.file

    if file_arg == "-":
        text = sys.stdin.read()
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, prefix="storageops-stdin-",
        )
        tmp.write(text)
        tmp.close()
        file_arg = tmp.name

    # Pre-flight classification
    if fmt == "human":
        try:
            text = Path(file_arg).read_text(encoding="utf-8", errors="replace")
            detections = auto_detect(text)
            domain = detections[0]["domain"] if detections else "unknown"
            conf = detections[0]["confidence"] if detections else 0.0
            print()
            print(bold("Diagnose") + "  " + dim(args.file))
            print(hr())
            pct = f"{conf * 100:.0f}%"
            conf_str = green(pct) if conf >= 0.7 else (yellow(pct) if conf >= 0.4 else red(pct))
            print(f"  Classifying evidence...    {green('✓')}  {bold(domain)}  ({conf_str})")
            print(f"  Starting Pi agent...       {yellow('→')}  (max {getattr(args, 'timeout_seconds', 600)}s)")
            print()
        except Exception:
            pass

    # Use the new Agent
    is_streaming = getattr(args, "stream", False)
    verbose = getattr(args, "verbose", False)

    session = Session()
    agent = Agent(
        session=session,
        max_turns=getattr(args, "max_turns", 8),
        timeout_seconds=getattr(args, "timeout_seconds", 600),
    )

    display = StreamDisplay(verbose=verbose)

    # Build redacted evidence text
    try:
        raw_text = Path(file_arg).read_text(encoding="utf-8", errors="replace")
    except OSError:
        raw_text = ""

    from secret_scanner import scan as scan_secrets
    secret_result = scan_secrets(raw_text)
    redacted_text = secret_result["redacted_text"]

    # Create temp evidence file for Pi to read
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", prefix="storageops-evidence-",
        delete=False, encoding="utf-8",
    ) as tmp:
        tmp.write(redacted_text)
        evidence_path = tmp.name

    # Build full prompt with evidence
    from storageops.core.context import build_prompt
    prompt = build_prompt(
        session, raw_text[:500],
        extra={
            "evidence_file": evidence_path,
            "original_filename": Path(file_arg).name,
            "redaction_count": str(secret_result.get("count", 0)),
        },
    )

    t_start = time.monotonic()

    try:
        events = agent.run(prompt)
    except Exception as exc:
        print(f"\n  {red('✗')} Error: {exc}\n")
        try:
            Path(evidence_path).unlink()
        except OSError:
            pass
        sys.exit(1)

    try:
        Path(evidence_path).unlink()
    except OSError:
        pass

    elapsed = time.monotonic() - t_start

    # Extract report
    report = ""
    for evt in events:
        if hasattr(evt, "text") and evt.text:
            report = evt.text

    if fmt == "human" and not is_streaming:
        print()
        print(hr(70))
        print(f"  {dim(f'{elapsed:.0f}s')}")
        print()

    print(report)

    if getattr(args, "exit_code", False):
        fm_match = re.search(r"severity:\s*(\w+)", report)
        sev = fm_match.group(1).lower() if fm_match else "unknown"
        sys.exit(1 if sev in ("critical", "high") else 0)

    agent.runtime.stop()
