# Changelog

## v1.0.0 — Autonomous Agent

- **Agent:** `storageops agent <evidence> [--interactive]` — autonomous multi-turn diagnostic agent
  - Automatic evidence quality assessment
  - Targeted follow-up questions when evidence is insufficient
  - Multi-domain detection with cross-domain routing suggestions
  - Structured markdown report generation
- **Cross-tool comparison:** `parse_s5cmd_error.py` detects awscli-works-but-s5cmd-fails patterns
- **Inline security analysis:** `analyze_inline_403()` diagnoses 403 errors without requiring policy JSON
- **Lifecycle XML parser:** `parse_lifecycle_xml.py` extracts transition/expiration rules with auto-warnings
- **pip install:** `pip install -e storageops-cli/` makes `storageops` available globally
- **CI:** GitHub Actions workflow — smoke tests + validation + eval on push
- **Git:** project under version control
- **Secret scanner:** expanded to 11 patterns including bce-auth and mid-line credential formats
- **rclone parser:** handles truncated logs, short MD5s, size diff details, timeout errors
- **Smoke tests:** 7/7 passing
- **Validation:** 5/5 real-world style cases, 0 gaps

## v0.3.0 — CLI

- **`storageops triage`:** classifies evidence, auto-detects domain, scans for secrets
- **`storageops analyze`:** runs domain-specific parser + analyzer pipeline
- **`storageops report`:** generates structured markdown from analysis JSON
- **`storageops eval`:** runs golden case evaluation with 7-dimension scoring
- Shell wrapper for development use without pip install

## v0.2.0 — Core Engines

- **Parsers:** awscli debug, rclone verbose, s5cmd debug, SigV4 error XML
- **Analyzers:** throughput/bottleneck, throttling detection, IAM policy tracing, metadata amplification, cost attribution
- **Eval runner:** golden case scoring with hard gates (category match + unsafe output)
- **Secret scanner:** redacts AK/SK, tokens, Authorization headers, embedded credentials
- **Smoke test:** 7 integration tests

## v0.1.0 — Skill Pack

- **10 diagnostic Skills:** triage, S3 protocol, CLI/SDK, performance, mount, network, security, lifecycle, reporting, eval
- **47 reference documents** covering SigV4, ETag, multipart, rclone, s5cmd, IAM policy, KMS, lifecycle, etc.
- **4 report templates:** customer, engineering note, reproduction checklist, diagnosis report
- **5 golden cases** with expected.json validation schemas
- **AGENTS.md + README.md** — project-level agent instructions
- **skill-registry.yaml** — skill discovery and routing
