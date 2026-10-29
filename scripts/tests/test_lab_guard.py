"""Real process crashes/reaping with fake namespaces; no network or root needed."""

from contextlib import redirect_stdout, redirect_stderr
import importlib.util
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SOURCE = Path(__file__).resolve().parents[1] / "lab-guard.py"
SPEC = importlib.util.spec_from_file_location("lab_guard", SOURCE)
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)

# Run in a dedicated process: subreaper state and adopted children must not
# affect the unittest runner or other tests. The filesystem stands in for ip.
HARNESS = r'''
import importlib.util, json, os, signal, subprocess, sys
from pathlib import Path
source, root, scenario, mode = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], sys.argv[4]
spec = importlib.util.spec_from_file_location("guard", source)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)

class FakeNamespaces(guard.Namespaces):
    def __init__(self):
        super().__init__("unused-ip", root / "namespaces")
        self.directory.mkdir()
        self.calls = []
        self.created = 0

    def identity(self, name):
        path = self.directory / name
        if scenario == "collision" and name.endswith("-g") and not path.exists():
            path.mkdir()
        identity = super().identity(name)
        if scenario == "changed_identity" and self.created == 3 and name.endswith("-s"):
            self.created += 1
            return (identity[0], identity[1] + 1)
        return identity

    def command(self, action, name, timeout):
        assert 0 < timeout <= 2
        self.calls.append([action, name])
        (root / "calls.json").write_text(json.dumps(self.calls))
        path = self.directory / name
        if action == "add":
            path.mkdir()
            self.created += 1
            if scenario == "uncertain_creation" and name.endswith("-g"):
                raise subprocess.TimeoutExpired(["fake-ip", "add", name], timeout)
            if scenario == "interrupt_after_create" and name.endswith("-g"):
                os.kill(os.getpid(), signal.SIGTERM)
            if scenario == "extra_file" and name.endswith("-s"):
                next(root.glob("coopace-guard.*")).joinpath("foreign-file").touch()
        elif action == "del":
            if scenario == "cleanup_failure" and name.endswith("-s"):
                raise subprocess.CalledProcessError(1, ["fake-ip", "del", name])
            # All process-group members must have been reaped BEFORE any delete.
            for record in (root / "proc").glob("*"):
                assert not Path("/proc", record.name).exists(), "live/zombie helper at namespace deletion"
            path.rmdir()
        else:
            raise AssertionError(action)

    def worker_args(self, gateway, mode):
        assert gateway.endswith("-g") and (self.directory / gateway).exists()
        code = guard.WORKER
        # Preserve PIDs independently of stdout for failure/timeout assertions.
        code = code.replace('print("READY " + str(child.pid), flush=True)',
            'from pathlib import Path\nimport os, signal\n'
            + 'Path(' + repr(str(root / "proc")) + ', str(os.getpid())).touch()\n'
            + 'Path(' + repr(str(root / "proc")) + ', str(child.pid)).touch()\n'
            + 'print("READY " + str(child.pid), flush=True)')
        if scenario == "driver_failure":
            code += '\nraise SystemExit(7)\n'
        if scenario == "output_limit":
            code = 'print("x" * 5000, flush=True)\nimport time\ntime.sleep(120)'
        if scenario == "no_readiness":
            code = 'import time\ntime.sleep(120)'
        if scenario == "early_exit":
            code = 'raise SystemExit(0)'
        if scenario == "deadline":
            mode = "check-crash"  # keep driver and descendant alive until guard deadline
        if scenario == "interrupt_running":
            code += '\n'
            code = code.replace('if sys.argv[1] == "check-crash":',
                                'os.kill(os.getppid(), signal.SIGTERM)\nif True:')
        return [sys.executable, "-I", "-c", code, mode]

(root / "proc").mkdir()
backend = FakeNamespaces()
try:
    timeout = 0.7 if scenario in ("deadline", "no_readiness") else 5
    result = guard.run_check(mode, backend, timeout=timeout, tempdir=root)
    print(json.dumps(result))
except guard.Interrupted as error:
    print(str(error), file=sys.stderr)
    raise SystemExit(error.code)
except (OSError, guard.GuardError, subprocess.SubprocessError) as error:
    print(str(error), file=sys.stderr)
    raise SystemExit(1)
'''


