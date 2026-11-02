"""Whole Go/path/campaign handoff: fake kernel/tools, actual owned groups."""

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_lab_cake_go_path_control as fixtures
import test_lab_cake_go_campaign_traffic as driver_fixtures

SOURCE = fixtures.SOURCE.with_name("lab_cake_go_campaign_collect.py")
spec = importlib.util.spec_from_file_location("campaign_collect_tests", SOURCE)
model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)

ADAPTER = r'''
spec=importlib.util.spec_from_file_location('campaign',source.with_name('lab_cake_go_campaign.py'))
campaign=importlib.util.module_from_spec(spec);spec.loader.exec_module(campaign)
class CampaignInventory(PathInventory):
 source_fingerprints=staticmethod(campaign.source_fingerprints)
class CampaignJournal(combined.Journal):
 def __init__(self,path):super().__init__(path,limit=16*1024*1024)
class CampaignCollector(campaign.collection.Collector):
 helpers=Collector.helpers
 def control(self,action):
  if action=='start':
   (root/'phase.json').write_text(json.dumps({'index':self.dialogue.index,'pair':self.current['pair'],'condition':self.current['condition']}))
  return super().control(action)
 def event(self,raw,observed,crash):
  if scenario=='campaign_wrong_phase' and b'"ready"' in raw:raw=raw.replace(b'"pair":1',b'"pair":2')
  if scenario=='campaign_foreign_pid' and b'"ready"' in raw:
   v=json.loads(raw);v['helper_pids'][0]=os.getpid();raw=json.dumps(v).encode()+b'\n'
  return super().event(raw,observed,crash)
 def empty_phase(self,observed):
  if scenario=='campaign_empty_deadline':observed=time.monotonic_ns()-3_100_000_000
  reading=super().empty_phase(observed)
  if scenario=='campaign_late_advance':time.sleep(3)
  return reading
campaign_write=combined.Journal.write
def campaign_record(self,event):
 if scenario=='campaign_ack_evidence' and event['event']=='campaign_control_intent':raise OSError('injected campaign ack evidence failure')
 if scenario=='campaign_end_evidence' and event['event']=='phase_end_observed':raise OSError('injected end observation failure')
 if scenario=='campaign_sample_evidence' and event['event']=='campaign_sample' and event['reading']['phase']=='running':raise OSError('injected campaign sample failure')
 return campaign_write(self,event)
combined.Journal.write=campaign_record
campaign_execute=Kernel.execute
def campaign_kernel(self,args,owner):
 raw=campaign_execute(self,args,owner)
 if 'qdisc' in args and 'show' in args and (root/'phase.json').exists():
  rows=json.loads(raw)
  if scenario=='campaign_never_empty':rows[0].update(backlog=1,qlen=1)
  if scenario=='campaign_counter_reset':rows[0]['bytes']=0
  return json.dumps(rows).encode()
 return raw
Kernel.execute=campaign_kernel
if mode=='check':mode='run'
'''
HARNESS = fixtures.HARNESS.replace("kernel=Kernel();failure=None", ADAPTER + "\nkernel=Kernel();failure=None")
HARNESS = HARNESS.replace("combined.run(mode,kernel,sys.executable,sys.executable,sys.executable,root/'bin',artifacts,",
                          "campaign.collect(mode,kernel,sys.executable,sys.executable,sys.executable,sys.executable,root/'bin',artifacts,")
HARNESS = HARNESS.replace("inventory_factory=PathInventory,collector_factory=Collector,path_factory=PathCheck,",
                          "inventory_factory=CampaignInventory,collector_factory=CampaignCollector,path_factory=PathCheck,journal_factory=CampaignJournal,")
# Complete campaigns need more time than a single-flow fixture. Keep the
# owner's cleanup deadline ahead of the outer test watchdog (50s + 10s < 70s).
HARNESS = HARNESS.replace("else 180)", "else 50)")


