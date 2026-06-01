# Case: Routing Spark Committer

## Scenario
Spark writes to S3A fail with output committer errors.

## What It Tests
- Routes Spark/Hadoop object-storage write semantics to the bigdata skill.
- Avoids generic NoSuchKey or permission routing.

## Expected Diagnosis
Route to `storageops-bigdata-pipeline`.

## Difficulty
medium

## Domains Tested
- bigdata_pipeline
