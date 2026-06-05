# 摘要

Category: bigdata_pipeline
Route: storageops-bigdata-pipeline
Confidence: 0.85
Root cause type: rename_not_atomic (committer_race)

The Spark job uses FileOutputCommitter with `algorithm.version=1` and no S3A
committer, so the commit finishes by renaming `_temporary` output to the final
S3 paths. On object storage that rename is non-atomic, and with speculative
execution two attempts race to the same key — producing
`FileAlreadyExistsException` and, on retry, duplicate part files. This is a
commit-protocol problem, not data corruption.

# 诊断结论

Reading `spark-defaults.conf` confirms the mechanism rather than guessing:
`mapreduce.fileoutputcommitter.algorithm.version=1` with no `fs.s3a.committer.name`
means the default rename-based FileOutputCommitter is in effect. The driver log
shows the job "Committing job by renaming _temporary output" immediately before
the `FileAlreadyExistsException`, and speculative execution launched a second
attempt for task 17.

`scripts/analyze_committer.py --conf spark-defaults.conf` classifies this
offline as `fileoutputcommitter-v1`, risk=high.

# 关键证据

- `FileOutputCommitter` algorithm version 1 (from spark-defaults.conf).
- Commit performed by rename of the `_temporary` tree to final S3 paths.
- `FileAlreadyExistsException` during `rename`/`mergePaths` on s3a://.
- Speculative execution launched a second attempt for the same task.
- Re-run left duplicate `part-00017` objects in the partition prefix.

# What Would Falsify This

- If `fs.s3a.committer.name` were already `magic`/`directory`/`partitioned`, the
  commit would be rename-free and the diagnosis is wrong.
- If the failure were a single transient 5xx with no duplicate output, it would
  point elsewhere.

# 修复建议

- Switch to an S3A committer: set `fs.s3a.committer.name=magic` and the S3A
  factory `mapreduce.outputcommitter.factory.scheme.s3a`, so commit is
  rename-free on object storage.
- Or adopt a table format (Iceberg/Delta) whose commit avoids renames.
- Disable speculative execution for write stages only as a stopgap; it does not
  fix the non-atomic rename and is not a substitute for an S3A committer.
- Do not just retry — retries on v1 reproduce the duplicate-output race.
