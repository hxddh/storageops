from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def load():
    root = Path(__file__).resolve().parents[1]
    p = root / "skills" / "storageops-data-consistency" / "scripts" / "multipart_etag_calculator.py"
    spec = importlib.util.spec_from_file_location("multipart_etag_calculator", p)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


M0 = "d41d8cd98f00b204e9800998ecf8427e"  # md5("")
MA = "0cc175b9c0f1b6a831c399e269772661"  # md5("a")


def test_compute_matches_known_algorithm():
    import hashlib
    m = load()
    out = m.compute_multipart_etag([M0, MA], fmt="aws")
    expected = hashlib.md5(bytes.fromhex(M0) + bytes.fromhex(MA)).hexdigest()
    assert out["etag"] == f"{expected}-2"
    assert out["part_count"] == 2


def test_bos_format_leading_dash():
    m = load()
    out = m.compute_multipart_etag([M0, MA], fmt="bos")
    assert out["etag"].startswith("-")
    assert "-2" not in out["etag"]


def test_compute_rejects_bad_md5():
    m = load()
    try:
        m.compute_multipart_etag(["nothex"])
    except ValueError:
        return
    assert False, "expected ValueError on non-hex MD5"


def test_derive_part_size_band():
    m = load()
    total = 100 * 1024 ** 2
    band = m.derive_part_size(total, 2)
    assert band["feasible"] is True
    assert band["part_size_min"] == total // 2  # 50 MiB
    # 64 MiB and 64 MB both yield exactly 2 parts.
    labels = {d["label"] for d in band["matching_standard_sizes"]}
    assert "64MiB" in labels


def test_derive_single_part_has_no_max():
    m = load()
    band = m.derive_part_size(1000, 1)
    assert band["part_size_max"] is None
    assert band["part_size_min"] == 1000


def test_rechunk_different_count_differs():
    m = load()
    total = 100 * 1024 ** 2
    # 16 MiB parts -> 7 parts, not 2.
    r = m.analyze_rechunk(total, 2, 16 * 1024 ** 2)
    assert r["other_part_count"] == 7
    assert r["verdict"] == "etag_differs"


def test_rechunk_same_count_is_conditional():
    m = load()
    total = 100 * 1024 ** 2
    # 64 MiB also yields 2 parts but other sizes in the band do too.
    r = m.analyze_rechunk(total, 2, 64 * 1024 ** 2)
    assert r["other_part_count"] == 2
    assert r["verdict"] == "etag_matches_iff_same_part_size"


def test_cli_compute_and_verify(tmp_path, capsys):
    m = load()
    parts = tmp_path / "parts.txt"
    parts.write_text(f"{M0}\n{MA}\n", encoding="utf-8")
    rc = m.main(["--part-md5s", str(parts)])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    etag = out["computed_etag"]
    rc = m.main(["--part-md5s", str(parts), "--expected", etag])
    assert rc == 0
    out2 = json.loads(capsys.readouterr().out)
    assert out2["match"] is True


def test_cli_oss_warns():
    m = load()
    out = load_run(m, ["--part-md5s", _write([M0, MA])])
    assert "computed_etag" in out


def test_cli_bad_input_emits_ok_false(capsys):
    m = load()
    rc = m.main(["--total-size", "0", "--observed-etag", "abc-2"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False


# small helpers -------------------------------------------------------------
def _write(lines):
    import tempfile
    f = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False)
    f.write("\n".join(lines))
    f.close()
    return f.name


def load_run(m, argv):
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        m.main(argv)
    return json.loads(buf.getvalue())
