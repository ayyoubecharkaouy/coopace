"""Strict pipe protocol and real processes; no sockets, namespaces or qdiscs."""

from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import test_lab_active as fixtures

SOURCE = fixtures.SOURCE.with_name("lab_cake_go_traffic.py")
SPEC = importlib.util.spec_from_file_location("traffic", SOURCE)
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)
SESSION = "traffic1"

HELPER = r'''
import json,os,signal,sys,time
from pathlib import Path
root=Path(__file__).resolve().parents[1]
assert os.readlink('/proc/self/fd/0')=='/dev/null','helper inherited the control pipe'
name=Path(sys.argv[0]).name
scenario=(root/'scenario').read_text()
if scenario=='crash':signal.signal(signal.SIGTERM,signal.SIG_IGN)
if scenario=='bad_group' and name=='coopace-lab-load' and sys.argv[1]=='receive':os.setsid()
(root/'pids'/str(os.getpid())).write_text(json.dumps({'args':sys.argv,'group':os.getpgrp()}))
docs=json.loads((root/'documents.json').read_text())
if name=='coopace-lab-tcp':
 print('READY 10.203.0.6:46001',flush=True)
 while True:time.sleep(.02)
elif name=='coopace-lab-load':
 sending=sys.argv[1]=='send'
 if sending:(root/'first_write').write_text(str(time.monotonic()))
 print('STARTED' if sending else 'READY 10.203.0.6:46002',flush=True)
 if sending and scenario=='helper_exit':raise SystemExit(7)
 while not (root/'probe_started').exists():time.sleep(.01)
 print(json.dumps(docs[0 if sending else 1]),flush=True)
else:
 (root/'probe_started').write_text(str(time.monotonic()))
 if scenario=='bad_flow':docs[1]['received_bytes']=1
 print(json.dumps(docs[2]),flush=True)
 raise SystemExit(1 if scenario=='all_failed' else 0)
'''

