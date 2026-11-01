"""Campaign wire behavior and refusal cases; no children, sockets or clocks."""

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import unittest

import test_lab_active as fixtures

SOURCE = fixtures.SOURCE.with_name("lab_cake_go_campaign_protocol.py")
spec = importlib.util.spec_from_file_location("campaign_protocol_tests", SOURCE)
protocol = importlib.util.module_from_spec(spec)
spec.loader.exec_module(protocol)
SESSION = "traffic1"
# Fixed by the v1 contract, independently of the implementation's phase table.
PHASES = ((1, "idle"), (1, "loaded"), (2, "loaded"), (2, "idle"), (3, "idle"), (3, "loaded"))


def result(condition, failed=False):
    send, receive, latency = deepcopy(fixtures.documents())
    latency["declared_condition"] = condition
    if failed:
        latency.update(successful=0, failed=10)
        for attempt in latency["attempts"]:
            attempt.update(connect_ms=None, failure="timeout")
    code = 1 if failed else 0
    if condition == "idle":
        return {"latency": latency, "measurement_exit_code": code}
    return protocol.traffic.active.flow_documents(*(json.dumps(v).encode() for v in (send, receive, latency)), code)


def event(name, pair=1, condition="idle", **payload):
    return protocol.event_frame(SESSION, name, pair=pair, condition=condition, **payload)


def transcript(failed=False):
    frames = []
    for pair, condition in PHASES:
        helpers = [100] if condition == "idle" else [100, 101, 102]
        frames.extend([
            ("event", event("begin", pair, condition)),
            ("control", protocol.control_frame(SESSION, pair, condition, "start")),
            ("event", event("ready", pair, condition, helper_pids=helpers)),
            ("control", protocol.control_frame(SESSION, pair, condition, "continue")),
            ("event", event("end", pair, condition, result=result(condition, failed))),
            ("control", protocol.control_frame(SESSION, pair, condition, "advance")),
        ])
    frames.append(("event", protocol.event_frame(SESSION, "complete")))
    return frames


