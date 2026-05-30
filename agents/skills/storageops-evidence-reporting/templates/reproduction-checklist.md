# Reproduction Checklist Template

## Usage

Use this template to create a step-by-step reproduction guide for an issue.
The goal is that another engineer (or agent) can follow these steps and
reproduce the same symptoms.

---

# Reproduction Checklist: [Issue Title]

**Reference:** STORAGEOPS-REPRO-XXXX
**Related Diagnosis:** STORAGEOPS-XXXX

## Prerequisites

### Required Environment
- [ ] Client machine: [OS, specs, region, network]
- [ ] Required tools: [tool name and version]
  ```bash
  tool --version  # expect: X.Y.Z
  ```
- [ ] Required permissions: [list of IAM permissions needed, without secrets]
- [ ] Test bucket and objects: [describe setup]

### Required Credentials (Redacted)
- AK/SK with permissions as described above. Do NOT use production credentials.
- Configure credentials in the standard location for the tool.

## Reproduction Steps

### Step 1: [Setup Action]
```bash
# Command to set up the test environment
# Example: create test files of specific sizes
dd if=/dev/urandom of=testfile-10mb bs=1M count=10
```

**Expected result:** [What should happen]

### Step 2: [Reproduce the Issue]
```bash
# The exact command that triggers the issue
# manual-only: <command with placeholders>
```

**Expected result (issue present):** [The symptom you're trying to reproduce]
**Expected result (if fixed):** [What should happen after resolution]

### Step N: Clean Up
```bash
# Clean up test resources (manual-only)
# manual-only: cleanup commands
```

## Observed Results Log

| Attempt | Date | Result | Notes |
|---|---|---|---|
| 1 | YYYY-MM-DD | Symptom reproduced | |
| 2 | YYYY-MM-DD | | |

## Environment Variables

```bash
# Set these before reproduction (values redacted)
export AWS_DEFAULT_REGION=<region>
export AWS_ACCESS_KEY_ID=<test-key>
export AWS_SECRET_ACCESS_KEY=<test-secret>
```

## Common Pitfalls

1. **Pitfall:** [Description] → **Check:** [How to verify it's not the issue]
2. **Pitfall:** ...

## Success Criteria
- [ ] Issue is consistently reproducible.
- [ ] Steps are clear enough for another engineer to follow.
- [ ] All commands are safe (no destructive operations on production data).
