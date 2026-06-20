# Cost Analysis: Premature GLACIER transition triggers minimum-duration penalty

Route: storageops-lifecycle-cost
Category: lifecycle_cost
Confidence: 0.85
Evidence Quality: sufficient
Root Cause Type: minimum_duration_penalty

# Summary

This is expected lifecycle billing behavior, not a provider fault. The lifecycle
rule transitions objects into GLACIER at day 30 and expires (deletes) them at day
60. GLACIER enforces a 90-day minimum storage duration, so each object is billed
for the full 90 days while it physically resides in GLACIER for only 30 days. The
result is 30 wasted days of minimum-duration billing per object — a
minimum_duration_penalty caused by a premature transition.

# Key Evidence

- Lifecycle rule `ArchiveThenExpire` has a `transition` to GLACIER at day 30 and
  an `Expiration` at day 60 (the `expire` / delete action;
  residency in GLACIER = 30 days).
- GLACIER has a minimum storage duration of 90 days. Deleting or re-transitioning
  before that minimum still bills the full 90 days.
- 90 (minimum) − 30 (actual residency) = 60 wasted days of minimum-duration
  billing for every object that completes the transition.
- The simulator `lifecycle_rule_simulator.py` reports
  `min_duration_risks: [{class: GLACIER, min_days: 90, residency_days: 30,
  wasted_days: 60}]`, confirming the penalty structurally (in days, not money).
- Average object size (~5 MB) is above the minimum billable size, so the
  small-object size multiplier is not a contributing factor here.

# Remediation

- Align the lifecycle timing with the GLACIER minimum duration: either delay the
  transition into GLACIER, or extend object residency to at least the 90-day
  minimum duration before the expiration deletes them.
- If objects truly must be deleted at 60 days, do not transition them to GLACIER
  at all — keep them in STANDARD (or STANDARD_IA after confirming its 30-day
  minimum duration) so no archive minimum-duration penalty applies.
- Re-run `lifecycle_rule_simulator.py` after adjusting the transition day to
  confirm `wasted_days` drops to 0 before applying the change in production.
