#!/usr/bin/env python3
"""Offline analyzer for the Spark/Hadoop S3 output-committer configuration.

Operationalizes the bigdata skill's first decision ("identify the committer
first"): given a spark-defaults.conf, a Hadoop *-site.xml, or a driver log, it
reports the committer type and the object-storage risk.

Offline-only: parses local text, never contacts a cluster or cloud endpoint. The
authoritative keys/behaviors mirror ``references/committer-guide.md``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional

# Keys that govern commit behavior (Hadoop names; Spark may prefix "spark.hadoop.").
ALGO = "mapreduce.fileoutputcommitter.algorithm.version"
S3A_NAME = "fs.s3a.committer.name"
FACTORY = "mapreduce.outputcommitter.factory.scheme.s3a"
MAGIC_ENABLED = "fs.s3a.committer.magic.enabled"
COMMIT_PROTOCOL = "spark.sql.sources.commitProtocolClass"
PARQUET_COMMITTER = "spark.sql.parquet.output.committer.class"

KNOWN_KEYS = [ALGO, S3A_NAME, FACTORY, MAGIC_ENABLED, COMMIT_PROTOCOL, PARQUET_COMMITTER]
SAFE_S3A_NAMES = {"magic", "directory", "partitioned", "staging"}


def parse_config_text(text: str) -> Dict[str, str]:
    """Extract known committer keys from XML, conf, or command/log text."""
    cfg: Dict[str, str] = {}

    # Hadoop XML: <property><name>K</name><value>V</value></property>
    if "<property" in text:
        try:
            root = ET.fromstring(text)
            for prop in root.iter("property"):
                name = prop.findtext("name")
                value = prop.findtext("value")
                if name and value is not None:
                    cfg[name.strip()] = value.strip()
        except ET.ParseError:
            for m in re.finditer(r"<name>\s*([^<]+?)\s*</name>\s*<value>\s*([^<]*?)\s*</value>", text, re.S):
                cfg[m.group(1).strip()] = m.group(2).strip()

    # conf / --conf k=v / "key value" lines
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("<"):
            continue
        line = re.sub(r"^--conf\s+", "", line)
        m = re.match(r"^([A-Za-z0-9_.\-]+)\s*[=:]\s*(.+)$", line) or re.match(r"^([A-Za-z0-9_.\-]+)\s+(\S.*)$", line)
        if m:
            cfg.setdefault(m.group(1).strip(), m.group(2).strip())

    # Index without the Spark "spark.hadoop." passthrough prefix too.
    for key, value in list(cfg.items()):
        if key.startswith("spark.hadoop."):
            cfg.setdefault(key[len("spark.hadoop."):], value)
    return cfg


def classify(cfg: Dict[str, str]) -> dict:
    """Return committer type + object-storage risk from a parsed config."""
    s3a = (cfg.get(S3A_NAME) or "").strip().lower()
    algo = (cfg.get(ALGO) or "").strip()
    keys_found = {k: cfg[k] for k in KNOWN_KEYS if k in cfg}

    if s3a in SAFE_S3A_NAMES:
        committer = f"s3a-{s3a}"
        risk = "low"
        cause = "An S3A committer is configured; commit is rename-free/staged and safe at object-storage scale."
        rec = (
            f"Verify the factory `{FACTORY}` is set"
            + (" and `fs.s3a.committer.magic.enabled=true` for the magic committer." if s3a == "magic" else ".")
        )
    elif algo == "2":
        committer = "fileoutputcommitter-v2"
        risk = "medium"
        cause = "FileOutputCommitter v2 renames per task; a failed task can leave partial output, and renames are non-atomic on object storage."
        rec = "Switch to an S3A committer (`fs.s3a.committer.name=magic` + the S3A factory) or a table format (Iceberg/Delta) whose commit avoids renames."
    elif algo == "1":
        committer = "fileoutputcommitter-v1"
        risk = "high"
        cause = "FileOutputCommitter v1 commits via a final rename of the job output; on object storage this is a non-atomic rename storm, risking duplicate/partial output and FileAlreadyExistsException, with slow large commits."
        rec = "Switch to an S3A committer (`fs.s3a.committer.name=magic` + the S3A factory) or a table format (Iceberg/Delta)."
    else:
        committer = "default-fileoutputcommitter-v1-assumed"
        risk = "high"
        cause = "No committer configuration found; Spark/Hadoop default to FileOutputCommitter (rename-based), which is unsafe on object storage."
        rec = "Explicitly configure an S3A committer (`fs.s3a.committer.name=magic` + `" + FACTORY + "`) or use a rename-free table format."

    return {
        "ok": True,
        "committer_type": committer,
        "algorithm_version": algo or None,
        "s3a_committer_name": s3a or None,
        "risk": risk,
        "likely_cause": cause,
        "recommendation": rec,
        "keys_found": keys_found,
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--conf", type=Path, help="spark-defaults.conf (or any k=v / --conf k=v text)")
    ap.add_argument("--xml", type=Path, help="Hadoop core-site.xml / mapred-site.xml")
    ap.add_argument("--stdin", action="store_true", help="Read config/log text from stdin")
    ap.add_argument("--json", action="store_true", help="Emit JSON")
    args = ap.parse_args(argv)

    text = ""
    if args.conf:
        text += "\n" + args.conf.read_text(encoding="utf-8", errors="ignore")
    if args.xml:
        text += "\n" + args.xml.read_text(encoding="utf-8", errors="ignore")
    if args.stdin:
        text += "\n" + sys.stdin.read()
    if not text.strip():
        ap.print_help()
        return 1

    result = classify(parse_config_text(text))
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"committer_type : {result['committer_type']}")
        print(f"risk           : {result['risk']}")
        print(f"likely_cause   : {result['likely_cause']}")
        print(f"recommendation : {result['recommendation']}")
        if result["keys_found"]:
            print("keys_found     :")
            for k, v in result["keys_found"].items():
                print(f"  {k} = {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
