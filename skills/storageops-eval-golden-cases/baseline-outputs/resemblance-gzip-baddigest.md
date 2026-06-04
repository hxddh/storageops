# 摘要

Category: s3_protocol_compatibility
Route: storageops-s3-protocol-compatibility
Confidence: 0.88
Evidence Quality: sufficient
Root cause type: payload_hash_mismatch (content_encoding_mismatch)

`BadDigest` here is not data corruption — it is a SigV4 payload-hash mismatch.
The script `bos_sync.py` computes `x-amz-content-sha256` over the uncompressed
bytes but sends the gzip-compressed body, so the server's hash of what it
received cannot match the hash the client signed. The error reproduces
deterministically, which rules out a transient in-flight integrity failure.

# 诊断结论

Reading `bos_sync.py` confirms the mechanism rather than inferring it from the
error string: `body = gzip.compress(raw)` is sent on the wire, but
`x-amz-content-sha256` is set to `sha256(raw)` (the original, uncompressed
bytes). The signed payload hash therefore describes bytes the server never
received. This is a client-side request-construction bug, not a storage
integrity failure.

# 关键证据

- Error: `BadDigest` ("The SHA256 you specified did not match what we received"),
  i.e. a mismatch on the SigV4 payload hash, not a stored-object checksum.
- Request sends `Content-Encoding: gzip` with a gzip-compressed body.
- `x-amz-content-sha256` equals `sha256(uncompressed out.json)` per the script.
- Server `CalculatedDigest` differs from the client `ExpectedDigest`.
- Deterministic and stable across runs; on-disk file is intact → not corruption,
  not a transient retry case.

# What Would Falsify This

- If `x-amz-content-sha256` already equalled `sha256(gzip.compress(raw))`, the
  hypothesis is wrong and the issue is elsewhere (e.g. a proxy re-encoding the
  body, or signed-headers drift).
- If the same request without `Content-Encoding: gzip` also failed BadDigest,
  the compression mismatch is not the cause.

# 修复建议

- Compute `x-amz-content-sha256` over the **compressed bytes** actually sent:
  `hashlib.sha256(body).hexdigest()` where `body = gzip.compress(raw)`. The
  payload hash must describe the exact bytes on the wire.
- Equivalently, let the SDK compute the payload hash after compression so the
  signed `x-amz-content-sha256` and the transmitted body always agree.
- Do not retry blindly and do not blame the network or disk — the request is
  malformed by construction and will fail identically every time.
