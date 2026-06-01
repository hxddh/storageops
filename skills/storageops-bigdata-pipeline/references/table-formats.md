# Table Formats on Object Storage

## When to read
Use when the workload mentions Iceberg, Delta Lake, or Hudi.

## Key distinctions
- Iceberg/Delta/Hudi use metadata/manifest protocols that avoid some rename races.
- Commit failures often involve catalog locks, manifest visibility, or concurrent writers.
- Data files can be present while table metadata does not reference them.

## Evidence
Ask for table format, catalog type, commit error, latest metadata/manifest path, and whether multiple writers run concurrently.
