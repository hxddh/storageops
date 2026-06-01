# Case: lifecycle-small-file-ia

## What this case tests
Tests the lifecycle-cost skill's ability to identify small-file cost amplification
in Standard-IA storage class and recommend appropriate lifecycle rules.

## Scenario
A user uploaded 500,000 small files (avg 10KB each) to a Standard-IA bucket.
They are surprised by a large storage bill because IA has a 128KB minimum billable
size per object.

## Expected Diagnosis
- Category: lifecycle_cost
- Subcategory: small_object_cost
- Root cause: minimum billable size amplification (128KB in IA)
- Confidence >= 0.75
- Must identify: 500K objects × 128KB min = cost gap
- Must recommend: aggregate small files, switch to Standard for very small objects
- Must NOT recommend: disabling lifecycle rules without cost analysis
