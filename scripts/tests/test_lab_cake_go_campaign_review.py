"""Synthetic phase replay; no native certificate, commands or process signals."""
from copy import deepcopy
import base64
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_lab_cake_go_campaign_assess as fixtures
import test_lab_cake as cake_fixtures
import test_lab_cake_go_campaign_report as integration

spec=importlib.util.spec_from_file_location('phase_replay_tests',fixtures.fixtures.SOURCE.with_name('lab_cake_go_campaign_review.py'))
review=importlib.util.module_from_spec(spec);spec.loader.exec_module(review)


def write(folder,report,rows,wire):
    def seal(name,raw):
        (folder/name).write_bytes(raw)
        return {'file':name,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
    for i,row in enumerate(rows):
        row.update(schema_version=1,kind='lab_cake_go_active_journal',sequence=i+1,
                   recorded_at='2026-11-03T00:00:00Z',elapsed_ns=i*1000000)
    report['supervisor_journal']=seal('supervisor.jsonl',b''.join(json.dumps(r).encode()+b'\n' for r in rows))
    report['traffic_group']['stdout']=seal('driver.stdout.bin',b''.join(wire))
    report['traffic_group']['stderr']=seal('driver.stderr.bin',b'')


def fixture(folder,crash=False):
    names=['cg-traffic1-'+role for role in ('c','g','s')];owned=[[n,[1,100+i]] for i,n in enumerate(names)]
    tools={n:{'path':'/tools/'+n,'sha256':'a'*64} for n in ('ip','tc','target','load','agent')}
    phases=fixtures.campaign()[:2 if crash else 6];rows=[];wire=[];samples=[]
    def record(event,**fields):rows.append({'data':{'event':event,**fields}})
    def event(kind,pair=None,condition=None,**fields):
        raw=review.wire.event_frame('traffic1',kind,pair=pair,condition=condition,**fields);wire.append(raw)
        record('campaign_driver_event',message=json.loads(raw));return raw
    def control(pair,condition,action,when):
        raw=review.wire.control_frame('traffic1',pair,condition,action)
        record('campaign_control_intent',pair=pair,condition=condition,action=action,frame_base64=base64.b64encode(raw).decode())
        record('campaign_control_sent',pair=pair,condition=condition,action=action,sent_monotonic_ns=when)
    def sample(phase,value,when):
        qdisc=cake_fixtures.fixture()
        for k,v in value['statistics']['counters'].items():qdisc[0][k]=v
        reading={'qdiscs':qdisc,'configuration':review.base.collect.cake.configured_qdisc(json.dumps(qdisc).encode(),review.base.collect.cake.PROFILE),
                 'statistics':review.base.collect.cake.statistics(json.dumps(qdisc).encode(),review.base.collect.cake.PROFILE),
                 'collected_at':value['collected_at'],'elapsed_since_start_ms':when/1000000,'read_duration_ms':1}
        show=[tools['ip']['path'],'netns','exec',names[1],tools['tc']['path'],'-j','-s','-r','qdisc','show','dev','wan']
        record('activation_tool_intent',arguments=show)
        record('activation_tool_result',arguments=show,error='',duration_ns=1000000,stdout_base64=base64.b64encode(json.dumps(qdisc).encode()).decode())
        record('activation_qdisc',reading=reading)
        value.update(reading,read_started_monotonic_ns=when-1000000,read_finished_monotonic_ns=when)
        phase['samples'].append(value);samples.append(value);record('campaign_sample',reading=value)
    for index,phase in enumerate(phases):
        pair,condition=phase['pair'],phase['condition'];origin=(index*30+1)*1000000000
        original=phase['samples'];phase['samples']=[]
        event('begin',pair,condition);sample(phase,original[0],origin)
        control(pair,condition,'start',origin+100000000)
        helpers=[]
        for i,args in enumerate(review.base.collect.expected_helpers(tools)[:1 if condition=='idle' else 3]):
            helpers.append({'pid':100+index*3+i,'state':'S','start_ticks':1000+i,'parent':10000,'group':10000,'session':10000,
                            'network_namespace':owned[2 if i<2 else 0][1], 'executable':tools['target' if i==0 else 'load'],'arguments':args})
        phase['helpers']=helpers
        event('ready',pair,condition,helper_pids=[h['pid'] for h in helpers]);record('campaign_helpers_verified',pair=pair,condition=condition,helpers=helpers)
        if crash and index==1:
            phase.update(state='interrupted',result=None)
            record('traffic_kill_intent',driver_pid=10000)
            break
        control(pair,condition,'continue',origin+1500000000)
        for second,value in zip((2,3,4),original[1:4]):sample(phase,value,origin+second*1000000000)
        raw_end=review.wire.event_frame('traffic1','end',pair=pair,condition=condition,result=phase['result'])
        phase['end_observed_monotonic_ns']=origin+20900000000
        record('phase_end_observed',pair=pair,condition=condition,observed_monotonic_ns=phase['end_observed_monotonic_ns'],line_sha256=hashlib.sha256(raw_end).hexdigest())
        event('end',pair,condition,result=phase['result'])
        phase['helpers_stopped']=[{'pid':h['pid'],'previous_start_ticks':h['start_ticks'],'reason':'absent'} for h in helpers]
        record('campaign_helpers_stopped',pair=pair,condition=condition,helpers=phase['helpers_stopped'])
        last=deepcopy(original[-1]);last['collected_at']=last['collected_at'].replace(':21+',':21.500000+').replace(':51+',':51.500000+')
        sample(phase,original[-1],origin+21000000000);sample(phase,last,origin+21500000000)
        phase['statistics_delta']=review.base.collect.cake.queue.statistics_delta(phase['samples'][0]['statistics'],phase['samples'][-1]['statistics'])
        record('campaign_phase_collected',pair=pair,condition=condition,statistics_delta=phase['statistics_delta'])
        control(pair,condition,'advance',origin+21600000000)
    if not crash:event('complete')
    report={'kind':'lab_cake_go_campaign','mode':'check-crash' if crash else 'run','session_id':'traffic1',
            'traffic_group':{'driver_pid':10000,'phases':phases,'queue_samples':samples},'phases':phases,
            'assessment':{'forged':True},'technical_valid':False}
    write(folder,report,rows,wire)
    return report,rows,wire,tools,owned


class PhaseReviewTests(unittest.TestCase):
    def test_replays_all_phases_from_raw_evidence_without_trusting_verdict(self):
        with tempfile.TemporaryDirectory() as root:
            folder=Path(root);report,rows,wire,tools,owned=fixture(folder)
            facts=review.replay(folder,report,tools,owned)
            self.assertEqual(facts['phase_count'],6)
            self.assertTrue(facts['measurements']['measurements_valid'],facts)
            self.assertEqual(facts['measurements']['load_scenario'],'qualified')
            self.assertEqual(len(facts['recorded_helper_pids']),12)
            self.assertFalse(facts['native_certificate']);self.assertFalse((folder/'validation.json').exists())

    def test_crash_replays_idle_then_first_loaded_ready_without_measurement_verdict(self):
        with tempfile.TemporaryDirectory() as root:
            folder=Path(root);report,_,_,tools,owned=fixture(folder,True)
            facts=review.replay(folder,report,tools,owned)
            self.assertEqual(facts['phase_count'],2);self.assertIsNone(facts['measurements']['measurements_valid'])

    def test_rehashed_changes_in_raw_options_helpers_controls_or_drains_are_refused(self):
        for case in ('options','options_consistent','counter','sample','helper','control','end','drain','phase_delta','missing_helper'):
            with self.subTest(case=case),tempfile.TemporaryDirectory() as root:
                folder=Path(root);report,rows,wire,tools,owned=fixture(folder)
                data=[r['data'] for r in rows];phase=report['phases'][0]
                if case in ('options','options_consistent'):
                    d=next(d for d in data if d['event']=='activation_tool_result');q=json.loads(base64.b64decode(d['stdout_base64']));q[0]['options']['bandwidth']=1;d['stdout_base64']=base64.b64encode(json.dumps(q).encode()).decode()
                    if case=='options_consistent':
                        next(d for d in data if d['event']=='activation_qdisc')['reading']['qdiscs'][0]['options']['bandwidth']=1
                if case=='counter':
                    d=[d for d in data if d['event']=='activation_tool_result'][2];q=json.loads(base64.b64decode(d['stdout_base64']));q[0]['bytes']=0;d['stdout_base64']=base64.b64encode(json.dumps(q).encode()).decode()
                if case=='sample':phase['samples'][1]['statistics']['counters']['bytes']=999
                if case=='helper':phase['helpers'][0]['parent']=999
                if case=='missing_helper':phase['helpers'].clear()
                if case=='control':next(d for d in data if d['event']=='campaign_control_sent')['action']='advance'
                if case=='end':phase['end_observed_monotonic_ns']+=100
                if case=='drain':phase['samples'][-1]['read_finished_monotonic_ns']+=10000000000
                if case=='phase_delta':phase['statistics_delta']['counters']['bytes']=999
                write(folder,report,rows,wire)
                with self.assertRaises(review.Error):review.replay(folder,report,tools,owned)

    def test_pid_reuse_is_observed_without_any_command_or_signal(self):
        with tempfile.TemporaryDirectory() as root:
            folder=Path(root);report,rows,wire,tools,owned=fixture(folder)
            stopped=report['phases'][0]['helpers_stopped'][0]
            stopped.update(reason='pid_reused',current_start_ticks=stopped['previous_start_ticks']+1)
            write(folder,report,rows,wire)
            with patch.object(review.base.os,'kill',side_effect=AssertionError('signal')), \
                 patch.object(review.base.subprocess,'run',side_effect=AssertionError('command')), \
                 patch.object(review.base.subprocess,'check_output',side_effect=AssertionError('command')):
                facts=review.replay(folder,report,tools,owned)
            self.assertTrue(facts['phase_evidence_valid']);self.assertFalse(facts['native_certificate'])


@unittest.skipUnless(sys.platform == "linux", "Linux process evidence")
class RecordedProcessTests(unittest.TestCase):
    def test_replays_actual_collector_journals_for_both_modes_without_certificate(self):
        hook=r'''
if (artifacts/'report.json').exists():
 spec=importlib.util.spec_from_file_location('phase_replay',source.with_name('lab_cake_go_campaign_review.py'))
 replay=importlib.util.module_from_spec(spec);spec.loader.exec_module(replay)
 report=json.loads((artifacts/'report.json').read_text())
 journal=[json.loads(line) for line in (artifacts/'supervisor.jsonl').read_text().splitlines()]
 owned=next(r['data']['namespaces'] for r in journal if r['data']['event']=='resources_owned')
 state['phase_review']=replay.replay(artifacts,report,report['environment']['tools'],owned)
 state['no_certificate']=not (artifacts/'validation.json').exists()
'''
        harness=integration.collection.HARNESS
        needle="(root/'observed.json').write_text(json.dumps(state))"
        self.assertIn(needle,harness)
        harness=harness.replace(needle,hook+'\n '+needle)
        with patch.object(integration.collection,'HARNESS',harness):
            for mode in ('check','check-crash'):
                with self.subTest(mode=mode):
                    process,report,_,observed=integration.IntegrationTests(methodName='runTest').run_case(mode=mode)
                    self.assertEqual(process.returncode,0 if mode=='check-crash' else 1,process.stderr)
                    facts=observed['phase_review']
                    self.assertTrue(facts['phase_evidence_valid'])
                    self.assertEqual(facts['phase_count'],2 if mode=='check-crash' else 6)
                    self.assertEqual(facts['measurements']['measurements_valid'],None if mode=='check-crash' else False)
                    self.assertTrue(observed['no_certificate'])

    def test_truncated_or_noncanonical_wire_and_journal_are_refused(self):
        for case in ('wire','crlf','journal'):
            with self.subTest(case=case),tempfile.TemporaryDirectory() as root:
                folder=Path(root);report,rows,wire,tools,owned=fixture(folder)
                if case=='wire':wire[-1]=wire[-1][:-1]
                if case=='crlf':wire=[r.replace(b'\n',b'\r\n') for r in wire]
                if case=='journal':rows[0]['sequence']=True
                write(folder,report,rows,wire)
                if case=='journal':
                    raw=(folder/'supervisor.jsonl').read_bytes()[:-1];(folder/'supervisor.jsonl').write_bytes(raw)
                    report['supervisor_journal'].update(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
                with self.assertRaises(review.Error):review.replay(folder,report,tools,owned)


if __name__=='__main__':unittest.main()
