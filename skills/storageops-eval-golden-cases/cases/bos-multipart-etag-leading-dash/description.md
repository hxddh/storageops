# BOS leading-dash multipart ETag mistaken for corruption

A non-AWS (Baidu BOS) integrity case. BOS formats a multipart ETag as a **leading
dash** `-<32 hex>` — the MD5 of the concatenated part MD5s with no part count —
unlike AWS S3's trailing `<hex>-N`. A verifier hardcoded to the AWS shape (or to
"ETag == whole-object MD5") flags a perfectly intact BOS object as corrupted.

Expected diagnosis (data-consistency): not corruption — a provider-specific ETag
format. Verify integrity on BOS with an explicit content hash rather than the
ETag, or use the BOS-aware path of `multipart_etag_calculator.py` /
`etag_parser.py`. This case exists to keep the corpus from over-fitting AWS ETag
phrasing.
