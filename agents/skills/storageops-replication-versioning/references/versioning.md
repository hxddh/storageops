# S3 Object Versioning

## Overview

When versioning is enabled on a bucket, S3 assigns a unique VersionId to every
object stored. All versions of an object are retained until explicitly deleted.

States:
- **Unversioned** (default) — No versioning; all PutObject to same key overwrites
- **Versioning-enabled** — Every PutObject creates a new version; each has a VersionId
- **Versioning-suspended** — No new versions created; new PutObject gets VersionId `null`; existing versions retained

---

## Key Operations and Version Behavior

| Operation | Versioned Bucket Behavior |
|---|---|
| `PutObject` | Creates a new version with a new VersionId |
| `GetObject` (no VersionId) | Returns the latest version; if latest is a delete marker, returns 404 |
| `GetObject` (with VersionId) | Returns that specific version |
| `DeleteObject` (no VersionId) | Creates a delete marker; does NOT delete any version |
| `DeleteObject` (with VersionId) | Permanently deletes that specific version |
| `ListObjects` / `ListObjectsV2` | Shows only the latest non-delete-marker version |
| `ListObjectVersions` | Shows ALL versions and delete markers |

---

## Delete Markers

A delete marker is a placeholder that makes the object "look deleted" to unversioned API calls.

**Properties:**
- Has a VersionId like any other version
- Has `IsDeleteMarker: true`
- Has no data (zero bytes)
- `GetObject` on the latest delete marker returns 404
- The underlying versions are NOT deleted

**Creating a delete marker:**
- `DeleteObject` without VersionId on a versioned bucket creates a delete marker

**Removing a delete marker (manual-only):**
- `DeleteObject` specifying the delete marker's VersionId permanently removes the marker
- The prior version becomes the new latest version and is visible again

---

## Common Versioning Issues

### "Object not found" after delete

**Cause:** A delete marker was created as the latest version.

**Diagnosis:**
```
# manual-only: aws s3api list-object-versions --bucket <bucket> --prefix <key>
```
Look for: `IsDeleteMarker: true` on the latest version entry.

**Resolution:** Delete the delete marker (specify its VersionId) to restore visibility.

### "NoSuchVersion" on GetObject with VersionId

**Cause:** The specified VersionId does not exist. Either:
- The version was permanently deleted (DeleteObject with its VersionId)
- The VersionId was from a different bucket
- The object was overwritten and the old VersionId was garbage-collected (only possible if lifecycle rules expire noncurrent versions)

**Diagnosis:**
```
# manual-only: aws s3api list-object-versions --bucket <bucket> --prefix <key>
```
Check if the VersionId appears in the list.

### Unbounded version accumulation

**Cause:** No lifecycle rule to expire noncurrent versions.

**Check:**
```
# manual-only: aws s3api get-bucket-lifecycle-configuration --bucket <bucket>
```
Look for `NoncurrentVersionExpiration` rules.

**Recommended lifecycle rule (manual-only):**
```xml
<Rule>
  <ID>expire-old-versions</ID>
  <Status>Enabled</Status>
  <NoncurrentVersionExpiration>
    <NoncurrentDays>30</NoncurrentDays>
  </NoncurrentVersionExpiration>
</Rule>
```

### Delete markers accumulating

**Cause:** No lifecycle rule to clean up expired delete markers.

**Recommended lifecycle rule (manual-only):**
```xml
<Rule>
  <ID>expire-delete-markers</ID>
  <Status>Enabled</Status>
  <Expiration>
    <ExpiredObjectDeleteMarker>true</ExpiredObjectDeleteMarker>
  </Expiration>
</Rule>
```

### Versioning suspended, null versions

When versioning is suspended:
- New PutObject creates a `null` version
- If a `null` version already exists, the new one overwrites it
- All other versioned objects are unaffected
- Replication and Object Lock require versioning to be Enabled, not Suspended

---

## Lifecycle Rules for Versioned Buckets

| Rule Type | Effect |
|---|---|
| `Expiration` | Expires the current version (creates a delete marker) |
| `NoncurrentVersionExpiration` | Permanently deletes non-current versions after N days |
| `ExpiredObjectDeleteMarker` | Removes delete markers that are the only version remaining |
| `NoncurrentVersionTransition` | Moves non-current versions to a cheaper storage class |

---

## Cost Impact of Uncleaned Versions

All versions (including noncurrent and delete markers) occupy storage and incur cost.
A bucket without `NoncurrentVersionExpiration` lifecycle rules will accumulate
unbounded versions, potentially multiplying storage cost significantly.

Example: 100 GB of objects with 10 versions each = 1 TB billed storage.
