import importlib.util
import sys
from pathlib import Path


def load_analyzer():
    root = Path(__file__).resolve().parents[1]
    module_path = root / "skills" / "storageops-lifecycle-cost" / "scripts" / "small_object_analyzer.py"
    spec = importlib.util.spec_from_file_location("small_object_analyzer", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_flags_small_ia_object_and_ignores_standard(tmp_path):
    analyzer = load_analyzer()
    csv_path = tmp_path / "objects.csv"
    csv_path.write_text(
        "key,size_bytes,storage_class\n"
        "small.txt,1024,STANDARD_IA\n"
        "big.bin,1048576,STANDARD\n",
        encoding="utf-8",
    )

    result = analyzer.run(file_path=str(csv_path))

    assert result["ok"] is True
    assert result["summary"]["total_objects"] == 2
    assert result["summary"]["flagged"] == 1
    # 128 KB min-billable minus the actual 1 KB object.
    assert result["summary"]["total_penalty_bytes"] == (128 << 10) - 1024
    assert result["details"][0]["key"] == "small.txt"


def test_missing_size_column_returns_error(tmp_path):
    analyzer = load_analyzer()
    csv_path = tmp_path / "bad.csv"
    csv_path.write_text("key,storage_class\nfoo,STANDARD_IA\n", encoding="utf-8")

    result = analyzer.run(file_path=str(csv_path))

    assert result["ok"] is False
    assert "size_bytes" in result["error"]
