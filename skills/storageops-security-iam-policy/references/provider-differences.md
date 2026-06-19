# Provider IAM Differences

S3-compatible providers expose an S3-like API but each has its **own** identity and
authorization model. The wire protocol matching does not mean the auth model
matches. Do not assume AWS concepts (SCP, KMS key policies, Block Public Access,
`sts:AssumeRole`) exist or behave the same elsewhere.

> **Verify before applying.** Provider auth models and console/API surfaces change
> over time and differ by region/edition. Treat the notes below as orientation,
> then confirm against the provider's current official documentation before
> recommending any change. Do not invent exact API/action names you are unsure of.

## What Carries Over vs What Does Not

Generally portable across most providers:
- Bucket policies and per-object/bucket ACLs (canned ACLs like `private`,
  `public-read`).
- Signature v4-style request signing and the basic Allow/Deny + condition model.
- Pre-signed URLs.

Often AWS-specific — do NOT assume present:
- Service Control Policies (org-level deny).
- AWS-style KMS key policies and `kms:ViaService`.
- AWS Block Public Access semantics (providers have their own public-access toggles).
- `sts:AssumeRole` trust-policy mechanics.
- Exact IAM action names (`s3:GetObject` etc.) — provider action namespaces differ.

## Provider Notes (orient, then verify)

### AWS — IAM
Baseline model used in the rest of this skill: identity policies + bucket policies +
ACLs + SCP + Block Public Access, with KMS for SSE-KMS. Cross-account needs both
sides.

### Alibaba Cloud OSS — RAM
- Identity/authorization via **RAM** (Resource Access Management): RAM users, RAM
  roles, and policies analogous to IAM. Has its own STS for temporary credentials.
- Supports bucket policy and ACL; the action namespace is OSS-specific, not the
  `s3:*` namespace.
- Server-side encryption includes an SSE-KMS option backed by Alibaba's KMS, not
  AWS KMS.

### Tencent Cloud COS — CAM
- Identity/authorization via **CAM** (Cloud Access Management): CAM users/roles and
  policies. Temporary credentials via Tencent STS.
- Supports bucket policy and ACL; COS-specific action namespace.

### Baidu Cloud BOS — IAM-style
- Has its own IAM-style identity service with users/policies and ACLs.
- Public-access and encryption controls are provider-native; do not map them
  one-to-one onto AWS Block Public Access or AWS KMS.

### MinIO (self-hosted)
- Uses AWS-compatible IAM-style policies and bucket policies, but no SCP, no AWS
  KMS (it has its own KMS/KES integration). Identity may come from an external
  provider (LDAP/OIDC).

## Diagnostic Implications

When a non-AWS provider reports AccessDenied:
1. Identify the provider FIRST (endpoint host, error code style, console naming).
2. Map AWS layers to the provider's equivalents — and drop the ones that do not
   exist there (e.g. do not chase an SCP on OSS).
3. Use the provider's own policy-inspection and read-only test commands; the AWS
   CLI may work against the endpoint but the AWS IAM simulator does NOT evaluate
   another provider's RAM/CAM rules.
4. Confirm action names and condition keys against that provider's docs before
   proposing a policy edit.

## Do Not Assume

- That an AWS bucket-policy JSON will paste cleanly into another provider.
- That "Block Public Access" or "KMS key policy" exist by that name elsewhere.
- That cross-account works identically — account/sub-account models differ.
- That the AWS IAM policy simulator reflects a non-AWS provider's decision.
