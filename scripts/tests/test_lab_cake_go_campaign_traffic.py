"""Actual driver/process groups with fake network tools and synthetic reports."""

from copy import deepcopy
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import test_lab_active as fixtures

SOURCE = fixtures.SOURCE.with_name("lab_cake_go_campaign_traffic.py")
spec = importlib.util.spec_from_file_location("campaign_driver_tests", SOURCE)
model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)

HELPER = r'''
import json,os,signal,sys,time
from pathlib import Path
root=Path(__file__).resolve().parents[1]
assert os.readlink('/proc/self/fd/0')=='/dev/null','inherited campaign control pipe'
scenario=(root/'scenario').read_text();phase=json.loads((root/'phase.json').read_text())
name=Path(sys.argv[0]).name
role='target' if name=='coopace-lab-tcp' else ('probe' if name=='coopace' else sys.argv[1])
(root/'pids'/str(os.getpid())).touch()
fd=os.open(root/'calls.jsonl',os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)
os.write(fd,(json.dumps({'pid':os.getpid(),'phase':phase['index'],'condition':phase['condition'],'role':role})+'\n').encode());os.close(fd)
if scenario=='crash':signal.signal(signal.SIGTERM,signal.SIG_IGN)
if scenario=='helper_exit' and role=='target':raise SystemExit(7)
if role=='target':
 print('READY 10.203.0.6:46001',flush=True)
 if scenario=='stderr_overflow':
  while True:os.write(2,b'x'*8192)
 while True:time.sleep(.01)
elif role in ('send','receive'):
 print('STARTED' if role=='send' else 'READY 10.203.0.6:46002',flush=True)
 while not (root/('probe-'+str(phase['index']))).exists():time.sleep(.005)
 docs=json.loads((root/'documents.json').read_text())
 print(json.dumps(docs[0 if role=='send' else 1]),flush=True)
else:
 assert sys.argv[sys.argv.index('--condition')+1]==phase['condition']
 (root/('probe-'+str(phase['index']))).touch()
 if scenario=='stdout_overflow':
  os.write(1,b'x'*300000);time.sleep(60)
 docs=json.loads((root/'documents.json').read_text());latency=docs[2]
 latency['declared_condition']=phase['condition']
 print(json.dumps(latency),flush=True)
 raise SystemExit(1 if scenario=='all_failed' else 0)
'''

