"""CAKE campaign decisions and real process supervision with fake network tools."""

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_lab_cake import fixture
from test_lab_cake_active import HARNESS as CAKE_HARNESS
import test_lab_campaign as shared
from test_lab_campaign import HARNESS as CAMPAIGN_HARNESS, SOURCE, phases


spec = importlib.util.spec_from_file_location("cake_campaign", SOURCE.with_name("lab_cake_campaign.py"))
model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)
TOTAL = {"available": True}

# Same fake namespace/CAKE serializer and passage/compare behavior as prior stages.
HARNESS = CAKE_HARNESS[:CAKE_HARNESS.index("namespaces=CakeNamespaces()")]+r'''
spec = importlib.util.spec_from_file_location("cake_campaign", source.with_name("lab_cake_campaign.py"))
model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)
c = model.campaign
'''+CAMPAIGN_HARNESS[CAMPAIGN_HARNESS.index("class Topology(c.Topology):"):
                     CAMPAIGN_HARNESS.index("c.Topology = Topology")].replace(
                         "class Topology(c.Topology):", "class Topology(model.Topology):")+r'''
    def read(self, include_statistics=False):
        reading=super().read(include_statistics)
        # Fake measurement documents have a fixed UTC window, unlike real tc reads.
        reading["collected_at"]="2026-10-30T00:00:02.500000+00:00"
        if scenario=="missing_window":
            reading["collected_at"]="2026-10-30T00:00:20+00:00"
        if scenario=="no_progress" and include_statistics:
            reading["statistics"]["counters"]["bytes"]=100
        return reading
model.Topology = Topology
'''+CAMPAIGN_HARNESS[CAMPAIGN_HARNESS.index("def compare("):
                     CAMPAIGN_HARNESS.index("namespaces = FakeNamespaces()")]+r'''
namespaces = CakeNamespaces()
try:
    result=model.run(namespaces,"fake-tc","fake-sysctl","fake-ping",root/"bin",root/"artifacts",
                     crash=scenario=="crash",tempdir=root,timeout=.3 if scenario=="deadline" else 45)
    print(json.dumps(result))
except Exception as error:
    print(str(error),file=sys.stderr)
    raise SystemExit(1)
'''


class CakeQualificationTests(unittest.TestCase):
    def test_zero_backlog_and_lower_latency_still_qualify_load_only(self):
        values=phases()
        for phase in values:
            for sample in phase["samples"]:
                sample["statistics"].update(backlog_bytes=0,queued_packets=0)
            if phase["condition"]=="loaded":
                phase["result"]["latency"]["connect_ms"]["p50"]=0.5
        decision=model.assess(values,TOTAL,False)
        self.assertTrue(decision["technical_valid"])
        self.assertEqual(decision["load_scenario"],"qualified")
        self.assertEqual(decision["comparison"],"not_assessed")
        self.assertEqual(decision["congestion"],"not_assessed")
        self.assertTrue(all(p["p50_loaded_minus_idle_ms"]==-0.5 for p in decision["pairs"]))

    def test_rate_boundaries_are_inclusive_and_unfavorable_data_stays_valid(self):
        for rate,expected in ((350000,"qualified"),(525000,"qualified"),(349999,"not_qualified"),
                              (525001,"not_qualified")):
            with self.subTest(rate=rate):
                values=phases()
                next(p for p in values if p["condition"]=="loaded")["result"]["receive"]["average_bytes_per_second"]=rate
                decision=model.assess(values,TOTAL,False)
                self.assertTrue(decision["technical_valid"])
                self.assertEqual(decision["load_scenario"],expected)

    def test_missing_percentiles_and_all_tcp_failures_remain_explicit(self):
        values=phases()
        for phase in values:
            phase["result"]["latency"].update(connect_ms=None,successful=0,failed=10)
        decision=model.assess(values,TOTAL,False)
        self.assertEqual(decision["load_scenario"],"qualified")
        self.assertTrue(all(p["p50_loaded_minus_idle_ms"] is None for p in decision["pairs"]))

    def test_window_progress_is_required_even_if_phase_counters_grow(self):
        values=phases()
        loaded=next(p for p in values if p["condition"]=="loaded")
        for sample in loaded["samples"]:
            sample["statistics"]["counters"]["bytes"]=10
        decision=model.assess(values,TOTAL,False)
        self.assertTrue(decision["technical_valid"])
        self.assertEqual(decision["load_scenario"],"not_qualified")
        self.assertFalse(decision["pairs"][0]["bytes_progress_during_probes"])

    def test_incomplete_reordered_overlap_settle_and_resets_are_not_exploitable(self):
        for scenario in ("incomplete","reordered","overlap","settle","phase_reset","window_reset","global_reset","missing_window"):
            with self.subTest(scenario=scenario):
                values,total=phases(),deepcopy(TOTAL)
                loaded=next(p for p in values if p["condition"]=="loaded")
                if scenario=="incomplete": values.pop()
                elif scenario=="reordered": values.reverse()
                elif scenario=="overlap": loaded["result"]["probe_window_inside_application_writes"]=False
                elif scenario=="settle": loaded["result"]["latency"]["started_at"]="2026-10-30T00:00:00.999999999Z"
                elif scenario=="phase_reset": loaded["statistics_delta"]["available"]=False
                elif scenario=="window_reset": loaded["samples"][1]["statistics"]["counters"]["bytes"]=20
                elif scenario=="global_reset": total["available"]=False
                else:
                    for sample in loaded["samples"]: sample["collected_at"]="2026-10-30T00:00:20+00:00"
                decision=model.assess(values,total,False)
                self.assertFalse(decision["technical_valid"])
                self.assertEqual(decision["load_scenario"],"non_exploitable")

    def test_crash_is_never_qualified(self):
        decision=model.assess([],TOTAL,True)
        self.assertIsNone(decision["technical_valid"])
        self.assertEqual(decision["load_scenario"],"not_assessed")


