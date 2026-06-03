import importlib.util
import sys
from pathlib import Path


def load_parser():
    root = Path(__file__).resolve().parents[1]
    module_path = root / "skills" / "storageops-data-consistency" / "scripts" / "etag_parser.py"
    spec = importlib.util.spec_from_file_location("etag_parser", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_classify_plain_md5():
    parser = load_parser()
    info = parser.classify_etag("d41d8cd98f00b204e9800998ecf8427e")
    assert info["type"] == "md5"


def test_classify_s3_multipart_extracts_part_count():
    parser = load_parser()
    info = parser.classify_etag('"d41d8cd98f00b204e9800998ecf8427e-3"')
    assert info["type"] == "multipart"
    assert info["part_count"] == 3


def test_s3_shaped_multipart_classifies_regardless_of_provider():
    # S3 / MinIO / OSS / COS all expose the "<hex>-N" multipart shape; the parser
    # classifies by shape (it cannot identify the provider from the string alone).
    parser = load_parser()
    info = parser.classify_etag("ceb8853ddc5086cc4ab9e149f8f09c88-5")
    assert info["type"] == "multipart"
    assert info["part_count"] == 5


def test_classify_bos_multipart_leading_dash():
    parser = load_parser()
    # BOS multipart: leading dash, no part count (contrast with S3's trailing -N).
    info = parser.classify_etag("-d41d8cd98f00b204e9800998ecf8427e")
    assert info["type"] == "bos-multipart"
    assert info["md5"] == "d41d8cd98f00b204e9800998ecf8427e"


def test_old_crct_pattern_is_no_longer_classified_as_bos():
    parser = load_parser()
    # The previously-invented "crct...-md5" composite is not a real BOS format.
    info = parser.classify_etag("crctABCD-d41d8cd98f00b204e9800998ecf8427e")
    assert info["type"] != "bos-multipart"


def test_parse_etags_empty_input_is_not_ok():
    parser = load_parser()
    result = parser.parse_etags("")
    assert result["ok"] is False


def test_parse_etags_classifies_each_line():
    parser = load_parser()
    result = parser.parse_etags("d41d8cd98f00b204e9800998ecf8427e\nabc123def456abc123def456abc12300-5")
    # Mixed plain/multipart ETags legitimately raise a consistency finding, so we
    # only assert that each line is classified by type here.
    types = {d["type"] for d in result["details"]}
    assert types == {"md5", "multipart"}
    assert len(result["details"]) == 2