HARNESS = r'''
import hashlib,importlib.util,json,os,signal,subprocess,sys,time
from pathlib import Path
source,root,scenario=Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3]
spec=importlib.util.spec_from_file_location('driver',source);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
groups=m.active.sibling('test_campaign_groups','lab_process_group.py')
m.active.guard_module.enable_subreaper()
tools={}
for role,name in (('agent','coopace'),('target','coopace-lab-tcp'),('load','coopace-lab-load'),('ip',None)):
 path=(root/'bin'/name).resolve() if name else Path(sys.executable).resolve()
 tools[role]={'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
manifest=json.dumps({'schema_version':1,'kind':'lab_cake_go_campaign_tools','session_id':'traffic1','tools':tools})
args=['--session-id','traffic1','--client','cg-traffic1-c','--server','cg-traffic1-s',
 '--ip',tools['ip']['path'],'--binaries',str(root/'bin'),'--tools-json',manifest]
bootstrap='''+repr('''import importlib.util,sys,time
spec=importlib.util.spec_from_file_location('private_driver',sys.argv[1]);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
if sys.argv[2]=='global_deadline':
 original=m.CampaignRunner.__init__
 def init(self,*args,**kwargs):
  original(self,*args,**kwargs);self.deadline=min(self.deadline,time.monotonic()+.4)
 m.CampaignRunner.__init__=init
raise SystemExit(m.main(sys.argv[3:]))
''')+r'''
group=groups.ProcessGroup();output=bytearray();events=[];eof=False;failure=None;split_count=0
dialogue=m.protocol.Dialogue('traffic1');reader=m.protocol.LineReader('traffic1','events')
with (root/'stderr').open('wb') as errors:
 child=subprocess.Popen([sys.executable,'-I','-B','-c',bootstrap,str(source),scenario,*args],
  stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=errors,start_new_session=True,cwd=root)
 group.attach(child);os.set_blocking(child.stdout.fileno(),False)
 if scenario=='pre_control':os.write(child.stdin.fileno(),m.protocol.control_frame('traffic1',1,'idle','start'))
 deadline=time.monotonic()+30;killed=False;closed=False;late=None;blocked_until=0
 def control(value,action):
  global split_count
  pair,condition=value['pair'],value['condition']
  ack=m.protocol.control_frame('traffic1',pair,condition,action)
  if scenario=='wrong_session':ack=m.protocol.control_frame('other123',pair,condition,action)
  if scenario=='wrong_pair' and action=='continue':ack=m.protocol.control_frame('traffic1',2,'idle',action)
  if scenario=='duplicate' and action=='start':ack+=ack
  doubled=scenario=='continue_duplicate' and action=='continue' and condition=='loaded'
  if doubled:ack+=ack
  if scenario=='split':
   mid=len(ack)//2;os.write(child.stdin.fileno(),ack[:mid]);time.sleep(.02)
   if action=='continue':assert not (root/('probe-'+str(dialogue.index))).exists(),'probe before complete continue'
   os.write(child.stdin.fileno(),ack[mid:]);split_count+=1
  else:os.write(child.stdin.fileno(),ack)
  if scenario not in ('wrong_session','wrong_pair','duplicate') and not doubled:dialogue.control(ack)
 try:
  while True:
   assert time.monotonic()<deadline,'test controller deadline'
   if late is not None and time.monotonic()>=late:
    os.write(child.stdin.fileno(),m.protocol.control_frame('traffic1',1,'idle','continue'));late=None
   if not eof and time.monotonic()>=blocked_until:
    try:data=os.read(child.stdout.fileno(),8192)
    except BlockingIOError:data=None
    if data==b'':eof=True
    elif data:
     output.extend(data)
     for value in reader.feed(data):
      events.append(value)
      if scenario not in ('wrong_session','wrong_pair','duplicate'):dialogue.event(m.protocol._wire(value))
      kind=value['event']
      if kind=='begin':
       (root/'phase.json').write_text(json.dumps({'index':dialogue.index,'pair':value['pair'],'condition':value['condition']}))
       if scenario=='start_eof':child.stdin.close();closed=True
       else:control(value,'start')
      elif kind=='ready':
       pids=value['helper_pids'];expected=1 if value['condition']=='idle' else 3
       assert len(pids)==expected and all(Path('/proc',str(pid)).exists() and os.getpgid(pid)==child.pid for pid in pids)
       assert not (root/('probe-'+str(dialogue.index))).exists(),'probe before continue'
       if value['condition']=='loaded' and scenario in ('crash','signal'):
        os.kill(child.pid,signal.SIGKILL if scenario=='crash' else signal.SIGTERM);killed=True
       elif scenario=='continue_eof':child.stdin.close();closed=True
       elif scenario=='continue_timeout':pass
       else:
        if scenario=='tool_changed':(root/'bin/coopace').write_text('modified')
        control(value,'continue')
        if scenario=='late_duplicate':late=time.monotonic()+.02
        if scenario=='output_backpressure':blocked_until=time.monotonic()+6
      elif kind=='end':
       assert all(not Path('/proc',str(e['pid'])).exists() for e in [json.loads(l) for l in (root/'calls.jsonl').read_text().splitlines()]
        if e['phase']==dialogue.index),'live tool before end'
       control(value,'advance')
      elif kind=='complete':
       if not closed:child.stdin.close();closed=True;dialogue.finish_controls()
   if group.exited() and eof:break
   time.sleep(.005)
  if scenario!='output_backpressure':reader.finish()
  if scenario in ('normal','split','all_failed'):dialogue.finish_events();assert dialogue.complete
 except Exception as error:failure=str(error)
 finally:
  group.stop(time.monotonic()+5)
  (root/'observed.json').write_text(json.dumps({'failure':failure,'code':group.driver_code,
   'reaped':group.reaped_descendants,'events':events,'bytes':len(output),'split_controls':split_count,'killed':killed}))
'''


class CampaignToolSetTests(unittest.TestCase):
    def manifest(self):
        path = Path(sys.executable).resolve()
        tool = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        return {"schema_version": 1, "kind": "lab_cake_go_campaign_tools", "session_id": "traffic1",
                "tools": {name: dict(tool) for name in ("ip", "agent", "target", "load")}}

    def test_inventory_requires_campaign_scope_session_and_four_fingerprints(self):
        for change in (lambda v: v.update(kind="lab_cake_go_active_tools"),
                       lambda v: v.update(session_id="other123"), lambda v: v.update(schema_version=True),
                       lambda v: v["tools"].pop("load"), lambda v: v["tools"]["ip"].update(sha256="g" * 64)):
            value = self.manifest(); change(value)
            with self.subTest(change=change), self.assertRaises((model.Error, model.traffic.Error)):
                model.ToolSet(json.dumps(value), "traffic1")

    def test_tools_cannot_skip_phase_order_launch_wrong_role_or_repeat_a_start(self):
        tools = model.ToolSet(json.dumps(self.manifest()), "traffic1")
        with self.assertRaises(model.Error):tools.begin_phase(1, "loaded")
        tools.begin_phase(1, "idle")
        with self.assertRaises(model.Error):tools.before_start(tools.commands[4])
        tools.before_start(tools.commands[0])
        with self.assertRaises(model.Error):tools.before_start(tools.commands[0])
        with self.assertRaises(model.Error):tools.before_start(tools.commands[1])
        with self.assertRaises(model.Error):tools.begin_phase(1, "loaded")
        tools.before_start(tools.commands[4])
        tools.begin_phase(1, "loaded")
        with self.assertRaises(model.Error):tools.before_start(tools.commands[3])


