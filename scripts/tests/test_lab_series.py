"""Series orchestration and bounded process tests, without network resources."""

from copy import deepcopy
import importlib.util
import io
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr


SOURCE = Path(__file__).resolve().parents[1] / "lab-series.py"
SPEC = importlib.util.spec_from_file_location("lab_series", SOURCE)
series = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(series)


def latency(condition, failed=False):
    return {"schema_version": 1, "method": "tcp_connect", "target": series.TARGET,
            "declared_condition": condition, "requested_attempts": 10, "timeout_ms": 250,
            "pause_between_attempts_ms": 250, "successful": 0 if failed else 10,
            "failed": 10 if failed else 0,
            "started_at": "2026-10-29T18:00:01.000000001Z",
            "finished_at": "2026-10-29T18:00:04.000000001Z"}


def load():
    return {"schema_version": 1, "method": "synthetic_tcp_send", "target": series.LOAD_TARGET,
            "requested_bytes": 8388608, "written_bytes": 8388608,
            "requested_bytes_per_second": 1048576, "block_bytes": 16384, "timeout_ms": 12000,
            "elapsed_ms": 8000, "average_bytes_per_second": 1048576,
            "started_at": "2026-10-29T18:00:00Z", "first_write_at": "2026-10-29T18:00:00.01Z",
            "last_write_at": "2026-10-29T18:00:07.99Z", "finished_at": "2026-10-29T18:00:08Z"}


class FakeProcess:
    def __init__(self, runner, kind, raw=b"", fail=False):
        self.runner, self.kind, self.raw, self.fail = runner, kind, raw, fail
        self.active = True

    def ready(self, expected, runner):
        self.runner.events.append(("ready", self.kind, expected))
        if self.fail:
            raise series.ExperimentError("readiness failed")

    def running(self):
        return self.active

    def finish(self, runner, timeout, allowed=(0,)):
        if self.fail:
            raise series.ExperimentError("worker failed")
        self.active = False
        return self.raw, 0

    def stop(self):
        self.active = False
        self.runner.events.append(("stop", self.kind))


class FakeRunner:
    def __init__(self, fail=None, failed_probes=False):
        self.fail, self.failed_probes = fail, failed_probes
        self.children, self.events, self.conditions = [], [], []

    def start(self, args):
        binary = Path(args[4]).name
        kind = "target" if binary == "coopace-lab-tcp" else args[5]
        raw = json.dumps(load()).encode() if kind == "send" else b""
        if self.fail == "overlap" and kind == "send":
            value = load()
            value["last_write_at"] = "2026-10-29T18:00:03Z"
            raw = json.dumps(value).encode()
        child = FakeProcess(self, kind, raw, fail=self.fail == kind)
        self.children.append(child)
        self.events.append(("start", kind))
        return child

    def execute(self, args, timeout=8, allowed=(0,)):
        if args[1:3] == ["latency", "compare"]:
            if self.fail == "compare":
                raise series.ExperimentError("strict comparison rejected reports")
            idle = json.loads(Path(args[4]).read_bytes())
            loaded = json.loads(Path(args[6]).read_bytes())
            assert idle["declared_condition"] == "idle" and loaded["declared_condition"] == "loaded"
            return b"comparison with missing distributions when all attempts failed\n", 0
        condition = args[args.index("--condition")+1]
        if condition == "idle":
            assert not any(child.active and child.kind in {"send", "receive"} for child in self.children)
        else:
            assert all(any(child.active and child.kind == kind for child in self.children) for kind in ["send", "receive"])
        self.conditions.append(condition)
        if self.fail == "measure":
            raise series.ExperimentError("measurement aborted")
        code = 1 if self.failed_probes else 0
        assert code in allowed
        return json.dumps(latency(condition, self.failed_probes)).encode(), code

    def pause(self):
        self.events.append(("pause",))


