# Case: BadDigest on a gzip Sync Script (Resemblance Trap)

## Scenario

一个自研上传脚本（`bos_sync.py`）在 PUT 之前先 gzip 压缩文件，并设置
`Content-Encoding: gzip`。自从切到 gzip 存储后，每次上传都返回 400 `BadDigest`
（"The SHA256 you specified did not match what we received"）。磁盘上的文件没有损坏，
错误是确定性的、每次都复现。

## What It Tests

This is a **resemblance trap** for evidence-first discipline. The error string
`BadDigest` superficially resembles data corruption or a multipart/checksum
problem. An agent that pattern-matches on the error string alone — without
reading `bos_sync.py` — will misdiagnose it as network corruption / a flaky disk
/ a retryable transient, and will be confidently wrong.

The decisive artifact (`bos_sync.py`) is in `input/`. Reading it reveals the
mechanism: the script computes the SigV4 payload hash (`x-amz-content-sha256`)
over the **uncompressed** bytes, but sends the **gzip-compressed** bytes on the
wire. The server hashes what it actually received → digests differ → `BadDigest`.

- Correctly identifies this as a client-side request-construction bug, not data
  corruption.
- Requires inspecting the script, not just the error string (the case fails for
  a non-investigating agent because `Content-Encoding` / `gzip` /
  `x-amz-content-sha256` only surface once the mechanism is understood).
- Does not recommend a blind retry or blame the network/disk.

## Expected Diagnosis

category: s3_protocol_compatibility / subcategory: content_sha256
root cause: `x-amz-content-sha256` computed over uncompressed bytes while a
gzip-compressed body is sent (Content-Encoding mismatch with the signed payload
hash).
recommendation: compute `x-amz-content-sha256` over the compressed bytes actually
transmitted (or let the SDK compute the payload hash after compression).

## Difficulty

hard

## Domains Tested

- s3_protocol_compatibility
- sigv4_payload_hash
- content_encoding
