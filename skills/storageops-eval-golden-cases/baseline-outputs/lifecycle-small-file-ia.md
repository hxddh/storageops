# Summary
Category: lifecycle_cost
Route: storageops-lifecycle-cost
Confidence: 0.80
Root Cause Type: small_object_ia_size_penalty
Evidence Quality: sufficient
Primary Diagnosis: root_cause_type=small_object_ia_size_penalty, affected_layer=storage_class

Tiny objects in STANDARD_IA are billed against the per-object 128KB minimum billable
size, so storage is amplified many-fold for sub-128KB objects.

# Key Evidence
- Objects in STANDARD_IA are far below the 128KB minimum-billable threshold, so each
  is billed as 128KB regardless of true size — a large multiplier (storage penalty).

# Remediation
- Add an object size filter so the lifecycle transition to IA applies only to objects
  above ~128KB (e.g. thumbnails transitioned after 30 days); keep small objects in STANDARD or pack them into larger objects.