HARNESS = r'''
import importlib.util,json,os,signal,subprocess,sys,time
from pathlib import Path
source,root,scenario=Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3]
spec=importlib.util.spec_from_file_location('traffic',source);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
groups=m.active.sibling('test_group','lab_process_group.py')
m.active.guard_module.enable_subreaper()
group=groups.ProcessGroup();raw=bytearray();ready=None;sent=False;later=None;first_received=None
args=[sys.executable,'-I','-B',str(source.with_name('lab-cake-go-traffic.py')),
      '--session-id','traffic1','--client','cg-traffic1-c','--server','cg-traffic1-s',
      '--ip',str(root/'ip'),'--binaries',str(root/'bin')]
with (root/'stderr').open('wb') as errors:
 child=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=errors,start_new_session=True)
 group.attach(child);os.set_blocking(child.stdout.fileno(),False)
 if scenario=='preack':os.write(child.stdin.fileno(),m.continue_frame('traffic1'))
 if scenario=='early_eof':child.stdin.close()
 deadline=time.monotonic()+10
 try:
  while True:
   assert time.monotonic()<deadline,'driver deadline in test'
   try:data=os.read(child.stdout.fileno(),8192)
   except BlockingIOError:data=b''
   raw.extend(data)
   if ready is None and b'\n' in raw:
    line,rest=raw.split(b'\n',1);ready=m.parse_ready(bytes(line)+b'\n','traffic1');raw=bytearray(rest)
    first_received=time.monotonic()
    assert len(list((root/'pids').iterdir()))==3,'fourth helper before acknowledgement'
    assert not (root/'probe_started').exists(),'probe before acknowledgement'
    assert all(os.getpgid(pid)==child.pid for pid in ready['helper_pids'])
    time.sleep(.10)
    assert not (root/'probe_started').exists(),'probe while withholding acknowledgement'
    ack=m.continue_frame('traffic1')
    if scenario=='crash':os.kill(child.pid,signal.SIGKILL)
    elif scenario=='interrupt':os.kill(child.pid,signal.SIGTERM)
    elif scenario in ('timeout','helper_exit'):pass
    elif scenario=='partial_eof':os.write(child.stdin.fileno(),ack[:-1]);child.stdin.close()
    elif scenario=='duplicate':os.write(child.stdin.fileno(),ack+ack)
    elif scenario=='late_duplicate':os.write(child.stdin.fileno(),ack);later=time.monotonic()+.15
    elif scenario=='split':
     mid=len(ack)//2;os.write(child.stdin.fileno(),ack[:mid]);time.sleep(.08)
     assert not (root/'probe_started').exists();os.write(child.stdin.fileno(),ack[mid:])
    elif scenario=='wrong_session':os.write(child.stdin.fileno(),m.continue_frame('other123'))
    elif scenario=='oversized':os.write(child.stdin.fileno(),b' '*1024+b'\n')
    else:
     os.write(child.stdin.fileno(),ack)
     if scenario=='ack_eof':child.stdin.close()
   if later is not None and time.monotonic()>=later:
    os.write(child.stdin.fileno(),m.continue_frame('traffic1'));later=None
   if group.exited():
    # The leader stays unreaped until the last collective signal.
    if scenario=='crash':
     assert ready is not None
     assert all(Path('/proc',str(pid)).exists() for pid in ready['helper_pids'])
    while True:
     try:data=os.read(child.stdout.fileno(),8192)
     except BlockingIOError:break
     if not data:break
     raw.extend(data)
    break
   time.sleep(.005)
 finally:group.stop(time.monotonic()+3)
 stderr=(root/'stderr').read_text()
 pids=[int(p.name) for p in (root/'pids').iterdir()]
 assert all(not Path('/proc',str(pid)).exists() for pid in pids),'unreaped helper'
 assert not Path('/proc',str(child.pid)).exists(),'unreaped driver'
 flow=m.parse_flow(bytes(raw),'traffic1') if raw else None
 if (root/'probe_started').exists():
  assert float((root/'probe_started').read_text())-float((root/'first_write').read_text())>=1
 print(json.dumps({'code':group.driver_code,'reaped':group.reaped_descendants,
                   'ready':ready,'flow':flow,'probed':(root/'probe_started').exists(),
                   'helpers':len(pids),'stderr':stderr}))
'''


