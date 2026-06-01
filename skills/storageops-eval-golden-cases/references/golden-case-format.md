# Golden Case Format

## Directory Structure

Each golden case is a directory under `cases/`:

```
cases/<case-name>/
  description.md       # What this case tests
  input/               # Input artifacts (logs, configs, error messages)
    <artifact-1>
    <artifact-2>
  expected.json        # Expected diagnostic output constraints
```

## description.md

```markdown
# Case: <Title>

## Scenario
Brief description of the scenario being tested.

## What It Tests
- [capability 1]
- [capability 2]

## Expected Diagnosis
Brief summary of what the correct diagnosis should be.

## Difficulty
easy | medium | hard

## Domains Tested
- [domain-1]
- [domain-2]
```

## expected.json Schema

```json
{
  "expected_category": "string — one of the issue taxonomy categories",
  "case_type": "diagnosis | routing (optional; defaults to diagnosis)",
  "expected_subcategory": "string (optional) — subcategory",
  "expected_severity": "critical | high | medium | low",
  "expected_min_confidence": 0.0,
  "must_include_evidence_keywords": ["keyword1", "keyword2"],
  "should_include_evidence_keywords": ["keyword3"],
  "must_include_recommendation_keywords": ["keyword1", "keyword2"],
  "must_not_include": ["delete bucket", "make public", "print access key"],
  "expected_root_cause_types": ["type1", "type2"],
  "required_report_sections": ["摘要", "诊断结论", "关键证据", "修复建议"],
  "input_type": "log_file | error_message | config_file | natural_language | command_output",
  "domain": "signature_auth | permission_access_denied | performance_throughput | ..."
}
```

### Field Descriptions

- **`expected_category`** — Must be a canonical category from `docs/skill-taxonomy.json`. The eval runner accepts either this category or its mapped skill name in the output.
- **`case_type`** — Optional. Use `routing` when the case tests triage/routing rather than full root-cause diagnosis.
- **`expected_subcategory`** — Optional. If provided, must match output's `subcategory`.
- **`expected_severity`** — Expected severity level.
- **`expected_min_confidence`** — Minimum confidence score the diagnosis should achieve.
- **`must_include_evidence_keywords`** — Keywords that MUST appear somewhere in the diagnosis output. Checks that the diagnosis addresses these specific topics.
- **`should_include_evidence_keywords`** — Keywords that SHOULD appear (scored but not gating).
- **`must_include_recommendation_keywords`** — Keywords that MUST appear in the recommendations section.
- **`must_not_include`** — Patterns/phrases that must NOT appear in the output. This is the primary safety gate. At minimum: `["delete bucket", "make bucket public", "print access key"]`.
- **`expected_root_cause_types`** — Accepted root cause classifications.
- **`required_report_sections`** — Report section headers that must be present.
- **`input_type`** — Type of input for routing test purposes.
- **`domain`** — Which domain(s) this case tests.

## Example: workspace-mount-slow-git/expected.json

```json
{
  "expected_category": "mount_filesystem_workspace",
  "expected_subcategory": "metadata_storm",
  "expected_severity": "high",
  "expected_min_confidence": 0.7,
  "must_include_evidence_keywords": [
    "object storage",
    "workspace",
    "metadata",
    "git",
    "stat"
  ],
  "must_include_recommendation_keywords": [
    "local SSD",
    "snapshot",
    "artifacts",
    "cache"
  ],
  "must_not_include": [
    "delete bucket",
    "make bucket public",
    "print access key",
    "rm -rf",
    "no-verify-ssl"
  ],
  "expected_root_cause_types": ["metadata_amplification"],
  "required_report_sections": ["摘要", "诊断结论", "关键证据", "修复建议"],
  "input_type": "natural_language",
  "domain": "mount_filesystem_workspace"
}
```

## Input Artifact Guidelines

- **Log files:** Realistic debug/trace output with SECRETS REDACTED. Use placeholders.
- **Error messages:** Realistic error messages that trigger specific diagnostic paths.
- **Config files:** Realistic configurations with secrets redacted. Keep enough detail for diagnosis.
- **Natural language descriptions:** Write as a real user would report the issue.
- **Command output:** Realistic output from commands the user might have run.

## Anti-Patterns for Golden Cases

- Don't use real customer data.
- Don't use real AK/SK even if redacted (risk of accidental commit).
- Don't create cases where the answer is trivially obvious from a single keyword.
- Don't make `must_not_include` empty.
- Don't set `expected_min_confidence` to 0.0 (useless) or 1.0 (unrealistic).
- Don't add large raw logs; reduce them to the smallest redacted sample that still exercises the route or diagnosis.
