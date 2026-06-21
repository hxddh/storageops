# CRR fails because destination bucket versioning is disabled

A replication-versioning case. The replication rule is Enabled and the IAM role has
the right actions, but objects never replicate and show replication status FAILED —
because the **destination bucket has versioning disabled** (`get-bucket-versioning`
returns empty). S3 replication requires versioning on BOTH source and destination.

Expected diagnosis: enable versioning on the destination bucket; existing objects
then need S3 Batch Replication to backfill. Not an IAM or rule problem.
