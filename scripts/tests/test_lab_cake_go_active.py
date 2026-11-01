"""Complete handoff with a simulated kernel and real worker/traffic groups."""

from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import test_lab_active as flow_fixtures
import test_lab_cake_go_topology as topology_fixtures
import test_lab_cake_go_traffic as traffic_fixtures

SOURCE = topology_fixtures.SOURCE.with_name("lab_cake_go_active.py")
spec = importlib.util.spec_from_file_location("combined_model", SOURCE)
model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)

# Reuse the simulated kernel's observations, not a second implementation of it.
PREFIX = topology_fixtures.HARNESS[:topology_fixtures.HARNESS.index("kernel=Kernel();")]
HARNESS = PREFIX + r'''
import hashlib,stat,time
spec=importlib.util.spec_from_file_location('combined',source.with_name('lab_cake_go_active.py'))
combined=importlib.util.module_from_spec(spec);spec.loader.exec_module(combined)
base_execute=Kernel.execute
def execute(self,args,owner):
 raw=base_execute(self,args,owner)
 if args[1:5]==['-n',owner.owned[1][0],'link','add'] and args[5]=='wan':
  g=owner.owned[1][0]
  (root/'link-fixture.json').write_text(json.dumps(list(self.rows[g].values())))
  (root/'address-fixture.json').write_text(json.dumps([{**self.rows[g]['wan'],'addr_info':[]}]))
 if 'qdisc' in args and 'show' in args and self.forward:
  rows=json.loads(raw);started=(root/'first_write').exists()
  if owner.child is None:self.before_launch_bytes=rows[0]['bytes']
  if not started:self.before_traffic_bytes=rows[0]['bytes']
  if started:
   self.traffic_reads=getattr(self,'traffic_reads',0)+1
   if scenario=='traffic_counter_reset' and self.traffic_reads>1:rows[0]['bytes']=0
   if scenario=='never_empty':rows[0].update(backlog=1,qlen=1)
  if scenario=='no_progress' and owner.child is not None:rows[0]['bytes']=self.before_launch_bytes
  return json.dumps(rows).encode()
 if scenario=='link_changed_late' and (root/'probe_started').exists() and args[1]=='-n' and args[3:]==['-j','-d','link','show']:
  rows=json.loads(raw)
  if args[2].endswith('-g'):next(r for r in rows if r['ifname']=='wan')['mtu']=1400
  return json.dumps(rows).encode()
 return raw
Kernel.execute=execute
class Inventory(combined.Inventory):
 @staticmethod
 def fingerprint(path):
  path=Path(path).resolve(strict=True)
  return {'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
 def metadata(self):return {'tools':self.tools,'source_sha256':self.sources,'git_commit':self.commit,'versions':'simulated'}
class Collector(combined.collect.Collector):
 def helpers(self,pids):
  # PID, parent, group, session and start-time reads remain real. Only executable
  # roles and namespace identities are simulated for the Python stand-in tools.
  result=[]
  for i,(pid,args) in enumerate(zip(pids,combined.collect.expected_helpers(self.inventory.tools))):
   value=combined.collect.process_snapshot(pid)
   spec=self.inventory.tools['target' if i==0 else 'load']
   identity=self.topology.names[2 if i<2 else 0][1]
   value.update(executable=spec,arguments=args,network_namespace=list(identity))
   result.append(combined.collect.validate_helper(value,pid,self.owner.child.pid,identity,spec,args))
  return result
 def decide(self,crash):
  if not self.ready and b'\n' in self.pending:
   if scenario=='traffic_wrong_session':self.pending[:]=self.pending.replace(self.session.encode(),b'other123')
   if scenario=='foreign_pid':
    event=json.loads(self.pending[6:]);event['helper_pids'][0]=os.getpid()
    self.pending[:]=b'READY '+json.dumps(event).encode()+b'\n'
   if scenario=='early_flow':self.pending.extend(b'{}\n')
  return super().decide(crash)
base_write=combined.Journal.write
def write(self,event):
 if scenario=='ack_evidence_failure' and event['event']=='traffic_continue_intent':raise OSError('injected ack evidence failure')
 if scenario=='sample_evidence_failure' and event['event']=='traffic_sample' and event['reading']['phase']=='running':raise OSError('injected sample evidence failure')
 if scenario=='final_evidence_failure' and event['event']=='control_complete':raise OSError('injected final evidence failure')
 return base_write(self,event)
combined.Journal.write=write
kernel=Kernel();failure=None
try:
 result=combined.run(mode,kernel,sys.executable,sys.executable,sys.executable,root/'bin',artifacts,
                     tempdir=root,session_factory=Session,inventory_factory=Inventory,collector_factory=Collector,
                     timeout=.7 if scenario=='deadline' else 180)
 print(json.dumps(result))
except Exception as error:
 failure=str(error);print(failure,file=sys.stderr)
finally:
 state={'error':failure,'remaining_names':list(p.name for p in (root/'namespaces').iterdir()),'calls':kernel.calls}
 (root/'observed.json').write_text(json.dumps(state))
if failure:raise SystemExit(1)
'''


