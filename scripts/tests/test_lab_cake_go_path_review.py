"""Replay complete simulated passage evidence; never publish a native proof."""

from copy import deepcopy
import base64
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

import test_lab_cake_go_active_review as existing
import test_lab_cake_go_path_control as path_fixtures

SOURCE = path_fixtures.SOURCE.with_name("lab_cake_go_path_review.py")
spec = importlib.util.spec_from_file_location("path_review_tests", SOURCE)
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


@unittest.skipUnless(sys.platform == "linux", "Linux process evidence")
class PathReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        harness = path_fixtures.HARNESS
        harness = harness.replace("'versions':'simulated'", "'versions':{'ping':{'available':True,'stdout':'ping from iputils simulated\\n','stderr':''}},'bootstrap_sha256':hashlib.sha256(combined.go.BOOTSTRAP.encode()).hexdigest()")
        harness = harness.replace("exit_code=code,process_stopped=True)",
                                  "exit_code=code,process_stopped=True,pid=10000000+len(kernel.calls))")
        with patch.object(existing.fixtures, "HARNESS", harness):
            existing.ReviewTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def validate(self, folder, report):
        return review.validate_control(folder, report, report["environment"]["tools"],
                                       report["environment"]["source_sha256"], {"go_version": "simulated"})

    def test_both_modes_replay_without_publishing_native_validation(self):
        for mode in ("check", "check-crash"):
            folder, report = self.cases["normal", mode]
            value = self.validate(folder, report)
            self.assertEqual(value["path_check"]["commands"], 6)
            self.assertEqual(value["path_check"]["without_forwarding"]["received"], 0)
            self.assertEqual(value["path_check"]["with_forwarding"]["received"], 3)
            self.assertEqual(len(value["recorded_pids"]), 25)
            self.assertFalse((folder / "validation.json").exists())

    def test_old_reviewer_refuses_the_new_scope_and_failed_tcp_is_not_positive(self):
        folder, report = self.cases["normal", "check"]
        with self.assertRaises(review.Error):
            review.base.validate_control(folder, report, report["environment"]["tools"],
                                          report["environment"]["source_sha256"], {"go_version": "simulated"})
        folder, report = self.cases["all_failed", "check"]
        with self.assertRaisesRegex(review.Error, "Dix sondes"):
            self.validate(folder, report)

    def test_summary_flags_counts_and_separate_delta_are_recomputed(self):
        folder, original = self.cases["normal", "check"]
        for change in (lambda p: p.update(path_verified=1), lambda p: p.update(probe_attempted=False),
                       lambda p: p["without_forwarding"].update(received=1),
                       lambda p: p["with_forwarding"].update(transmitted=4),
                       lambda p: p["statistics_delta"]["counters"].update(bytes=999)):
            report = deepcopy(original)
            change(report["path_check"])
            with self.subTest(change=change), self.assertRaises(review.Error):
                self.validate(folder, report)

    def altered(self, change):
        original_folder, original_report = self.cases["normal", "check"]
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / "check"
            shutil.copytree(original_folder, folder)
            report = deepcopy(original_report)
            rows = [json.loads(line) for line in (folder / "supervisor.jsonl").read_text().splitlines()]
            change(report, rows)
            # Rehash the altered journal, so refusal must go beyond the digest.
            (folder / "supervisor.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
            report["supervisor_journal"] = review.base.fingerprint(folder / "supervisor.jsonl", 4 * 1024 * 1024)
            self.validate(folder, report)

    def test_changed_command_code_capture_timing_or_tool_arguments_are_rejected(self):
        def mutate(index, key, value):
            def change(report, rows):
                command = report["path_check"]["commands"][index]
                command[key] = value
                row = next(r for r in rows if r["data"].get("event") == "path_tool_result" and r["data"]["index"] == index + 1)
                row["data"][key] = value
            return change
        for change in (mutate(0, "exit_code", True), mutate(2, "stdout_base64", ""),
                       mutate(1, "stdout_base64", "MQo="), mutate(2, "process_stopped", False),
                       mutate(5, "stdout_truncated", True), mutate(0, "duration_ns", 2_000_000_001),
                       mutate(0, "pid", True), mutate(0, "arguments", ["/host/sysctl"]),
                       mutate(0, "started_at", "invalid")):
            with self.subTest(change=change), self.assertRaises((review.Error, ValueError)):
                self.altered(change)

    def test_path_verified_after_tcp_launch_or_missing_command_is_rejected(self):
        def late(report, rows):
            index = next(i for i, r in enumerate(rows) if r["data"].get("event") == "path_verified")
            event = rows.pop(index)
            target = next(i for i, r in enumerate(rows) if r["data"].get("event") == "traffic_launch_intent")
            rows.insert(target + 1, event)
            for i, row in enumerate(rows):
                row.update(sequence=i + 1, elapsed_ns=i * 1000000)
        def missing(report, rows):
            report["path_check"]["commands"].pop()
        for change in (late, missing):
            with self.subTest(change=change), self.assertRaises(review.Error):
                self.altered(change)

    def test_intermediate_link_change_is_detected_even_when_final_topology_matches(self):
        def change(report, rows):
            first = next(i for i, r in enumerate(rows) if r["data"].get("event") == "path_tool_result")
            row = next(r["data"] for r in rows[first + 1:] if r["data"].get("event") == "activation_tool_result"
                       and r["data"]["arguments"][-4:] == ["-j", "-d", "link", "show"])
            links = json.loads(base64.b64decode(row["stdout_base64"]))
            next(link for link in links if link["ifname"] == "wan")["mtu"] = 1400
            row["stdout_base64"] = base64.b64encode(json.dumps(links).encode()).decode()
        with self.assertRaisesRegex(review.Error, "Lien modifié"):
            self.altered(change)

    def test_missing_or_modified_preparation_creates_no_certificate(self):
        with tempfile.TemporaryDirectory() as directory:
            case = Path(directory)
            (case / "prepared.json").write_text('{}\n')
            (case / "prepared.sha256").write_text('0' * 64 + '  prepared.json\n')
            with self.assertRaises(review.Error):
                review.review(case)
            self.assertFalse((case / "validation.json").exists())


if __name__ == "__main__":
    unittest.main()
