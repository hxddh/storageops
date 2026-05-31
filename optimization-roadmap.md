# Next-Step Optimization Plan

## Phase 6: Practical Completeness (本次)

### P0: Evidence Collection How-To (8 skills)
Skills say "you need X evidence" but not "here's how to collect it."
Add a "How to collect evidence" subsection to: lifecycle-cost, mount, network,
performance, replication-versioning, s3-protocol, security-iam-policy, eval.

### P1: Deepen Thin References (4 files)
- `bcecmd.md` — Currently 2.0KB. Add debug log parsing, common issues matrix
- `prefix-hotspot.md` — 2.3KB. Add detection methods, AWS partition model
- `checksum-etag.md` — 2.4KB. Add provider-specific ETag algorithms
- `integration-test-plan.md` — New. Already covers multi-skill flow

### P1: Provider Conditional Branches (7 skills)
Add "if provider is BOS → check bos.md quirks" conditional logic to skills
that currently have no provider-specific handling.

### P2: Cross-Skill Chaining
Auto-invoke workflow: triage output → parse route_to → invoke specialists → 
gather results → invoke evidence-reporting.

---

## Phase 7: Production Readiness (future)

- Real-world dry-run: feed StorageOps simulated-rclone-errors.log through the full pipeline
- Latency benchmarks: how fast does pi respond with all 11 skills loaded?
- CI/CD: GitHub Actions for golden case regression
- Freshness: provider pricing/behavior update mechanism
