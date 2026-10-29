"""Exercise lab lifecycle with fake OS tools; never creates network resources."""

import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest


@unittest.skipUnless(platform.system() == "Linux", "The virtual lab targets Linux")
class LabNetworkTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="coopace-lab-tests-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / "scripts").mkdir()
        self.script = self.root / "scripts/lab-network.sh"
        source = Path(__file__).resolve().parents[1] / "lab-network.sh"
        shutil.copyfile(source, self.script)
        for name in ["coopace-gateway", "coopace", "coopace-lab-tcp"]:
            binary = self.root / ".local/bin" / name
            binary.parent.mkdir(parents=True, exist_ok=True)
            binary.write_text("#!/bin/sh\nexit 0\n")
            binary.chmod(0o755)
        self.log = self.root / "calls.jsonl"
        self.state = self.root / "state.json"
        self.reservation = self.root / "coopace-lab.ABC123xy"
        self.tools = self.root / "tools"
        self.tools.mkdir()
        stub = self.root / "stub.py"
        stub.write_text(r'''
import json, os, signal, sys, time
from pathlib import Path
command, args = sys.argv[1], sys.argv[2:]
with open(os.environ["COOPACE_LAB_TEST_LOG"], "a") as log:
    log.write(json.dumps([command, *args]) + "\n")
mode = os.environ["COOPACE_LAB_TEST_MODE"]
state_path = Path(os.environ["COOPACE_LAB_TEST_STATE"])
state = json.loads(state_path.read_text()) if state_path.exists() else {"namespaces": [], "forwarding": False}
def save():
    state_path.write_text(json.dumps(state))
if command == "uname":
    print("Linux")
elif command == "id":
    print("1000" if mode == "unprivileged" else "0")
elif command == "sed":
    print("0" if mode == "no_caps" else "0000000000203000")
elif command == "mktemp":
    path = Path(os.environ["COOPACE_LAB_TEST_RESERVATION"])
    path.mkdir(mode=0o700)
    print(path)
elif command == "ip":
    if args[:2] == ["netns", "add"]:
        name = args[2]
        if mode == "collision" and name.endswith("-s"):
            sys.exit(1)
        state["namespaces"].append(name)
        save()
    elif args[:2] == ["netns", "del"]:
        if mode in {"cleanup_failure", "tcp_cleanup_failure"} and args[2].endswith("-s"):
            sys.exit(1)
        pid_file = Path(os.environ["COOPACE_LAB_TEST_STATE"]).parent / "server-pid"
        if pid_file.exists():
            try:
                os.kill(int(pid_file.read_text()), 0)
            except ProcessLookupError:
                pass
            else:
                sys.exit("server process still alive during namespace deletion")
        state["namespaces"].remove(args[2])
        save()
    elif args[:2] == ["netns", "exec"]:
        assert args[2] in state["namespaces"]
        if args[3] == "sysctl":
            state["forwarding"] = args[-1].endswith("=1")
            save()
        elif args[3] == "ping":
            if mode == "probe_error" and not state["forwarding"]:
                sys.exit(2)
            if mode == "unexpected_pass" and not state["forwarding"]:
                sys.exit(0)
            sys.exit(1 if not state["forwarding"] or mode == "unreachable" else 0)
        elif Path(args[3]).name == "coopace-lab-tcp":
            assert args[2].endswith("-s")
            assert args[4:] == ["--listen", "10.203.0.6:46001", "--connections", "5", "--duration", "15s"]
            root = state_path.parent
            (root / "server-pid").write_text(str(os.getpid()))
            def stop(signum, frame):
                (root / "server-stopped").touch()
                sys.exit(1)
            signal.signal(signal.SIGTERM, stop)
            if mode == "tcp_server_failure":
                sys.exit(1)
            if mode == "tcp_no_readiness":
                time.sleep(10)
                sys.exit(1)
            print("READY 10.203.0.6:46001", flush=True)
            if mode == "tcp_server_incomplete":
                sys.exit(1)
            deadline = time.monotonic() + 3
            while not (root / "client-done").exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            sys.exit(0 if (root / "client-done").exists() else 1)
        elif Path(args[3]).name == "coopace":
            assert args[2].endswith("-c")
            assert args[4:] == ["latency", "--target", "10.203.0.6:46001", "--count", "5", "--timeout", "1s", "--interval", "250ms", "--condition", "unspecified", "--json"]
            if mode == "tcp_pause":
                Path(os.environ["COOPACE_LAB_TEST_PAUSED"]).touch()
                time.sleep(1)
            if mode == "tcp_latency_failure":
                sys.exit(1)
            (state_path.parent / "client-done").touch()
            if mode != "tcp_empty":
                print(json.dumps({"schema_version": 1, "kind": "tcp_connect_fixture"}))
        else:
            assert args[-2:] == ["inspect", "--json"]
            if mode == "inventory_failure":
                sys.exit(1)
            print(json.dumps({"schema_version": 1, "kind": "gateway_inventory", "mode": "read_only"}))
    else:
        assert args[0] == "-n" and args[1] in state["namespaces"]
        if mode == "pause" and "veth" in args:
            Path(os.environ["COOPACE_LAB_TEST_PAUSED"]).touch()
            time.sleep(1)
        if mode == "link_failure" and "veth" in args:
            sys.exit(1)
''')
        for command in ["uname", "id", "sed", "ip", "ping", "sysctl", "mktemp"]:
            wrapper = self.tools / command
            wrapper.write_text("#!/bin/sh\nexec " + " ".join(
                shlex.quote(value) for value in [sys.executable, str(stub), command]
            ) + ' "$@"\n')
            wrapper.chmod(0o755)

    def environment(self, mode):
        environment = dict(os.environ)
        environment.update({
            "PATH": str(self.tools) + os.pathsep + environment["PATH"],
            "COOPACE_LAB_TEST_LOG": str(self.log),
            "COOPACE_LAB_TEST_STATE": str(self.state),
            "COOPACE_LAB_TEST_RESERVATION": str(self.reservation),
            "COOPACE_LAB_TEST_MODE": mode,
            "COOPACE_LAB_TEST_PAUSED": str(self.root / "paused"),
        })
        return environment

    def run_lab(self, mode="complete", args=("run",)):
        return subprocess.run(["sh", str(self.script), *args], env=self.environment(mode),
                              capture_output=True, text=True, timeout=15)

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def test_plan_and_bad_arguments_never_call_network_tools(self):
        for args, expected in [((), 0), (("plan",), 0), (("unknown",), 2), (("run", "extra"), 2)]:
            with self.subTest(args=args):
                result = self.run_lab(args=args)
                self.assertEqual(result.returncode, expected, result.stderr)
                self.assertEqual(self.calls(), [])
                self.assertFalse(self.reservation.exists())

    def test_missing_privileges_stop_before_any_resource_creation(self):
        for mode in ["unprivileged", "no_caps"]:
            with self.subTest(mode=mode):
                result = self.run_lab(mode)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(any(call[0] in {"ip", "mktemp"} for call in self.calls()))
                self.assertFalse(self.reservation.exists())

    def test_success_only_targets_owned_namespaces_and_cleans_them(self):
        result = self.run_lab()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["kind"], "gateway_inventory")
        calls = [call[1:] for call in self.calls() if call[0] == "ip"]
        added = [call[2] for call in calls if call[:2] == ["netns", "add"]]
        removed = [call[2] for call in calls if call[:2] == ["netns", "del"]]
        self.assertEqual(len(added), 3)
        self.assertCountEqual(added, removed)
        for call in calls:
            if call[0] == "-n":
                self.assertIn(call[1], added)
            elif call[:2] == ["netns", "exec"]:
                self.assertIn(call[2], added)
            else:
                self.assertIn(call[:2], [["netns", "add"], ["netns", "del"]])
        self.assertFalse(any("default" in call for call in calls))
        self.assertEqual(json.loads(self.state.read_text())["namespaces"], [])
        self.assertFalse(self.reservation.exists())

    def test_failures_clean_only_successfully_created_resources(self):
        for mode in ["collision", "link_failure", "probe_error", "unexpected_pass", "unreachable", "inventory_failure"]:
            with self.subTest(mode=mode):
                self.log.unlink(missing_ok=True)
                self.state.unlink(missing_ok=True)
                result = self.run_lab(mode)
                self.assertNotEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, "")
                calls = [call[1:] for call in self.calls() if call[0] == "ip"]
                added = [call[2] for call in calls if call[:2] == ["netns", "add"]]
                removed = [call[2] for call in calls if call[:2] == ["netns", "del"]]
                if mode == "collision":
                    self.assertNotIn(added[-1], removed)
                    added = added[:-1]
                self.assertCountEqual(added, removed)
                self.assertEqual(json.loads(self.state.read_text())["namespaces"], [])
                self.assertFalse(self.reservation.exists())

    def test_cleanup_failure_is_reported_as_failure(self):
        result = self.run_lab("cleanup_failure")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Nettoyage incomplet", result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(len(json.loads(self.state.read_text())["namespaces"]), 1)

    def assert_server_stopped(self):
        pid_file = self.root / "server-pid"
        if pid_file.exists():
            with self.assertRaises(ProcessLookupError):
                os.kill(int(pid_file.read_text()), 0)

    def test_tcp_success_exports_report_after_stopping_server_and_cleanup(self):
        result = self.run_lab(args=("run-tcp",))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["kind"], "tcp_connect_fixture")
        self.assert_server_stopped()
        self.assertEqual(json.loads(self.state.read_text())["namespaces"], [])
        self.assertFalse(self.reservation.exists())

    def test_tcp_failure_stops_server_and_emits_no_report(self):
        for mode in ["tcp_server_failure", "tcp_no_readiness", "tcp_server_incomplete", "tcp_latency_failure", "tcp_empty", "tcp_cleanup_failure"]:
            with self.subTest(mode=mode):
                for path in [self.log, self.state, self.root / "server-pid", self.root / "client-done", self.root / "server-stopped"]:
                    path.unlink(missing_ok=True)
                result = self.run_lab(mode, args=("run-tcp",))
                self.assertNotEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, "")
                self.assert_server_stopped()
                expected_remaining = 1 if mode == "tcp_cleanup_failure" else 0
                self.assertEqual(len(json.loads(self.state.read_text())["namespaces"]), expected_remaining)
                self.assertFalse(self.reservation.exists())
                if mode in {"tcp_latency_failure", "tcp_no_readiness"}:
                    self.assertTrue((self.root / "server-stopped").exists())

    def test_missing_tcp_binary_stops_before_resource_creation(self):
        (self.root / ".local/bin/coopace-lab-tcp").unlink()
        result = self.run_lab(args=("run-tcp",))
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(call[0] in {"ip", "mktemp"} for call in self.calls()))

    def test_termination_runs_cleanup(self):
        self.check_termination("run", "pause")

    def test_tcp_termination_stops_server_before_namespace_cleanup(self):
        self.check_termination("run-tcp", "tcp_pause")
        self.assert_server_stopped()

    def check_termination(self, command, mode):
        process = subprocess.Popen(["sh", str(self.script), command],
                                   env=self.environment(mode),
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 5
            while not (self.root / "paused").exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue((self.root / "paused").exists(), "helper did not reach the interruption point")
            process.send_signal(signal.SIGTERM)
            stdout, stderr = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 143, stderr)
            self.assertEqual(stdout, "")
            self.assertEqual(json.loads(self.state.read_text())["namespaces"], [])
            self.assertFalse(self.reservation.exists())
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main()