@unittest.skipUnless(sys.platform == "linux", "Linux supervision")
class GuardTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="coopace-guard-tests-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def run_guard(self, scenario="complete", mode="check"):
        result = subprocess.run([sys.executable, "-I", "-c", HARNESS,
                                 str(SOURCE), str(self.root), scenario, mode],
                                capture_output=True, text=True, timeout=8)
        # Check real process absence, including zombie recovery, also on failure.
        for record in (self.root / "proc").glob("*"):
            self.assertFalse(Path("/proc", record.name).exists(), result.stderr)
        return result

    def calls(self):
        path = self.root / "calls.json"
        return json.loads(path.read_text()) if path.exists() else []

    def test_plan_and_invalid_arguments_never_reach_preflight(self):
        for args, expected in (([], 0), (["plan"], 0), (["unknown"], 2), (["check", "extra"], 2)):
            with self.subTest(args=args), patch.object(guard, "preflight") as preflight:
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    try:
                        code = guard.main(args)
                    except SystemExit as error:
                        code = error.code
                self.assertEqual(code, expected)
                preflight.assert_not_called()

    def test_unprivileged_check_stops_before_reservation(self):
        with patch.object(guard.os, "geteuid", return_value=1000), \
                patch.object(guard.tempfile, "mkdtemp") as create, \
                redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
            self.assertEqual(guard.main(["check"]), 1)
            create.assert_not_called()

    def test_normal_exit_reaps_abandoned_descendant_then_cleans_resources(self):
        result = self.run_guard()
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["driver_exit_code"], 0)
        self.assertEqual(report["reaped_descendants"], 1)
        self.assertTrue(report["cleanup_verified"])
        self.assertFalse(report["queue_applied"])
        self.assertFalse(Path(report["workspace"]).exists())
        self.assertEqual(list((self.root / "namespaces").iterdir()), [])
        calls = self.calls()
        self.assertEqual([name for action, name in calls if action == "del"],
                         [name for action, name in calls if action == "add"][::-1])

    def test_sigkill_of_driver_still_reaps_term_resistant_descendant(self):
        result = self.run_guard(mode="check-crash")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["driver_exit_code"], -signal.SIGKILL)
        self.assertEqual(report["reaped_descendants"], 1)
        self.assertTrue(report["cleanup_verified"])
        self.assertEqual(list((self.root / "namespaces").iterdir()), [])

    def test_unrelated_process_is_never_signalled(self):
        other = subprocess.Popen([sys.executable, "-I", "-c", "import time; time.sleep(30)"],
                                 start_new_session=True)
        try:
            result = self.run_guard(mode="check-crash")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIsNone(other.poll())
        finally:
            other.kill()
            other.wait(timeout=2)

    def test_deadline_stops_entire_group_and_emits_no_report(self):
        result = self.run_guard("deadline")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("Échéance indépendante", result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(list((self.root / "namespaces").iterdir()), [])

    def test_signal_just_after_creation_records_ownership_before_cleanup(self):
        result = self.run_guard("interrupt_after_create")
        self.assertEqual(result.returncode, 143, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(len(self.calls()), 4)
        self.assertEqual(list((self.root / "namespaces").iterdir()), [])

    def test_signal_during_measurement_stops_group_and_keeps_signal_exit(self):
        result = self.run_guard("interrupt_running")
        self.assertEqual(result.returncode, 143, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(list((self.root / "namespaces").iterdir()), [])

    def test_name_collision_never_deletes_foreign_namespace(self):
        result = self.run_guard("collision")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("Collision", result.stderr)
        remaining = list((self.root / "namespaces").iterdir())
        self.assertEqual(len(remaining), 1)
        self.assertTrue(remaining[0].name.endswith("-g"))
        self.assertFalse(any(name.endswith("-g") for _action, name in self.calls()))

    def test_ambiguous_creation_is_preserved_with_recovery_journal(self):
        result = self.run_guard("uncertain_creation")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("création ambiguë", result.stderr)
        journal = json.loads(next(self.root.glob("coopace-guard.*/owner.json")).read_text())
        self.assertEqual(journal["state"], "cleanup_failed")
        self.assertEqual(len(journal["uncertain_names"]), 1)
        self.assertFalse(any(action == "del" and name.endswith("-g") for action, name in self.calls()))

    def test_replaced_namespace_identity_prevents_deletion(self):
        result = self.run_guard("changed_identity")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("Identité", result.stderr)
        self.assertFalse(any(action == "del" and name.endswith("-s") for action, name in self.calls()))

    def test_failed_delete_keeps_journal_and_never_announces_success(self):
        result = self.run_guard("cleanup_failure")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("Nettoyage incomplet", result.stderr)
        self.assertNotIn("espaces du contrôle supprimés", result.stderr)
        self.assertEqual(len(list((self.root / "namespaces").iterdir())), 1)
        self.assertTrue(list(self.root.glob("coopace-guard.*/owner.json")))

    def test_unknown_workspace_file_is_preserved(self):
        result = self.run_guard("extra_file")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertTrue(list(self.root.glob("coopace-guard.*/foreign-file")))

    def test_driver_failure_does_not_publish_success_after_cleanup(self):
        result = self.run_guard("driver_failure")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertIn("non conforme", result.stderr)
        self.assertEqual(list((self.root / "namespaces").iterdir()), [])

    def test_bad_output_and_missing_readiness_clean_up(self):
        for scenario in ("output_limit", "no_readiness", "early_exit"):
            with self.subTest(scenario=scenario):
                directory = self.root / scenario
                directory.mkdir()
                result = subprocess.run([sys.executable, "-I", "-c", HARNESS,
                                         str(SOURCE), str(directory), scenario, "check"],
                                        capture_output=True, text=True, timeout=8)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertEqual(result.stdout, "")
                self.assertEqual(list((directory / "namespaces").iterdir()), [])

    def test_native_backend_uses_exact_namespace_and_bounded_command(self):
        backend = guard.Namespaces("/usr/sbin/ip", self.root)
        with patch.object(guard.subprocess, "run") as run:
            backend.command("add", "cg-abc123xy-g", 1)
        run.assert_called_once_with(["/usr/sbin/ip", "netns", "add", "cg-abc123xy-g"],
                                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                    check=True, timeout=1)
        link = self.root / "symlink"
        link.symlink_to(self.root)
        with self.assertRaises(guard.GuardError):
            backend.identity(link.name)

    def test_unconfirmed_process_stop_preserves_all_namespaces(self):
        backend = guard.Namespaces("unused-ip", self.root)
        owner = guard.Guard(backend, tempdir=self.root)
        owner.owned = [("cg-abc123xy-g", (1, 2))]
        with patch.object(owner, "stop_group", side_effect=guard.GuardError("still alive")), \
                patch.object(backend, "command") as command:
            with self.assertRaisesRegex(guard.GuardError, "arrêt des processus"):
                owner.close()
            command.assert_not_called()


if __name__ == "__main__":
    unittest.main()
