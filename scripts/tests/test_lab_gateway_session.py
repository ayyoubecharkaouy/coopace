"""Simulated network and protocol peer, with real processes and crashes.

Go's side of the protocol has separate real-pipe tests in labcontrol. Here the
existing recovery fixtures exercise the supervisor and its independent rollback.
"""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import test_lab_queue_recovery as previous
ROOT=previous.ROOT
spec=importlib.util.spec_from_file_location('test_session',ROOT/'scripts/lab_gateway_session.py')
model=importlib.util.module_from_spec(spec);spec.loader.exec_module(model)

PEER=r'''
import json,os,struct,sys,time
control,events,journal=map(int,sys.argv[1:4]);scenario=sys.argv[4]
def receive():
    prefix=os.read(control,4)
    if not prefix:raise SystemExit(1)
    size=struct.unpack('>I',prefix)[0];raw=b''
    while len(raw)<size:
        block=os.read(control,size-len(raw))
        if not block:raise SystemExit(1)
        raw+=block
    return json.loads(raw)
init=receive();token=init['session_id'];seq=0;start=time.monotonic_ns()
def record(event,data):
    global seq
    seq+=1
    row={'schema_version':1,'kind':'gateway_session_worker_journal','session_id':token,'sequence':seq,
         'event':event,'recorded_at':'2026-11-13T00:00:00Z','elapsed_ns':time.monotonic_ns()-start,'data':data}
    os.write(journal,(json.dumps(row)+'\n').encode());os.fsync(journal)
record('launch',{'operator_uid':os.getuid(),'network_changes_executed':False})
if not init['local_lab_consent']:raise SystemExit(1)
def event(n,phase,sha=None):
    row={'schema_version':1,'kind':'gateway_session_event','session_id':token,'sequence':n,'phase':phase,'before_sha256':init['before_sha256']}
    if sha is not None:row['snapshot_sha256']=sha
    if scenario=='wrong_event' and phase=='applied':row['session_id']='foreign1'
    if scenario=='numeric_alias' and phase=='ready':row['sequence']=True
    record(phase,row);raw=json.dumps(row).encode();os.write(events,struct.pack('>I',len(raw))+raw)
event(1,'ready');assert receive()['action']=='begin';event(2,'apply_requested')
if scenario=='peer_died':raise SystemExit(7)
command=receive();assert command['action']=='applied';event(3,'applied',command['snapshot_sha256'])
assert receive()['action']=='stop';event(4,'release_requested')
if scenario=='extra_event':event(5,'release_requested')
record('worker_exit',{'awaiting_supervisor_recovery':True,'succeeded':True})
'''

INJECTION=r'''
spec=importlib.util.spec_from_file_location('session',root/'scripts/lab_gateway_session.py')
session=importlib.util.module_from_spec(spec);spec.loader.exec_module(session)
class Pilot(session.Pilot):
    def start(self):
        calls.append(['driver_start'])
        cr,cw=os.pipe2(os.O_CLOEXEC);er,ew=os.pipe2(os.O_CLOEXEC)
        self.keep(cr);self.control=self.keep(cw);self.events=self.keep(er);self.keep(ew)
        fd=self.keep(os.open(self.evidence.folder/'worker.jsonl',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_APPEND,0o600))
        st=os.fstat(fd);self.journal_identity=st.st_dev,st.st_ino
        self.evidence.record('session_launch_intent',session_id=self.token,operator_uid=self.uid,
            local_lab_consent=self.consent,bootstrap_sha256=r.digest(session.BOOTSTRAP.encode()))
        self.owner.child=subprocess.Popen([sys.executable,'-I','-c',PEER,str(cr),str(ew),str(fd),scenario],
            pass_fds=(cr,ew,fd),stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
        for source in (cr,ew,fd):os.close(source);self.fds.remove(source)
        for source in (self.control,self.events,self.owner.child.stdout.fileno(),self.owner.child.stderr.fileno()):os.set_blocking(source,False)
        dev,ino=dict(self.owner.owned)[self.engine.gateway]
        self.send({'schema_version':1,'kind':'gateway_session_init','session_id':self.token,'scope':'owned_lab',
            'reference':'cake-ipv4-lab-4mbit-v1','local_lab_consent':self.consent,'operator_uid':self.uid,
            'namespace_identity':{'device':dev,'inode':ino},'before_path':str(self.evidence.folder/'before.json'),
            'before_sha256':self.evidence.files['before.json']})
    def close(self):
        super().close()
        if scenario=='journal_failure':raise session.runtime.Error('injected evidence failure')
session.Pilot=Pilot
'''
HARNESS=(previous.HARNESS
 .replace('namespaces=Namespaces();runner=Runner();namespaces.runner=runner',
          'PEER='+repr(PEER)+'\n'+INJECTION+'\nnamespaces=Namespaces();runner=Runner();namespaces.runner=runner')
 .replace("evidence.save('environment.json',{'simulation':True,'tools':tools.specs,'tool_descriptors':tools.files,'source_sha256':model.source_hashes()})",
          "tools.specs['worker']=dict(tools.specs['gateway'])\nevidence.save('environment.json',{'kind':'lab_gateway_session_environment','simulation':True,'tools':tools.specs,'tool_descriptors':tools.files,'source_sha256':session.source_hashes()})")
 .replace('result=model.cycle(mode,owner,engine,evidence)','result=session.cycle(mode,owner,engine,evidence,scenario!="no_consent")'))

class SessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build=tempfile.TemporaryDirectory(prefix='coopace-session-tests-');cls.binary=str(Path(cls.build.name)/'coopace-gateway')
        subprocess.run(['sh','scripts/go.sh','build','-o',cls.binary,'./apps/gateway/cmd/coopace-gateway'],cwd=ROOT,check=True)
    @classmethod
    def tearDownClass(cls):cls.build.cleanup()
    def control(self,scenario='ok',mode='check'):
        temporary=tempfile.TemporaryDirectory(prefix='coopace-session-case-');self.addCleanup(temporary.cleanup)
        folder=Path(temporary.name)
        result=subprocess.run([sys.executable,'-I','-B','-c',HARNESS,str(ROOT),str(folder),self.binary,mode,scenario],capture_output=True,text=True,timeout=25)
        self.assertEqual(result.returncode,0,result.stderr)
        report=json.loads(result.stdout);calls=json.loads((folder/'calls.json').read_text())
        self.assertTrue(report['cleanup_verified'],report);self.assertFalse(Path(report['workspace']).exists())
        self.assertEqual(list((folder/'namespaces').iterdir()),[])
        if report['driver_pid']:self.assertFalse(Path('/proc',str(report['driver_pid'])).exists())
        return report,calls,folder/'artifacts'
    def test_normal_and_crash_with_readonly_replay(self):
        review=model.runtime.sibling('test_session_review','lab_gateway_session_review.py')
        for mode,code in (('check',0),('check-crash',-9)):
            with self.subTest(mode=mode):
                report,calls,folder=self.control(mode=mode)
                self.assertEqual(report['state'],'complete',report);self.assertEqual(report['driver_exit_code'],code)
                self.assertEqual(report['session_state'],'restored_and_closed');self.assertEqual(report['reaped_descendants'],0)
                operations=[row[0] for row in calls]
                self.assertLess(operations.index('driver_start'),operations.index('tc_add'));self.assertLess(operations.index('tc_del'),operations.index('ns_del'))
                value=review.review(folder,self.binary)
                self.assertTrue(value['protocol_verified']);self.assertFalse(value['native_certificate']);self.assertEqual(value['execution_source'],'simulated')
    def test_no_consent_never_applies(self):
        for scenario in ('no_consent','numeric_alias'):
            with self.subTest(scenario=scenario):
                report,calls,_=self.control(scenario);self.assertEqual(report['state'],'failed')
                self.assertFalse(any(row[0] in ('tc_add','tc_del') for row in calls))
    def test_faults_still_recover(self):
        for scenario in ('peer_died','wrong_event','journal_failure','add_failed_after','interrupt_after_add','extra_event'):
            with self.subTest(scenario=scenario):
                report,calls,_=self.control(scenario);self.assertEqual(report['state'],'failed',report)
                self.assertTrue(report['restoration_verified'],report);self.assertTrue(any(row[0]=='tc_del' for row in calls))
    def test_foreign_state_is_not_removed(self):
        for scenario in ('foreign_root','filter_before_restore','identity_changed','delete_failure'):
            with self.subTest(scenario=scenario):
                report,calls,_=self.control(scenario);self.assertEqual(report['state'],'failed');self.assertFalse(report['restoration_verified'])
                if scenario!='delete_failure':self.assertFalse(any(row[0]=='tc_del' for row in calls))
    def test_review_rejects_rebound_dialogue_with_updated_hash(self):
        review=model.runtime.sibling('test_session_review_tamper','lab_gateway_session_review.py')
        report,_,folder=self.control();frames=review.frames((folder/'control.frames').read_bytes());frames[0]['local_lab_consent']=False
        import struct
        raw=b''.join(struct.pack('>I',len(data))+data for data in [json.dumps(row).encode() for row in frames])
        (folder/'control.frames').write_bytes(raw);report['artifacts_sha256']['control.frames']=model.runtime.digest(raw)
        (folder/'report.json').write_text(json.dumps(report))
        with self.assertRaises(Exception):review.review(folder,self.binary)
    def test_cli_refuses_without_agreement_before_preflight(self):
        cli=model.runtime.sibling('test_session_cli','lab-gateway-session.py')
        with patch.object(cli.model.recovery.guards,'preflight') as native:
            with self.assertRaises(Exception):cli.run('check',Path('/missing'),Path('/missing'),Path('/missing'),False)
            native.assert_not_called()

if __name__=='__main__':unittest.main()
