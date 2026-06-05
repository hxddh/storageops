# Scripts

## `analyze_committer.py`

Offline analyzer for the Spark/Hadoop S3 output-committer configuration. Given a
`spark-defaults.conf`, a Hadoop `*-site.xml`, or a driver log, it reports the
committer type and object-storage risk — operationalizing the skill's first
decision ("identify the committer first").

```bash
./analyze_committer.py --conf spark-defaults.conf --json
./analyze_committer.py --xml core-site.xml
cat spark-driver.log | ./analyze_committer.py --stdin
```

Detects `mapreduce.fileoutputcommitter.algorithm.version` and
`fs.s3a.committer.name`: FileOutputCommitter v1/v2 (rename-based, unsafe on
object storage) vs S3A `magic`/`staging`/`directory`/`partitioned` (rename-free).
Offline-only: parses local text, never contacts a cluster or cloud endpoint.

## Planned scripts

- `small-file-analyzer.py` — Analyze an S3 directory listing to detect small-file problems
