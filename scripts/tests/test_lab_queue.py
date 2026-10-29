"""TBF parsing and bounded subprocess checks; no real network resources."""

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time
import unittest
from unittest.mock import Mock


SOURCE = Path(__file__).resolve().parents[1] / "lab_queue.py"
SPEC = importlib.util.spec_from_file_location("lab_queue", SOURCE)
queue = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(queue)


def tbf():
    # Numeric options with tc -j -r (no -d); dev may be omitted by a dev filter.
    return [{"kind": "tbf", "handle": "10:", "root": True, "refcnt": 2,
             "options": {"rate": 500000, "burst": 65536, "burst_raw": "0x200000",
                         "lat": 131072, "limit": 131072}}]


def raw(value):
    return json.dumps(value).encode()


def statistics_row():
    value = tbf()
    value[0].update({"bytes": 12345, "packets": 15, "drops": 2, "overlimits": 100,
                     "requeues": 3, "backlog": 4096, "qlen": 4})
    return value


class Owner:
    def __init__(self, timeout=2):
        self.deadline = time.monotonic() + timeout
        self.command_child = None

    def check(self):
        if time.monotonic() >= self.deadline:
            raise queue.QueueError("Échéance du propriétaire dépassée")


class QueueParsingTests(unittest.TestCase):
    def test_statistics_keep_counters_and_instantaneous_gauges_distinct(self):
        value = queue.statistics(raw(statistics_row()))
        self.assertEqual(value, {"counters": {"bytes": 12345, "packets": 15, "drops": 2,
                                               "overlimits": 100, "requeues": 3},
                                 "backlog_bytes": 4096, "queued_packets": 4})
        later = deepcopy(statistics_row())
        later[0]["bytes"] += 10
        later[0]["backlog"] = 0
        delta = queue.statistics_delta(value, queue.statistics(raw(later)))
        self.assertTrue(delta["available"])
        self.assertEqual(delta["counters"]["bytes"], 10)
        self.assertNotIn("backlog_bytes", delta["counters"])

    def test_missing_negative_fractional_or_oversized_statistics_are_rejected(self):
        for field in (*queue.COUNTERS, "backlog", "qlen"):
            for invalid in (None, False, -1, 1.5, 2**64):
                with self.subTest(field=field, invalid=invalid):
                    value = statistics_row()
                    value[0][field] = invalid
                    with self.assertRaises(queue.QueueError):
                        queue.statistics(raw(value))
            value = statistics_row()
            del value[0][field]
            with self.assertRaises(queue.QueueError):
                queue.statistics(raw(value))

    def test_counter_decrease_is_unavailable_without_wrapping_or_zeroing(self):
        initial = queue.statistics(raw(statistics_row()))
        for field in queue.COUNTERS:
            with self.subTest(field=field):
                later = deepcopy(initial)
                later["counters"][field] -= 1
                result = queue.statistics_delta(initial, later)
                self.assertEqual(result, {"available": False, "reason": "counter_decreased", "counters": None})
    def test_noqueue_only_on_expected_root(self):
        valid = [{"kind": "noqueue", "handle": "0:", "root": True}]
        self.assertEqual(queue.initial_qdisc(raw(valid)), valid)
        self.assertEqual(queue.initial_qdisc(b'[]'), [])
        for value in (valid * 2, tbf(), [{**valid[0], "root": False}],
                      [{**valid[0], "dev": "eth0"}], [{**valid[0], "parent": "1:1"}]):
            with self.subTest(value=value), self.assertRaises(queue.QueueError):
                queue.initial_qdisc(raw(value))

    def test_effective_tbf_parameters_and_single_byte_quantization(self):
        valid = tbf()
        self.assertEqual(queue.configured_qdisc(raw(valid)), valid)
        for burst in (65535, 65536.5, 65537):
            value = deepcopy(valid)
            value[0]["options"]["burst"] = burst
            self.assertEqual(queue.configured_qdisc(raw(value))[0]["options"]["burst"], burst)
        value = deepcopy(valid)
        value[0]["dev"] = "wan"
        self.assertEqual(queue.configured_qdisc(raw(value)), value)

    def test_wrong_numeric_options_and_extra_queue_are_rejected(self):
        cases = []
        for field, value in (("rate", True), ("rate", 4000000), ("rate", "500000"),
                             ("limit", 65536), ("limit", None), ("burst", "64Kb/8"),
                             ("burst", False), ("burst", 65534), ("burst", 10**400),
                             ("burst", float('inf')), ("overhead", 20), ("mpu", False),
                             ("linklayer", "atm")):
            item = tbf()
            item[0]["options"][field] = value
            cases.append(item)
        for field, value in (("handle", "11:"), ("kind", "cake"), ("root", 1),
                             ("options", None), ("dev", "eth0"), ("parent", "1:1")):
            item = tbf()
            item[0][field] = value
            cases.append(item)
        cases.append(tbf() * 2)
        for value in cases:
            with self.subTest(value=value), self.assertRaises(queue.QueueError):
                queue.configured_qdisc(raw(value))

    def test_malformed_ambiguous_and_excessive_json(self):
        cases = (b'{}', b'[null]', b'[{},3]', b'[{"kind":"a","kind":"b"}]',
                 b'[NaN]', b'[{"unknown":1e999}]', b'[] extra', b'["\xff"]', b' ' * (queue.LIMIT + 1))
        for value in cases:
            with self.subTest(value=value[:80]), self.assertRaises(queue.QueueError):
                queue.document(value)

    def test_changed_namespace_identity_blocks_every_operation(self):
        namespaces = Mock(ip="fake-ip")
        namespaces.identity.return_value = (1, 3)
        owner = Mock(owned=[("cg-abc123xy-g", (1, 2))])
        check = queue.QueueCheck(namespaces, "fake-tc")
        check.owner = owner
        with self.assertRaises(queue.QueueError):
            check.execute(["fake-ip", "-n", "cg-abc123xy-g", "link", "show"])
        namespaces.execute.assert_not_called()


@unittest.skipUnless(sys.platform == "linux", "Linux lab subprocesses")
class QueueCommandTests(unittest.TestCase):
    def test_stdout_is_fully_drained_and_child_reaped(self):
        owner = Owner()
        value = queue.run_command([sys.executable, "-I", "-c",
                                   'import sys; sys.stdout.buffer.write(b"x" * 12345)'], owner)
        self.assertEqual(value, b"x" * 12345)
        self.assertIsNone(owner.command_child)

    def test_output_failure_and_timeout_reap_child(self):
        cases = [('import sys; sys.stdout.write("x" * 1000000)', 2),
                 ('raise SystemExit(7)', 2), ('import time; time.sleep(30)', .1)]
        for code, timeout in cases:
            with self.subTest(code=code):
                owner = Owner(timeout)
                with self.assertRaises(queue.QueueError):
                    queue.run_command([sys.executable, "-I", "-c", code], owner)
                self.assertIsNone(owner.command_child)

    def test_cancellation_during_command_reaps_child(self):
        owner = Owner()
        calls = 0
        def cancel():
            nonlocal calls
            calls += 1
            if calls > 2:
                raise queue.QueueError("Interruption simulée")
        owner.check = cancel
        with self.assertRaisesRegex(queue.QueueError, "Interruption"):
            queue.run_command([sys.executable, "-I", "-c", 'import time; time.sleep(30)'], owner)
        self.assertIsNone(owner.command_child)


if __name__ == "__main__":
    unittest.main()
