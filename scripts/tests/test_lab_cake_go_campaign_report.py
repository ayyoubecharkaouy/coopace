"""Final decisions require closed, matching operational evidence."""
from copy import deepcopy
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_lab_cake_go_campaign_assess as measurements
import test_lab_cake_go_campaign_collect as collection

spec=importlib.util.spec_from_file_location('campaign_report_tests',measurements.fixtures.SOURCE.with_name('lab_cake_go_campaign_report.py'))
model=importlib.util.module_from_spec(spec);spec.loader.exec_module(model)


def fixture(folder):
    phases=measurements.campaign();data=[];wire=[]
    def record(event,**values):data.append({'event':event,**values})
    def event(kind,**values):
        raw=model.protocol.event_frame('traffic1',kind,**values);wire.append(raw)
        record('campaign_driver_event',message=json.loads(raw))
    def control(pair,condition,action,when):
        raw=model.protocol.control_frame('traffic1',pair,condition,action)
        record('campaign_control_intent',pair=pair,condition=condition,action=action,frame_base64=base64.b64encode(raw).decode())
        record('campaign_control_sent',pair=pair,condition=condition,action=action,sent_monotonic_ns=when)
    record('environment_verified');record('resources_owned')
    go={'worker_exit_code':0};record('go_phase_finished',phase=go)
    record('path_verified');record('traffic_launch_intent')
    for index,phase in enumerate(phases):
        pair,condition=phase['pair'],phase['condition'];base=(index*30+1)*1_000_000_000
        event('begin',pair=pair,condition=condition);control(pair,condition,'start',base)
        helpers=[{'pid':100+index*3+n,'start_ticks':1000+n} for n in range(1 if condition=='idle' else 3)]
        phase.update(helpers=helpers,helpers_stopped=[{'pid':h['pid'],'previous_start_ticks':h['start_ticks'],'reason':'absent'} for h in helpers])
        event('ready',pair=pair,condition=condition,helper_pids=[h['pid'] for h in helpers])
        record('campaign_helpers_verified',pair=pair,condition=condition,helpers=helpers)
        control(pair,condition,'continue',base+1)
        extra=deepcopy(phase['samples'][-1]);extra['collected_at']=extra['collected_at'].replace(':21+',':21.500000+').replace(':51+',':51.500000+')
        phase['samples'].append(extra)
        for i,s in enumerate(phase['samples']):
            s.update(read_started_monotonic_ns=base+20_000_000_000+i*500_000_000,
                     read_finished_monotonic_ns=base+20_000_000_001+i*500_000_000)
            record('campaign_sample',reading=s)
        end=base+20_000_000_000;phase['end_observed_monotonic_ns']=end
        raw=model.protocol.event_frame('traffic1','end',pair=pair,condition=condition,result=phase['result'])
        record('phase_end_observed',pair=pair,condition=condition,observed_monotonic_ns=end,line_sha256=hashlib.sha256(raw).hexdigest())
        event('end',pair=pair,condition=condition,result=phase['result'])
        record('campaign_helpers_stopped',pair=pair,condition=condition,helpers=phase['helpers_stopped'])
        control(pair,condition,'advance',base+22_800_000_000)
    event('complete');record('traffic_group_stopped');record('combined_evidence_verified');record('control_complete',cleanup_verified=True)
    report={'state':'complete','mode':'run','session_id':'traffic1','cleanup_verified':True,'go_phase':go,
            'path_check':{'path_verified':True,'state':'verified'},'groups':[{'state':'stopped'}]*2,
            'traffic_group':{'state':'collected','driver_exit_code':0,'reaped_descendants':0,'phases':phases}}
    def save(name,raw):
        (folder/name).write_bytes(raw)
        return {'file':name,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
    rows=[{'sequence':i+1,'data':d} for i,d in enumerate(data)]
    report['supervisor_journal']=save('supervisor.jsonl',b''.join(json.dumps(r).encode()+b'\n' for r in rows))
    report['traffic_group']['stdout']=save('driver.stdout.bin',b''.join(wire))
    report['traffic_group']['stderr']=save('driver.stderr.bin',b'')
    return report


class VerdictTests(unittest.TestCase):
    def test_matching_evidence_and_measurements_allow_separate_decisions(self):
        with tempfile.TemporaryDirectory() as root:
            report=fixture(Path(root));model.finalize(report,Path(root),operational_success=True)
            self.assertTrue(report['technical_valid'],report)
            self.assertEqual(report['load_scenario'],'qualified')
            self.assertEqual(report['connections'],'confirmed')
            self.assertEqual(report['kind'],'lab_cake_go_campaign')
            self.assertEqual(report['coopace_benefit'],'not_assessed')

    def test_changed_capture_or_report_never_publishes_positive_decisions(self):
        for case in ('capture','sample','helper','cleanup','code','end','drain'):
            with self.subTest(case=case),tempfile.TemporaryDirectory() as root:
                folder=Path(root);report=fixture(folder)
                if case=='capture':(folder/'driver.stdout.bin').write_bytes(b'{}\n')
                if case=='sample':report['phases']=[];report['traffic_group']['phases'][0]['samples'][0]['condition']='loaded'
                if case=='helper':report['traffic_group']['phases'][0]['helpers'][0]['pid']=999
                if case=='cleanup':report['cleanup_verified']=False
                if case=='code':report['traffic_group']['driver_exit_code']=1
                if case=='end':report['traffic_group']['phases'][0]['end_observed_monotonic_ns']=1
                if case=='drain':report['traffic_group']['phases'][0]['samples'][-1]['read_finished_monotonic_ns']+=10**10
                with self.assertRaises(Exception):model.finalize(report,folder,operational_success=True)
                self.assertFalse(report['technical_valid'])
                self.assertEqual(report['connections'],'not_assessed')

    def test_operational_failure_suppresses_all_scientific_decisions(self):
        report={'state':'failed','mode':'run','traffic_group':None}
        model.finalize(report,Path('/unused'),operational_success=False)
        self.assertFalse(report['technical_valid']);self.assertIsNone(report['assessment'])

    def test_noncanonical_or_truncated_stdout_is_refused_even_with_updated_digest(self):
        for case in ('crlf','truncated'):
            with self.subTest(case=case),tempfile.TemporaryDirectory() as root:
                folder=Path(root);report=fixture(folder);target=folder/'driver.stdout.bin';raw=target.read_bytes()
                raw=raw.replace(b'\n',b'\r\n') if case=='crlf' else raw[:-1]
                target.write_bytes(raw)
                report['traffic_group']['stdout'].update(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
                with self.assertRaises(Exception):model.finalize(report,folder,operational_success=True)
                self.assertFalse(report['technical_valid'])

    def test_unqualified_load_or_failed_connections_keep_valid_technical_result(self):
        for case in ('load','connections'):
            with self.subTest(case=case),tempfile.TemporaryDirectory() as root:
                phases=measurements.campaign()
                for phase in phases:
                    if case=='load' and phase['condition']=='loaded':
                        baseline=phase['samples'][1]['statistics']['counters']['bytes']
                        for sample in phase['samples'][1:4]:sample['statistics']['counters']['bytes']=baseline
                    if case=='connections':
                        phase['result']['measurement_exit_code']=1
                        latency=phase['result']['latency'];latency.update(successful=0,failed=10)
                        if phase['condition']=='loaded':phase['result']['has_successful_probe']=False
                        for attempt in latency['attempts']:attempt.update(connect_ms=None,failure='timeout')
                with patch.object(measurements,'campaign',return_value=phases):report=fixture(Path(root))
                model.finalize(report,Path(root),operational_success=True)
                self.assertTrue(report['technical_valid'],report)
                self.assertEqual(report['state'],'complete')
                self.assertEqual(report['load_scenario'],'not_qualified' if case=='load' else 'qualified')
                self.assertEqual(report['connections'],'degraded' if case=='connections' else 'confirmed')


class IntegrationTests(unittest.TestCase):
    def run_case(self,scenario='normal',mode='check'):
        harness=collection.HARNESS.replace('campaign.collect(mode,','campaign.run(mode,')
        if scenario=='interrupt_after_verdict':
            hook="""
original_finalizer=campaign.verdict.finalize
def interrupted_finalizer(*args,**kwargs):
 original_finalizer(*args,**kwargs)
 os.kill(os.getpid(),signal.SIGTERM)
campaign.verdict.finalize=interrupted_finalizer
"""
            harness=harness.replace('class CampaignInventory',hook+'\nclass CampaignInventory')
        with patch.object(collection,'HARNESS',harness):
            return collection.CampaignCollectTests(methodName='runTest').run_case(scenario,mode)

    def test_complete_collection_with_inconsistent_measurement_dates_is_non_exploitable(self):
        process,report,_,_=self.run_case()
        self.assertNotEqual(process.returncode,0)
        self.assertEqual(report['kind'],'lab_cake_go_campaign')
        self.assertTrue(report['cleanup_verified'])
        self.assertEqual(report['traffic_group']['state'],'collected')
        self.assertFalse(report['technical_valid'])
        self.assertEqual(report['load_scenario'],'non_exploitable')
        self.assertIsNotNone(report['assessment'])

    def test_crash_reports_recovery_without_measurement_qualification(self):
        process,report,_,_=self.run_case(mode='check-crash')
        self.assertEqual(process.returncode,0,process.stderr)
        self.assertIsNone(report['technical_valid'])
        self.assertEqual(report['connections'],'not_assessed')
        self.assertEqual(report['load_scenario'],'not_assessed')

    def test_cleanup_or_final_journal_failure_prevents_assessment(self):
        for scenario in ('cleanup_failure','final_evidence_failure'):
            with self.subTest(scenario=scenario):
                process,report,_,_=self.run_case(scenario,mode='check-crash')
                self.assertNotEqual(process.returncode,0)
                self.assertFalse(report['technical_valid'])
                self.assertIsNone(report['assessment'])

    def test_interrupt_after_verdict_prevents_successful_publication(self):
        process,report,_,_=self.run_case('interrupt_after_verdict',mode='check-crash')
        self.assertNotEqual(process.returncode,0)
        self.assertTrue(report['cleanup_verified'])
        self.assertEqual(report['state'],'failed')
        self.assertFalse(report['technical_valid'])
        self.assertEqual(report['connections'],'not_assessed')


if __name__=='__main__':unittest.main()
