# Example: rclone Reports `corrupted on transfer`

This example is a compact diagnosis for a common S3-compatible storage case:
rclone copies an object successfully, then reports an MD5 mismatch because the
source and destination expose different ETag formats.

## Incident

A user reports:

```text
ERROR : largefile.bin: corrupted on transfer: md5 hash differ
  "a1b2c3d4e5f6789012345678abcdef01"
  vs
  "a1b2c3d4e5f6789012345678abcdef01-3"
```

The object size is identical on both sides. The copy was a server-side copy
between two S3-compatible providers.

## Routing

The triage skill should classify this as:

```yaml
category: cli_sdk_behavior
secondary_categories:
  - consistency_integrity
route_to:
  - storageops-cli-sdk-diagnosis
evidence_quality: sufficient
```

The main signal is not the word `corrupted`; it is the shape of the two values.
A plain 32-character hex ETag is being compared with a multipart-style ETag that
has a `-N` suffix.

## Diagnosis

The destination object appears to have a multipart ETag:

```text
source:      a1b2c3d4e5f6789012345678abcdef01
destination: a1b2c3d4e5f6789012345678abcdef01-3
```

The `-3` suffix indicates a three-part multipart representation. rclone is
comparing the full destination ETag with the source MD5-like ETag, so it reports
a mismatch even though the useful prefix matches.

This evidence supports:

```yaml
root_cause_type: tool_sdk_incompatibility
confidence: 0.90
```

Do not claim absolute data integrity from ETag format alone. The correct wording
is that the provided evidence is consistent with an ETag format mismatch and
does not prove byte-level corruption.

## Recommended Response

Use a response like this:

```text
The failure is most likely an rclone/S3 ETag compatibility issue, not confirmed
file corruption. The destination ETag has a multipart suffix (`-3`) while the
source ETag is a plain 32-character value. Because this was a server-side copy
and the object size is unchanged, the strongest explanation is that rclone
compared two different ETag formats.

To proceed safely, verify one sample object end to end by downloading both sides
or by using provider-supported checksums. If that passes, rerun the copy with
`--s3-use-multipart-etag=false` for this provider pair. Avoid using
`--ignore-checksum` as the first fix because it disables broader integrity
checks.
```

## Safe Commands

Commands that transfer or delete data should remain manual-only unless the user
explicitly authorizes execution.

```bash
# manual-only: compare bytes outside ETag semantics
rclone copy source:bucket/largefile.bin /tmp/source-check/
rclone copy dest:bucket/largefile.bin /tmp/dest-check/
md5sum /tmp/source-check/largefile.bin /tmp/dest-check/largefile.bin

# manual-only: rerun with multipart ETag comparison disabled
rclone copy source:bucket dest:bucket --s3-use-multipart-etag=false
```

## Eval Linkage

The golden case for this scenario lives under:

```text
skills/storageops-eval-golden-cases/cases/rclone-corrupted-transfer/
```

The case should pass only when an answer:

- identifies rclone or S3 ETag behavior as the root cause,
- explains the multipart suffix,
- avoids claiming confirmed corruption from the log alone,
- recommends checksum-preserving verification before disabling checks.
