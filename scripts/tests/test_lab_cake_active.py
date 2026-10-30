"""CAKE active orchestration with fake network commands and real processes."""

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_lab_active import HARNESS as ACTIVE_HARNESS, HELPER, SOURCE as ACTIVE_SOURCE, documents
from test_lab_cake import fixture


SOURCE = ACTIVE_SOURCE.with_name("lab_cake_active.py")
spec = importlib.util.spec_from_file_location("cake_active", SOURCE)
model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)


HARNESS = ACTIVE_HARNESS[:ACTIVE_HARNESS.index('namespaces = FakeNamespaces()')]+r'''
spec = importlib.util.spec_from_file_location("cake_active", source.with_name("lab_cake_active.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
class CakeNamespaces(FakeNamespaces):
    def execute(self, args, owner):
        if args == ["fake-tc", "-V"]:
            return b"tc utility, iproute2-9.0.0\n" if scenario == "unsupported_profile" else b"tc utility, iproute2-6.1.0, libbpf 1.3.0\n"
        if args[1] == "-n" or "fake-sysctl" in args:
            return super().execute(args, owner)
        self.calls.append(args)
        (root / "calls.json").write_text(json.dumps(self.calls))
        c,g,s = [name for name,_ in owner.owned]
        assert args[:5] == [self.ip,"netns","exec",g,"fake-tc"]
        command=args[5:]
        if command[:3] == ["qdisc","add","dev"]:
            assert command == ["qdisc","add","dev","wan","root","handle","10:",*m.cake.ARGUMENTS]
            assert not self.has_queue and (g,"wan") not in self.up
            self.has_queue=True
            return b""
        assert command[-4:] == ["qdisc","show","dev","wan"]
        if not self.has_queue:
            return b"[]"
        rows=json.loads((root / "cake-fixture.json").read_text())
        if "-s" in command:
            self.reads+=1
            if scenario == "statistics_failure" and self.reads==6:
                raise m.cake.Error("injected statistics failure")
            if scenario == "interrupt" and self.reads==6:
                os.kill(os.getpid(),signal.SIGTERM)
            count=1 if scenario=="counter_reset" and self.reads==7 else self.reads*100
            rows[0].update({key:count for key in m.cake.queue.COUNTERS})
            rows[0]["backlog"]=1 if scenario=="queue_never_empty" else 0
            rows[0]["tins"][0]["sent_bytes"]=count
        if scenario=="changed_after_activation" and (g,"wan") in self.up:
            rows[0]["options"]["split_gso"]=False
        return json.dumps(rows).encode()
namespaces=CakeNamespaces()
try:
    result=m.run("check-crash" if scenario=="crash" else "check",namespaces,"fake-tc","fake-sysctl",
                 root/"bin",root/"evidence.jsonl",tempdir=root,timeout=.7 if scenario=="deadline" else 12)
    print(json.dumps(result))
except Exception as error:
    print(str(error),file=sys.stderr)
    raise SystemExit(1)
'''


