"""Recovery state machine with simulated networking, real Go and real crashes."""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("test_recovery_model", ROOT/"scripts/lab_queue_recovery.py")
model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)

HARNESS = r'''
import copy, importlib.util, json, os, signal, subprocess, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
root,folder,binary,mode,scenario=Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3],sys.argv[4],sys.argv[5]
spec=importlib.util.spec_from_file_location('recovery',root/'scripts/lab_queue_recovery.py')
model=importlib.util.module_from_spec(spec);spec.loader.exec_module(model)
r=model.runtime
model.guards.enable_subreaper()
artifacts=folder/'artifacts';artifacts.mkdir()
evidence=r.Evidence(artifacts)
calls=[]
class Tools:
    specs={'ip':{'path':'/tools/ip','sha256':'0'*64},'tc':{'path':'/tools/tc','sha256':'0'*64},
           'gateway':{'path':binary,'sha256':r.digest(r.read(binary,64*1024*1024))},
           'python':{'path':sys.executable,'sha256':'0'*64}}
    files={'ip':3,'tc':4,'gateway':5,'python':6}
    def verify(self,*args):pass
    def executable(self,name):return '/proc/self/fd/'+str(self.files[name])
tools=Tools()
class Namespaces(model.guards.Namespaces):
    def __init__(self):super().__init__('/tools/ip',folder/'namespaces');self.directory.mkdir();self.runner=None
    def command(self,action,name,timeout):
        calls.append(['ns_'+action,name])
        path=self.directory/name
        if action=='add':path.mkdir()
        else:
            assert owner.process_group.state=='stopped'
            path.rmdir()
class Owner(model.guards.Guard):
    def start_pinned_driver(self,tools,gateway,mode):
        calls.append(['driver_start'])
        if scenario=='driver_failure':
            code=model.guards.WORKER+'\nraise SystemExit(7)\n'
        else:code=model.guards.WORKER
        self.start([sys.executable,'-I','-c',code,mode])
class Runner:
    def __init__(self):self.tools=tools;self.active=False;self.created=False;self.up=set();self.n=0;self.captures=0
    def snapshot(self):
        source=json.loads((root/'docs/examples/queue-snapshot-noqueue.json').read_text().replace('lab0','wan'))
        start=datetime.now(timezone.utc)
        def at(us):return (start+timedelta(microseconds=us)).isoformat().replace('+00:00','Z')
        source['snapshot']['started_at']=at(0);source['snapshot']['finished_at']=at(20)
        for i,row in enumerate(source['snapshot']['readings']):
            row['started_at']=at(i*3+1);row['finished_at']=at(i*3+3);row['path']=tools.specs[row['tool']]['path']
            if 'classes_text_fallback' in row:
                row['classes_text_fallback']['started_at']=at(i*3+1);row['classes_text_fallback']['finished_at']=at(i*3+2)
        if self.active:
            source['snapshot']['readings'][1]['value']=json.loads((root/'platforms/linux/testdata/cake/down.json').read_text())
            source['snapshot']['readings'][0]['value'][0]['qdisc']='cake'
        if scenario=='filter_before_restore' and self.active and owner.process_group.state=='stopped':
            source['snapshot']['readings'][3]['value']=[{}]
        if scenario=='identity_changed' and self.active and owner.process_group.state=='stopped':
            source['snapshot']['interface']['hardware_address']='02:00:00:00:00:02'
        return json.dumps(source).encode()
    def dispatch(self,owner,tool,args,**options):
        if tool=='gateway':
            child=subprocess.run([binary,*args],capture_output=True)
            if child.returncode not in options.get('allowed',(0,)):raise model.Error(child.stderr.decode() or child.stdout.decode())
            return child.stdout,child.returncode
        assert tool=='ip'
        if args[:1]==['-n']:
            namespace=args[1];tail=args[2:]
            interface='wan' if namespace.endswith('-g') else 'eth0'
            if tail==['-j','-d','link','show']:
                rows=[{'ifname':'lo','flags':[]}]
                if self.created:rows.append({'ifname':interface,'flags':['UP'] if namespace in self.up else [],'linkinfo':{'info_kind':'veth'}})
                return json.dumps(rows).encode(),0
            if tail==['-j','address','show']:
                rows=[{'ifname':'lo','addr_info':[]}]
                if self.created:rows.append({'ifname':interface,'addr_info':[]})
                return json.dumps(rows).encode(),0
            if tail[:3]==['link','add','wan']:self.created=True;return b'',0
            if tail==['link','set','dev',interface,'up']:self.up.add(namespace);return b'',0
            raise AssertionError(args)
        assert args[:2]==['netns','exec']
        target=args[3];tail=args[4:]
        if target==tools.executable('python'):
            assert tail==['-I','-c',model.DISABLE_IPV6];return b'',0
        if target==tools.executable('gateway'):
            assert tail==['snapshot','--interface','wan','--json'];self.captures+=1;return self.snapshot(),0
        assert target==tools.executable('tc')
        if tail==['-V']:return b'tc utility, iproute2-6.1.0\n',0
        if tail==['-j','-s','-r','qdisc','show','dev','wan']:
            if scenario=='foreign_root' and owner.process_group.state=='stopped':
                return b'[{"kind":"fq_codel","handle":"20:","root":true}]',0
            return (root/'platforms/linux/testdata/cake/down.json').read_bytes(),0
        if tail[:2]==['qdisc','add']:
            assert tail==['qdisc','add','dev','wan','root','handle','10:',*model.cake.ARGUMENTS]
            calls.append(['tc_add'])
            if scenario=='add_failed_before':raise model.Error('injected add failure before change')
            self.active=True
            if scenario=='add_failed_after':raise model.Error('injected add failure after change')
            if scenario=='interrupt_after_add':os.kill(os.getpid(),signal.SIGTERM)
            return b'',0
        if tail[:2]==['qdisc','del']:
            assert tail==['qdisc','del','dev','wan','root','handle','10:']
            assert owner.process_group.state=='stopped'
            calls.append(['tc_del'])
            if scenario=='delete_failure':raise model.Error('injected delete failure')
            self.active=False;return b'',0
        raise AssertionError(args)
    def run(self,owner,tool,args,**options):
        self.n+=1;n=self.n;evidence.record('command_intent',command=n,tool=tool,arguments=args)
        try:
            output,code=self.dispatch(owner,tool,args,**options)
        except BaseException as error:
            evidence.record('command_result',command=n,pid=os.getpid(),exit_code=1,reaped_descendants=0,group_stopped=True,error=str(error));raise
        evidence.save(f'command-{n:03d}.stdout',output);evidence.save(f'command-{n:03d}.stderr',b'')
        evidence.record('command_result',command=n,pid=os.getpid(),exit_code=code,reaped_descendants=0,group_stopped=True,error=None)
        return output,code
class Engine(model.Engine):
    def retain(self):
        self.original='simulated'
        evidence.record('namespace_bindings_retained',origin_identity=[1,1],namespaces=[{'name':n,'identity':list(i)} for n,i in owner.owned])
    def binding(self):
        owner.check()
        for name,identity in owner.owned:
            assert owner.namespaces.identity(name)==identity
    def release(self):self.original=None
    def verify_driver_namespace(self):
        assert os.getpgid(owner.descendant)==owner.child.pid
        evidence.record('driver_namespace_verified',driver_pid=owner.child.pid,descendant_pid=owner.descendant,identity=list(owner.owned[1][1]))
namespaces=Namespaces();runner=Runner();namespaces.runner=runner
owner=Owner(namespaces,tempdir=folder,timeout=15)
evidence.save('environment.json',{'simulation':True,'tools':tools.specs,'tool_descriptors':tools.files,'source_sha256':model.source_hashes()})
engine=Engine(owner,runner,evidence)
result=model.cycle(mode,owner,engine,evidence)
(folder/'calls.json').write_text(json.dumps(calls))
print(json.dumps(result))
'''


class RecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory(prefix="coopace-recovery-tests-")
        cls.binary = str(Path(cls.build.name)/"coopace-gateway")
        subprocess.run(["sh","scripts/go.sh","build","-o",cls.binary,"./apps/gateway/cmd/coopace-gateway"],cwd=ROOT,check=True)

    @classmethod
    def tearDownClass(cls):
        cls.build.cleanup()

    def control(self, scenario="ok", mode="check"):
        temporary = tempfile.TemporaryDirectory(prefix="coopace-recovery-case-")
        self.addCleanup(temporary.cleanup)
        folder=Path(temporary.name)
        result=subprocess.run([sys.executable,"-I","-B","-c",HARNESS,str(ROOT),str(folder),self.binary,mode,scenario],
                              capture_output=True,text=True,timeout=25)
        self.assertEqual(result.returncode,0,result.stderr)
        report=json.loads(result.stdout)
        calls=json.loads((folder/"calls.json").read_text())
        self.assertTrue(report["cleanup_verified"],report)
        self.assertFalse(Path(report["workspace"]).exists())
        self.assertEqual(list((folder/"namespaces").iterdir()),[])
        for field in ("driver_pid","descendant_pid"):
            if report.get(field):self.assertFalse(Path("/proc",str(report[field])).exists())
        return report,calls,folder

    def test_normal_and_crash_restore_before_namespace_deletion(self):
        for mode,code in (("check",0),("check-crash",-9)):
            with self.subTest(mode=mode):
                report,calls,folder=self.control(mode=mode)
                self.assertEqual(report["state"],"complete",report)
                self.assertTrue(report["restoration_verified"])
                self.assertEqual(report["driver_exit_code"],code)
                self.assertEqual(report["reaped_descendants"],1)
                operations=[call[0] for call in calls]
                self.assertLess(operations.index("tc_add"),operations.index("driver_start"))
                self.assertLess(operations.index("tc_del"),operations.index("ns_del"))
                comparison=json.loads((folder/"artifacts/comparison.json").read_text())
                self.assertEqual(comparison["decision"],"selected_state_matches")

    def test_uncertain_add_attempt_is_recovered_without_blind_deletion(self):
        for scenario,removed in (("add_failed_before",False),("add_failed_after",True),("interrupt_after_add",True)):
            with self.subTest(scenario=scenario):
                report,calls,_=self.control(scenario)
                self.assertEqual(report["state"],"failed")
                self.assertEqual(any(call[0]=="tc_del" for call in calls),removed)
                self.assertEqual(report["restoration_verified"],removed)

    def test_changed_configuration_or_identity_is_never_deleted(self):
        for scenario in ("foreign_root","filter_before_restore","identity_changed"):
            with self.subTest(scenario=scenario):
                report,calls,_=self.control(scenario)
                self.assertEqual(report["state"],"failed")
                self.assertFalse(report["restoration_verified"])
                self.assertFalse(any(call[0]=="tc_del" for call in calls))

    def test_driver_failure_and_delete_failure_do_not_claim_success(self):
        for scenario,restored in (("driver_failure",True),("delete_failure",False)):
            with self.subTest(scenario=scenario):
                report,_calls,_folder=self.control(scenario)
                self.assertEqual(report["state"],"failed")
                self.assertEqual(report["restoration_verified"],restored)

    def test_owned_root_rejects_unknown_options_blocks_and_handles(self):
        fixture=json.loads((ROOT/"platforms/linux/testdata/cake/down.json").read_text())
        self.assertTrue(model.owned_cake(json.dumps(fixture).encode()))
        import copy
        for key,value in (("handle","20:"),("ingress_block",42),("options",{**fixture[0]["options"],"unknown":True})):
            changed=copy.deepcopy(fixture);changed[0][key]=value
            with self.assertRaises(model.Error):model.owned_cake(json.dumps(changed).encode())

    def test_plan_does_not_create_resources(self):
        result=subprocess.run([sys.executable,"-I","-B",str(ROOT/"scripts/lab-queue-recovery.py"),"plan"],capture_output=True,text=True,check=True)
        self.assertIn("Aucune interface physique",result.stdout)

    def test_review_replays_both_modes_without_native_certificate(self):
        review=model.runtime.sibling('test_recovery_review','lab_queue_recovery_review.py')
        for mode in ('check','check-crash'):
            with self.subTest(mode=mode):
                _report,_calls,folder=self.control(mode=mode)
                value=review.review(folder/'artifacts',self.binary)
                self.assertEqual(value['state'],'queue_recovery_evidence_reviewed')
                self.assertFalse(value['native_certificate'])
                self.assertEqual(value['execution_source'],'simulated')

    def test_review_rejects_changed_bytes_and_wrong_remove_command(self):
        review=model.runtime.sibling('test_recovery_review_tamper','lab_queue_recovery_review.py')
        _report,_calls,folder=self.control()
        artifacts=folder/'artifacts'
        with (artifacts/'after.json').open('ab') as stream:stream.write(b' ')
        with self.assertRaises(Exception):review.review(artifacts,self.binary)
        report,_calls,folder=self.control()
        artifacts=folder/'artifacts'
        events=[json.loads(line) for line in (artifacts/'events.jsonl').read_text().splitlines()]
        for event in events:
            args=event.get('arguments',[])
            if event.get('state')=='command_intent' and 'del' in args and 'qdisc' in args:args[-1]='20:'
        raw=('\n'.join(json.dumps(event) for event in events)+'\n').encode()
        (artifacts/'events.jsonl').write_bytes(raw)
        report['artifacts_sha256']['events.jsonl']=model.runtime.digest(raw)
        (artifacts/'report.json').write_text(json.dumps(report))
        with self.assertRaises(Exception):review.review(artifacts,self.binary)


if __name__ == "__main__":
    unittest.main()
