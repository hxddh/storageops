from __future__ import annotations

import importlib.util
from pathlib import Path


def load():
    root = Path(__file__).resolve().parents[1]
    module_path = root / "skills" / "storageops-bigdata-pipeline" / "scripts" / "analyze_committer.py"
    spec = importlib.util.spec_from_file_location("analyze_committer", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_v1_is_high_risk_rename_storm():
    m = load()
    cfg = m.parse_config_text("spark.hadoop.mapreduce.fileoutputcommitter.algorithm.version 1\n")
    r = m.classify(cfg)
    assert r["committer_type"] == "fileoutputcommitter-v1"
    assert r["risk"] == "high"
    assert "magic" in r["recommendation"]


def test_v2_is_medium_risk():
    m = load()
    r = m.classify(m.parse_config_text("mapreduce.fileoutputcommitter.algorithm.version=2"))
    assert r["committer_type"] == "fileoutputcommitter-v2"
    assert r["risk"] == "medium"


def test_s3a_magic_is_low_risk():
    m = load()
    cfg = m.parse_config_text(
        "fs.s3a.committer.name=magic\n"
        "mapreduce.outputcommitter.factory.scheme.s3a=org.apache.hadoop.fs.s3a.commit.S3ACommitterFactory\n"
    )
    r = m.classify(cfg)
    assert r["committer_type"] == "s3a-magic"
    assert r["risk"] == "low"


def test_missing_config_assumes_default_v1():
    m = load()
    r = m.classify(m.parse_config_text("spark.master=yarn\n"))
    assert r["committer_type"] == "default-fileoutputcommitter-v1-assumed"
    assert r["risk"] == "high"


def test_hadoop_xml_is_parsed():
    m = load()
    xml = (
        "<configuration>"
        "<property><name>fs.s3a.committer.name</name><value>directory</value></property>"
        "</configuration>"
    )
    r = m.classify(m.parse_config_text(xml))
    assert r["committer_type"] == "s3a-directory"
    assert r["risk"] == "low"
