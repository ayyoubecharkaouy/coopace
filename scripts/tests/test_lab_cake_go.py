"""Actual descriptor handoff and guarded processes; no namespace creation."""

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "lab_cake_go.py"
spec = importlib.util.spec_from_file_location("cake_go_tests", SOURCE)
model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)

FAKE_WORKER = r'''
import base64,datetime,json,os,signal,struct,subprocess,sys,time
source,root,scenario,token,tools=json.loads(sys.argv[1])
root=__import__('pathlib').Path(root)
spec=__import__('importlib.util',fromlist=['x']).spec_from_file_location('protocol',source)
p=__import__('importlib.util',fromlist=['x']).module_from_spec(spec);spec.loader.exec_module(p)
fixture=json.loads((__import__('pathlib').Path(source).parents[1]/'platforms/linux/testdata/cake/down.json').read_text())
(root/'proc'/str(os.getpid())).touch()
def identity(fd):
 s=os.fstat(fd);return {'device':s.st_dev,'inode':s.st_ino}
target,original=identity(5),identity(6)
seq=0;start=time.monotonic_ns()
def record(event,data=None):
 global seq
 seq+=1
 row={'schema_version':1,'kind':'lab_cake_worker_journal','session_id':token,'sequence':seq,'event':event,
 'recorded_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'elapsed_ns':time.monotonic_ns()-start,'data':data}
 os.write(7,json.dumps(row).encode()+b'\n');os.fsync(7)
def receive():
 def read(n):
  data=b''
  while len(data)<n:
   part=os.read(3,n-len(data))
   if not part:raise SystemExit(3)
   data+=part
  return data
 return json.loads(read(struct.unpack('!I',read(4))[0]))
def event(name):
 value={'schema_version':1,'kind':'lab_cake_worker_event','session_id':token,'event':name,'reference':p.REFERENCE}
 if name=='applied':value.update(producer_profile=p.cake.PROFILE,qdisc=fixture)
 if scenario=='wrong_session':value['session_id']='other123'
 os.write(4,p.encode(value,p.EVENT_LIMIT))
def calls(first,last):
 for index in range(first,last):
  tool,args=p.CALLS[index];meta={'path':tools[tool]['path'],'sha256':tools[tool]['sha256'],'arguments':args}
  record('tool_intent',meta)
  if scenario=='orphan' and index==0:
   child=subprocess.Popen([sys.executable,'-I','-c','import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);print("READY",flush=True);time.sleep(60)'],stdout=subprocess.PIPE)
   assert child.stdout.readline()==b'READY\n';child.stdout.close();(root/'proc'/str(child.pid)).touch();os.kill(os.getpid(),signal.SIGKILL)
  output=b'[]'
  if args==['-V']:output=b'tc utility, iproute2-6.1.0\n'
  if args==p.ADD:(root/'added').touch();output=b''
  if args==p.SHOW and index not in (3,6):output=json.dumps(fixture).encode()
  record('tool_result',{**meta,'started_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'duration_ns':1,
   'pid':os.getpid()+100000+index,'exit_code':0,'stdout_base64':base64.b64encode(output).decode(),'stderr_base64':None,
   'stdout_truncated':False,'stderr_truncated':False,'error':''})
record('launch',{'coopace_version':'fixture','build':{'go_version':'simulated'},'pid':os.getpid(),'os':'linux','architecture':'amd64',
 'purpose':'cake_down_control','reference':p.REFERENCE,'ip_tool':tools['ip'],'tc_tool':tools['tc'],'target_namespace':target,'original_namespace':original})
if scenario=='hang':time.sleep(60)
assert receive()['namespace_identity']==target
record('context_accepted',{'reference':p.REFERENCE});calls(0,4);record('ready')
if scenario=='bad_journal':
 path=root/'artifacts/worker.jsonl';rows=[json.loads(v) for v in path.read_text().splitlines()];rows[2]['data']['arguments']=['arbitrary'];path.write_text(''.join(json.dumps(v)+'\n' for v in rows))
if scenario=='oversize':os.write(4,struct.pack('!I',p.EVENT_LIMIT+1));time.sleep(60)
event('ready');assert receive()['action']=='apply';record('apply_received');calls(4,11)
record('applied',{'producer_profile':p.cake.PROFILE});event('applied')
assert receive()['action']=='finish';record('finish_received');calls(11,14);record('final_verified')
record('worker_exit',{'intended_exit_code':0,'backend_state':'finished','add_attempted':True,'error':'','cleanup':'not_attested','traffic_generated':False,'active_path_verified':False})
'''

