"""Global replay: synthetic decisions and actual supervised crash evidence."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import patch

import test_lab_cake_go_campaign_review as phases

SOURCE=phases.fixtures.fixtures.SOURCE.with_name('lab_cake_go_campaign_native_review.py')
spec=importlib.util.spec_from_file_location('global_review_tests',SOURCE)
review=importlib.util.module_from_spec(spec);spec.loader.exec_module(review)


def policy_fixture(folder):
    report,rows,wire,tools,owned=phases.fixture(folder)
    tools['python']={'path':'/tools/python','sha256':'a'*64}
    report.update(environment={'binaries':'/tools'},go_phase={'worker_pid':999},flow=None,technical_valid=True,
                  groups=[{'driver_pid':999,'driver_exit_code':0,'reaped_descendants':0,'state':'stopped'},
                          {'driver_pid':10000,'driver_exit_code':0,'reaped_descendants':0,'state':'stopped'}],
                  congestion='not_assessed',comparison='not_assessed',coopace_benefit='not_assessed')
    report['traffic_group'].update(state='collected',driver_exit_code=0,reaped_descendants=0,traffic_generated=True,flow=None,interrupted_phase=None)
    for phase in report['phases']:
        for value in phase['result'].values():
            if isinstance(value,dict):value.update(go_version='simulated',os='linux',architecture='amd64')
    data=[r['data'] for r in rows];wire=[]
    for d in data:
        if d['event']=='campaign_driver_event':
            msg=d['message']
            if msg['event']=='end':msg['result']=deepcopy(next(p['result'] for p in report['phases'] if p['pair']==msg['pair'] and p['condition']==msg['condition']))
            raw=review.phases.wire._wire(msg);wire.append(raw)
            if msg['event']=='end':
                next(v for v in data if v['event']=='phase_end_observed' and v['pair']==msg['pair'] and v['condition']==msg['condition'])['line_sha256']=hashlib.sha256(raw).hexdigest()
    manifest={'schema_version':1,'kind':'lab_cake_go_campaign_tools','session_id':'traffic1','tools':{n:tools[n] for n in ('ip','agent','target','load')}}
    args=['/tools/python','-I','-B','-S',str(SOURCE.with_name('lab-cake-go-campaign-traffic.py')),'--session-id','traffic1',
          '--client',owned[0][0],'--server',owned[2][0],'--ip',tools['ip']['path'],'--binaries','/tools','--tools-json',json.dumps(manifest,separators=(',',':'))]
    rows.insert(0,{'data':{'event':'traffic_launch_intent','arguments':args}})
    report['assessment']=review.phases.assessment.assess(report['phases'])
    report.update(load_scenario=report['assessment']['load_scenario'],connections=report['assessment']['connections'])
    phases.write(folder,report,rows,wire)
    return report,tools,owned


class DecisionTests(unittest.TestCase):
    def test_native_positive_requirements_are_recomputed_from_phase_evidence(self):
        with tempfile.TemporaryDirectory() as root:
            folder=Path(root);report,tools,owned=policy_fixture(folder)
            facts=review.campaign_facts(folder,report,tools,owned,{'go_version':'simulated'})
            self.assertEqual(facts['measurements']['connections'],'confirmed')
            self.assertEqual(facts['measurements']['load_scenario'],'qualified')
            self.assertFalse(facts['native_certificate']);self.assertFalse((folder/'validation.json').exists())

    def test_forged_decisions_groups_or_invocation_are_refused(self):
        for case in ('assessment','load','connections','benefit','groups','flow','interrupt','build','verdict'):
            with self.subTest(case=case),tempfile.TemporaryDirectory() as root:
                folder=Path(root);report,tools,owned=policy_fixture(folder)
                if case=='assessment':report['assessment']['pairs'][0]['p50_loaded_minus_idle_ms']=999
                if case=='load':report['load_scenario']='not_qualified'
                if case=='connections':report['connections']='degraded'
                if case=='benefit':report['coopace_benefit']='improved'
                if case=='groups':report['groups'][1]['reaped_descendants']=True
                if case=='flow':report['flow']={}
                if case=='interrupt':report['traffic_group']['interrupted_phase']={'pair':1,'condition':'loaded'}
                if case=='build':tools['python']['path']='/changed/python'
                if case=='verdict':report['technical_valid']=1
                with self.assertRaises(review.Error):review.campaign_facts(folder,report,tools,owned,{'go_version':'simulated'})

    def test_missing_or_changed_preparation_never_creates_a_certificate(self):
        with tempfile.TemporaryDirectory() as root:
            folder=Path(root);(folder/'prepared.json').write_text('{}\n');(folder/'prepared.sha256').write_text('0'*64+'  prepared.json\n')
            with self.assertRaises(review.Error):review.review(folder)
            self.assertFalse((folder/'validation.json').exists())


class FrozenCaseTests(unittest.TestCase):
    def fixture(self,root,stack):
        revision='c'*40;(root/'.go-version').write_text('1.27.3\n')
        info='binary: go1.27.3\n vcs.revision='+revision+'\n vcs.modified=false\n GOOS=linux\n GOARCH=amd64\n'
        builds={name:name+'.build-info.txt' for name in ('coopace-cake-worker','coopace','coopace-lab-tcp','coopace-lab-load')}
        for file in builds.values():(root/file).write_text(info)
        (root/'bin').mkdir()
        tools={role:review.go.tool(sys.executable) for role in ('python','ip','tc','sysctl','ping')}
        for role,name in (('worker','coopace-cake-worker'),('agent','coopace'),('target','coopace-lab-tcp'),('load','coopace-lab-load')):
            binary=root/'bin'/name;binary.write_bytes(b'\x7fELFsynthetic');binary.chmod(0o700);tools[role]=review.go.tool(binary)
        prepared={'schema_version':1,'tracked_tree_clean':True,'native_launcher_available':False,
                  'kind':'lab_cake_go_campaign_preparation','state':'not_run','native_execution':'not_run','native_steps':['run','check-crash'],
                  'project':str(root),'source_commit':revision,'kernel':'test-kernel','python_version':'3.test','go_version':'go1.27.3',
                  'go_executable':'/pinned/go','build_info':builds,'tools':tools,'supervisor_sources':{},'ping_version':{'producer':'pinned'}}
        raw=json.dumps(prepared).encode();(root/'prepared.json').write_bytes(raw)
        (root/'prepared.sha256').write_text(hashlib.sha256(raw).hexdigest()+'  prepared.json\n')
        (root/'runtime.json').write_text(json.dumps({'kernel':'test-kernel','python_version':'3.test'}))
        for mode in ('run','check-crash'):
            (root/mode).mkdir();(root/(mode+'.exit')).write_text('0\n')
            report={'mode':mode,'environment':{'git_commit':revision,'kernel':'test-kernel','python':'3.test','versions':{'ping':prepared['ping_version']}},
                    'workspace':str(root/('absent-'+mode)), 'namespaces':['cg-test-'+mode+'-'+role for role in ('c','g','s')]}
            for p in (root/mode/'report.json',root/(mode+'.stdout.json')):p.write_text(json.dumps(report))
            (root/(mode+'.log')).write_text(report['workspace']+'\nProcessus récupérés et espaces du contrôle supprimés.\n')
        inputs=stack.enter_context(patch.object(review.base,'verify_inputs',return_value=123))
        go_version=stack.enter_context(patch.object(review.subprocess,'check_output',return_value=info))
        validate=stack.enter_context(patch.object(review,'validate_control',side_effect=lambda folder,report,*args:
            {'namespaces':report['namespaces'],'recorded_pids':[999999999]}))
        return inputs,go_version,validate

    def test_frozen_case_wiring_checks_both_modes_without_writing_certificate(self):
        with tempfile.TemporaryDirectory() as directory,ExitStack() as stack:
            root=Path(directory);inputs,go_version,validate=self.fixture(root,stack)
            result=review.review(root)
            self.assertEqual(result['state'],'campaign_evidence_reviewed');self.assertFalse(result['native_certificate'])
            self.assertEqual(inputs.call_count,2);self.assertEqual(go_version.call_count,4)
            self.assertEqual([call.args[0].name for call in validate.call_args_list],['run','check-crash'])
            self.assertFalse((root/'validation.json').exists())

    def test_nonzero_code_or_missing_cleanup_evidence_refuses_frozen_case(self):
        for case in ('exit','log','stdout','workspace'):
            with self.subTest(case=case),tempfile.TemporaryDirectory() as directory,ExitStack() as stack:
                root=Path(directory);self.fixture(root,stack)
                if case=='exit':(root/'run.exit').write_text('1\n')
                if case=='log':(root/'run.log').write_text('')
                if case=='stdout':(root/'run.stdout.json').write_text('{}')
                if case=='workspace':(root/'absent-run').mkdir()
                with self.assertRaises(review.Error):review.review(root)
                self.assertFalse((root/'validation.json').exists())

    def test_changed_artifact_during_review_is_refused(self):
        with tempfile.TemporaryDirectory() as directory,ExitStack() as stack:
            root=Path(directory);_,_,validate=self.fixture(root,stack)
            def changed(folder,report,*args):
                (root/'run.log').write_text((root/'run.log').read_text()+'changed\n')
                return {'namespaces':report['namespaces'],'recorded_pids':[999999999]}
            validate.side_effect=changed
            with self.assertRaises(review.Error):review.review(root)
            self.assertFalse((root/'validation.json').exists())

    def test_tool_roles_and_hashes_are_checked_beyond_prepared_seal(self):
        for case in ('role','hash'):
            with self.subTest(case=case),tempfile.TemporaryDirectory() as directory,ExitStack() as stack:
                root=Path(directory);self.fixture(root,stack);prepared=json.loads((root/'prepared.json').read_text())
                if case=='role':prepared['tools']['worker']=prepared['tools']['python']
                if case=='hash':prepared['tools']['tc']['sha256']='0'*64
                raw=json.dumps(prepared).encode();(root/'prepared.json').write_bytes(raw)
                (root/'prepared.sha256').write_text(hashlib.sha256(raw).hexdigest()+'  prepared.json\n')
                with self.assertRaises(review.Error):review.review(root)
                self.assertFalse((root/'validation.json').exists())

    def test_cli_help_and_missing_preparation_do_not_publish_certificate(self):
        entry=SOURCE.with_name('lab-cake-go-campaign-review.py')
        with tempfile.TemporaryDirectory() as directory:
            for args,code in ((['--help'],0),([],2),(['--artifacts',directory],1)):
                result=subprocess.run([sys.executable,'-I','-B',str(entry),*args],capture_output=True,text=True,timeout=5)
                self.assertEqual(result.returncode,code,result.stderr)
            self.assertEqual(list(Path(directory).iterdir()),[])


@unittest.skipUnless(sys.platform=='linux','Linux process evidence')
class GlobalControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory=tempfile.TemporaryDirectory();root=Path(cls.directory.name);cls.root=root
        (root/'bin').mkdir();(root/'pids').mkdir()
        docs=deepcopy(phases.integration.collection.fixtures.fixtures.flow_fixtures.documents())
        for value in docs:value.update(go_version='simulated',os='linux',architecture='amd64')
        (root/'documents.json').write_text(json.dumps(docs));(root/'scenario').write_text('crash')
        for name in ('coopace','coopace-lab-tcp','coopace-lab-load'):
            p=root/'bin'/name;p.write_text('#!'+sys.executable+'\n'+phases.integration.collection.driver_fixtures.HELPER);p.chmod(0o700)
        (root/'netns').write_text('import os,sys\nassert sys.argv[1]=="exec"\nos.execv(sys.argv[3],sys.argv[3:])\n')
        harness=phases.integration.collection.HARNESS.replace('campaign.collect(mode,','campaign.run(mode,').replace('tempdir=root,','tempdir=None,')
        harness=harness.replace("'versions':'simulated'", "'binaries':str(self.binaries),'versions':{'ping':{'available':True,'stdout':'ping from iputils simulated\\n','stderr':''}},'bootstrap_sha256':hashlib.sha256(combined.go.BOOTSTRAP.encode()).hexdigest()")
        harness=harness.replace('exit_code=code,process_stopped=True)','exit_code=code,process_stopped=True,pid=10000000+len(kernel.calls))')
        fixture=phases.integration.collection.fixtures.fixtures
        result=subprocess.run([sys.executable,'-I','-B','-c',harness,str(fixture.topology_fixtures.fixtures.SOURCE),str(root),'normal','check-crash',fixture.topology_fixtures.WORKER],
                              cwd=root,capture_output=True,text=True,timeout=70)
        if result.returncode:raise RuntimeError(result.stderr)
        cls.folder=root/'check-crash';(root/'artifacts').rename(cls.folder);cls.report=review.document(cls.folder/'report.json')

    @classmethod
    def tearDownClass(cls):cls.directory.cleanup()

    def validate(self,report=None):
        report=self.report if report is None else report
        return review.validate_control(self.folder,report,report['environment']['tools'],report['environment']['source_sha256'],{'go_version':'simulated'})

    def test_full_go_ipv4_and_crash_replay_does_not_publish_certificate(self):
        facts=self.validate()
        self.assertEqual(facts['go_tool_calls'],14);self.assertEqual(facts['path_check']['commands'],6)
        self.assertEqual(facts['campaign']['phase_count'],2)
        self.assertEqual(facts['reaped_traffic_helpers'],3)
        self.assertFalse((self.folder/'validation.json').exists())

    def test_go_path_cleanup_and_scope_changes_are_refused(self):
        mutations=(lambda r:r['go_phase']['journal']['build'].update(go_version='forged'),lambda r:r['path_check']['with_forwarding'].update(received=2),
                   lambda r:r.update(cleanup_verified=False),lambda r:r.update(traffic_coverage='household'),
                   lambda r:r['traffic_statistics_delta']['counters'].update(bytes=1),lambda r:r['groups'][1].update(state='running'))
        for mutate in mutations:
            with self.subTest(case=mutate):
                report=deepcopy(self.report);mutate(report)
                with self.assertRaises(review.Error):self.validate(report)

    def test_raw_go_and_ipv4_captures_are_required_beyond_report_flags(self):
        for name in ('go/events.bin','go/worker.jsonl'):
            p=self.folder/name;raw=p.read_bytes()
            try:
                p.write_bytes(raw+b'{}\n')
                with self.subTest(file=name),self.assertRaises(review.Error):self.validate()
            finally:p.write_bytes(raw)

    def test_historical_reviewer_refuses_campaign_format(self):
        with self.assertRaises(review.Error):review.base.validate_control(self.folder,self.report,self.report['environment']['tools'],self.report['environment']['source_sha256'],{'go_version':'simulated'})


if __name__=='__main__':unittest.main()
