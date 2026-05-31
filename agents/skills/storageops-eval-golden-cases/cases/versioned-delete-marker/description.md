# Case: versioned-delete-marker

## What this case tests
Tests replication-versioning skill's ability to diagnose confusion around
delete markers in versioned buckets, including users thinking objects are
"deleted" when a delete marker is hiding them.

## Scenario
A user deleted objects from a versioned bucket and now sees "AccessDenied" or
"NoSuchKey" when trying to access them. They think the data is lost but the
previous versions still exist with delete markers on top.

## Expected Diagnosis
- Category: replication_versioning
- Subcategory: delete_marker
- Root cause: delete marker hiding previous versions
- Confidence >= 0.80
- Must explain: delete vs delete marker difference
- Must recommend: list-object-versions to find previous versions