@unittest.skipUnless(sys.platform == "linux", "Linux owned groups")
class CampaignCollectTests(unittest.TestCase):
    def run_case(self, scenario="normal", mode="check"):
        runner = fixtures.fixtures.CombinedTests(methodName="runTest")
        original = subprocess.run
        def run(*args, **kwargs):
            if kwargs.get("timeout") == 22:
                kwargs["timeout"] = 70
            return original(*args, **kwargs)
        with patch.object(fixtures.fixtures, "HARNESS", HARNESS), \
             patch.object(fixtures.fixtures.traffic_fixtures, "HELPER", driver_fixtures.HELPER), \
             patch.object(fixtures.fixtures.subprocess, "run", side_effect=run):
            return runner.run_case(scenario, mode)

    def test_six_phases_follow_go_path_and_keep_replayable_drain_timing(self):
        process, report, journal, _ = self.run_case()
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(report["kind"], "lab_cake_go_campaign_collection")
        self.assertEqual(report["mode"], "run")
        collected = report["traffic_group"]
        self.assertEqual(collected["state"], "collected")
        self.assertEqual(collected["assessment"], "not_implemented")
        self.assertEqual([(p["pair"], p["condition"]) for p in collected["phases"]],
                         [(1,"idle"),(1,"loaded"),(2,"loaded"),(2,"idle"),(3,"idle"),(3,"loaded")])
        self.assertEqual([p["result"]["receive"]["received_bytes"] for p in collected["phases"] if p["condition"]=="loaded"], [8388608]*3)
        events = [r["data"]["event"] for r in journal]
        self.assertLess(events.index("path_verified"), events.index("traffic_launch_intent"))
        self.assertEqual(events.count("phase_end_observed"), 6)
        for phase in collected["phases"]:
            self.assertEqual(phase["state"], "complete")
            self.assertTrue(all(h["reason"]=="absent" for h in phase["helpers_stopped"]))
            drains = [s for s in phase["samples"] if s["phase"]=="drain"]
            self.assertGreaterEqual(drains[-1]["read_finished_monotonic_ns"]-drains[0]["read_finished_monotonic_ns"], 500_000_000)
            self.assertLess(drains[-1]["read_finished_monotonic_ns"]-phase["end_observed_monotonic_ns"], 3_000_000_000)
        self.assertTrue(report["cleanup_verified"])
        self.assertIsNone(report["flow"])

    def test_crash_after_idle_and_first_loaded_ready_recovers_three_helpers(self):
        process, report, journal, _ = self.run_case(mode="check-crash")
        self.assertEqual(process.returncode, 0, process.stderr)
        group = report["traffic_group"]
        self.assertEqual(group["state"], "crash_verified")
        self.assertEqual(group["driver_exit_code"], -9)
        self.assertEqual(group["reaped_descendants"], 3)
        self.assertEqual(group["phases"][0]["state"], "complete")
        self.assertEqual(group["phases"][1]["state"], "interrupted")
        self.assertIsNone(group["phases"][1]["result"])
        controls = [r["data"] for r in journal if r["data"]["event"]=="campaign_control_sent"]
        self.assertFalse(any(c["condition"]=="loaded" and c["action"]=="continue" for c in controls))

    def test_invalid_identity_phase_or_evidence_is_terminal_with_cleanup(self):
        for scenario in ("campaign_foreign_pid", "campaign_wrong_phase", "campaign_ack_evidence", "campaign_end_evidence",
                         "campaign_sample_evidence", "campaign_empty_deadline", "campaign_late_advance", "campaign_never_empty",
                         "campaign_counter_reset", "helper_exit", "deadline"):
            with self.subTest(scenario=scenario):
                process, report, journal, _ = self.run_case(scenario)
                self.assertNotEqual(process.returncode, 0, process.stderr)
                self.assertEqual(report["state"], "failed")
                self.assertTrue(report["cleanup_verified"])
                if report["traffic_group"]:
                    self.assertNotEqual(report["traffic_group"]["state"], "collected")
                if scenario=="campaign_late_advance":
                    self.assertEqual(len(report["traffic_group"]["phases"]), 1)
                    sent=[r["data"] for r in journal if r["data"]["event"]=="campaign_control_sent"]
                    self.assertFalse(any(c["action"]=="advance" for c in sent))

    def test_uncertain_cleanup_prevents_global_success(self):
        process, report, _, _ = self.run_case("cleanup_failure", mode="check-crash")
        self.assertNotEqual(process.returncode, 0)
        self.assertEqual(report["state"], "failed")
        self.assertFalse(report["cleanup_verified"])

    def test_invalid_go_or_path_never_starts_campaign(self):
        for scenario in ("wrong_session", "path_negative_reply"):
            with self.subTest(scenario=scenario):
                process, report, journal, _ = self.run_case(scenario)
                self.assertNotEqual(process.returncode, 0)
                self.assertIsNone(report["traffic_group"])
                self.assertNotIn("traffic_launch_intent", [r["data"]["event"] for r in journal])

    def test_failed_tcp_attempts_remain_collected_without_scientific_verdict(self):
        process, report, _, _ = self.run_case("all_failed")
        self.assertEqual(process.returncode, 0, process.stderr)
        group = report["traffic_group"]
        self.assertEqual(group["state"], "collected")
        self.assertTrue(all(p["result"]["latency"]["failed"]==10 for p in group["phases"]))
        self.assertEqual(group["assessment"], "not_implemented")


class StoppedIdentityTests(unittest.TestCase):
    def test_live_identity_is_refused_reused_identity_observed_without_signal(self):
        child = subprocess.Popen([sys.executable, "-I", "-c", "import time;time.sleep(30)"])
        try:
            # Start-time remains stable across exec, so reading stat is enough.
            raw = Path("/proc",str(child.pid),"stat").read_bytes()
            ticks = int(raw[raw.rfind(b") ")+2:].split()[19])
            with self.assertRaises(model.Error):model.stopped_helper({"pid":child.pid,"start_ticks":ticks})
            reused = model.stopped_helper({"pid":child.pid,"start_ticks":ticks-1})
            self.assertEqual(reused["reason"], "pid_reused")
            self.assertIsNone(child.poll())
        finally:
            child.terminate(); child.wait(timeout=2)
        self.assertEqual(model.stopped_helper({"pid":child.pid,"start_ticks":ticks})["reason"], "absent")


if __name__ == "__main__":
    unittest.main()
