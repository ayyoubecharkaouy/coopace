"""Campaign evidence, qualification and real process cleanup without networking."""

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from test_lab_active import HARNESS as ACTIVE_HARNESS, HELPER, SOURCE as ACTIVE_SOURCE, documents


SOURCE = ACTIVE_SOURCE.with_name("lab_campaign.py")
spec = importlib.util.spec_from_file_location("campaign", SOURCE)
campaign = importlib.util.module_from_spec(spec)
spec.loader.exec_module(campaign)

# Reuse the same fake owned-namespace backend as the validated functional tool.
HARNESS = ACTIVE_HARNESS[:ACTIVE_HARNESS.index("namespaces = FakeNamespaces()")]+r'''
spec = importlib.util.spec_from_file_location("campaign", source.with_name("lab_campaign.py"))
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
class Topology(c.Topology):
    forwarding = 1
    def control(self, args, *, timeout=2, allowed=(0,)):
        assert timeout <= 6
        self.owner.check()
        if "fake-sysctl" in args:
            if "net.ipv4.ip_forward=0" in args:
                self.forwarding = 0
            elif "net.ipv4.ip_forward=1" in args:
                self.forwarding = 1
            else:
                return str(self.forwarding).encode()
            return b""
        assert "fake-ping" in args and args[3] == self.owner.owned[0][0]
        if allowed == (1,):
            assert self.forwarding == 0
            if scenario == "bad_negative_ping":
                raise c.Error("unexpected passage without forwarding")
            return b"1 packets transmitted, 0 received\n"
        assert self.forwarding == 1 and allowed == (0,)
        return b"3 packets transmitted, 3 received\n"
c.Topology = Topology
def compare(args, owner, **kwargs):
    assert args[1:3] == ["latency", "compare"]
    idle,loaded = [json.loads(Path(args[args.index(flag)+1]).read_text()) for flag in ("--idle","--loaded")]
    assert idle["declared_condition"]=="idle" and loaded["declared_condition"]=="loaded"
    if scenario == "comparison_failure":
        raise c.Error("injected comparison failure")
    return b"fake strict comparison\n"
c.queue.run_command = compare
namespaces = FakeNamespaces()
try:
    result=c.run(namespaces,"fake-tc","fake-sysctl","fake-ping",root/"bin",root/"artifacts",
                 crash=scenario=="crash",tempdir=root,timeout=.3 if scenario=="deadline" else 45)
    print(json.dumps(result))
except Exception as error:
    print(str(error),file=sys.stderr)
    raise SystemExit(1)
'''


def phases():
    result=[]
    for index,condition in campaign.PHASES:
        send,receive,latency=documents()
        latency["declared_condition"]=condition
        latency["connect_ms"]={"p50":1 if condition=="idle" else 20}
        flow={"latency":latency,"measurement_exit_code":0}
        if condition=="loaded":
            flow.update(send=send,receive=receive,probe_window_inside_application_writes=True)
        samples=[]
        for n,microseconds in enumerate((0,300000,600000,900000)):
            samples.append({"collected_at":f"2026-10-30T00:00:02.{microseconds:06d}+00:00",
                            "elapsed_since_start_ms":n*300,
                            "statistics":{"counters":{key:n for key in campaign.queue.COUNTERS},
                                          "backlog_bytes":100,"queued_packets":1}})
        result.append({"pair":index,"condition":condition,"result":flow,"samples":samples,
                       "statistics_delta":{"available":True}})
    return result