@unittest.skipUnless(platform.system() == "Linux", "Linux lab orchestration")
class SeriesTests(unittest.TestCase):
    def test_fixed_order_three_pairs_and_no_load_during_idle(self):
        with tempfile.TemporaryDirectory() as directory, redirect_stderr(io.StringIO()):
            root = Path(directory)
            runner = FakeRunner()
            result = series.experiment(root, "cp-ABC123xy-c", "cp-ABC123xy-s", root, runner)
            self.assertEqual(runner.conditions, ["idle", "loaded", "loaded", "idle", "idle", "loaded"])
            self.assertEqual(result["total_synthetic_bytes"], 3*8388608)
            self.assertEqual(len(result["pairs"]), 3)
            self.assertEqual(result["overlap_check"], "application_write_window")
            for pair in result["pairs"]:
                self.assertIsNone(pair["idle"]["load"])
                self.assertEqual(pair["loaded"]["load"]["written_bytes"], 8388608)
                self.assertTrue(pair["comparison"])
            self.assertFalse(any(child.active for child in runner.children))
            self.assertEqual(list(root.iterdir()), [])

    def test_failed_attempts_are_preserved_as_data(self):
        with tempfile.TemporaryDirectory() as directory, redirect_stderr(io.StringIO()):
            root = Path(directory)
            result = series.experiment(root, "cp-ABC123xy-c", "cp-ABC123xy-s", root, FakeRunner(failed_probes=True))
            for pair in result["pairs"]:
                for condition in ["idle", "loaded"]:
                    self.assertEqual(pair[condition]["measurement_exit_code"], 1)
                    self.assertEqual(pair[condition]["latency"]["failed"], 10)

    def test_errors_stop_every_started_child_and_remove_owned_temporary_files(self):
        for mode in ["target", "receive", "send", "measure", "compare", "overlap"]:
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory, redirect_stderr(io.StringIO()):
                root = Path(directory)
                runner = FakeRunner(fail=mode)
                with self.assertRaises(series.ExperimentError):
                    series.experiment(root, "cp-ABC123xy-c", "cp-ABC123xy-s", root, runner)
                self.assertFalse(any(child.active for child in runner.children))
                self.assertEqual(list(root.iterdir()), [])

    def test_overlap_uses_nanoseconds_and_actual_write_window(self):
        probe = latency("loaded")
        value = load()
        self.assertEqual(series.load_document(json.dumps(value), probe), value)
        for field, timestamp in [("first_write_at", "2026-10-29T18:00:01.000000002Z"),
                                 ("last_write_at", "2026-10-29T18:00:04Z")]:
            invalid = deepcopy(value)
            invalid[field] = timestamp
            with self.assertRaises(series.ExperimentError):
                series.load_document(json.dumps(invalid), probe)

    def test_invalid_load_reports_and_probe_parameters_are_rejected(self):
        for field, value in [("schema_version", True), ("written_bytes", 1), ("elapsed_ms", 7999),
                             ("average_bytes_per_second", 1048577), ("first_write_at", None)]:
            invalid = load()
            invalid[field] = value
            with self.subTest(field=field), self.assertRaises(series.ExperimentError):
                series.load_document(json.dumps(invalid), latency("loaded"))
        invalid = latency("idle")
        invalid["timeout_ms"] = 1000
        with self.assertRaises(series.ExperimentError):
            series.latency_document(json.dumps(invalid), "idle", 0)
        with self.assertRaises(series.ExperimentError):
            series.latency_document(json.dumps(latency("idle", failed=True)), "idle", 0)
        for raw in [b'{"x":1,"x":2}', b'{"x":NaN}', b'[]', b'not json']:
            with self.assertRaises(series.ExperimentError):
                series.document(raw)

    def test_foreign_namespaces_or_nonprivate_workspace_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for client, server in [("default", "default"), ("cp-ABC123xy-c", "cp-foreign1-s")]:
                with self.assertRaises(series.ExperimentError):
                    series.experiment(root, client, server, root, FakeRunner())
            root.chmod(0o755)
            with self.assertRaises(series.ExperimentError):
                series.experiment(root, "cp-ABC123xy-c", "cp-ABC123xy-s", root, FakeRunner())

    def test_real_child_ready_output_and_stop_without_network(self):
        runner = series.Runner(timeout=2)
        try:
            child = runner.start([sys.executable, "-c", 'import time; print("READY", flush=True); time.sleep(10)'])
            child.ready("READY", runner)
            pid = child.process.pid
        finally:
            runner.close()
        self.assertIsNotNone(child.process.returncode)
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)

    def test_real_child_output_bound_timeout_and_wrong_readiness(self):
        cases = [("import sys; sys.stdout.write('x'*300000); sys.stdout.flush()", "limit"),
                 ("import time; time.sleep(10)", "timeout"),
                 ("print('BAD', flush=True)", "ready")]
        for source, mode in cases:
            runner = series.Runner(timeout=2)
            try:
                child = runner.start([sys.executable, "-c", source])
                with self.assertRaises(series.ExperimentError):
                    if mode == "ready":
                        child.ready("READY", runner)
                    else:
                        child.finish(runner, 0.2)
            finally:
                runner.close()
            self.assertIsNotNone(child.process.returncode)

    def test_driver_signal_stops_its_real_child_and_emits_no_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "scripts").mkdir()
            driver = root / "scripts/lab-series.py"
            shutil.copyfile(SOURCE, driver)
            workspace = root / "workspace"
            workspace.mkdir(mode=0o700)
            tools = root / "tools"
            tools.mkdir()
            marker = root / "child-pid"
            ip = tools / "ip"
            ip.write_text(f"#!{sys.executable}\n" +
                          "import os, time\nfrom pathlib import Path\n" +
                          f"Path({str(marker)+'.tmp'!r}).write_text(str(os.getpid()))\n" +
                          f"Path({str(marker)+'.tmp'!r}).replace({str(marker)!r})\n" +
                          "print('READY 10.203.0.6:46001', flush=True)\ntime.sleep(10)\n")
            ip.chmod(0o755)
            environment = dict(os.environ, PATH=str(tools)+os.pathsep+os.environ["PATH"])
            process = subprocess.Popen([sys.executable, str(driver), "--client", "cp-ABC123xy-c", "--server", "cp-ABC123xy-s", "--workspace", str(workspace)],
                                       env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                deadline = time.monotonic() + 5
                while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue(marker.exists(), "fake target did not start")
                process.send_signal(signal.SIGTERM)
                stdout, stderr = process.communicate(timeout=3)
                self.assertEqual(process.returncode, 143, stderr)
                self.assertEqual(stdout, b"")
                self.assertEqual(list(workspace.iterdir()), [])
                with self.assertRaises(ProcessLookupError):
                    os.kill(int(marker.read_text()), 0)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate(timeout=3)
                if marker.exists():
                    pid = int(marker.read_text())
                    try:
                        command = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
                        if os.fsencode(ip) in command:
                            os.kill(pid, signal.SIGKILL)
                    except (FileNotFoundError, ProcessLookupError):
                        pass


if __name__ == "__main__":
    unittest.main()