@unittest.skipUnless(sys.platform == "linux", "Linux owned process groups")
class CombinedTests(unittest.TestCase):
    def run_case(self, scenario="normal", mode="check"):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'bin').mkdir();(root/'pids').mkdir()
            docs=deepcopy(flow_fixtures.documents())
            if scenario=='all_failed':
                docs[2].update(successful=0,failed=10)
                for attempt in docs[2]['attempts']:attempt.update(connect_ms=None,failure='timeout')
            (root/'documents.json').write_text(json.dumps(docs))
            (root/'scenario').write_text('crash' if mode=='check-crash' else scenario)
            for name in ('coopace','coopace-lab-tcp','coopace-lab-load'):
                p=root/'bin'/name;p.write_text('#!'+sys.executable+'\n'+traffic_fixtures.HELPER);p.chmod(0o700)
            # The ELF Python used as fake ip runs this script instead of setns.
            (root/'netns').write_text('import os,sys\nassert sys.argv[1]=="exec"\nos.execv(sys.argv[3],sys.argv[3:])\n')
            process=subprocess.run([sys.executable,'-I','-B','-c',HARNESS,str(topology_fixtures.fixtures.SOURCE),
                                    directory,scenario,mode,topology_fixtures.WORKER],
                                   cwd=root,capture_output=True,text=True,timeout=22)
            self.assertTrue((root/'observed.json').exists(),process.stderr)
            observed=json.loads((root/'observed.json').read_text())
            path=root/'artifacts/report.json'
            self.assertTrue(path.exists(),process.stderr)
            report=json.loads(path.read_text())
            for folder in ('proc','pids'):
                for p in (root/folder).iterdir():self.assertFalse(Path('/proc',p.name).exists(),process.stderr)
            remaining=observed['remaining_names']
            self.assertEqual(len(remaining),1 if scenario=='cleanup_failure' else 0,process.stderr)
            self.assertEqual(report['cleanup_verified'],not remaining)
            journal=[json.loads(line) for line in (root/'artifacts/supervisor.jsonl').read_text().splitlines()]
            self.assertEqual([r['sequence'] for r in journal],list(range(1,len(journal)+1)))
            if process.returncode==0:
                self.assertEqual(json.loads(process.stdout)['state'],'complete')
                self.assertEqual(len(report['groups']),2)
                self.assertTrue(all(g['state']=='stopped' for g in report['groups']))
                self.assertEqual(report['go_phase']['worker_exit_code'],0)
            else:self.assertEqual(process.stdout,'')
            return process,report,journal,observed

    def test_normal_handoff_preserves_phase_and_collects_traffic_before_cleanup(self):
        process,report,journal,observed=self.run_case()
        self.assertEqual(process.returncode,0,process.stderr)
        self.assertEqual(report['state'],'complete')
        self.assertEqual(report['flow']['receive']['received_bytes'],8_388_608)
        self.assertEqual(report['flow']['latency']['successful'],10)
        self.assertTrue(report['traffic_generated'])
        self.assertEqual(report['traffic_group']['driver_exit_code'],0)
        self.assertEqual(report['go_phase']['cleanup'],'deferred_to_supervisor')
        self.assertGreater(report['traffic_statistics_delta']['counters']['bytes'],0)
        self.assertGreaterEqual(len(report['queue_samples']),4)
        running=[r for r in report['queue_samples'] if r['phase']=='running']
        self.assertTrue(all(b['elapsed_since_start_ms']-a['elapsed_since_start_ms']>=250 for a,b in zip(running,running[1:])))
        drains=[r for r in report['queue_samples'] if r['phase']=='drain']
        self.assertGreaterEqual(drains[-1]['elapsed_since_start_ms']-drains[0]['elapsed_since_start_ms'],500)
        self.assertEqual(report['congestion'],'not_assessed')
        events=[r['data']['event'] for r in journal]
        self.assertLess(events.index('go_phase_finished'),events.index('activation_begin'))
        self.assertLess(events.index('activation_verified'),events.index('traffic_launch_intent'))
        self.assertLess(events.index('traffic_ready'),events.index('traffic_continue_intent'))
        self.assertFalse(any('qdisc' in a and any(k in a for k in ('add','replace','del')) for a in observed['calls']))
        self.assertLess(report['topology']['activation_statistics_delta']['counters']['bytes'],
                        report['traffic_statistics_delta']['counters']['bytes'])

    def test_crash_kills_only_traffic_driver_then_recovers_three_orphans(self):
        process,report,journal,_=self.run_case(mode='check-crash')
        self.assertEqual(process.returncode,0,process.stderr)
        self.assertEqual(report['traffic_group']['driver_exit_code'],-9)
        self.assertEqual(report['traffic_group']['reaped_descendants'],3)
        self.assertIsNone(report['flow'])
        self.assertTrue(report['cleanup_verified'])
        self.assertTrue(report['traffic_generated'])
        events=[r['data']['event'] for r in journal]
        self.assertIn('traffic_kill_intent',events)
        self.assertNotIn('traffic_continue_sent',events)
        self.assertEqual(report['queue_samples'][-1]['phase'],'after_crash_stop')

    def test_failure_evidence_identity_counters_and_cleanup_cannot_publish_success(self):
        for scenario in ('wrong_session','address_failure','traffic_wrong_session','foreign_pid','early_flow',
                         'traffic_counter_reset','no_progress','never_empty','link_changed_late',
                         'ack_evidence_failure','sample_evidence_failure','final_evidence_failure','cleanup_failure',
                         'helper_exit','deadline'):
            with self.subTest(scenario=scenario):
                process,report,_,_=self.run_case(scenario)
                self.assertNotEqual(process.returncode,0,process.stderr)
                self.assertEqual(report['state'],'failed')
                if scenario in ('wrong_session','address_failure'):
                    self.assertFalse(report['traffic_generated'])
                if scenario=='traffic_wrong_session':self.assertIsNone(report['traffic_generated'])

    def test_complete_collection_preserves_all_failed_probes(self):
        process,report,_,_=self.run_case('all_failed')
        self.assertEqual(process.returncode,0,process.stderr)
        self.assertEqual(report['flow']['latency']['failed'],10)
        self.assertFalse(report['flow']['has_successful_probe'])
        self.assertEqual(report['flow']['measurement_exit_code'],1)

    def test_plan_is_inert_and_check_requires_explicit_inputs(self):
        entry=SOURCE.with_name('lab-cake-go-active.py')
        for args,code in ((['plan'],0),(['check'],2)):
            p=subprocess.run([sys.executable,'-I','-B',str(entry),*args],capture_output=True,text=True,timeout=4)
            self.assertEqual(p.returncode,code,p.stderr)


