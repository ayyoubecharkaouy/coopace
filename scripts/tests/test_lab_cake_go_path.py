"""Pure ICMP readers: expected blocking must include an interpretable capture."""

import importlib.util
from pathlib import Path
import unittest


SOURCE = Path(__file__).resolve().parents[1] / "lab_cake_go_path.py"
spec = importlib.util.spec_from_file_location("path_readers", SOURCE)
model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)

HEADER = b"PING 10.203.0.6 (10.203.0.6) 56(84) bytes of data.\n"
HEADING = b"\n--- 10.203.0.6 ping statistics ---\n"
NEGATIVE = HEADER + HEADING + b"1 packets transmitted, 0 received, 100% packet loss, time 0ms\n\n"
POSITIVE = HEADER + (
    b"64 bytes from 10.203.0.6: icmp_seq=1 ttl=63 time=0.051 ms\n"
    b"64 bytes from 10.203.0.6: icmp_seq=2 ttl=63 time=0.044 ms\n"
    b"64 bytes from 10.203.0.6: icmp_seq=3 ttl=63 time=0.049 ms\n"
) + HEADING + b"3 packets transmitted, 3 received, 0% packet loss, time 2075ms\n" + (
    b"rtt min/avg/max/mdev = 0.044/0.048/0.051/0.003 ms\n"
)


class PathReadersTests(unittest.TestCase):
    def test_blocked_probe_requires_one_send_and_zero_echo_replies(self):
        result = model.validate_probe(NEGATIVE, 1, forwarding=0)
        self.assertEqual((result["transmitted"], result["received"]), (1, 0))
        self.assertEqual(result["reported_packet_loss_percent"], 100)
        with_error = NEGATIVE.replace(b"0 received, ", b"0 received, +1 errors, ")
        self.assertEqual(model.validate_probe(with_error, 1, forwarding=0)["reported_errors"], 1)

    def test_positive_capture_keeps_reported_counts_and_time(self):
        result = model.validate_probe(POSITIVE, 0, forwarding=1)
        self.assertEqual(result, {"target": "10.203.0.6", "forwarding": 1, "exit_code": 0,
                                  "transmitted": 3, "received": 3, "reported_errors": 0,
                                  "reported_packet_loss_percent": 0, "reported_elapsed_ms": 2075})
        # This reader issues no native-validation certificate or latency claim.
        self.assertNotIn("state", result)
        self.assertNotIn("rtt", result)

    def test_exit_status_alone_and_technical_errors_never_prove_blocking(self):
        for data, code in ((b"", 1), (b"ping: socket: Operation not permitted\n", 1),
                           (NEGATIVE, 2), (NEGATIVE, -9), (NEGATIVE, 0), (NEGATIVE, True),
                           (NEGATIVE, "1"), (NEGATIVE, None)):
            with self.subTest(code=code), self.assertRaises(model.Error):
                model.validate_probe(data, code, forwarding=0)

    def test_any_negative_reply_or_wrong_count_is_rejected(self):
        for data in (NEGATIVE.replace(b"0 received", b"1 received"),
                     NEGATIVE.replace(b"1 packets transmitted", b"3 packets transmitted"),
                     NEGATIVE.replace(b"100%", b"0%"),
                     NEGATIVE.replace(b"0 received, ", b"0 received, +2 errors, ")):
            with self.subTest(data=data), self.assertRaises(model.Error):
                model.validate_probe(data, 1, forwarding=0)

    def test_partial_positive_duplicate_or_error_is_rejected(self):
        for data, code in ((POSITIVE, 1), (POSITIVE.replace(b"3 received", b"2 received"), 0),
                           (POSITIVE.replace(b"3 received, ", b"3 received, +1 duplicates, "), 0),
                           (POSITIVE.replace(b"3 received, ", b"3 received, +1 errors, "), 0),
                           (POSITIVE.replace(b"0% packet loss", b"100% packet loss"), 0)):
            with self.subTest(code=code), self.assertRaises(model.Error):
                model.validate_probe(data, code, forwarding=1)

    def test_wrong_target_ambiguous_summary_and_localized_output_are_rejected(self):
        summary = NEGATIVE.splitlines()[-2] + b"\n"
        for data in (NEGATIVE.replace(b"10.203.0.6", b"127.0.0.1"),
                     NEGATIVE + summary, NEGATIVE + HEADING,
                     NEGATIVE.replace(b"1 packets transmitted", b"1 paquets transmis"),
                     NEGATIVE.replace(b"100%", b"nan%"),
                     NEGATIVE.replace(b"100%", b"1000%"),
                     NEGATIVE.replace(b"time 0ms", b"time -1ms"),
                     NEGATIVE.replace(b"100%", b"99.9%")):
            with self.subTest(data=data), self.assertRaises(model.Error):
                model.validate_probe(data, 1, forwarding=0)

    def test_capture_types_bounds_encoding_and_states_are_checked(self):
        for data in (None, "text", bytearray(NEGATIVE), NEGATIVE + b"x" * model.OUTPUT_LIMIT,
                     NEGATIVE.rstrip(b"\n"), NEGATIVE + b"\xff\n", NEGATIVE + b"\0\n", NEGATIVE + b"\r\n"):
            with self.subTest(data_type=type(data)), self.assertRaises(model.Error):
                model.validate_probe(data, 1, forwarding=0)
        for state in (False, True, -1, 2, "0", None):
            with self.subTest(state=state), self.assertRaises(model.Error):
                model.validate_probe(NEGATIVE, 1, forwarding=state)

    def test_forwarding_readback_is_exact_and_not_inferred_from_write(self):
        for state in (0, 1):
            self.assertEqual(model.validate_forwarding(f"{state}\n".encode(), state), state)
            for data in (b"", b"0\n1\n", b"00\n", b"net.ipv4.ip_forward = 0\n",
                         f"{1-state}\n".encode(), f"{state}".encode()):
                with self.subTest(state=state, data=data), self.assertRaises(model.Error):
                    model.validate_forwarding(data, state)
        with self.assertRaises(model.Error):
            model.validate_forwarding(b"1\n", True)


if __name__ == "__main__":
    unittest.main()
