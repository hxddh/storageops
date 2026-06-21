# Summary
Category: mount_filesystem_workspace
Route: storageops-mount-filesystem-workspace
Confidence: 0.78
Root Cause Type: metadata_amplification
Evidence Quality: sufficient
Primary Diagnosis: root_cause_type=metadata_amplification, affected_layer=mount-cache

git on an rclone mount issues thousands of concurrent stat/HEAD calls (10000+ per status); each is a round-trip, so
git status appears to hang and operations time out — metadata amplification, not a bug.

# Key Evidence
- The fuse mount turns each git stat into a HEAD/GET round-trip; the timeout tracks
  directory size, not file content.

# Remediation
- Raise cache aggressiveness: --vfs-cache-mode full and a longer dir/stat cache TTL,
  or keep the git working tree on local disk and use the mount for bulk read/write.