HARNESS = r'''
import importlib.util,json,os,subprocess,sys
from pathlib import Path
source,root,scenario,mode,worker_code=Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3],sys.argv[4],sys.argv[5]
spec=importlib.util.spec_from_file_location('model',source);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
(root/'proc').mkdir();(root/'namespaces').mkdir();artifacts=root/'artifacts';artifacts.mkdir()
fixture=json.loads((source.parents[1]/'platforms/linux/testdata/cake/down.json').read_text())
class Namespaces(m.guards.Namespaces):
 def __init__(self):super().__init__(sys.executable,root/'namespaces');self.linked=False
 def command(self,action,name,timeout):
  path=self.directory/name
  if action=='add':path.touch()
  else:
   assert all(not Path('/proc',p.name).exists() for p in (root/'proc').iterdir()),'process alive at deletion'
   if scenario=='cleanup_failure' and name.endswith('-g'):raise OSError('simulated deletion failure')
   path.unlink()
 def execute(self,args,owner):
  if args==[self.ip,'-V']:return b'tc utility, iproute2-6.1.0\n'
  if '-n' in args:
   if 'add' in args:self.linked=True;return b''
   role='wan' if args[2].endswith('-g') else 'eth0'
   return json.dumps([{'ifname':'lo','flags':['LOOPBACK']}]+([{'ifname':role,'flags':[]}] if self.linked else [])).encode()
  if scenario=='post_read_failure' and owner.driver_code is not None:raise m.Error('post-exit read failed')
  return json.dumps(fixture if (root/'added').exists() else []).encode()
class Session(m.Session):
 def identity(self,fd):
  s=os.fstat(fd);return {'device':s.st_dev,'inode':s.st_ino} # namespace type is simulated
 def launch_args(self,sources):
  args=super().launch_args(sources)
  args[4]=args[4].replace('os.setns(5, os.CLONE_NEWNET)','') # only test entry is simulated; remapping/exec are real
  data=json.dumps([str(source.with_name('lab_cake_go_protocol.py')),str(root),scenario,self.token,self.tools])
  return args[:7]+['-I','-S','-c',worker_code,data]
try:
 result=m.run(mode,Namespaces(),sys.executable,sys.executable,artifacts,session_factory=Session,tempdir=root,timeout=0.6 if scenario=='hang' else 5)
 print(json.dumps(result))
except Exception as e:
 print(str(e),file=sys.stderr);raise SystemExit(1)
'''


@unittest.skipUnless(sys.platform == "linux", "Linux process supervision")
class GoGuardTests(unittest.TestCase):
    def run_case(self, scenario="normal", mode="check"):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = subprocess.run([sys.executable, "-I", "-B", "-c", HARNESS, str(SOURCE), str(root), scenario, mode, FAKE_WORKER],
                                    capture_output=True, text=True, timeout=12)
            for pid in (root / "proc").iterdir():
                self.assertFalse(Path("/proc", pid.name).exists(), result.stderr)
            report = json.loads((root / "artifacts/report.json").read_text())
            if scenario == "cleanup_failure":
                self.assertFalse(report["cleanup_verified"])
                self.assertTrue(list((root / "namespaces").iterdir()))
            else:
                self.assertTrue(report["cleanup_verified"], result.stderr)
                self.assertEqual(list((root / "namespaces").iterdir()), [])
                self.assertEqual(list(root.glob("coopace-guard.*")), [])
            return result, report

    def test_normal_and_crash_match_journal_and_real_exit_before_cleanup(self):
        for mode in ("check", "check-crash"):
            with self.subTest(mode=mode):
                result, report = self.run_case(mode=mode)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(report["state"], "complete")
                self.assertEqual(report["worker_exit_code"], -9 if mode.endswith("crash") else 0)
                self.assertEqual(report["journal"]["tool_calls"], 11 if mode.endswith("crash") else 14)
                self.assertFalse(report["traffic_generated"])

    def test_failure_timeout_orphan_and_cleanup_never_publish_success(self):
        for scenario in ("wrong_session", "oversize", "bad_journal", "hang", "orphan", "post_read_failure", "cleanup_failure"):
            with self.subTest(scenario=scenario):
                result, report = self.run_case(scenario)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertEqual(report["state"], "failed")
                if scenario == "orphan": self.assertEqual(report["reaped_descendants"], 1)

    def test_plan_is_inert(self):
        result = subprocess.run([sys.executable, "-I", "-B", str(SOURCE.with_name("lab-cake-go.py")), "plan"], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("aucun privilège", result.stdout)


class ProtocolTests(unittest.TestCase):
    def test_strict_events_reject_bad_types_session_and_extra_authority(self):
        p = model.protocol
        good = {"schema_version": 1, "kind": "lab_cake_worker_event", "session_id": "abcd1234", "event": "ready", "reference": p.REFERENCE}
        self.assertEqual(p.event(json.dumps(good).encode(), "abcd1234", "ready"), good)
        for field, value in (("schema_version", True), ("session_id", "other123"), ("cleanup_verified", True), ("event", "applied")):
            bad = {**good, field: value}
            with self.assertRaises(p.Error): p.event(json.dumps(bad).encode(), "abcd1234", "ready")
        for raw in (b'{"a":1,"a":2}', b'{"x":NaN}', b'{"x":1e999}', b'{} {}', b'\xff'):
            with self.assertRaises(p.Error): p.document(raw, 4096)


if __name__ == "__main__":
    unittest.main()
