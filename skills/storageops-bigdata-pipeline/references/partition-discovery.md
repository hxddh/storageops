# Partition Discovery

## When to read
Use when Hive/Spark tables on object storage show stale, missing, or slow partition discovery.

## Patterns
- `MSCK REPAIR TABLE` can be slow with deep/high-cardinality partition trees.
- Partition metadata may exist in object paths but not in the metastore.
- Spark glob filters and hidden-file rules can hide valid data files.

## Recommendations
- Prefer explicit `ALTER TABLE ADD PARTITION` or catalog-managed table formats.
- Validate object prefixes and metastore entries separately.
- For large partition counts, avoid recursive LIST storms during query planning.
