"""Real supervised processes with fake ip/tc; no sockets or namespaces."""

from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SOURCE = Path(__file__).resolve().parents[1] / "lab_active.py"
SPEC = importlib.util.spec_from_file_location("active", SOURCE)
active = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(active)


def documents():
    def stamp(seconds):
        return f"2026-10-30T00:00:{seconds:02d}Z"
    common = {"schema_version": 1, "requested_bytes": active.VOLUME, "block_bytes": 16384,
              "started_at": stamp(0), "finished_at": stamp(20)}
    send = {**common, "method": "synthetic_tcp_send", "target": active.LOAD_TARGET,
            "written_bytes": active.VOLUME, "timeout_ms": 25000,
            "requested_bytes_per_second": 1048576, "elapsed_ms": 20000,
            "average_bytes_per_second": active.VOLUME / 20,
            "first_write_at": stamp(0), "last_write_at": stamp(19)}
    receive = {**common, "method": "synthetic_tcp_receive", "listen": active.LOAD_TARGET,
               "received_bytes": active.VOLUME, "timeout_ms": 28000, "receive_elapsed_ms": 20000,
               "elapsed_ms": 20000,
               "average_bytes_per_second": active.VOLUME / 20,
               "first_read_at": stamp(0), "last_read_at": stamp(20)}
    latency = {"schema_version": 1, "method": "tcp_connect", "target": active.TARGET,
               "declared_condition": "loaded", "requested_attempts": 10,
               "timeout_ms": 1000, "pause_between_attempts_ms": 250,
               "started_at": stamp(2), "finished_at": stamp(4), "successful": 10, "failed": 0,
               "attempts": [{"started_at": stamp(2), "connect_ms": 1} for _ in range(10)]}
    return send, receive, latency


HARNESS = r'''
import importlib.util, json, os, signal, sys
from pathlib import Path
source, root, scenario = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
spec = importlib.util.spec_from_file_location("active", source)
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)
class FakeNamespaces(a.guard_module.Namespaces):
    def __init__(self):
        super().__init__(str(root / "ip"), root / "namespaces")
        self.directory.mkdir()
        self.interfaces, self.up, self.has_queue, self.reads, self.calls = {}, set(), False, 0, []
    def command(self, action, name, timeout):
        path = self.directory / name
        if action == "add":
            path.mkdir()
            self.interfaces[name] = ["lo"]
        else:
            for pid in (root / "pids").iterdir():
                assert not Path("/proc", pid.name).exists(), "unreaped helper before namespace deletion"
            path.rmdir()
    def execute(self, args, owner):
        self.calls.append(args)
        (root / "calls.json").write_text(json.dumps(self.calls))
        c, g, s = [name for name, _ in owner.owned]
        assert args[0] == self.ip
        if args[1] == "-n":
            namespace, command = args[2], args[3:]
            assert namespace in (c, g, s)
            if command == ["-j", "link", "show"]:
                return json.dumps([{"ifname": name, "flags": ["UP"] if (namespace,name) in self.up else []}
                                   for name in self.interfaces[namespace]]).encode()
            if command[:2] == ["link", "add"]:
                assert namespace == g and command[2] in ("wan", "lan")
                peer = s if command[2] == "wan" else c
                assert command == ["link", "add", command[2], "type", "veth", "peer", "name", "eth0", "netns", peer]
                self.interfaces[g].append(command[2])
                self.interfaces[peer].append("eth0")
            elif command[:2] == ["link", "set"]:
                assert command[2] == "dev" and command[3] in self.interfaces[namespace] and command[4] == "up"
                self.up.add((namespace,command[3]))
            elif command[:2] == ["address", "add"]:
                assert command[2] in ("10.203.0.2/30", "10.203.0.1/30", "10.203.0.5/30", "10.203.0.6/30")
                if scenario == "configuration_failure":
                    raise a.Error("injected address failure")
            elif command[:2] == ["route", "add"]:
                assert namespace in (c,s) and "default" not in command and "via" in command
            else:
                raise AssertionError(args)
            return b""
        assert args[1:4] == ["netns", "exec", g]
        command = args[4:]
        if command[0] == "fake-sysctl":
            if command[1:] == ["-n", "net.ipv4.ip_forward"]:
                return b"1\n"
            assert command[1:] == ["-q", "-w", "net.ipv4.ip_forward=1"]
            return b""
        assert command[0] == "fake-tc"
        if command[1:4] == ["qdisc", "add", "dev"]:
            assert not self.has_queue and (g,"wan") not in self.up
            self.has_queue = True
            return b""
        assert command[-4:] == ["qdisc", "show", "dev", "wan"]
        if not self.has_queue:
            return b"[]"
        row = {"kind":"tbf", "root":True, "handle":"10:",
               "options":{"rate":500000,"burst":65536,"limit":131072}}
        if "-s" in command:
            self.reads += 1
            if scenario == "statistics_failure" and self.reads == 6:
                raise a.Error("injected statistics failure")
            if scenario == "interrupt" and self.reads == 6:
                os.kill(os.getpid(), signal.SIGTERM)
            count = self.reads * 100
            if scenario == "counter_reset" and self.reads == 7:
                count = 1
            row.update({key:count for key in a.queue.COUNTERS})
            row.update(backlog=1 if scenario == "queue_never_empty" else 0, qlen=0)
        return json.dumps([row]).encode()
namespaces = FakeNamespaces()
try:
    result = a.run("check-crash" if scenario == "crash" else "check", namespaces,
                   "fake-tc", "fake-sysctl", root / "bin", tempdir=root,
                   timeout=0.7 if scenario == "deadline" else 12)
    print(json.dumps(result))
except Exception as error:
    print(str(error), file=sys.stderr)
    raise SystemExit(1)
'''


