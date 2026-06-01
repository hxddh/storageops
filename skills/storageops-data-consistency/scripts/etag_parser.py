#!/usr/bin/env python3
"""ETag Parser — classify cloud-storage ETag formats and detect encryption/mismatches.

Formats: plain-MD5 | multipart (MD5-N) | BOS composite (crctY-md5) | weak | KMS-blob
Encryption heuristics: SSE-KMS (AQID* base64), SSE-S3, SSE-C, BOS-SSE (via headers)
Output: JSON {ok, summary, details[], findings[]}
"""

import argparse, json, re, sys
from typing import Any, Dict, List, Optional

# ── Patterns ────────────────────────────────────────────────────────────────
RE_PLAIN_MD5 = re.compile(r'^"?[0-9a-fA-F]{32}"?$')
RE_MULTIPART = re.compile(r'^"?([0-9a-fA-F]{32})-(\d+)"?$')
RE_BOS_COMP  = re.compile(r'^"?crct[-A-Za-z0-9=+]+-([0-9a-fA-F]{32})"?$')
RE_WEAK      = re.compile(r'^W/".+"$')
RE_KMS_B64   = re.compile(r'^"?[A-Za-z0-9+/=]{40,}"?$')
SSE_HEADERS  = {
    "x-amz-server-side-encryption": "SSE-S3 (AES-256)",
    "x-amz-server-side-encryption-aws-kms-key-id": "SSE-KMS",
    "x-amz-server-side-encryption-customer-algorithm": "SSE-C",
    "x-bce-server-side-encryption": "BOS-SSE",
}

# ── Classification ──────────────────────────────────────────────────────────
def classify_etag(raw: str) -> Dict[str, Any]:
    s = raw.strip()
    no_q = s.strip('"')
    info: Dict[str, Any] = {"raw": s, "normalized": no_q}

    if RE_WEAK.match(s):
        weak_body = re.sub(r'^W/"?|"?$', '', s)
        info.update(type="weak", normalized=weak_body,
                     note="HTTP weak validator — not for integrity")
    elif (m := RE_MULTIPART.match(no_q) or RE_MULTIPART.match(s)):
        info.update(type="multipart", md5=m.group(1).lower(),
                     part_count=int(m.group(2)), encryption="none (inferable)")
    elif (m := RE_BOS_COMP.match(no_q) or RE_BOS_COMP.match(s)):
        info.update(type="bos-composite", md5=m.group(1).lower(),
                     algorithm="CRC-32C+MD5", encryption="none (inferable)")
    elif (m := RE_PLAIN_MD5.match(no_q) or RE_PLAIN_MD5.match(s)):
        info.update(type="md5", md5=no_q.lower(), encryption="none (inferable)")
    elif (m := RE_KMS_B64.match(no_q) or RE_KMS_B64.match(s)):
        info["type"] = "binary-blob"
        info["base64_value"] = no_q
        info["encryption"] = ("SSE-KMS (likely AWS)" if no_q.startswith(("AQID","AQIC"))
                              else "SSE-KMS or SSE-C (base64 blob)")
    else:
        info.update(type="unknown", note="Unrecognised ETag format")
    return info

def augment_encryption(etag_info: Dict[str, Any],
                        metadata: Optional[Dict[str, str]]) -> Dict[str, Any]:
    if not metadata:
        return etag_info
    meta_lower = {k.lower(): v for k, v in metadata.items()}
    for key, label in SSE_HEADERS.items():
        if key.lower() in meta_lower:
            etag_info.update(encryption=label, encryption_header=key)
            break
    return etag_info

# ── Consistency checks ─────────────────────────────────────────────────────
def check_consistency(infos: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    f: List[Dict[str, str]] = []
    types = {i["type"] for i in infos}
    md5s  = {i.get("md5") for i in infos if i.get("md5")}
    pcs   = {i.get("part_count") for i in infos if "part_count" in i}
    encs  = {i.get("encryption", "") for i in infos}

    if len(types) > 1:
        f.append({"level": "warning", "msg": f"Mixed ETag types: {', '.join(sorted(types))}"})
    if len(md5s) > 1:
        f.append({"level": "error", "msg": f"ETag MD5 mismatch: {', '.join(sorted(md5s))}"})
    if len(pcs) > 1:
        f.append({"level": "error", "msg": f"Multipart part-count mismatch: {', '.join(str(p) for p in sorted(pcs))}"})
    if len(encs) > 1:
        f.append({"level": "error", "msg": "Encryption flag mismatch across sources"})
    return f

# ── I/O ─────────────────────────────────────────────────────────────────────
def load_input(file_path: Optional[str], use_stdin: bool) -> str:
    if use_stdin and not sys.stdin.isatty():
        return sys.stdin.read()
    return open(file_path).read() if file_path else ""

# ── Core ────────────────────────────────────────────────────────────────────
def parse_etags(raw: str, metadata: Optional[Dict[str, str]] = None,
                delimiter: str = "\n") -> Dict[str, Any]:
    parts = [p.strip() for p in raw.split(delimiter) if p.strip()]
    if not parts:
        return {"ok": False, "summary": "No ETag input", "details": [], "findings": []}

    details = [augment_encryption(classify_etag(p), metadata) for p in parts]
    findings = check_consistency(details)
    types = ", ".join(sorted({d["type"] for d in details}))
    enc   = ", ".join(sorted({d.get("encryption", "?") for d in details}))
    ok = not any(f["level"] == "error" for f in findings)

    summary = f'{len(parts)} ETag(s) | type(s): {types} | encryption: {enc}'
    if findings:
        summary += f' | {len(findings)} finding(s)'
    return {"ok": ok, "summary": summary, "details": details, "findings": findings}

def main() -> None:
    ap = argparse.ArgumentParser(description="Parse and classify cloud-storage ETags")
    ap.add_argument("--file", "-f", help="File with one ETag per line")
    ap.add_argument("--stdin", "-s", action="store_true", help="Read ETags from stdin")
    ap.add_argument("--header", help="JSON file with response headers for encryption inference")
    ap.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    ap.add_argument("etag", nargs="*", help="ETag string(s) directly on command line")
    args = ap.parse_args()

    raw = "\n".join(
        [load_input(None, True) if args.stdin else ""] +
        [load_input(f, False) for f in ([args.file] if args.file else [])] +
        [e.strip() for e in args.etag]
    ).strip("\n")
    if not raw:
        ap.print_help(); sys.exit(1)

    meta = json.load(open(args.header)) if args.header else None
    result = parse_etags(raw, metadata=meta)
    print(json.dumps(result, indent=2 if args.pretty else None, ensure_ascii=False))
    sys.exit(0 if result["ok"] else 1)

if __name__ == "__main__":
    main()