class CakeCampaignProcessTests(unittest.TestCase):
    def run_case(self,scenario):
        return shared.CampaignProcessTests.run_case(self,scenario,harness=HARNESS,cake_fixture=fixture())

    def test_six_phases_receipts_comparisons_and_cake_options_survive_cleanup(self):
        completed,evidence,files=self.run_case("normal")
        self.assertEqual(completed.returncode,0,completed.stderr.decode())
        result=json.loads(completed.stdout)
        self.assertEqual(result["kind"],"lab_cake_campaign")
        self.assertEqual(result["queue"]["kind"],"cake")
        self.assertEqual(result["decision"]["load_scenario"],"qualified")
        self.assertEqual([(p["pair"],p["condition"]) for p in result["phases"]],model.campaign.PHASES)
        self.assertEqual(sum(p["result"].get("receive",{}).get("received_bytes",0) for p in result["phases"]),3*8388608)
        self.assertEqual(sum(e["event"]=="comparison" for e in evidence),3)
        self.assertTrue(any(e["event"]=="qdisc" and e["include_statistics"] for e in evidence))
        self.assertTrue(result["cleanup_verified"])
        self.assertEqual(evidence[-1]["decision"],result["decision"])
        self.assertEqual(len(files),7)

    def test_crash_after_first_idle_reaps_three_orphans(self):
        completed,evidence,files=self.run_case("crash")
        self.assertEqual(completed.returncode,0,completed.stderr.decode())
        result=json.loads(completed.stdout)
        self.assertEqual(result["driver_exit_code"],-9)
        self.assertEqual(result["reaped_descendants"],3)
        self.assertEqual(len(result["phases"]),1)
        self.assertIn("phase-1-idle.json",files)
        self.assertIsNone(result["decision"]["technical_valid"])
        self.assertEqual(evidence[-1]["event"],"cleaned")

    def test_errors_preserve_partial_evidence_and_cleanup_every_owned_process(self):
        for scenario in ("bad_negative_ping","unsupported_profile","changed_after_activation",
                         "configuration_failure","statistics_failure","comparison_failure",
                         "queue_never_empty","interrupt","deadline"):
            with self.subTest(scenario=scenario):
                completed,evidence,_=self.run_case(scenario)
                self.assertEqual(completed.returncode,1,completed.stderr.decode())
                self.assertEqual(completed.stdout,b"")
                self.assertTrue(evidence)
                self.assertNotEqual(evidence[-1]["event"],"cleaned")

    def test_invalid_collection_and_unqualified_load_keep_complete_results(self):
        for scenario,expected in (("counter_reset","non_exploitable"),("missing_window","non_exploitable"),
                                  ("no_progress","not_qualified")):
            with self.subTest(scenario=scenario):
                completed,evidence,files=self.run_case(scenario)
                self.assertEqual(completed.returncode,0,completed.stderr.decode())
                result=json.loads(completed.stdout)
                self.assertEqual(result["decision"]["load_scenario"],expected)
                self.assertEqual(len(result["phases"]),6)
                self.assertEqual(len(files),7)
                self.assertEqual(evidence[-1]["event"],"cleaned")

    def test_exclusive_artifacts_and_inert_cli_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"progress.jsonl"
            path.write_text("preserve")
            with self.assertRaises(FileExistsError):
                model.run(None,None,None,None,None,Path(directory))
            self.assertEqual(path.read_text(),"preserve")
        entry=SOURCE.with_name("lab-cake-campaign.py")
        completed=subprocess.run([sys.executable,"-I","-B",str(entry),"plan"],capture_output=True,timeout=3,check=True)
        self.assertIn(b"150s",completed.stdout)
        self.assertIn(b"CAKE",completed.stdout)
        completed=subprocess.run([sys.executable,"-I","-B",str(entry),"run"],capture_output=True,timeout=3)
        self.assertEqual(completed.returncode,2)
        self.assertIn(b"--artifacts",completed.stderr)

    def test_cli_exit_distinguishes_invalid_collection_from_unqualified_load(self):
        spec=importlib.util.spec_from_file_location("cake_campaign_cli",SOURCE.with_name("lab-cake-campaign.py"))
        entry=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(entry)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name in ("coopace","coopace-lab-tcp","coopace-lab-load"):
                path=root/name
                path.write_text("fixture")
                path.chmod(0o700)
            for technical,expected in ((True,0),(False,1),(None,0)):
                with self.subTest(technical=technical),patch.object(entry.model.campaign.guards,"preflight"), \
                     patch.object(entry.shutil,"which",return_value="fake-tool"), \
                     patch.object(entry.Path,"read_text",return_value="CapEff: 0000000000203000\n"), \
                     patch.object(entry.model,"run",return_value={"decision":{"technical_valid":technical}}), \
                     patch("builtins.print"):
                    self.assertEqual(entry.main(["run","--artifacts",directory,"--binaries",directory]),expected)


if __name__=="__main__":
    unittest.main()
