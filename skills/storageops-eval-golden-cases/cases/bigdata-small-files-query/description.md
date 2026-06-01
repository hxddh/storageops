# Case: Big Data Small Files Query

## Scenario
Athena/Trino queries are slow because partitions contain hundreds of thousands of tiny files.

## What It Tests
- Big data skill recognizes small-file amplification rather than network slowness.
- Recommends compaction and target file sizing.

## Expected Diagnosis
Identify small-file amplification and recommend compaction into larger columnar files.

## Difficulty
medium

## Domains Tested
- bigdata_pipeline
