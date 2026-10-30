"""Frozen comparative boundaries and validation of original campaign evidence."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from test_lab_active import documents
from test_lab_cake import fixture as cake_fixture


SOURCE = Path(__file__).resolve().parents[1] / "lab_comparison.py"
spec = importlib.util.spec_from_file_location("comparison", SOURCE)
model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)


def summary(block, engine, token):
    phases = []
    for pair, condition in model.campaign.PHASES:
        row = {"pair": pair, "condition": condition, "failed": 0,
               "connect_ms": {"min": 1, "p50": 1 if condition == "idle" else 21 if engine == "tbf" else 1.5,
                              "p95": 25, "p99": 25, "max": 25}}
        if condition == "loaded":
            row.update(received_bytes_per_second=500000, bytes_progress=True)
        phases.append(row)
    return {"block": block, "engine": engine, "namespaces": [f"cg-{token}-{role}" for role in ("c", "g", "s")],
            "workspace": f"/tmp/coopace-guard.{token}", "phases": phases,
            "measurement_provenance": ["linux", "amd64", "go1.27.3", "test"],
            "reference_qualified": engine == "tbf"}


def arms():
    return [summary(block, engine, f"test{i:04d}") for i, (block, engine) in enumerate(model.ORDER)]


def set_p50(values, engine, condition, value, *, block=None, pair=None):
    for arm in values:
        if arm["engine"] != engine or block is not None and arm["block"] != block:
            continue
        for phase in arm["phases"]:
            if phase["condition"] == condition and (pair is None or phase["pair"] == pair):
                phase["connect_ms"] = None if value is None else {"p50": value}


def report_fixture(engine, folder, token="test0001", *, loaded_p50=None):
    """Generate bounded, internally consistent synthetic reports without networking."""
    campaign = model.campaign
    origin = datetime(2026, 10, 30, tzinfo=timezone.utc)
    def stamp(seconds):
        return (origin + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")
    count = 0
    def reading(seconds, phase=None, backlog=0):
        nonlocal count
        count += 1
        row = (cake_fixture()[0] if engine == "cake" else
               {"kind": "tbf", "root": True, "handle": "10:", "options": {"rate": 500000, "burst": 65536, "limit": 131072}})
        row.update({key: count * 10000 for key in campaign.queue.COUNTERS})
        row.update(backlog=backlog, qlen=1 if backlog else 0)
        raw = json.dumps([row]).encode()
        value = {"collected_at": stamp(seconds), "elapsed_since_start_ms": seconds * 1000,
                 "read_duration_ms": 1, "qdiscs": [row],
                 "statistics": model.cake.statistics(raw, model.cake.PROFILE) if engine == "cake" else campaign.queue.statistics(raw)}
        if engine == "cake": value["configuration"] = model.cake.configured_qdisc(raw, model.cake.PROFILE)
        if phase: value["phase"] = phase
        return value
    topology = {"kind": engine, "namespace": f"cg-{token}-g", "interface": "wan", "link_state": "UP",
                "before": {"qdiscs": []}, "after_add": reading(0), "after_activation": reading(1), "after_passage": reading(2)}
    if engine == "cake":
        topology.update(arguments=list(model.cake.ARGUMENTS), producer={"version_output": "tc utility, iproute2-6.1.0\n"})
    phases = []
    for n, (pair, condition) in enumerate(campaign.PHASES):
        base = 10 + n * 25
        send, receive, latency = deepcopy(documents())
        for value in (send, receive, latency):
            for key in value:
                if key.endswith("_at"):
                    seconds = (datetime.fromisoformat(value[key].replace("Z", "+00:00")) - origin).total_seconds()
                    value[key] = stamp(base + seconds)
            value.update(os="linux", architecture="amd64", go_version="go1.27.3")
        duration = (1 if condition == "idle" else
                    loaded_p50 if loaded_p50 is not None else 21 if engine == "tbf" else 1.5)
        latency.update(coopace_version="test", declared_condition=condition,
                       connect_ms={key: duration for key in ("min", "p50", "p95", "p99", "max")})
        latency["attempts"] = [{"started_at": stamp(base + 2 + i * .18), "connect_ms": duration} for i in range(10)]
        flow = {"latency": latency, "measurement_exit_code": 0}
        if condition == "loaded":
            flow = campaign.active.flow_documents(*(json.dumps(v).encode() for v in (send, receive, latency)), 0)
        samples = [reading(base, "before")]
        samples += [reading(base + x, "running", 100 if engine == "tbf" and condition == "loaded" else 0)
                    for x in (2, 2.3, 2.6, 3, 3.4, 3.8)]
        end = 20 if condition == "loaded" else 4
        samples += [reading(base + end + .1, "after"), reading(base + end + .4, "drain"), reading(base + end + .95, "drain")]
        phase = {"pair": pair, "condition": condition, "result": flow, "samples": samples,
                 "statistics_delta": campaign.delta(samples)}
        if n % 2: phase["comparison"] = "strict comparison fixture\n"
        phases.append(phase)
        (folder / f"phase-{pair}-{condition}.json").write_text(json.dumps(latency))
    topology["after_driver_exit"] = reading(157)
    topology["statistics_delta"] = campaign.queue.statistics_delta(topology["after_add"]["statistics"], topology["after_driver_exit"]["statistics"])
    samples = [s for p in phases for s in p["samples"]]
    total = campaign.delta([topology["after_passage"], *samples, topology["after_driver_exit"]])
    decision = (campaign.assess(phases, total, False) if engine == "tbf" else model.cake_model.assess(phases, total, False))
    result = {"schema_version": 1, "kind": "lab_bottleneck_campaign" if engine == "tbf" else "lab_cake_campaign",
              "mode": "run", "cleanup_verified": True, "driver_exit_code": 0, "reaped_descendants": 0,
              "interrupted_phase": None, "traffic_coverage": "synthetic_ipv4_only",
              "workspace": f"/tmp/coopace-guard.{token}", "namespaces": [f"cg-{token}-{r}" for r in ("c", "g", "s")],
              "evidence": str(folder / "progress.jsonl"), "queue": topology, "phases": phases,
              "statistics_delta": total, "decision": decision,
              "passage": {"without_forwarding_exit_code": 1, "with_forwarding_exit_code": 0,
                          "without_forwarding_stdout": "3 packets transmitted, 0 received\n",
                          "with_forwarding_stdout": "3 packets transmitted, 3 received\n"}}
    entries = [{"event": "owned", "namespaces": result["namespaces"], "workspace": result["workspace"]},
               {"event": "passage", **result["passage"]}]
    if engine == "cake":
        all_readings = [topology[k] for k in ("before", "after_add", "after_activation", "after_passage")]
        all_readings += [{k: v for k, v in s.items() if k != "phase"} for s in samples]
        all_readings.append(topology["after_driver_exit"])
        entries += [{"event": "qdisc", "reading": r} for r in all_readings]
    entries += [{"event": "statistics", "reading": s} for s in samples]
    entries += [{"event": "comparison", "pair": pair, "text": "strict comparison fixture\n"} for pair in (1, 2, 3)]
    entries.append({"event": "cleaned", "decision": decision})
    (folder / "progress.jsonl").write_text("".join(json.dumps(e) + "\n" for e in entries))
    return result


class DecisionTests(unittest.TestCase):
    def test_nine_pairs_three_blocks_and_signed_penalties(self):
        values = arms()
        set_p50(values, "cake", "loaded", .5)
        decision = model.assess(values)
        self.assertEqual(decision["decision"], "static_cake_improvement_v1")
        self.assertEqual(len(decision["pairs"]), 9)
        self.assertTrue(all(p["cake_penalty_ms"] == -.5 for p in decision["pairs"]))
        self.assertFalse(decision["coopace_gain_assessed"])

    def test_exact_latency_thresholds(self):
        for tbf, cake, expected in ((21, 11, True), (21, 11.000001, False),
                                    (11, 1, True), (10.999999, 1, False)):
            with self.subTest(tbf=tbf, cake=cake):
                values = arms()
                set_p50(values, "tbf", "loaded", tbf)
                set_p50(values, "cake", "loaded", cake)
                self.assertEqual(model.assess(values)["decision"] == "static_cake_improvement_v1", expected)

    def test_two_pairs_required_in_every_block(self):
        values = arms()
        set_p50(values, "cake", "loaded", 20, block=3, pair=1)
        self.assertEqual(model.assess(values)["decision"], "static_cake_improvement_v1")
        set_p50(values, "cake", "loaded", 20, block=3, pair=2)
        result = model.assess(values)
        self.assertEqual(result["decision"], "improvement_not_demonstrated")
        self.assertEqual(result["blocks"][2]["improved_pairs"], 1)

    def test_rate_ratio_boundary_and_guard_priority(self):
        for rate, expected in ((450000, "static_cake_improvement_v1"), (449999.999999, "guard_failed")):
            values = arms()
            for arm in values:
                if arm["engine"] == "cake":
                    for phase in arm["phases"]:
                        if phase["condition"] == "loaded": phase["received_bytes_per_second"] = rate
            result = model.assess(values)
            self.assertEqual(result["decision"], expected)
            self.assertTrue(all(p["latency_improved"] for p in result["pairs"]))

    def test_rate_range_progress_and_reference_precede_guards(self):
        for rate, load in ((350000, True), (525000, True), (349999, False), (525001, False)):
            values = arms()
            for arm in values:
                for phase in arm["phases"]:
                    if phase["condition"] == "loaded": phase["received_bytes_per_second"] = rate
            self.assertEqual(model.assess(values)["load_scenario_qualified"], load)
        values = arms()
        values[1]["phases"][1]["bytes_progress"] = False
        self.assertEqual(model.assess(values)["decision"], "load_scenario_unqualified")
        values[0]["reference_qualified"] = False
        self.assertEqual(model.assess(values)["decision"], "reference_unqualified")

    def test_idle_boundary_missing_values_and_connection_regressions(self):
        for p50, expected in ((3, "static_cake_improvement_v1"), (3.000001, "guard_failed"), (None, "guard_failed")):
            values = arms()
            set_p50(values, "cake", "idle", p50, block=1, pair=1)
            result = model.assess(values)
            self.assertEqual(result["decision"], expected)
            if p50 is None: self.assertEqual(result["guard_failures"][0]["status"], "unavailable")
        values = arms()
        values[1]["phases"][0]["failed"] = 1
        self.assertEqual(model.assess(values)["guard_failures"][0]["guard"], "failed_connections")

    def test_missing_percentiles_stay_in_denominator(self):
        values = arms()
        set_p50(values, "cake", "loaded", None, block=3, pair=1)
        set_p50(values, "tbf", "loaded", None, block=3, pair=1)
        result = model.assess(values)
        self.assertEqual(result["decision"], "static_cake_improvement_v1")
        self.assertIsNone(result["pairs"][6]["tbf_penalty_ms"])
        self.assertEqual(result["blocks"][2]["improved_pairs"], 2)
        set_p50(values, "cake", "loaded", None, block=3, pair=2)
        self.assertEqual(model.assess(values)["decision"], "improvement_not_demonstrated")

    def test_incomplete_reordered_reused_and_incompatible_inputs_are_rejected(self):
        for scenario in ("incomplete", "order", "reuse", "provenance"):
            values = arms()
            if scenario == "incomplete": values.pop()
            elif scenario == "order": values.reverse()
            elif scenario == "reuse": values[1]["namespaces"] = values[0]["namespaces"]
            else: values[1]["measurement_provenance"][2] = "different"
            with self.subTest(scenario=scenario), self.assertRaises(model.Error): model.assess(values)


class EvidenceTests(unittest.TestCase):
    def test_complete_original_reports_are_revalidated_for_both_engines(self):
        for engine in ("tbf", "cake"):
            with self.subTest(engine=engine), tempfile.TemporaryDirectory() as directory:
                folder = Path(directory)
                report = report_fixture(engine, folder)
                calls = []
                def compare(binaries, path, pair):
                    calls.append((path, pair))
                    return "strict comparison fixture\n"
                result = model.summarize(report, engine, folder, folder, compare)
                self.assertEqual(len(result["phases"]), 6)
                self.assertEqual(calls, [(folder, i) for i in (1, 2, 3)])
                self.assertEqual(result["reference_qualified"], True if engine == "tbf" else None)

    def test_configuration_counter_reset_proof_and_receipt_tampering_are_rejected(self):
        for scenario in ("config", "counter", "cleanup", "receipt", "latency_file", "evidence", "compare"):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as directory:
                folder = Path(directory)
                report = report_fixture("cake", folder)
                if scenario == "config": report["queue"]["after_add"]["qdiscs"][0]["options"]["split_gso"] = False
                elif scenario == "counter": report["phases"][1]["samples"][3]["statistics"]["counters"]["bytes"] = 0
                elif scenario == "cleanup": report["cleanup_verified"] = False
                elif scenario == "receipt": report["phases"][1]["result"]["receive"]["received_bytes"] -= 1
                elif scenario == "latency_file": (folder / "phase-1-idle.json").write_text("{}")
                elif scenario == "evidence": (folder / "progress.jsonl").write_text('{}\n')
                compare = lambda *args: "different\n" if scenario == "compare" else "strict comparison fixture\n"
                with self.assertRaises((model.Error, model.cake.Error, KeyError)):
                    model.summarize(report, "cake", folder, folder, compare)

    def test_duplicate_nonfinite_and_oversized_json_are_rejected(self):
        for raw in (b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":1e400}', b'[]'):
            with self.assertRaises(model.Error): model.document(raw)
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "report"
            file.write_bytes(b"x" * 10)
            with self.assertRaises(model.Error): model.read(file, 9)


if __name__ == "__main__":
    unittest.main()
