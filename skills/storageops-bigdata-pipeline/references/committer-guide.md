# S3A Committer Guide

## When to read
Use when Spark/Hive/Flink jobs fail with `FileNotFoundException`, `FileAlreadyExistsException`, duplicate output, or `_temporary` rename symptoms on object storage.

## Diagnosis checklist
- Identify `mapreduce.fileoutputcommitter.algorithm.version` and `fs.s3a.committer.name`.
- Treat FileOutputCommitter v1/v2 rename-heavy output as unsafe for object storage scale.
- Prefer S3A `magic`, `staging`, or table-format-native committers where supported.
- Verify output path isolation: concurrent jobs must not write to the same final prefix.

## Evidence to request
- Spark/Hadoop version, filesystem implementation, committer config, table format, and one failed task log.
