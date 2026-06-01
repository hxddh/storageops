# Case: SignatureDoesNotMatch Due to Clock Skew

## Scenario

User reports that `aws s3 ls s3://my-bucket --endpoint-url https://s3.example.com` fails with SignatureDoesNotMatch. The credentials are correct and work via web console. Uploads also fail with the same error.

## What It Tests

- Correctly identifies SignatureDoesNotMatch as a SigV4 issue
- Checks for clock skew as primary root cause
- Does NOT misattribute to wrong AK/SK or policy
- Provides clock sync recommendation (manual-only)

## Expected Diagnosis

category: s3_protocol_compatibility / subcategory: sigv4
root cause: system clock differs from server by more than the ±15 minute SigV4 tolerance
recommendation: sync system clock via NTP

## Difficulty

easy

## Domains Tested

- s3_protocol_compatibility
- sigv4
- triage
