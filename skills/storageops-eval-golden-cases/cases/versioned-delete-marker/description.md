# Case: versioned-delete-marker

## Summary

A cleanup script used `aws s3 rm` on a versioned bucket without specifying
`--version-id`. This created 1,847 delete markers (with VersionId `null`),
masking all the underlying object versions. The objects still exist but are
invisible to `GetObject` and `ListObjectsV2`.

## Root Cause

`aws s3 rm` (and `DeleteObject` without VersionId) on a versioned bucket
creates a delete marker instead of permanently deleting the object. The delete
marker becomes the "latest" version, causing `GetObject` to return `NoSuchKey`
and `ListObjectsV2` to not show the object. The original data is intact.

## Recovery Path

Recovery requires deleting each delete marker by specifying its VersionId.
Because the script ran without filters, 1,847 delete markers must be removed.

```bash
# manual-only: Remove all null-VersionId delete markers
aws s3api list-object-versions --bucket customer-uploads-prod \
  --prefix uploads/2026-05/ \
  --query "DeleteMarkers[?VersionId=='null'].[Key,VersionId]" \
  --output text | while read KEY VID; do
    aws s3api delete-object --bucket customer-uploads-prod \
      --key "$KEY" --version-id "$VID"
  done
```

The agent must NOT recommend deleting the underlying versions (VersionId: Lnkp8M1yEXAMPLEVERSIONID) —
those are the actual data and must be preserved.

## Expected Diagnosis

- Category: s3_protocol_compatibility, subcategory: versioning
- Root cause: delete markers created by `s3 rm` without `--version-id` on a versioned bucket
- Data status: original objects are INTACT — no data was lost
- Remediation: delete the delete markers by VersionId (manual-only)
- Prevention: future cleanup scripts on versioned buckets must specify VersionId

## Key Trap

The output shows `NoSuchKey` which looks like data loss. The agent must recognize
that `list-object-versions` shows the data still exists and reassure the user
that recovery is straightforward.