class HelperIdentityTests(unittest.TestCase):
    def test_modified_or_replaced_capture_is_rejected(self):
        for replacement in (False,True):
            with self.subTest(replacement=replacement),tempfile.TemporaryDirectory() as directory:
                p=Path(directory)/'proof.bin';capture=model.collect.Capture(p,1024)
                capture.append(b'original');capture.close()
                if replacement:p.unlink()
                p.write_bytes(b'modified')
                with self.assertRaises(model.Error):capture.summary()

    def test_reject_wrong_group_namespace_executable_and_arguments(self):
        spec={'path':'/tool','sha256':'a'*64};args=['/tool','--listen','10.203.0.6:46001']
        good={'pid':20,'state':'S','parent':10,'group':10,'session':10,'start_ticks':30,
              'network_namespace':[4,50],'executable':spec,'arguments':args}
        model.collect.validate_helper(good,20,10,(4,50),spec,args)
        for key,value in (('pid',True),('state','Z'),('parent',11),('group',20),('session',11),
                          ('start_ticks',False),('network_namespace',[4,51]),('executable',{}),('arguments',[])):
            with self.subTest(key=key),self.assertRaises(model.Error):
                model.collect.validate_helper({**good,key:value},20,10,(4,50),spec,args)

    def test_process_snapshot_reads_actual_elf_child_without_reaping_it(self):
        child=subprocess.Popen([sys.executable,'-I','-c','import time;time.sleep(5)'])
        try:
            # The process may still be between fork and exec, so retry boundedly.
            import time
            deadline=time.monotonic()+2
            while True:
                value=model.collect.process_snapshot(child.pid)
                if value['executable']['path']==str(Path(sys.executable).resolve()):break
                self.assertLess(time.monotonic(),deadline)
            self.assertEqual(value['parent'],os.getpid())
            self.assertGreater(value['start_ticks'],0)
        finally:
            child.terminate();child.wait(timeout=2)


if __name__=='__main__':unittest.main()
