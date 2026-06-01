---
name: storageops-bigdata-pipeline
description: >
  Diagnose Spark/Hive/Flink/Presto failures on object storage (S3A).
  Covers committer race conditions (FileOutputCommitter V1 vs S3A committers),
  partition discovery, small-file amplification, connection pool exhaustion,
  and table format issues (Iceberg/Delta/Hudi). Use when user reports
  Spark job failures, FileNotFoundException, FileAlreadyExistsException,
  or slow analytics queries on S3-backed tables.
maturity: stable
mode: light_heavy
estimated_tokens: 1400
trigger_keywords:
  - Spark
  - Hive
  - Flink
  - Presto
  - Trino
  - EMR
  - FileNotFoundException
  - FileAlreadyExistsException
  - committer
  - S3A
  - partition discovery
  - small files
  - Iceberg
  - Delta Lake
  - Hudi
recommended_tools:
  - scan_secrets
  - detect_domain
  - search_memory
---

# Big Data Pipeline Diagnosis

The most common S3 big-data failures are committer race conditions (V1 default), small-file amplification, and connection pool exhaustion. Always identify the committer type first — it determines the entire diagnosis path.

## Decision Tree

```
Spark/Hive job failure →
  ├─ "FileNotFoundException: Output directory does not exist"?
  │   ├─ Using FileOutputCommitter V1 (default)? → V1 commit race (Step 2)
  │   └─ Using S3A committer? → Check fs.s3a.committer configuration
  ├─ "FileAlreadyExistsException"?
  │   ├─ V1 committer + speculative execution? → Task duplication + V1 conflict
  │   └─ S3A committer? → Task attempt collision → Check magic committer
  ├─ Job succeeds but reads wrong data?
  │   ├─ Hive MSCK? → Partition not discovered (Step 3)
  │   └─ Iceberg/Delta? → Snapshot isolation issue (Step 6)
  ├─ Slow queries, no errors?
  │   ├─ Thousands of small files? → Small-file amplification (Step 4)
  │   └─ Normal file count? → Connection pool (Step 5) or S3Guard (Step 7)
  └─ Non-AWS (BOS/OSS/COS)? → Committer compatibility may differ (Step 2)
```

## Workflow

### Step 1: Identify Stack and Committer
Extract from config: engine (Spark/Hive/Flink), committer type (`mapreduce.fileoutputcommitter.algorithm.version`, `fs.s3a.committer.name`), and table format (Iceberg/Delta/Hudi/plain).

### Step 2: Committer Protocol Diagnosis
- **FileOutputCommitter V1** (default): Known to cause `FileNotFoundException` and task duplication on S3. The `_temporary` → final rename is NOT atomic on object storage. **Recommend**: switch to S3A committer (`fs.s3a.committer.name=magic`).
- **S3A Committers** (magic/staging/partitioned): See `references/committer-guide.md` for configuration matrix.

### Step 3: Partition Discovery
- **Hive**: `MSCK REPAIR TABLE` is slow on S3 with many partitions. Check if partitions exist at expected paths. See `references/partition-discovery.md`.
- **Spark**: `spark.sql.parquet/pathGlobFilter` may miss new partitions.

### Step 4: Small-File Amplification
High partition count × small files per partition causes excessive LIST/HEAD requests. For analytics, files <128MB per partition cause I/O overhead. Recommendation: compaction job or `spark.sql.files.maxPartitionBytes`.

### Step 5: Connection Pool
Default S3A pool is 256 connections per JVM. Exhaustion causes hangs. Check `fs.s3a.connection.maximum` and thread count.

### Step 6: Table Format Issues
- **Iceberg**: Check `write.format.default`. Snapshot expiration may cause missing data.
- **Delta**: `_delta_log` concurrency. Optimistic concurrency conflicts on concurrent writes.
- **Hudi**: Timeline server and compaction scheduling.

### Step 7: S3Guard/DynamoDB Consistency (EMR)
S3Guard provides consistent listing on S3. If using EMR with consistent view disabled, stale listings cause `FileNotFoundException`.

## Output Format

```markdown
# Diagnosis: [one-line]
**Committer**: [type]
**Root cause**: committer-race | partition-discovery | small-files | connection-pool | table-format | s3guard
**Confidence**: high | medium | low

## Evidence
- Engine: [Spark 3.x / Hive 3.x]
- Committer: [V1 / magic / staging / partitioning]
- Table format: [plain / Iceberg / Delta / Hudi]

## Root Cause
[Explanation with config evidence]

## Recommendations
1. **[config change]** — `fs.s3a.committer.name=magic` (manual-only, test in staging)
2. ...
```

## Examples

### Example 1: V1 committer race
**Input**: Spark job on EMR, 100 tasks writing to S3. Error: `FileNotFoundException: Output directory s3://bucket/output/_temporary does not exist`.
**Diagnosis**: FileOutputCommitter V1 race — task 1 deleted `_temporary` while task 2 was still writing.  
**Recommendation**: `fs.s3a.committer.name=magic`, `spark.sql.sources.commitProtocolClass=org.apache.spark.sql.execution.datasources.SQLHadoopMapReduceCommitProtocol`

### Example 2: Small-file amplification
**Input**: Athena query on 500K files × 10KB across 1000 partitions. Query takes 8 min for simple COUNT.
**Diagnosis**: Small-file amplification — 500K S3 LIST/HEAD per query  
**Recommendation**: Compaction job to merge into 128MB files, target 5000 files total. Expect query time <30s.

### Example 3: Cross-provider Iceberg
**Input**: Iceberg table on BOS, writes succeed but reads return stale data after compaction.
**Diagnosis**: BOS Iceberg catalog may not support atomic rename required by Iceberg commit protocol  
**Recommendation**: Use Hive catalog with BOS, test snapshot isolation under concurrent writes.

## References
- `references/committer-guide.md` — S3A committer configuration matrix
- `references/partition-discovery.md` — Hive/Spark partition strategies
- `references/connection-pool.md` — S3A connection pool tuning
- `references/table-formats.md` — Iceberg/Delta/Hudi on object storage
- `references/provider-compatibility.md` — Non-AWS committer behavior