class ProtocolTests(unittest.TestCase):
    def test_parent_inventory_is_bound_to_session_and_rechecked_at_each_start(self):
        with tempfile.TemporaryDirectory() as directory:
            tools={}
            for name in ('ip','agent','target','load'):
                p=Path(directory)/name;p.write_bytes(b'#!/bin/sh\nexit 0\n');p.chmod(0o700)
                tools[name]={'path':str(p.resolve()),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
            value={'schema_version':1,'kind':'lab_cake_go_active_tools','session_id':SESSION,'tools':tools}
            inventory=m.ToolSet(json.dumps(value),SESSION)
            for args in inventory.commands:inventory.before_start(args)
            wrong=list(inventory.commands[0]);wrong[3]='cg-other123-s'
            with self.assertRaises(m.Error):inventory.before_start(wrong)
            Path(tools['agent']['path']).write_bytes(b'changed')
            with self.assertRaisesRegex(m.Error,'modifié'):inventory.before_start(inventory.commands[3])
            for change in ({**value,'session_id':'other123'},{**value,'extra':True},
                           {**value,'schema_version':True},{**value,'tools':{'ip':tools['ip']}}):
                with self.subTest(change=change),self.assertRaises(m.Error):m.ToolSet(json.dumps(change),SESSION)

    def test_ready_and_continue_are_strict_session_bound_lines(self):
        self.assertEqual(m.parse_ready(m.ready_frame(SESSION, [11, 22, 33]), SESSION)["helper_pids"], [11,22,33])
        self.assertEqual(m.parse_continue(m.continue_frame(SESSION), SESSION)["action"], "continue")
        for value in ("bad", "toolong12", "../test1", "Traffic1", True):
            with self.subTest(session=value), self.assertRaises(m.Error):
                m.continue_frame(value)
        for pids in ([1,1,2], [True,2,3], [0,2,3], [1,2], [1,2,3,4], [[],2,3]):
            with self.subTest(pids=pids), self.assertRaises(m.Error):
                m.ready_frame(SESSION,pids)

    def test_unknown_duplicate_wrong_types_and_truncated_frames_fail(self):
        valid=m.continue_frame(SESSION)
        value=json.loads(valid)
        cases=[valid[:-1],valid+valid,valid+b' ',b'\xff\n',b'{}\n',b'[]\n',b' '*1024+b'\n',
               valid.replace(b'"schema_version":1',b'"schema_version":1,"schema_version":1')]
        for key,new in (("schema_version",True),("schema_version",1.0),("kind","other"),
                         ("session_id","other123"),("action","stop"),("extra",1)):
            cases.append(m.frame({**value,key:new}))
        for raw in cases:
            with self.subTest(raw=raw[:90]), self.assertRaises(m.Error):
                m.parse_continue(raw,SESSION)
        ready=m.ready_frame(SESSION,[1,2,3])
        for raw in (ready[:-1],ready+ready,b'READY '+b' '*1017+b'\n',ready.replace(b'"helper_pids":[1,2,3]',b'"helper_pids":[true,2,3]')):
            with self.subTest(raw=raw[:90]), self.assertRaises(m.Error):
                m.parse_ready(raw,SESSION)

    def test_exact_frame_limit_includes_newline_and_ready_prefix(self):
        control=m.continue_frame(SESSION)
        padded=control[:-1]+b' '*(m.FRAME_LIMIT-len(control))+b'\n'
        self.assertEqual(len(padded),1024)
        m.parse_continue(padded,SESSION)
        with self.assertRaises(m.Error):m.parse_continue(padded[:-1]+b' \n',SESSION)
        ready=m.ready_frame(SESSION,[1,2,3])
        padded=ready[:-1]+b' '*(1024-len(ready))+b'\n'
        m.parse_ready(padded,SESSION)
        with self.assertRaises(m.Error):m.parse_ready(padded[:-1]+b' \n',SESSION)

    def test_flow_recomputes_flags_and_preserves_failed_attempts(self):
        docs=fixtures.documents()
        flow=m.active.flow_documents(*(json.dumps(d).encode() for d in docs),0)
        self.assertEqual(m.parse_flow(m.flow_frame(SESSION,flow),SESSION),flow)
        for key,value in (("has_successful_probe",False),("probe_window_inside_application_writes",1),
                          ("measurement_exit_code",False),("extra",1)):
            with self.subTest(key=key),self.assertRaises(m.Error):m.flow_frame(SESSION,{**flow,key:value})
        docs[2].update(successful=0,failed=10)
        for attempt in docs[2]["attempts"]:attempt.update(connect_ms=None,failure="timeout")
        failed=m.active.flow_documents(*(json.dumps(d).encode() for d in docs),1)
        self.assertFalse(m.parse_flow(m.flow_frame(SESSION,failed),SESSION)["has_successful_probe"])
        with self.assertRaises(m.Error):m.parse_flow(m.flow_frame(SESSION,flow),'other123')

    def test_stdout_backpressure_budget_and_runner_deadlines_are_bounded(self):
        rd,wr=os.pipe();out_rd,out_wr=os.pipe()
        try:
            channel=m.Channel(SESSION,rd,out_wr);runner=m.TrafficRunner(channel)
            channel.state="waiting"
            while True:
                try:os.write(out_wr,b'x'*4096)
                except BlockingIOError:break
            with self.assertRaisesRegex(m.Error,"écriture"):
                channel.send(b'blocked',runner,timeout=.04)
            channel.written=m.OUTPUT_LIMIT
            with self.assertRaisesRegex(m.Error,"volumineuse"):channel.send(b'x',runner)
            with patch.object(m.time,'monotonic',return_value=runner.ready_deadline+.01):
                with self.assertRaisesRegex(m.Error,'15s'):runner.check()
            runner.availability_announced=True
            with patch.object(m.time,'monotonic',return_value=runner.deadline+.01):
                with self.assertRaisesRegex(m.Error,'global'):runner.check()
        finally:
            for fd in (rd,wr,out_rd,out_wr):os.close(fd)


@unittest.skipUnless(sys.platform=='linux','Linux process-group supervision')
class DriverTests(unittest.TestCase):
    def run_case(self,scenario):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'bin').mkdir();(root/'pids').mkdir()
            docs=deepcopy(fixtures.documents())
            if scenario=='all_failed':
                docs[2].update(successful=0,failed=10)
                for attempt in docs[2]['attempts']:attempt.update(connect_ms=None,failure='timeout')
            if scenario=='bad_flow':docs[1]['received_bytes']=1
            (root/'documents.json').write_text(json.dumps(docs));(root/'scenario').write_text(scenario)
            for name in ('coopace','coopace-lab-tcp','coopace-lab-load'):
                p=root/'bin'/name;p.write_text('#!'+sys.executable+'\n'+HELPER);p.chmod(0o700)
            ip=root/'ip'
            ip.write_text('#!'+sys.executable+'\nimport os,sys\n'
                          'assert sys.argv[1:3]==["netns","exec"]\n'
                          'assert sys.argv[3] in ("cg-traffic1-c","cg-traffic1-s")\n'
                          'os.execv(sys.argv[4],sys.argv[4:])\n');ip.chmod(0o700)
            p=subprocess.run([sys.executable,'-I','-B','-c',HARNESS,str(SOURCE),directory,scenario],
                             capture_output=True,text=True,timeout=15)
            self.assertEqual(p.returncode,0,p.stderr)
            return json.loads(p.stdout)

    def test_normal_and_split_acknowledgement_launch_only_then_probe(self):
        for scenario in ('normal','split','ack_eof'):
            with self.subTest(scenario=scenario):
                value=self.run_case(scenario)
                self.assertEqual(value['code'],0,value['stderr'])
                self.assertEqual(value['helpers'],4)
                self.assertEqual(value['flow']['receive']['received_bytes'],8_388_608)
                self.assertTrue(value['flow']['probe_window_inside_application_writes'])
                self.assertEqual(value['reaped'],0)

    def test_no_ack_or_invalid_control_never_launches_the_probe(self):
        for scenario in ('timeout','partial_eof','duplicate','late_duplicate','wrong_session','oversized'):
            with self.subTest(scenario=scenario):
                value=self.run_case(scenario)
                self.assertEqual(value['code'],1,value['stderr'])
                self.assertFalse(value['probed'])
                self.assertIsNone(value['flow'])
                self.assertEqual(value['helpers'],3)

    def test_premature_control_eof_and_helper_failures_are_cleaned(self):
        for scenario in ('preack','early_eof','helper_exit','bad_group'):
            with self.subTest(scenario=scenario):
                value=self.run_case(scenario)
                self.assertEqual(value['code'],1,value['stderr'])
                self.assertFalse(value['probed'])
                if scenario!='helper_exit':self.assertIsNone(value['ready'])

    def test_driver_killed_while_waiting_leaves_three_helpers_for_the_supervisor(self):
        value=self.run_case('crash')
        self.assertEqual(value['code'],-9)
        self.assertEqual(value['reaped'],3)
        self.assertEqual(value['helpers'],3)
        self.assertFalse(value['probed'])
        self.assertIsNone(value['flow'])

    def test_signal_bad_receipt_and_failed_probes_remain_distinct(self):
        value=self.run_case('interrupt')
        self.assertEqual(value['code'],143,value['stderr']);self.assertFalse(value['probed'])
        value=self.run_case('bad_flow')
        self.assertEqual(value['code'],1,value['stderr']);self.assertIsNone(value['flow'])
        value=self.run_case('all_failed')
        self.assertEqual(value['code'],0,value['stderr'])
        self.assertEqual(value['flow']['latency']['failed'],10)
        self.assertEqual(value['flow']['measurement_exit_code'],1)
        self.assertFalse(value['flow']['has_successful_probe'])


if __name__=='__main__':
    unittest.main()
