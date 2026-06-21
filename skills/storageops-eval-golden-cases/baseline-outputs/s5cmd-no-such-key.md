# Summary
Category: cli_sdk_behavior
Route: storageops-cli-sdk-diagnosis
Confidence: 0.80
Root Cause Type: wrong_key_path
Evidence Quality: sufficient
Primary Diagnosis: root_cause_type=wrong_key_path, affected_layer=configuration

s5cmd returns NoSuchKey / 404 because the key path does not match the stored object
key (a prefix/leading-slash mismatch), not because the object is missing.

# Key Evidence
- The NoSuchKey 404 from s5cmd is for a key path that differs from the actual stored
  prefix (extra/missing leading slash or wrong prefix segment).

# Remediation
- List the prefix (e.g. exports/2024 vs exports/2024-backup) to find the exact key, then correct the path; mind the leading
  slash and prefix segments in the s5cmd argument.
