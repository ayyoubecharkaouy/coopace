"""Network/Go peer fixtures with real helper groups, SIGKILL and offline replay."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import test_lab_gateway_session as previous
import test_gateway_session_flow as flow_tests
ROOT=previous.ROOT
spec=importlib.util.spec_from_file_location('test_session_active',ROOT/'scripts/lab_gateway_session_active.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

LOAD_ACTIVE="""
spec=importlib.util.spec_from_file_location('active_session',root/'scripts/lab_gateway_session_active.py')
active=importlib.util.module_from_spec(spec);spec.loader.exec_module(active)
"""
FAKE_FLOW=r'''
class Flow:
    def __init__(self,owner,engine,evidence,pilot):
        self.owner,self.engine,self.evidence,self.pilot=owner,engine,evidence,pilot
        self.helpers=[];self.samples=[]
        self.report={'traffic_generated':False,'flow':None,'observed_with_live_helpers':False,'addresses_removed':False}
    def sample(self,label,volume,packets):
        value={'label':label,'bytes':volume,'packets':packets,'backlog':0,'qlen':0}
        fixture=json.loads((root/'platforms/linux/testdata/cake/down.json').read_text())
        fixture[0]['bytes']=volume;fixture[0]['packets']=packets
        evidence.save('flow-queue-%03d.json'%len(self.samples),fixture)
        self.samples.append(value);evidence.record('flow_sample',sample=value)
    def start(self):
        evidence.record('flow_addresses_verified');self.sample('before',0,0)
        for role in ('receiver','sender'):
            group=model.guards.processes.ProcessGroup();owner.process_groups.append(group)
            evidence.record('flow_launch_intent',role=role,namespace=self.engine.server if role=='receiver' else self.engine.gateway,arguments=[])
            child=subprocess.Popen([sys.executable,'-I','-c','import time;time.sleep(.2)'],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
            group.attach(child)
            helper=type('Helper',(),{'group':group,'child':child,'role':role})()
            self.helpers.append(helper);evidence.record('flow_launched',role=role,pid=child.pid)
        self.sample('during',65536,42)
        self.report.update(traffic_generated=True,observed_with_live_helpers=True)
        evidence.record('flow_observed_while_go_applied',pilot_pid=owner.child.pid,helper_pids=[h.child.pid for h in self.helpers])
        if scenario=='flow_failure':raise model.Error('injected transfer failure')
        if scenario=='flow_interrupt':os.kill(os.getpid(),signal.SIGTERM)
    def finish(self):
        import time
        self.owner.check();time.sleep(.3)
        self.sample('after',active.traffic.VOLUME+1024,3000)
        self.report['flow']={'send':SEND,'receive':RECEIVE};evidence.record('flow_complete',received_bytes=active.traffic.VOLUME)
    def stop(self):
        for helper in reversed(self.helpers):
            helper.group.stop(__import__('time').monotonic()+3)
            role=helper.role
            raw=(b'STARTED\n'+json.dumps(SEND).encode() if role=='sender' else ('READY '+active.traffic.TARGET+'\n').encode()+json.dumps(RECEIVE).encode())
            if mode=='check-crash' or scenario.startswith('flow_'):raw=raw.split(b'\n',1)[0]+b'\n'
            evidence.save('flow-'+role+'.stdout',raw);evidence.save('flow-'+role+'.stderr',b'')
            evidence.record('flow_group_stopped',role=role,pid=helper.child.pid,exit_code=helper.group.driver_code,reaped_descendants=helper.group.reaped_descendants)
    def deactivate(self):
        assert all(h.group.state=='stopped' for h in self.helpers)
        calls.append(['addresses_removed']);self.report['addresses_removed']=True;evidence.record('flow_addresses_removed')
'''
SEND,RECEIVE=flow_tests.reports()
HARNESS=(previous.HARNESS
 .replace('class Engine(model.Engine):',LOAD_ACTIVE+'\nclass Engine(active.Engine):')
 .replace('session.Pilot=Pilot','session.Pilot=Pilot\nSEND='+repr(SEND)+'\nRECEIVE='+repr(RECEIVE)+'\n'+FAKE_FLOW)
 .replace("'kind':'lab_gateway_session_environment'","'kind':'lab_gateway_session_active_environment'")
 .replace("'source_sha256':session.source_hashes()","'source_sha256':active.source_hashes()")
 .replace("tools.specs['worker']=dict(tools.specs['gateway'])","tools.specs['worker']=dict(tools.specs['gateway']);tools.specs['load']=dict(tools.specs['gateway'])")
 .replace('result=session.cycle(mode,owner,engine,evidence,scenario!="no_consent")',
          'result=active.cycle(mode,owner,engine,evidence,scenario!="no_consent",pilot_factory=Pilot,flow_factory=Flow)')
 .replace("        if tail==['-V']:","        if tail==['class','show','dev','wan']:\n            return (b'class htb 10:1 parent 10:\\n' if scenario=='foreign_class' else b'class cake 10:1 parent 10:\\n'),0\n        if tail==['-V']:")
 .replace("        if scenario=='filter_before_restore'", "        if scenario=='legacy_classes' and self.active and owner.process_group.state=='stopped':\n            row=source['snapshot']['readings'][2];row.clear();row.update(section='classes',tool='tc',path=tools.specs['tc']['path'],arguments=['-j','-s','-d','class','show','dev','wan'],started_at=at(7),finished_at=at(9),available=False,value=None,reason='non JSON legacy classes');source['partial']=True\n        if scenario=='filter_before_restore'"))

class ActiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build=tempfile.TemporaryDirectory(prefix='coopace-session-active-test-');cls.binary=str(Path(cls.build.name)/'gateway')
        subprocess.run(['sh','scripts/go.sh','build','-o',cls.binary,'./apps/gateway/cmd/coopace-gateway'],cwd=ROOT,check=True)
    @classmethod
    def tearDownClass(cls):cls.build.cleanup()
    def control(self,scenario='ok',mode='check'):
        temporary=tempfile.TemporaryDirectory(prefix='coopace-session-active-case-');self.addCleanup(temporary.cleanup)
        folder=Path(temporary.name)
        completed=subprocess.run([sys.executable,'-I','-B','-c',HARNESS,str(ROOT),str(folder),self.binary,mode,scenario],capture_output=True,text=True,timeout=25)
        self.assertEqual(completed.returncode,0,completed.stderr)
        r=json.loads(completed.stdout);calls=json.loads((folder/'calls.json').read_text())
        self.assertTrue(r['cleanup_verified'],r);self.assertFalse(Path(r['workspace']).exists())
        self.assertEqual(list((folder/'namespaces').iterdir()),[])
        for pid in [r.get('driver_pid'),*[h['pid'] for h in r.get('flow_groups',[])]]:
            if pid:self.assertFalse(Path('/proc',str(pid)).exists())
        return r,calls,folder/'artifacts'
    def test_normal_crash_and_legacy_class_evidence(self):
        review=m.runtime.sibling('test_active_review','lab_gateway_session_active_review.py')
        for mode,scenario in (('check','ok'),('check-crash','ok'),('check','legacy_classes')):
            with self.subTest(mode=mode,scenario=scenario):
                r,calls,folder=self.control(scenario,mode)
                self.assertEqual(r['state'],'complete',r);self.assertTrue(r['restoration_verified'])
                self.assertEqual(r['driver_exit_code'],-9 if mode=='check-crash' else 0)
                ops=[v[0] for v in calls];self.assertLess(ops.index('addresses_removed'),ops.index('tc_del'))
                value=review.review(folder,self.binary);self.assertTrue(value['protocol_verified']);self.assertEqual(value['execution_source'],'simulated')
                self.assertFalse(value['native_certificate'])
                snap=json.loads((folder/'pre-restore.json').read_text());self.assertEqual(snap['partial'],scenario=='legacy_classes')
    def test_transfer_failure_and_interruption_restore_without_success(self):
        for scenario in ('flow_failure','flow_interrupt','journal_failure','add_failed_after'):
            with self.subTest(scenario=scenario):
                r,_,_=self.control(scenario);self.assertEqual(r['state'],'failed');self.assertTrue(r['restoration_verified'],r)
    def test_foreign_class_filter_or_identity_is_not_removed(self):
        for scenario in ('foreign_class','filter_before_restore','identity_changed','foreign_root'):
            with self.subTest(scenario=scenario):
                r,calls,_=self.control(scenario);self.assertEqual(r['state'],'failed')
                self.assertFalse(r['restoration_verified']);self.assertNotIn('tc_del',[v[0] for v in calls])
    def test_no_consent_never_starts_transfer(self):
        r,calls,_=self.control('no_consent');self.assertEqual(r['state'],'failed')
        self.assertNotIn('flow_groups',r);self.assertNotIn('tc_add',[v[0] for v in calls])
    def test_replay_rejects_missing_transfer_even_with_rehashed_file(self):
        review=m.runtime.sibling('test_active_tamper','lab_gateway_session_active_review.py')
        r,_,folder=self.control();data=(folder/'flow-receiver.stdout').read_bytes().replace(str(m.traffic.VOLUME).encode(),b'1')
        (folder/'flow-receiver.stdout').write_bytes(data);r['artifacts_sha256']['flow-receiver.stdout']=m.runtime.digest(data)
        (folder/'report.json').write_text(json.dumps(r))
        with self.assertRaises(Exception):review.review(folder,self.binary)

if __name__=='__main__':unittest.main()
