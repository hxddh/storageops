# OSS SigV4 region mismatch (SignatureDoesNotMatch)

A non-AWS (Alibaba OSS) protocol case. The SigV4 signing region in the credential
scope (`us-east-1`) does not match the OSS endpoint's region (`cn-hangzhou`). The
signature is computed over a credential scope the server rejects, so OSS returns
`SignatureDoesNotMatch` even though the access key/secret are correct — a classic
"works on AWS, fails on a non-AWS endpoint" signing-region pitfall.

Expected diagnosis (s3-protocol-compatibility): not a credential problem — a
region/scope mismatch in the SigV4 signature. Set the signing region to match the
OSS endpoint region (cn-hangzhou) or use the provider's native client. This case
keeps the corpus exercising non-AWS protocol quirks, not just AWS.