class CampaignProtocolTests(unittest.TestCase):
    def test_six_phases_roundtrip_and_stream_completion_require_both_eofs(self):
        dialogue = protocol.Dialogue(SESSION)
        measured, volumes = 0, []
        for direction, raw in transcript():
            value = getattr(dialogue, direction)(raw)
            if value.get("event") == "end":
                data = value["result"]
                measured += data["latency"]["requested_attempts"]
                if "receive" in data:
                    volumes.append(data["receive"]["received_bytes"])
        self.assertEqual(dialogue.index, 6)
        self.assertEqual(measured, 60)
        self.assertEqual(volumes, [8388608] * 3)
        self.assertFalse(dialogue.complete)
        dialogue.finish_events()
        self.assertFalse(dialogue.complete)
        dialogue.finish_controls()
        self.assertTrue(dialogue.complete)
        dialogue.finish_controls()  # Repeated EOF observation is harmless.
        dialogue.finish_events()

    def test_failed_measurements_are_preserved_without_qualification_claim(self):
        dialogue = protocol.Dialogue(SESSION)
        for direction, raw in transcript(failed=True):
            value = getattr(dialogue, direction)(raw)
            if value.get("event") == "end":
                self.assertEqual(value["result"]["measurement_exit_code"], 1)
                self.assertEqual(value["result"]["latency"]["failed"], 10)
                self.assertTrue(all(a["connect_ms"] is None for a in value["result"]["latency"]["attempts"]))
                self.assertNotIn("technical_valid", value)
        dialogue.finish_controls()
        dialogue.finish_events()
        self.assertTrue(dialogue.complete)  # Wire completion is not network success.

    def test_partial_success_uses_real_exit_code_and_keeps_each_attempt(self):
        data = result("idle")
        data["latency"].update(successful=7, failed=3)
        for attempt in data["latency"]["attempts"][:3]:
            attempt.update(connect_ms=None, failure="connection_failed")
        value = protocol.parse_event(event("end", result=data), SESSION)
        self.assertEqual(value["result"]["measurement_exit_code"], 0)
        self.assertEqual(value["result"]["latency"]["failed"], 3)

    def test_schema_direction_session_phase_and_extra_fields_are_strict(self):
        original = json.loads(event("begin"))
        changes = (("schema_version", True), ("schema_version", 1.0), ("schema_version", 2),
                   ("kind", protocol.CONTROL_KIND), ("session_id", "other123"), ("pair", True),
                   ("pair", 1.0), ("pair", 0), ("pair", 4), ("condition", "other"),
                   ("event", "unknown"), ("unexpected", 1))
        for key, value in changes:
            data = {**original, key: value}
            with self.subTest(key=key, value=value), self.assertRaises(protocol.Error):
                protocol.parse_event(json.dumps(data).encode() + b"\n", SESSION)
        for session in (None, 12345678, "short", "UPPER123"):
            with self.subTest(session=session), self.assertRaises(protocol.Error):
                protocol.Dialogue(session)
        with self.assertRaises(protocol.Error):
            protocol.parse_control(event("begin"), SESSION)
        with self.assertRaises(protocol.Error):
            protocol.parse_event(protocol.control_frame(SESSION, 1, "idle", "start"), SESSION)
        with self.assertRaises(protocol.Error):
            protocol.event_frame(SESSION, "complete", pair=1, condition="idle")

    def test_helper_roles_require_one_or_three_positive_distinct_integer_pids(self):
        for condition, pids in (("idle", []), ("idle", [100, 101]), ("idle", [True]), ("idle", [0]),
                                ("loaded", [1]), ("loaded", [1, 2, 2]), ("loaded", [1, 2, -1]),
                                ("loaded", [1, 2, 3.0]), ("loaded", [1, 2, {}])):
            with self.subTest(condition=condition, pids=pids), self.assertRaises(protocol.Error):
                event("ready", condition=condition, helper_pids=pids)

    def test_result_codes_conditions_and_flow_flags_are_validated(self):
        for condition, change in (
            ("idle", lambda r: r.update(measurement_exit_code=False)),
            ("idle", lambda r: r.update(extra=1)),
            ("idle", lambda r: r["latency"].update(declared_condition="loaded")),
            ("idle", lambda r: r.update(measurement_exit_code=1)),
            ("loaded", lambda r: r["receive"].update(received_bytes=1)),
            ("loaded", lambda r: r.update(has_successful_probe=False)),
            ("loaded", lambda r: r.update(probe_window_inside_application_writes=False)),
            ("loaded", lambda r: r.update(extra=1)),
        ):
            data = result(condition)
            change(data)
            with self.subTest(condition=condition, change=change), self.assertRaises(protocol.Error):
                event("end", condition=condition, result=data)

    def test_duplicate_nested_keys_nonfinite_numbers_and_bad_encodings_are_refused(self):
        begin = event("begin")
        idle = event("end", result=result("idle"))
        for raw in (begin.replace(b'"pair":1', b'"pair":1,"pair":1'),
                    idle.replace(b'"successful":10', b'"successful":10,"successful":10'),
                    idle.replace(b'"connect_ms":1', b'"connect_ms":NaN', 1),
                    idle.replace(b'"connect_ms":1', b'"connect_ms":1e400', 1),
                    idle.replace(b'"connect_ms":1', b'"connect_ms":Infinity', 1),
                    begin[:-1] + b"\r\n", begin + begin, begin[:-1],
                    b"\xff\n", begin.decode().encode("utf-16") + b"\n", b"[]\n", b"\n"):
            with self.subTest(raw=raw[:80]), self.assertRaises(protocol.Error):
                protocol.parse_event(raw, SESSION)

    def test_per_line_limits_include_lf_and_depend_on_event_type(self):
        for raw, limit, parse in (
            (event("begin"), protocol.FRAME_LIMIT, protocol.parse_event),
            (protocol.control_frame(SESSION, 1, "idle", "start"), protocol.FRAME_LIMIT, protocol.parse_control),
            (event("end", result=result("idle")), protocol.END_LIMIT, protocol.parse_event),
        ):
            exact = raw[:-1] + b" " * (limit - len(raw)) + b"\n"
            self.assertEqual(len(exact), limit)
            parse(exact, SESSION)
            with self.assertRaises(protocol.Error):
                parse(exact[:-1] + b" \n", SESSION)

    def test_fragmented_utf8_and_coalesced_messages_preserve_boundaries(self):
        data = result("idle")
        data["latency"]["coopace_version"] = "développement"
        raw = event("end", result=data)
        reader, decoded = protocol.LineReader(SESSION, "events"), []
        for byte in raw:
            decoded += reader.feed(bytes([byte]))
        reader.finish()
        self.assertEqual(decoded[0]["result"]["latency"]["coopace_version"], "développement")
        for direction in ("events", "controls"):
            reader = protocol.LineReader(SESSION, direction)
            expected = [r for d, r in transcript() if d == direction[:-1]]
            self.assertEqual(len(reader.feed(b"".join(expected))), 19 if direction == "events" else 18)
            reader.finish()

    def test_framing_eof_is_separate_from_dialogue_eof_and_cannot_repair_failure(self):
        reader = protocol.LineReader(SESSION, "events")
        self.assertEqual(reader.feed(event("begin")[:-1]), [])
        with self.assertRaises(protocol.Error):
            reader.finish()
        with self.assertRaises(protocol.Error):
            reader.feed(b"\n")
        reader = protocol.LineReader(SESSION, "events")
        reader.finish()  # An empty byte stream has no partial line.
        with self.assertRaises(protocol.Error):
            protocol.Dialogue(SESSION).finish_events()
        with self.assertRaises(protocol.Error):
            reader.feed(event("begin"))

    def test_pending_line_total_bytes_and_message_counts_are_bounded(self):
        reader = protocol.LineReader(SESSION, "events")
        with self.assertRaises(protocol.Error):
            reader.feed(b"x" * (protocol.END_LIMIT + 1))
        self.assertEqual(len(reader.pending), 0)
        raw = event("end", result=result("idle"))
        exact = raw[:-1] + b" " * (protocol.END_LIMIT - len(raw)) + b"\n"
        reader = protocol.LineReader(SESSION, "events")
        for _ in range(8):
            reader.feed(exact)
        self.assertEqual(reader.total, protocol.EVENT_BUDGET)
        with self.assertRaises(protocol.Error):
            reader.feed(b"x")
        for direction, raw, maximum in (("events", event("begin"), 19),
                                        ("controls", protocol.control_frame(SESSION, 1, "idle", "start"), 18)):
            reader = protocol.LineReader(SESSION, direction)
            for _ in range(maximum):
                reader.feed(raw)
            with self.assertRaises(protocol.Error):
                reader.feed(raw)
        raw = protocol.control_frame(SESSION, 1, "idle", "start")
        exact = raw[:-1] + b" " * (protocol.FRAME_LIMIT - len(raw)) + b"\n"
        reader = protocol.LineReader(SESSION, "controls")
        for _ in range(18):
            reader.feed(exact)
        self.assertEqual(reader.total, protocol.CONTROL_BUDGET)
        with self.assertRaises(protocol.Error):
            reader.feed(b"x")

    def test_every_replayed_boundary_is_terminal_and_cannot_be_retried(self):
        frames = transcript()
        for position in range(len(frames) + 1):
            dialogue = protocol.Dialogue(SESSION)
            for direction, raw in frames[:position]:
                getattr(dialogue, direction)(raw)
            direction, raw = frames[position - 1] if position else frames[2]
            with self.subTest(position=position), self.assertRaises(protocol.Error):
                getattr(dialogue, direction)(raw)
            self.assertEqual(dialogue.state, "failed")
            self.assertFalse(dialogue.complete)
            if position < len(frames):
                direction, raw = frames[position]
                with self.assertRaises(protocol.Error):
                    getattr(dialogue, direction)(raw)

    def test_wrong_phase_or_session_control_never_opens_current_boundary(self):
        for wrong in (protocol.control_frame(SESSION, 1, "loaded", "start"),
                      protocol.control_frame(SESSION, 2, "idle", "start"),
                      protocol.control_frame("other123", 1, "idle", "start"),
                      protocol.control_frame(SESSION, 1, "idle", "continue")):
            dialogue = protocol.Dialogue(SESSION)
            dialogue.event(event("begin"))
            with self.assertRaises(protocol.Error):
                dialogue.control(wrong)
            self.assertEqual(dialogue.index, 0)

    def test_eofs_at_every_boundary_and_extra_messages_after_completion(self):
        frames = transcript()
        for position in range(len(frames)):
            for control in (False, True):
                dialogue = protocol.Dialogue(SESSION)
                for direction, raw in frames[:position]:
                    getattr(dialogue, direction)(raw)
                finish = dialogue.finish_controls if control else dialogue.finish_events
                if control and position == len(frames) - 1:
                    finish()  # Last advance received, complete still allowed.
                    dialogue.event(frames[-1][1])
                    dialogue.finish_events()
                    self.assertTrue(dialogue.complete)
                else:
                    with self.subTest(position=position, control=control), self.assertRaises(protocol.Error):
                        finish()
        dialogue = protocol.Dialogue(SESSION)
        for direction, raw in frames:
            getattr(dialogue, direction)(raw)
        dialogue.finish_events()
        dialogue.finish_controls()
        with self.assertRaises(protocol.Error):
            dialogue.event(frames[-1][1])
        self.assertFalse(dialogue.complete)


if __name__ == "__main__":
    unittest.main()
