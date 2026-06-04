#!/usr/bin/env python3
"""Custom uploader: gzip-compress each file before PUT to an S3-compatible endpoint.

The in-house pipeline pins an old SDK, so SigV4 is hand-rolled. Reduced and
redacted for diagnosis. Credentials come from the environment, never hard-coded.
"""
import gzip
import hashlib
import os

import requests  # type: ignore
from sigv4 import sign_request  # in-house signer, body omitted for brevity

ENDPOINT = "https://s3.example-cloud.com"


def put_object(bucket: str, key: str, path: str) -> int:
    with open(path, "rb") as fh:
        raw = fh.read()

    # We store objects gzip-compressed to save space, and advertise it so
    # downstream readers can transparently decompress on GET.
    body = gzip.compress(raw)

    headers = {
        "Content-Encoding": "gzip",
        "Content-Type": "application/octet-stream",
        # NOTE: the SigV4 payload hash is computed over `raw` (the ORIGINAL
        # bytes), but `body` (what we actually send on the wire) is the
        # gzip-compressed bytes. These are different byte strings.
        "x-amz-content-sha256": hashlib.sha256(raw).hexdigest(),
    }

    signed = sign_request("PUT", f"{ENDPOINT}/{bucket}/{key}", headers, body)
    resp = requests.put(signed.url, headers=signed.headers, data=body)
    return resp.status_code


if __name__ == "__main__":
    code = put_object(os.environ["BUCKET"], "logs/2026-06-04.json.gz", "out.json")
    print("status", code)
