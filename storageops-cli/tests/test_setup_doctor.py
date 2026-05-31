"""Tests for storageops setup, doctor, and config module."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

_CLI_DIR = Path(__file__).parent.parent
_CORE_DIR = _CLI_DIR.parent / "storageops-core"
for _sub in ("utils", "parsers", "analyzers"):
    _p = str(_CORE_DIR / _sub)
    if _p not in sys.path:
        sys.path.insert(0, _p)


class TestConfig(unittest.TestCase):
    def test_load_returns_empty_dict_when_missing(self):
        from storageops.config import load
        with patch("storageops.config._FILE", Path("/nonexistent/path/config.json")):
            self.assertEqual(load(), {})

    def test_save_and_load_roundtrip(self, tmp_path=None):
        import tempfile
        import os
        with tempfile.TemporaryDirectory() as td:
            cfg_file = Path(td) / "config.json"
            with patch("storageops.config._DIR", Path(td)), \
                 patch("storageops.config._FILE", cfg_file):
                from storageops import config as cfg_mod
                cfg_mod.save({"pi_command": "pi", "workdir": td})
                result = cfg_mod.load()
        self.assertEqual(result["pi_command"], "pi")
        self.assertEqual(result["workdir"], td)

    def test_get_pi_command_default(self):
        from storageops.config import get_pi_command
        with patch("storageops.config._FILE", Path("/nonexistent/config.json")):
            self.assertEqual(get_pi_command(), "pi")

    def test_get_skills_dir_none_when_missing(self):
        from storageops.config import get_skills_dir
        with patch("storageops.config._FILE", Path("/nonexistent/config.json")), \
             patch("storageops.config._DIR", Path("/nonexistent")):
            self.assertIsNone(get_skills_dir())


class TestFindBundledSkills(unittest.TestCase):
    def test_finds_repo_skills(self):
        from storageops.cli import _find_bundled_skills
        result = _find_bundled_skills()
        # In the dev/repo layout, agents/skills must be discoverable
        self.assertIsNotNone(result, "_find_bundled_skills() should find skills in repo layout")
        self.assertTrue(result.exists())
        self.assertTrue(result.is_dir())

    def test_skills_contains_expected_dirs(self):
        from storageops.cli import _find_bundled_skills
        skills = _find_bundled_skills()
        if skills is None:
            self.skipTest("No bundled skills found")
        dirs = [d.name for d in skills.iterdir() if d.is_dir()]
        self.assertIn("storageops-triage", dirs)
        self.assertIn("storageops-security-iam-policy", dirs)


class TestSetupCommand(unittest.TestCase):
    def _run_setup(self, tmp_home: Path, pi_path: str) -> int:
        """Run cmd_setup with mocked Pi binary and home dir. Returns exit code (0=ok)."""
        import shutil
        import argparse
        from storageops.cli import cmd_setup

        args = argparse.Namespace(pi_command="pi")
        with patch("shutil.which", return_value=pi_path), \
             patch("subprocess.check_output", return_value="2.0.0"), \
             patch("storageops.config._DIR", tmp_home / ".storageops"), \
             patch("storageops.config._FILE", tmp_home / ".storageops" / "config.json"), \
             patch.object(Path, "home", return_value=tmp_home):
            try:
                cmd_setup(args)
                return 0
            except SystemExit as e:
                return int(e.code) if e.code is not None else 1

    def test_setup_fails_when_pi_missing(self):
        import argparse, tempfile
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            args = argparse.Namespace(pi_command="pi")
            with patch("shutil.which", return_value=None), \
                 patch.object(Path, "home", return_value=tmp):
                with self.assertRaises(SystemExit) as ctx:
                    from storageops.cli import cmd_setup
                    cmd_setup(args)
                self.assertEqual(ctx.exception.code, 1)

    def test_setup_creates_expected_files(self):
        import argparse, tempfile
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            home = tmp / "home"
            home.mkdir()
            storageops_dir = home / ".storageops"
            args = argparse.Namespace(pi_command="pi")

            with patch("shutil.which", return_value="/usr/bin/pi"), \
                 patch("subprocess.check_output", return_value="2.0.0"), \
                 patch("storageops.config._DIR", storageops_dir), \
                 patch("storageops.config._FILE", storageops_dir / "config.json"), \
                 patch.object(Path, "home", return_value=home):
                from storageops.cli import cmd_setup
                cmd_setup(args)

            # Check config.json was written
            cfg_file = storageops_dir / "config.json"
            self.assertTrue(cfg_file.exists())
            cfg = json.loads(cfg_file.read_text())
            self.assertEqual(cfg["pi_command"], "pi")

            # Check .pi/settings.json was written
            pi_settings = storageops_dir / ".pi" / "settings.json"
            self.assertTrue(pi_settings.exists())
            settings = json.loads(pi_settings.read_text())
            self.assertIn("skills", settings)
            self.assertTrue(settings.get("enableSkillCommands"))

            # Check skills were copied
            skills_dir = storageops_dir / "skills"
            self.assertTrue(skills_dir.exists())
            dirs = [d.name for d in skills_dir.iterdir() if d.is_dir()]
            self.assertIn("storageops-triage", dirs)


class TestDoctorCommand(unittest.TestCase):
    def test_doctor_runs_without_error(self):
        import argparse
        from storageops.cli import cmd_doctor
        args = argparse.Namespace()
        # doctor should not raise, even when Pi is missing
        try:
            cmd_doctor(args)
        except SystemExit:
            pass  # sys.exit is not expected but acceptable


class TestPiWorkdirFallback(unittest.TestCase):
    def test_skills_path_fallback_to_repo(self):
        from storageops.runtime.pi_rpc import _skills_path
        with patch("storageops.config._FILE", Path("/nonexistent/config.json")), \
             patch("storageops.config._DIR", Path("/nonexistent")):
            path = _skills_path()
            # Should return a non-empty string
            self.assertIsInstance(path, str)
            self.assertTrue(len(path) > 0)

    def test_pi_workdir_creates_dir(self):
        import tempfile
        from storageops.runtime.pi_rpc import _pi_workdir
        with tempfile.TemporaryDirectory() as td:
            wd = Path(td) / "workdir"
            with patch("storageops.config._FILE", Path("/nonexistent/config.json")), \
                 patch("storageops.config._DIR", wd):
                result = _pi_workdir()
                self.assertTrue(result.exists())


if __name__ == "__main__":
    unittest.main()
