# Case: FileOutputCommitter v1 Non-Atomic Commit on S3 (Spark)

## Scenario

Spark 作业写入 `s3a://warehouse/sales/`,提交阶段偶发失败,重试后在分区目录下留下重复
part 文件。配置 `mapreduce.fileoutputcommitter.algorithm.version=1`,未配置 S3A
committer,启用了动态分区覆盖与推测执行。

## What It Tests

- 正确识别根因为 **FileOutputCommitter v1 的 rename 提交在对象存储上非原子**(rename 风暴),
  而非数据损坏/网络问题。
- 识别 `_temporary` 重命名 + 推测执行导致 `FileAlreadyExistsException` 与重复输出。
- 给出 S3A committer(magic)或表格式(Iceberg/Delta)的修复,而不是盲目重试。
- 可由 `scripts/analyze_committer.py` 离线确证(committer_type=fileoutputcommitter-v1,risk=high)。

## Expected Diagnosis

category: bigdata_pipeline / subcategory: committer
root cause: FileOutputCommitter v1 rename-based commit is non-atomic on object storage
recommendation: 切换到 S3A magic committer(+ S3A factory)或 Iceberg/Delta 等免 rename 的表格式

## Difficulty

medium

## Domains Tested

- bigdata_pipeline
- committer
- rename_not_atomic
