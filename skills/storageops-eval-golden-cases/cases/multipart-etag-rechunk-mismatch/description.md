# Multipart ETag mismatch after migration (re-chunking)

A 100 MiB object copied from AWS S3 to an S3-compatible target shows a different
multipart ETag (`...-2` vs `...-7`) even though the byte count, streamed full
MD5, and a byte-for-byte diff all confirm the content is identical. The source
used 64 MiB parts; the destination tool (rclone) re-uploaded with 16 MiB parts.

The expected diagnosis (data-consistency / integrity): this is **not** data
corruption. A multipart ETag is the MD5 of the concatenated part MD5s plus
`-<part count>`, so a different part size produces a different ETag for identical
bytes. To reproduce the source ETag, the destination must re-upload with the same
part size (64 MiB). The `multipart_etag_calculator.py` helper (next to
`etag_parser.py`) confirms the part-size band deterministically.
