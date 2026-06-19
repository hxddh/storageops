# Summary

Category: access_log_analysis
Route: storageops-access-log-analysis
Confidence: 0.85
Root Cause Type: delete_storm

The missing objects were deleted by a burst of `REST.DELETE.OBJECT` requests from
a single requester, the `cleanup-lambda` role, starting at 03:10 UTC. This is a
delete_storm from a cleanup job, consistent with the user's report that ~15,000
objects disappeared between 03:00 and 03:15 UTC — a cleanup_job_misconfiguration,
not a provider fault.

# Key Evidence

- Every logged line is `REST.DELETE.OBJECT` with status `204`, beginning at
  03:10:01Z and continuing each second.
- The requester is the same on every line:
  `arn:aws:iam::111111111111:role/cleanup-lambda` (single-requester attribution),
  with `user_agent=boto3/1.34` from `remote_ip=198.51.100.10`.
- The 03:10 burst aligns with the user-reported ~15,000 deletions in the
  03:00–03:15 window.

# Remediation

- First, pause the `cleanup-lambda` job / disable its trigger so the deletes
  stop; preserve the access logs as evidence before anything ages out.
- If the bucket has versioning, restore the deleted objects by removing the
  delete markers (or copying prior noncurrent versions back); enable versioning
  going forward so an accidental delete is recoverable.
- Constrain the cleanup role: scope its prefix, add a dry-run / object-count
  guardrail, and review the filter that selected 15,000 objects.
