# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.x (current) | ✅ Active development |

## Reporting a Vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities.

Report vulnerabilities by emailing the maintainers directly, or by opening a
[GitHub private security advisory](https://github.com/hxddh/storageops/security/advisories/new).

Include:
- A description of the vulnerability and its potential impact
- Steps to reproduce (proof-of-concept if applicable)
- Affected versions

We aim to acknowledge reports within 48 hours and provide a fix or mitigation within 14 days.

---

## Design-Level Security Constraints

StorageOps enforces the following constraints by design. These are non-negotiable and apply
to all code contributions.

### 1. Offline-Only Evidence Processing

StorageOps never connects to real cloud accounts, object storage endpoints, or external
services during diagnosis. All analysis is performed on locally-provided log files,
configuration files, and command output.

### 2. Credential Redaction Before Pi

All evidence text is scanned by `secret_scanner.scan()` before it is passed to Pi Coding
Agent. The scanner detects and replaces:

- AWS access keys (`AKIA*`, `ASIA*`, `A3T*`)
- Secret access keys and session tokens
- Authorization headers and Bearer tokens
- Cookie values
- API keys from common providers
- Signed URL parameters (`X-Amz-Credential`, `X-Amz-Signature`, etc.)

**Redacted text is written to a temporary file.** Pi receives only the temporary file path,
never the raw evidence content.

### 3. No Automated Remediation

StorageOps never executes remediation commands automatically. All suggested commands in
diagnostic reports must be labeled `manual-only` and reviewed by a human before running.

The `validate_agent_report()` function rejects any report that contains destructive commands
(e.g., `aws s3api delete-bucket`, `aws s3 rm`) without a `manual-only` label.

### 4. Log Content Is Untrusted Input

Log files, configuration files, and command output are treated as untrusted data.
They are never evaluated as instructions, shell commands, or agent prompts.
StorageOps does not pass raw log content as part of the Pi prompt — only the file path.

### 5. Report Validation

Pi-generated reports are validated before being printed:
- YAML frontmatter must be present with valid fields
- A `## Key Evidence` section must be present
- Destructive commands must include `manual-only`
- Any secrets that slipped through redaction are caught and the report is rejected

### 6. No Real Credentials Accepted

StorageOps does not accept real AWS/cloud AK/SK credentials through any interface.
The CLI, API server, and MCP server have no credential fields that would be used to
make authenticated cloud API calls.

---

## Dependency Security

`storageops-core` has **zero runtime dependencies** — no third-party packages are required
for the deterministic diagnostic engine. This minimizes the supply chain attack surface.

`storageops-cli` optional extras:
- `[api]`: fastapi, uvicorn (web server only, not enabled by default)
- `[mcp]`: mcp (Claude Desktop integration only)
- `[dev]`: pytest, ruff (development only, not installed in production)