class CakeActiveTests(unittest.TestCase):
    def run_case(self, scenario):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/"bin").mkdir();(root/"pids").mkdir()
            (root/"documents.json").write_text(json.dumps(documents()))
            (root/"cake-fixture.json").write_text(json.dumps(fixture()))
            if scenario=="worker_failure":
                (root/"worker-failure").touch()
            for name in ("coopace","coopace-lab-tcp","coopace-lab-load"):
                path=root/"bin"/name
                path.write_text("#!"+sys.executable+"\n"+HELPER)
                path.chmod(0o700)
            ip=root/"ip"
            ip.write_text("#!"+sys.executable+"\nimport os,sys\nassert sys.argv[1:3]==['netns','exec']\nos.execv(sys.argv[4],sys.argv[4:])\n")
            ip.chmod(0o700)
            result=subprocess.run([sys.executable,"-I","-B","-c",HARNESS,str(ACTIVE_SOURCE),directory,scenario],
                                  capture_output=True,timeout=18)
            self.assertEqual(list((root/"namespaces").iterdir()),[],result.stderr.decode())
            self.assertEqual(list(root.glob("coopace-guard.*")),[],result.stderr.decode())
            for pid in (root/"pids").iterdir():
                self.assertFalse(Path("/proc",pid.name).exists(),result.stderr.decode())
            evidence=[json.loads(line) for line in (root/"evidence.jsonl").read_text().splitlines()]
            return result,evidence

    def test_complete_cake_flow_uses_shared_worker_and_keeps_periodic_evidence(self):
        result,evidence=self.run_case("normal")
        self.assertEqual(result.returncode,0,result.stderr.decode())
        data=json.loads(result.stdout)
        self.assertEqual(data["kind"],"lab_cake_active_check")
        self.assertEqual(data["queue"]["kind"],"cake")
        self.assertEqual(data["queue"]["link_state"],"UP")
        self.assertEqual(data["flow"]["receive"]["received_bytes"],8388608)
        self.assertGreater(data["traffic_statistics_delta"]["counters"]["bytes"],0)
        self.assertEqual(data["congestion"],"not_assessed")
        self.assertTrue(data["cleanup_verified"])
        self.assertEqual(evidence[0]["event"],"owned")
        self.assertEqual(evidence[-1]["event"],"cleaned")
        self.assertEqual(evidence[-1]["flow"],data["flow"])
        snapshots=[entry["reading"] for entry in evidence if entry["event"]=="qdisc"]
        for reading in data["queue_samples"]:
            self.assertIn({key:value for key,value in reading.items() if key!="phase"},snapshots)
        self.assertGreaterEqual(len(data["queue_samples"]),5)

    def test_crash_kills_and_reaps_three_helpers_before_removing_namespaces(self):
        result,evidence=self.run_case("crash")
        self.assertEqual(result.returncode,0,result.stderr.decode())
        data=json.loads(result.stdout)
        self.assertEqual(data["driver_exit_code"],-9)
        self.assertEqual(data["reaped_descendants"],3)
        self.assertEqual(len(data["helper_pids"]),3)
        self.assertIsNone(data["flow"])
        self.assertEqual(evidence[-1]["event"],"cleaned")

    def test_errors_keep_evidence_and_still_stop_all_owned_processes(self):
        for scenario,message in (("unsupported_profile","Profil JSON tc"),
                                 ("changed_after_activation","split_gso"),
                                 ("configuration_failure","injected address failure"),
                                 ("statistics_failure","injected statistics failure"),
                                 ("counter_reset","Progression des compteurs"),
                                 ("queue_never_empty","File non vidée"),
                                 ("deadline","Échéance indépendante"),
                                 ("interrupt","Supervision interrompue"),
                                 ("worker_failure","Un outil a échoué")):
            with self.subTest(scenario=scenario):
                result,evidence=self.run_case(scenario)
                self.assertEqual(result.returncode,1)
                self.assertEqual(result.stdout,b"")
                self.assertIn(message,result.stderr.decode())
                self.assertTrue(evidence)
                self.assertNotEqual(evidence[-1]["event"],"cleaned")

    def test_existing_or_symlinked_evidence_is_never_modified(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"evidence.jsonl"
            path.write_text("preserve")
            with patch.object(model.active,"run") as run:
                with self.assertRaises(FileExistsError):
                    model.run("check",None,None,None,None,path)
                run.assert_not_called()
            self.assertEqual(path.read_text(),"preserve")
            link=Path(directory)/"link.jsonl";link.symlink_to(Path(directory)/"missing")
            with self.assertRaises(FileExistsError):
                model.run("check",None,None,None,None,link)
            self.assertFalse((Path(directory)/"missing").exists())

    def test_plan_requires_no_privileges_and_real_run_requires_evidence_path(self):
        source=SOURCE.with_name("lab-cake-active.py")
        result=subprocess.run([sys.executable,"-I","-B",str(source),"plan"],capture_output=True,timeout=3)
        self.assertEqual(result.returncode,0,result.stderr.decode())
        self.assertIn(b"4mbit",result.stdout)
        result=subprocess.run([sys.executable,"-I","-B",str(source),"check"],capture_output=True,timeout=3)
        self.assertEqual(result.returncode,2)
        self.assertIn(b"--evidence",result.stderr)


if __name__=="__main__":
    unittest.main()
