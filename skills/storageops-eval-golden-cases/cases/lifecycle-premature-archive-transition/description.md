# Case: Premature GLACIER Transition Triggers Minimum-Duration Penalty

## Scenario

A lifecycle rule transitions objects from STANDARD to GLACIER after 30 days, then
expires (deletes) them after 60 days. GLACIER has a 90-day minimum storage
duration. Every object therefore resides in GLACIER for only 30 days (day 30 to
day 60) but is billed for the full 90-day minimum — 30 wasted days of
minimum-duration billing per object.

## What It Tests

- Correctly identifies the GLACIER 90-day minimum storage duration.
- Detects that a transition-at-30 + expire-at-60 pattern deletes objects before
  the minimum duration elapses (premature transition).
- Quantifies the structural penalty in wasted DAYS, not money.
- Recommends aligning the transition/expiration timing with the minimum duration.
- Does NOT misdiagnose as a provider billing bug.

## Expected Diagnosis

category: lifecycle_cost / subcategory: minimum_duration_penalty
root cause: objects transition into GLACIER (90-day minimum) at day 30 and are
expired at day 60, so each object is billed for 90 days while only residing 30 —
30 wasted days per object.
recommendation: delay the GLACIER transition or extend residency to at least the
90-day minimum duration before expiring/re-transitioning.

## Difficulty

medium

## Domains Tested

- lifecycle_cost
- storage_class
- triage
