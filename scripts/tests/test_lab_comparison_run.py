"""Six-arm sequencing and persistent failures, with fake network operations."""

import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock

import test_lab_comparison as shared


SOURCE = shared.SOURCE.with_name("lab_comparison_run.py")
spec = importlib.util.spec_from_file_location("comparison_run", SOURCE)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class FakeClock:
    value = 0

    def now(self):
        return self.value

    def pause(self, seconds):
        self.value += seconds


class SequenceTests(unittest.TestCase):
    def execute_case(self, scenario="normal"):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifacts, binaries = root / "experiment", root / "bin"
            artifacts.mkdir(); binaries.mkdir()
            for name in ("coopace", "coopace-lab-tcp", "coopace-lab-load"):
                (binaries / name).write_text("frozen executable fixture")
            clock, calls = FakeClock(), []
            def pause(seconds):
                clock.pause(seconds)
                if scenario == "between_interrupt":
                    os.kill(os.getpid(), signal.SIGTERM)
            def snapshot(*args):
                result = {"sha256": {str(path): runner.digest(path) for path in binaries.iterdir()}}
                if scenario == "environment" and len(calls) == 2: result["changed"] = True
                return result
            def execute(engine, namespaces, tc, sysctl, ping, binary_path, folder):
                calls.append((engine, folder.name, clock.now()))
                self.assertEqual(binary_path, binaries)
                os.write(2, b"owned helper diagnostic\n")
                if scenario == "failure" and len(calls) == 2:
                    raise runner.model.Error("injected campaign failure")
                if scenario == "interrupt" and len(calls) == 2:
                    raise runner.campaign.guards.Interrupted(143)
                clock.pause(60)
                loaded = 5 if scenario == "unfavorable" and engine == "tbf" else None
                token = "test0001" if scenario == "reuse" else f"test{len(calls):04d}"
                report = shared.report_fixture(engine, folder, token, loaded_p50=loaded)
                if scenario == "technical" and len(calls) == 2: report["decision"]["technical_valid"] = False
                return report
            def validate(report, engine, folder, binaries):
                return runner.model.summarize(report, engine, folder, binaries,
                                              lambda *args: "strict comparison fixture\n")
            error, result = None, None
            previous = {s: signal.getsignal(s) for s in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM)}
            try:
                result = runner.run(Mock(ip="fake-ip"), "tc", "sysctl", "ping", binaries, artifacts,
                                    execute=execute, snapshot=snapshot, validator=validate,
                                    clock=clock.now, pause=pause)
            except Exception as caught:
                error = caught
            self.assertEqual({s: signal.getsignal(s) for s in previous}, previous)
            session = json.loads((artifacts / "session.json").read_text())
            files = {str(p.relative_to(artifacts)): p.read_text() for p in artifacts.rglob("*") if p.is_file()}
            if result:
                self.assertEqual(runner.analyze(artifacts, validator=validate), result)
                if scenario == "normal":
                    for path in (artifacts / "01-block-1-tbf/phase-1-idle.json", artifacts / "comparison.json",
                                 artifacts / "environment.json", artifacts / "01-block-1-tbf/campaign.json", binaries / "coopace"):
                        previous_bytes = path.read_bytes()
                        path.write_text("{}")
                        try:
                            with self.assertRaises(runner.model.Error): runner.analyze(artifacts, validator=validate)
                        finally:
                            path.write_bytes(previous_bytes)
                    previous_bytes = (artifacts / "session.json").read_bytes()
                    modified = json.loads(previous_bytes)
                    modified["arms"][1]["started_elapsed_ms"] -= 1
                    (artifacts / "session.json").write_text(json.dumps(modified))
                    with self.assertRaises(runner.model.Error): runner.analyze(artifacts, validator=validate)
                    (artifacts / "session.json").write_bytes(previous_bytes)
            else:
                with self.assertRaises(runner.model.Error): runner.analyze(artifacts, validator=validate)
            return result, error, calls, session, files

    def test_six_fresh_topologies_fixed_order_gaps_and_reanalysis(self):
        result, error, calls, session, files = self.execute_case()
        self.assertIsNone(error)
        self.assertEqual([c[0] for c in calls], [engine for _, engine in runner.model.ORDER])
        self.assertEqual([c[2] for c in calls], [0, 62, 124, 186, 248, 310])
        self.assertEqual(len(set(c[1] for c in calls)), 6)
        self.assertEqual(session["state"], "complete")
        self.assertEqual(result["decision"], "static_cake_improvement_v1")
        self.assertEqual(len(result["pairs"]), 9)
        for arm in session["arms"]:
            self.assertIn("owned helper diagnostic", files[arm["directory"] + "/campaign.log"])

    def test_unfavorable_reference_still_collects_all_six_and_returns_complete(self):
        result, error, calls, session, _ = self.execute_case("unfavorable")
        self.assertIsNone(error)
        self.assertEqual(len(calls), 6)
        self.assertEqual(session["state"], "complete")
        self.assertEqual(result["decision"], "reference_unqualified")

    def test_failure_interrupt_invalid_collection_and_changed_environment_stop_next_arm(self):
        for scenario in ("failure", "interrupt", "technical", "environment", "reuse"):
            with self.subTest(scenario=scenario):
                result, error, calls, session, files = self.execute_case(scenario)
                self.assertIsNone(result)
                self.assertIsNotNone(error)
                self.assertEqual(len(calls), 2)
                self.assertEqual(session["state"], "failed")
                self.assertFalse(session["technical_valid"])
                self.assertEqual(session["decision"], "non_exploitable")
                self.assertNotIn("comparison.json", files)
                self.assertIn("01-block-1-tbf/campaign.json", files)
                if scenario == "failure": self.assertEqual(files["02-block-1-cake/campaign.exit"], "1\n")
                if scenario == "interrupt": self.assertEqual(files["02-block-1-cake/campaign.exit"], "143\n")

    def test_existing_results_are_not_truncated(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "session.json"
            path.write_text("preserve")
            with self.assertRaises(runner.model.Error):
                runner.run(None, None, None, None, None, root)
            self.assertEqual(path.read_text(), "preserve")

    def test_interrupt_between_campaigns_creates_no_next_topology(self):
        result, error, calls, session, _ = self.execute_case("between_interrupt")
        self.assertIsNone(result)
        self.assertEqual(error.code, 143)
        self.assertEqual(len(calls), 1)
        self.assertEqual(session["state"], "failed")

    def test_plan_and_analyze_need_no_network_privileges(self):
        entry = SOURCE.with_name("lab-compare.py")
        result = subprocess.run([sys.executable, "-I", "-B", str(entry), "plan"], capture_output=True, timeout=3, check=True)
        self.assertIn(b"360", result.stdout)
        self.assertIn(b"144", result.stdout)
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, "-I", "-B", str(entry), "analyze", "--artifacts", directory],
                                    capture_output=True, timeout=3)
            self.assertEqual(result.returncode, 1)
            self.assertIn(b"non exploitable", result.stderr)
            self.assertNotIn(b"CAP_", result.stderr)


if __name__ == "__main__":
    unittest.main()
