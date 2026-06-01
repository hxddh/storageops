# Case: Routing 403 Signature vs Permission

## Scenario
The user reports a 403 response that includes `SignatureDoesNotMatch`.

## What It Tests
- Routes signature-flavored 403 errors to protocol compatibility before IAM policy analysis.
- Keeps permission fixes out of the first recommendation until signing is checked.

## Expected Diagnosis
Route to `storageops-s3-protocol-compatibility`.

## Difficulty
medium

## Domains Tested
- s3_protocol_compatibility