HELPER = r'''
import json, os, signal, sys, time
from pathlib import Path
root = Path(__file__).resolve().parents[1]
(root / "pids" / str(os.getpid())).touch()
signal.signal(signal.SIGTERM, signal.SIG_IGN)
name = Path(sys.argv[0]).name
docs = json.loads((root / "documents.json").read_text())
if name == "coopace-lab-tcp":
    print("READY 10.203.0.6:46001", flush=True)
    time.sleep(40)
elif name == "coopace-lab-load":
    sending = sys.argv[1] == "send"
    print("STARTED" if sending else "READY 10.203.0.6:46002", flush=True)
    time.sleep(2)
    print(json.dumps(docs[0 if sending else 1]), flush=True)
else:
    if (root / "worker-failure").exists():
        raise SystemExit(7)
    print(json.dumps(docs[2]), flush=True)
'''


class ActiveTests(unittest.TestCase):
    def validate(self, values, code=0):
        return active.flow_documents(*(json.dumps(value).encode() for value in values), code)

    def test_full_reports_and_observed_overlap(self):
        result = self.validate(documents())
        self.assertTrue(result["probe_window_inside_application_writes"])
        values = documents()
        values[0]["last_write_at"] = "2026-10-30T00:00:03Z"
        self.assertFalse(self.validate(values)["probe_window_inside_application_writes"])

    def test_failed_probes_are_preserved(self):
        values = documents()
        latency = values[2]
        latency.update(successful=0, failed=10)
        for attempt in latency["attempts"]:
            attempt.update(connect_ms=None, failure="timeout")
        result = self.validate(values, code=1)
        self.assertFalse(result["has_successful_probe"])
        self.assertEqual(result["latency"]["failed"], 10)

    def test_incomplete_receipt_wrong_rate_and_incoherent_attempts_fail(self):
        for index, key, value in ((1,"received_bytes",1), (1,"average_bytes_per_second",None),
                                  (1,"receive_elapsed_ms",float("inf")), (0,"timeout_ms",12000),
                                  (0,"average_bytes_per_second",1), (2,"attempts",[]),
                                  (2,"failed",True), (2,"successful",9)):
            values = deepcopy(documents())
            values[index][key] = value
            with self.subTest(key=key), self.assertRaises((active.Error, active.series.ExperimentError)):
                self.validate(values)

    def test_ready_requires_exactly_three_distinct_pids(self):
        self.assertEqual(active.announcement(b"READY [1,2,3]"), [1,2,3])
        for line in (b"READY [1,1,2]", b"READY [true,2,3]", b"READY {}", b"other", b"READY [1,2,3,4]"):
            with self.subTest(line=line), self.assertRaises(active.Error):
                active.announcement(line)

    def run_case(self, scenario):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "bin").mkdir()
            (root / "pids").mkdir()
            (root / "documents.json").write_text(json.dumps(documents()))
            if scenario == "worker_failure":
                (root / "worker-failure").touch()
            for name in ("coopace", "coopace-lab-tcp", "coopace-lab-load"):
                path = root / "bin" / name
                path.write_text("#!" + sys.executable + "\n" + HELPER)
                path.chmod(0o700)
            ip = root / "ip"
            ip.write_text("#!" + sys.executable + "\nimport os,sys\n"
                          "assert sys.argv[1:3] == ['netns','exec']\n"
                          "os.execv(sys.argv[4],sys.argv[4:])\n")
            ip.chmod(0o700)
            result = subprocess.run([sys.executable, "-I", "-B", "-c", HARNESS, str(SOURCE), directory, scenario],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=18)
            self.assertEqual(list((root / "namespaces").iterdir()), [], result.stderr.decode())
            self.assertEqual(list(root.glob("coopace-guard.*")), [], result.stderr.decode())
            for pid in (root / "pids").iterdir():
                self.assertFalse(Path("/proc", pid.name).exists(), result.stderr.decode())
            return result, json.loads((root / "calls.json").read_text())

    def test_normal_flow_and_periodic_raw_statistics(self):
        result, calls = self.run_case("normal")
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        value = json.loads(result.stdout)
        self.assertEqual(value["driver_exit_code"], 0)
        self.assertEqual(value["reaped_descendants"], 0)
        self.assertTrue(value["cleanup_verified"])
        self.assertEqual(value["flow"]["receive"]["received_bytes"], active.VOLUME)
        self.assertGreaterEqual(len(value["queue_samples"]), 5)
        self.assertTrue(all("qdiscs" in reading for reading in value["queue_samples"]))
        self.assertGreater(value["traffic_statistics_delta"]["counters"]["bytes"], 0)
        self.assertEqual(value["congestion"], "not_assessed")
        self.assertTrue(any("net.ipv4.ip_forward=1" in call for call in calls))

    def test_crash_reaps_three_live_helpers_before_namespace_deletion(self):
        result, _ = self.run_case("crash")
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        value = json.loads(result.stdout)
        self.assertEqual(value["driver_exit_code"], -9)
        self.assertEqual(value["reaped_descendants"], 3)
        self.assertIsNone(value["flow"])

    def test_failure_deadline_undrained_queue_and_midwindow_reset_cleanup(self):
        for scenario, message in (("configuration_failure", "injected address failure"),
                                  ("deadline", "Échéance indépendante"),
                                  ("queue_never_empty", "File non vidée"),
                                  ("counter_reset", "Progression des compteurs"),
                                  ("statistics_failure", "injected statistics failure"),
                                  ("interrupt", "Supervision interrompue"),
                                  ("worker_failure", "Un outil a échoué")):
            with self.subTest(scenario=scenario):
                result, _ = self.run_case(scenario)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, b"")
                self.assertIn(message, result.stderr.decode())

    def test_plan_needs_no_privileges_or_resources(self):
        result = subprocess.run([sys.executable, "-I", "-B", str(SOURCE.with_name("lab-active.py")), "plan"],
                                capture_output=True, timeout=3, check=True)
        self.assertIn(b"4mbit", result.stdout)


if __name__ == "__main__":
    unittest.main()
