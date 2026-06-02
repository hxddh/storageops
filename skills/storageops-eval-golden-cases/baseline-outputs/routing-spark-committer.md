# Routing

Category: bigdata_pipeline
Route: storageops-bigdata-pipeline
Confidence: 0.80
Root Cause Type: committer_race

Spark output failures involving FileOutputCommitter and `_temporary` should route
to the big-data pipeline skill.

# Evidence Gaps

- Need exact S3A committer setting.
- Need whether speculative execution is enabled.
- Need object-store provider and table format.

Recommendation: use an S3A committer designed for object storage and review
speculative execution. Rename-based committers can hit non-atomic rename races.
