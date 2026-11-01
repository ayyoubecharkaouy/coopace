"""Path preparation profile and launcher guards, using fake sudo only."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_prepare_cake_go_active as existing


class PathPreparationTests(unittest.TestCase):
    def test_profile_targets_only_the_new_entry_and_keeps_old_default(self):
        runner = existing.prepare.runner_template(True)
        self.assertIn("scripts/lab-cake-go-path.py", runner)
        self.assertNotIn("scripts/lab-cake-go-active.py", runner)
        self.assertEqual(existing.prepare.runner_template(), existing.prepare.RUNNER)

    def test_dirty_tree_is_refused_before_build_for_path_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "unused"
            with patch.object(existing.prepare.os, "geteuid", return_value=1000), \
                 patch.object(existing.prepare, "command", return_value=b" M source\n"):
                with self.assertRaisesRegex(existing.prepare.model.Error, "non propre"):
                    existing.prepare.prepare(destination, path_control=True)
            self.assertFalse(destination.exists())

    def test_inputs_revision_and_existing_results_never_invoke_sudo(self):
        runner = existing.prepare.runner_template(True)
        helper = existing.PreparationTests(methodName="runTest")
        with patch.object(existing.prepare, "RUNNER", runner):
            for scenario in ("existing", "inputs", "revision"):
                with self.subTest(scenario=scenario):
                    process, calls, second, code = helper.run_shell(scenario)
                    self.assertEqual(process.returncode, 2, process.stderr)
                    self.assertEqual(calls, "")
                    self.assertFalse(second)
                    self.assertIsNone(code)

    def test_failed_first_path_control_is_preserved_without_second_invocation(self):
        runner = existing.prepare.runner_template(True)
        helper = existing.PreparationTests(methodName="runTest")
        with patch.object(existing.prepare, "RUNNER", runner):
            process, calls, second, code = helper.run_shell("first_fails")
        self.assertEqual(process.returncode, 7, process.stderr)
        self.assertEqual(calls, "called\n")
        self.assertFalse(second)
        self.assertEqual(code, "7\n")


if __name__ == "__main__":
    unittest.main()