class QualificationTests(unittest.TestCase):
    def test_negative_probe_exit_must_be_one_not_success_or_tool_error(self):
        for code in (0,1,2):
            owner=Mock(deadline=time.monotonic()+2)
            args=[sys.executable,"-I","-c",f'import sys; print("probe"); sys.exit({code})']
            if code==1:
                self.assertEqual(campaign.queue.run_command(args,owner,timeout=1,allowed=(1,)),b"probe\n")
            else:
                with self.assertRaises(campaign.Error):
                    campaign.queue.run_command(args,owner,timeout=1,allowed=(1,))
            self.assertIsNone(owner.command_child)

    def test_frozen_criteria_require_three_fed_flows_and_two_latency_differences(self):
        values=phases()
        decision=campaign.qualify(values)
        self.assertTrue(decision["technical_valid"])
        self.assertEqual(decision["congestion"],"observed")
        for phase in values:
            if phase["condition"]=="loaded" and phase["pair"] in (1,2):
                phase["result"]["latency"]["connect_ms"]["p50"]=2
        self.assertEqual(campaign.qualify(values)["congestion"],"not_demonstrated")
        for loaded_p50,expected in ((20.000002,"observed"),(20.000001,"not_demonstrated")):
            values=phases()
            for phase in values:
                phase["result"]["latency"]["connect_ms"]["p50"]=10.000002 if phase["condition"]=="idle" else loaded_p50
            self.assertEqual(campaign.qualify(values)["congestion"],expected)

    def test_rate_boundaries_and_missing_latency_are_not_fabricated(self):
        for rate,expected in ((350000,"observed"),(525000,"observed"),(349999,"not_demonstrated"),
                              (525001,"not_demonstrated")):
            values=phases()
            next(p for p in values if p["condition"]=="loaded")["result"]["receive"]["average_bytes_per_second"]=rate
            self.assertEqual(campaign.qualify(values)["congestion"],expected)
        values=phases()
        for p in values:
            p["result"]["latency"].update(connect_ms=None,successful=0,failed=10)
        decision=campaign.qualify(values)
        self.assertEqual(decision["congestion"],"not_demonstrated")
        self.assertTrue(all(p["p50_loaded_minus_idle_ms"] is None for p in decision["pairs"]))

    def test_incomplete_overlap_and_reset_are_non_exploitable(self):
        values=phases()
        self.assertEqual(campaign.qualify(values[:-1])["congestion"],"non_exploitable")
        for field in ("overlap","reset","settle"):
            value=deepcopy(values)
            loaded=next(p for p in value if p["condition"]=="loaded")
            if field=="overlap":
                loaded["result"]["probe_window_inside_application_writes"]=False
            elif field=="reset":
                loaded["statistics_delta"]["available"]=False
            else:
                loaded["result"]["latency"]["started_at"]="2026-10-30T00:00:00.5Z"
            self.assertFalse(campaign.qualify(value)["technical_valid"])

    def test_backlog_samples_must_be_spaced_and_counters_must_progress(self):
        for failure in ("too_close","outside_window","no_progress"):
            values=phases()
            loaded=next(p for p in values if p["condition"]=="loaded")
            for n,sample in enumerate(loaded["samples"]):
                if failure=="too_close":
                    sample["collected_at"]=f"2026-10-30T00:00:02.{n:06d}+00:00"
                    sample["elapsed_since_start_ms"]=n*.001
                elif failure=="outside_window":
                    sample["collected_at"]="2026-10-30T00:00:20+00:00"
                else:
                    sample["statistics"]["counters"]={key:0 for key in campaign.queue.COUNTERS}
            self.assertEqual(campaign.qualify(values)["congestion"],"not_demonstrated")

    def test_passage_requires_owned_names_and_three_positive_replies(self):
        ns=Mock(ip="fake-ip")
        ns.identity.return_value=(1,3)
        topology=campaign.Topology(ns,"tc","sysctl")
        topology.owner=Mock(owned=[("cg-12345678-c",(1,2))])
        with patch.object(campaign.queue,"run_command") as command:
            with self.assertRaises(campaign.Error):
                topology.control(["anything"])
            command.assert_not_called()
        topology.owner.owned=[("cg-12345678-c",(1,3))]
        topology.gateway="cg-12345678-g"
        with patch.object(topology,"control",side_effect=[b"",b"0",b"negative",b"",b"1",b"3 packets transmitted, 2 received"]):
            with self.assertRaises(campaign.Error):
                topology.passage("ping")

    def test_reset_between_readings_stays_unavailable_even_if_final_value_recovers(self):
        readings=phases()[0]["samples"]
        readings[1]["statistics"]["counters"]["bytes"]=10
        self.assertEqual(campaign.delta(readings),
                         {"available":False,"reason":"counter_decreased","counters":None})

    def test_out_of_order_and_premature_complete_cannot_advance_the_worker(self):
        owner=Mock()
        controller=campaign.Campaign(owner,Mock(),Mock(),Path("unused"),Path("unused"))
        for event in ({"event":"begin","pair":2,"condition":"idle"},{"event":"complete"},
                      {"event":"end","pair":1,"condition":"idle","result":{}}):
            with self.subTest(event=event),self.assertRaises(campaign.Error):
                controller.event(event)
        owner.child.stdin.write.assert_not_called()


