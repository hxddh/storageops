# Summary

Category: bigdata_pipeline
Route: storageops-bigdata-pipeline
Confidence: 0.84

Trino query latency is driven by small_file_amplification and metadata overhead:
486,000 objects averaging 12 KiB create excessive listing and open-file work.

# Key Evidence

- Engine: Trino.
- Object count: 486,000.
- Average object size: 12 KiB.
- Layout spans 720 partitions, increasing metadata planning overhead.

# Remediation

Run compaction to produce files around 128MB where practical, then revisit the
partition layout so each partition has fewer tiny objects.
