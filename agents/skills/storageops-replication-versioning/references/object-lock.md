# S3 Object Lock (WORM)

## Overview

S3 Object Lock enforces write-once-read-many (WORM) policies. Once configured,
objects cannot be overwritten or deleted until their retention period expires.

Object Lock requires versioning to be enabled on the bucket and must be enabled
at bucket creation time (cannot be enabled retroactively on existing buckets).

---

## Lock Modes

### GOVERNANCE mode

- Objects are protected from deletion or modification
- Users with `s3:BypassGovernanceRetention` permission can override and delete
- Use for: internal compliance, accidental-deletion protection

### COMPLIANCE mode

- Objects CANNOT be deleted or modified by ANY user, including the AWS root account
- The retain-until date CANNOT be shortened (only extended)
- The lock mode CANNOT be changed from COMPLIANCE to GOVERNANCE
- Use for: regulatory requirements (SEC 17a-4, FINRA, CFTC)

---

## Retention Period vs Legal Hold

| Feature | Retention Period | Legal Hold |
|---|---|---|
| Set by | Object owner | Any user with `s3:PutObjectLegalHold` |
| Duration | Fixed until a specific date | Indefinite, until explicitly removed |
| Effect | Object protected until retain-until date | Object protected regardless of retain-until |
| Override | GOVERNANCE: bypassable; COMPLIANCE: never | Removable with permission |

---

## Common Error Patterns

### "AccessDenied" on delete of locked object

```
An error occurred (AccessDenied) when calling the DeleteObject operation:
User is not authorized to perform s3:DeleteObject with Object Lock
```

**Cause:** Object has an active COMPLIANCE or GOVERNANCE lock.

**Diagnosis:**
```
# manual-only: aws s3api get-object-retention --bucket <bucket> --key <key> --version-id <vid>
# manual-only: aws s3api get-object-legal-hold --bucket <bucket> --key <key> --version-id <vid>
```

**Resolution:**
- GOVERNANCE: Can be overridden with `s3:BypassGovernanceRetention`
- COMPLIANCE: Cannot be deleted until retain-until date passes — warn user
- Legal hold: Remove the hold with `delete-object-legal-hold` (manual-only)

### "ObjectLockConfigurationNotFoundError"

```
An error occurred (ObjectLockConfigurationNotFoundError) when calling
the PutObjectRetention operation: Object Lock configuration does not exist
```

**Cause:** The bucket was created without Object Lock enabled. Object Lock cannot
be enabled after bucket creation.

**Resolution:** Create a new bucket with Object Lock enabled and migrate objects.

### "InvalidRequest" — Cannot reduce retain-until date in COMPLIANCE mode

**Cause:** Attempting to shorten or remove the retention period on a COMPLIANCE-locked object.

**Resolution:** Not possible. Retain-until date in COMPLIANCE mode is immutable until it passes.

---

## Bucket-Level Default Retention

A bucket can have a default retention policy that applies to all new objects:
```
# manual-only: aws s3api get-object-lock-configuration --bucket <bucket>
```

Returns the default `Mode` and `Days`/`Years`. New objects that do not explicitly
specify retention inherit the bucket default.

---

## Interaction with Lifecycle Rules

Object Lock and lifecycle rules interact:
- Lifecycle expiration will NOT delete COMPLIANCE-locked objects before their retain-until date
- Lifecycle rules and Object Lock are independent — both are enforced
- A lifecycle rule set to expire objects in 30 days will fail silently on locked objects
- Locked objects accumulate beyond the intended lifecycle window

---

## Checking Lock Status

```bash
# manual-only: Check if bucket has Object Lock
aws s3api get-object-lock-configuration --bucket <bucket>

# manual-only: Check specific object retention
aws s3api get-object-retention \
  --bucket <bucket> \
  --key <object-key> \
  --version-id <version-id>

# manual-only: Check legal hold
aws s3api get-object-legal-hold \
  --bucket <bucket> \
  --key <object-key> \
  --version-id <version-id>
```

---

## Safety Constraints

- **NEVER recommend bypassing COMPLIANCE mode** — it may violate regulatory requirements
- Always check if the user is in a regulated industry before discussing lock bypass
- All Object Lock changes must be tagged `manual-only`
- Warn the user that COMPLIANCE lock cannot be removed or shortened even by Anthropic/AWS support
