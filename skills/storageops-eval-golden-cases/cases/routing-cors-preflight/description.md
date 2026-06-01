# Case: Routing CORS Preflight

## Scenario
A browser upload fails at the preflight request.

## What It Tests
- Maps `cors_configuration` to the protocol compatibility skill.
- Keeps frontend CORS diagnosis separate from network reachability.

## Expected Diagnosis
Route to `storageops-s3-protocol-compatibility`.

## Difficulty
easy

## Domains Tested
- cors_configuration
