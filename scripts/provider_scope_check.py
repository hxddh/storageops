#!/usr/bin/env python3
"""Multi-provider scope gate.

StorageOps serves *all* S3-compatible object storage (AWS S3, MinIO, Baidu BOS,
Alibaba OSS, Tencent COS, GCS), not only AWS. Deterministic helpers naturally get
written against AWS semantics first because AWS is the reference API the others
emulate — which is fine, as long as an AWS-locked helper *says so* instead of
silently misleading a non-AWS user.

This gate makes that explicit. A helper script is "AWS-locked" if it hardcodes an
AWS-only identifier (`amazonaws.com` service principal/endpoint, or `arn:aws:iam`
ARN construction) AND is not provider-parameterised (no `--provider`). Such a
helper must declare its scope with the literal marker `AWS-specific` (and should
emit a `"model": "aws"` field / point at the provider-differences reference) so
the lean is visible, not silent.

Provider-parameterised helpers (those exposing `--provider`) are exempt — they are
multi-provider by construction.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = sorted((ROOT / "skills").glob("storageops-*/scripts/*.py"))

# AWS-only identifiers that signal the helper is built on AWS semantics.
AWS_LOCK = re.compile(r"amazonaws\.com|arn:aws:iam")
# A helper that exposes a provider selector is multi-provider by construction.
PROVIDER_PARAM = "--provider"
# The explicit scope declaration an AWS-locked helper must carry.
SCOPE_MARKER = "AWS-specific"


def main() -> int:
    errors: list[str] = []
    for path in SCRIPTS:
        text = path.read_text(encoding="utf-8")
        if not AWS_LOCK.search(text):
            continue
        if PROVIDER_PARAM in text:
            continue
        if SCOPE_MARKER not in text:
            try:
                rel = path.relative_to(ROOT)
            except ValueError:
                rel = path
            errors.append(
                f"{rel}: helper hardcodes AWS-only identifiers (amazonaws.com / arn:aws:iam) "
                f"but does not declare its scope. Add the marker '{SCOPE_MARKER}' to the docstring "
                f"and emit a \"model\": \"aws\" field pointing at the provider-differences reference, "
                f"or make the helper provider-parameterised (--provider)."
            )

    if errors:
        print("Provider scope check FAILED:")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"Provider scope check passed: {len(SCRIPTS)} helpers, AWS-locked ones declare their scope")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