@unittest.skipUnless(sys.platform == "linux", "Linux process groups")
class CampaignDriverTests(unittest.TestCase):
    def run_case(self, scenario="normal"):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "bin").mkdir(); (root / "pids").mkdir()
            docs = deepcopy(fixtures.documents())
            if scenario == "all_failed":
                docs[2].update(successful=0, failed=10)
                for attempt in docs[2]["attempts"]:
                    attempt.update(connect_ms=None, failure="timeout")
            if scenario == "output_backpressure":
                docs[2]["coopace_version"] = "v" * 100000
            (root / "documents.json").write_text(json.dumps(docs))
            (root / "scenario").write_text(scenario)
            for name in ("coopace", "coopace-lab-tcp", "coopace-lab-load"):
                path = root / "bin" / name
                path.write_text("#!" + sys.executable + "\n" + HELPER)
                path.chmod(0o700)
            (root / "netns").write_text('import os,sys\nassert sys.argv[1]=="exec"\nos.execv(sys.argv[3],sys.argv[3:])\n')
            process = subprocess.run([sys.executable, "-I", "-B", "-c", HARNESS, str(SOURCE), directory, scenario],
                                     capture_output=True, text=True, timeout=38)
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertTrue((root / "observed.json").exists(), process.stderr)
            observed = json.loads((root / "observed.json").read_text())
            diagnostic = (root / "stderr").read_text()
            self.assertIsNone(observed["failure"], (observed, diagnostic))
            for marker in (root / "pids").iterdir():
                self.assertFalse(Path("/proc", marker.name).exists(), diagnostic)
            calls = [json.loads(line) for line in (root / "calls.jsonl").read_text().splitlines()] if (root / "calls.jsonl").exists() else []
            self.assertLessEqual(observed["bytes"], model.protocol.EVENT_BUDGET)
            self.assertLessEqual(len((root / "stderr").read_bytes()), model.STDERR_LIMIT)
            return observed, calls, diagnostic

    def test_normal_and_fragmented_controls_finish_six_phases_with_fresh_tools(self):
        for scenario in ("normal", "split"):
            with self.subTest(scenario=scenario):
                observed, calls, diagnostic = self.run_case(scenario)
                self.assertEqual(observed["code"], 0, diagnostic)
                self.assertEqual(len(observed["events"]), 19)
                self.assertEqual(len(calls), 18)
                self.assertEqual([e["result"]["receive"]["received_bytes"] for e in observed["events"]
                                  if e["event"] == "end" and e["condition"] == "loaded"], [8388608] * 3)
                self.assertEqual(observed["reaped"], 0)
                if scenario == "split":self.assertEqual(observed["split_controls"], 18)

    def test_failed_tcp_measurements_remain_data_and_do_not_claim_qualification(self):
        observed, _, diagnostic = self.run_case("all_failed")
        self.assertEqual(observed["code"], 0, diagnostic)
        ends = [e for e in observed["events"] if e["event"] == "end"]
        self.assertEqual(len(ends), 6)
        self.assertTrue(all(e["result"]["latency"]["failed"] == 10 and e["result"]["measurement_exit_code"] == 1 for e in ends))

    def test_missing_invalid_or_early_controls_prevent_full_campaign_and_reap_tools(self):
        for scenario in ("pre_control", "start_eof", "continue_eof", "continue_timeout", "wrong_session",
                         "wrong_pair", "duplicate", "late_duplicate", "continue_duplicate"):
            with self.subTest(scenario=scenario):
                observed, _, diagnostic = self.run_case(scenario)
                self.assertNotEqual(observed["code"], 0, diagnostic)
                self.assertNotIn("complete", [e["event"] for e in observed["events"]])

    def test_blocked_output_times_out_without_leaving_tools_alive(self):
        observed, _, diagnostic = self.run_case("output_backpressure")
        self.assertNotEqual(observed["code"], 0, diagnostic)
        self.assertIn("écriture", diagnostic)
        self.assertNotIn("complete", [e["event"] for e in observed["events"]])

    def test_tool_failure_output_limits_changed_tool_or_global_deadline_are_terminal(self):
        for scenario in ("helper_exit", "stdout_overflow", "stderr_overflow", "tool_changed", "global_deadline"):
            with self.subTest(scenario=scenario):
                observed, _, diagnostic = self.run_case(scenario)
                self.assertNotEqual(observed["code"], 0, diagnostic)
                self.assertNotIn("complete", [e["event"] for e in observed["events"]])

    def test_signal_stops_tools_and_sigkill_leaves_three_owned_orphans_for_guard(self):
        for scenario, expected in (("signal", 143), ("crash", -9)):
            with self.subTest(scenario=scenario):
                observed, _, diagnostic = self.run_case(scenario)
                self.assertEqual(observed["code"], expected, diagnostic)
                self.assertTrue(observed["killed"])
                self.assertEqual(observed["reaped"], 3 if scenario == "crash" else 0)
                self.assertNotIn("complete", [e["event"] for e in observed["events"]])


if __name__ == "__main__":
    unittest.main()
