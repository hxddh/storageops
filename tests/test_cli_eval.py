"""Tests for the `storageops eval` golden-case harness subcommand."""

import io
from contextlib import redirect_stdout

import storageops_cli


def _run(args):
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = storageops_cli.cmd_eval(args)
    return rc, buf.getvalue()


def test_eval_help_lists_modes():
    rc, out = _run(["--help"])
    assert rc == 0
    assert "--list" in out and "--baselines" in out and "--output" in out


def test_eval_list_shows_cases_and_baseline_marker():
    rc, out = _run(["--list"])
    assert rc == 0
    assert "golden cases" in out
    # A case that has a committed baseline is flagged.
    assert "crr-replication-lag" in out
    assert "[baseline]" in out


def test_eval_unknown_case_is_a_clean_error():
    rc, out = _run(["definitely-not-a-case", "--output", "/dev/null"])
    assert rc == 1
    assert "no such golden case" in out


def test_eval_missing_args_returns_usage_error():
    rc, _ = _run([])
    assert rc == 2


def test_eval_single_case_scores_committed_baseline():
    corpus = storageops_cli._eval_corpus_dir()
    baseline = corpus / "baseline-outputs" / "crr-replication-lag.md"
    assert baseline.exists()
    rc, _ = _run(["crr-replication-lag", "--output", str(baseline)])
    # The committed baseline must pass its own case (exit 0).
    assert rc == 0
