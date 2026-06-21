# Routing
Category: mount_filesystem_workspace
Route: storageops-mount-filesystem-workspace
Confidence: 0.78
Root Cause Type: metadata_amplification

Slow git status on an s3fs mount is a metadata-amplification problem, routed to
mount-filesystem-workspace rather than throughput: it is per-file metadata calls,
not bandwidth. Keep the workspace on local disk where possible.

# Evidence Gaps
- Need the mount tool/options and a timing comparison (local vs mount) plus the
  stat/open call counts to confirm metadata amplification.