class CampaignProcessTests(unittest.TestCase):
    def run_case(self,scenario,*,harness=HARNESS,cake_fixture=None):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name in ("bin","pids","artifacts"):
                (root/name).mkdir()
            values=documents()
            values[2].update(os="linux",architecture="amd64",go_version="go1.27.3",coopace_version="test",
                             connect_ms={"min":1,"p50":1,"p95":1,"p99":1,"max":1})
            (root/"documents.json").write_text(json.dumps(values))
            if cake_fixture is not None:
                (root/"cake-fixture.json").write_text(json.dumps(cake_fixture))
            helper=HELPER.replace('print(json.dumps(docs[2]), flush=True)',
                'value=docs[2]\n    value["declared_condition"]=sys.argv[sys.argv.index("--condition")+1]\n    print(json.dumps(value),flush=True)')
            for name in ("coopace","coopace-lab-tcp","coopace-lab-load"):
                path=root/"bin"/name
                path.write_text("#!"+sys.executable+"\n"+helper)
                path.chmod(0o700)
            ip=root/"ip"
            ip.write_text("#!"+sys.executable+"\nimport os,sys\nassert sys.argv[1:3]==['netns','exec']\nos.execv(sys.argv[4],sys.argv[4:])\n")
            ip.chmod(0o700)
            completed=subprocess.run([sys.executable,"-I","-B","-c",harness,str(ACTIVE_SOURCE),directory,scenario],
                                     capture_output=True,timeout=50)
            self.assertEqual(list((root/"namespaces").iterdir()),[],completed.stderr.decode())
            self.assertEqual(list(root.glob("coopace-guard.*")),[],completed.stderr.decode())
            for pid in (root/"pids").iterdir():
                self.assertFalse(Path("/proc",pid.name).exists(),completed.stderr.decode())
            evidence=[json.loads(line) for line in (root/"artifacts/progress.jsonl").read_text().splitlines()]
            files=sorted(p.name for p in (root/"artifacts").iterdir())
            return completed,evidence,files

    def test_six_phases_three_receipts_and_comparisons_survive_cleanup(self):
        completed,evidence,files=self.run_case("normal")
        self.assertEqual(completed.returncode,0,completed.stderr.decode())
        result=json.loads(completed.stdout)
        self.assertEqual([(p["pair"],p["condition"]) for p in result["phases"]],campaign.PHASES)
        self.assertTrue(result["decision"]["technical_valid"])
        self.assertEqual(result["decision"]["congestion"],"not_demonstrated")
        self.assertEqual(len(files),7)
        self.assertEqual(sum(e["event"]=="comparison" for e in evidence),3)
        self.assertEqual(sum(p["result"].get("receive",{}).get("received_bytes",0) for p in result["phases"]),3*8388608)
        self.assertEqual(evidence[-1]["event"],"cleaned")

    def test_crash_after_idle_retains_evidence_and_reaps_three_orphans(self):
        completed,evidence,files=self.run_case("crash")
        self.assertEqual(completed.returncode,0,completed.stderr.decode())
        result=json.loads(completed.stdout)
        self.assertEqual(result["reaped_descendants"],3)
        self.assertEqual(result["driver_exit_code"],-9)
        self.assertEqual(len(result["phases"]),1)
        self.assertIn("phase-1-idle.json",files)
        self.assertTrue(any(e["event"]=="driver" and e["message"]["event"]=="ready" for e in evidence))

    def test_errors_keep_partial_artifacts_but_never_claim_success(self):
        for scenario in ("bad_negative_ping","deadline","statistics_failure","comparison_failure"):
            with self.subTest(scenario=scenario):
                completed,evidence,_=self.run_case(scenario)
                self.assertEqual(completed.returncode,1)
                self.assertEqual(completed.stdout,b"")
                self.assertGreater(len(evidence),0)
                self.assertNotEqual(evidence[-1]["event"],"cleaned")

    def test_existing_evidence_is_never_truncated_and_plan_is_inert(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"progress.jsonl"
            path.write_text("preserve")
            with self.assertRaises(FileExistsError):
                campaign.run(None,None,None,None,None,Path(directory))
            self.assertEqual(path.read_text(),"preserve")
        completed=subprocess.run([sys.executable,"-I","-B",str(SOURCE.with_name("lab-campaign.py")),"plan"],
                                 capture_output=True,timeout=3,check=True)
        self.assertIn(b"150s",completed.stdout)


if __name__=="__main__":
    unittest.main()
