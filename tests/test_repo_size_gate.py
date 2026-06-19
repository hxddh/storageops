from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path


def load_module():
    root = Path(__file__).resolve().parents[1]
    module_path = root / "scripts" / "repo_size_gate.py"
    spec = importlib.util.spec_from_file_location("repo_size_gate", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def init_repo(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)


def write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def run_gate(mod, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    # main() calls argparse.parse_args() with no args; isolate it from pytest argv.
    monkeypatch.setattr("sys.argv", ["repo_size_gate"])
    rc = mod.main()
    out = capsys.readouterr().out
    return rc, out


def test_within_budget_tree_passes(tmp_path, monkeypatch, capsys):
    mod = load_module()
    init_repo(tmp_path)
    case = tmp_path / mod.GOLDEN_ROOT / "case-a"
    write(case / "input.txt", b"x" * 100)
    base = tmp_path / mod.BASELINE_ROOT
    write(base / "out.md", b"y" * 100)
    write(tmp_path / "tests" / "test_small.py", b"z" * 100)

    rc, out = run_gate(mod, monkeypatch, tmp_path, capsys)
    assert rc == 0, out
    assert "passed" in out


def test_oversized_golden_file_rejected(tmp_path, monkeypatch, capsys):
    mod = load_module()
    init_repo(tmp_path)
    case = tmp_path / mod.GOLDEN_ROOT / "big"
    write(case / "input.txt", b"x" * (mod.GOLDEN_FILE_LIMIT + 1))

    rc, out = run_gate(mod, monkeypatch, tmp_path, capsys)
    assert rc == 1
    assert "golden case file too large" in out


def test_oversized_golden_case_total_rejected(tmp_path, monkeypatch, capsys):
    mod = load_module()
    init_repo(tmp_path)
    case = tmp_path / mod.GOLDEN_ROOT / "fat"
    # Several files each under the per-file limit but summing over the case limit.
    per = mod.GOLDEN_FILE_LIMIT
    n = (mod.GOLDEN_CASE_LIMIT // per) + 2
    for i in range(n):
        write(case / f"f{i}.txt", b"x" * per)

    rc, out = run_gate(mod, monkeypatch, tmp_path, capsys)
    assert rc == 1
    assert "golden case too large" in out


def test_oversized_test_file_rejected(tmp_path, monkeypatch, capsys):
    mod = load_module()
    init_repo(tmp_path)
    write(tmp_path / "tests" / "test_huge.py", b"z" * (mod.TEST_FILE_LIMIT + 1))

    rc, out = run_gate(mod, monkeypatch, tmp_path, capsys)
    assert rc == 1
    assert "test file too large" in out


def test_forbidden_binary_suffixes_rejected(tmp_path, monkeypatch, capsys):
    mod = load_module()
    init_repo(tmp_path)
    write(tmp_path / "dist" / "pkg.whl", b"binary")
    write(tmp_path / "data" / "archive.zip", b"binary")
    write(tmp_path / "data" / "blob.gz", b"binary")

    rc, out = run_gate(mod, monkeypatch, tmp_path, capsys)
    assert rc == 1
    assert "forbidden generated/binary artifact tracked" in out


def test_forbidden_pycache_part_rejected(tmp_path, monkeypatch, capsys):
    mod = load_module()
    init_repo(tmp_path)
    write(tmp_path / "pkg" / "__pycache__" / "mod.cpython.pyc", b"x")

    rc, out = run_gate(mod, monkeypatch, tmp_path, capsys)
    assert rc == 1
    assert "forbidden generated/binary artifact tracked" in out
