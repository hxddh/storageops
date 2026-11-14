#!/usr/bin/env python3
"""Resolve StorageOps root-cause ids against the canonical contract.

The contract (``contract/root-causes.json``) is the single source of truth for
the vocabulary shared by skills, the golden-case eval, and the runtime
``submit_diagnosis`` validator. Terms are matched case-insensitively with ``_``
treated as ``-``, so a legacy ``hot_prefix_throttling`` and the canonical
``hot-prefix-throttling`` resolve to the same id.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CONTRACT_PATH = ROOT / "contract" / "root-causes.json"


def load_contract(path: Path | None = None) -> dict:
    return json.loads((path or CONTRACT_PATH).read_text(encoding="utf-8"))


def normalize(term: str) -> str:
    return (term or "").strip().lower().replace("_", "-")


def build_index(contract: dict) -> dict[str, dict[str, str]]:
    """Return ``{domain: {normalized_term: canonical_id}}``."""
    index: dict[str, dict[str, str]] = {}
    for domain, spec in contract.get("domains", {}).items():
        terms: dict[str, str] = {}
        for entry in spec.get("root_causes", []):
            canonical = entry["id"]
            terms[normalize(canonical)] = canonical
            for alias in entry.get("aliases", []):
                terms[normalize(alias)] = canonical
        index[domain] = terms
    return index


def resolve(term: str, domain: str | None = None, contract: dict | None = None) -> str | None:
    """Resolve a term to its canonical id, optionally restricted to one domain."""
    contract = contract or load_contract()
    index = build_index(contract)
    key = normalize(term)
    if domain:
        return index.get(domain, {}).get(key)
    hits = {ids[key] for ids in index.values() if key in ids}
    return hits.pop() if len(hits) == 1 else None


def domain_ids(domain: str, contract: dict | None = None) -> list[str]:
    contract = contract or load_contract()
    spec = contract.get("domains", {}).get(domain, {})
    return [entry["id"] for entry in spec.get("root_causes", [])]


def skill_for_domain(domain: str, contract: dict | None = None) -> str:
    contract = contract or load_contract()
    return contract.get("domains", {}).get(domain, {}).get("skill", "")


def canonical_matches(output_terms: list[str], expected_terms: list[str], domain: str | None = None) -> bool:
    """True when any produced term resolves to a canonical id any expectation names."""
    contract = load_contract()
    expected = {resolve(t, domain, contract) for t in expected_terms}
    expected.discard(None)
    if not expected:
        # Unresolvable expectations fall back to normalized equality so a typo in a
        # case file cannot silently pass everything.
        expected = {normalize(t) for t in expected_terms}
        return any(normalize(t) in expected for t in output_terms)
    return any(resolve(t, domain, contract) in expected for t in output_terms)
