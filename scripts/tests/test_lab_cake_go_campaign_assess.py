"""Pure measurements: independent fixed expectations, no processes or network."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
import math
from pathlib import Path
import unittest

import test_lab_cake_go_campaign_protocol as fixtures

spec = importlib.util.spec_from_file_location('campaign_assess_tests', fixtures.SOURCE.with_name('lab_cake_go_campaign_assess.py'))
model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)


def campaign():
    phases = []
    for index, (pair, condition) in enumerate(fixtures.PHASES):
        result = fixtures.result(condition)
        def shift(value):
            if isinstance(value, dict):return {k:shift(v) for k,v in value.items()}
            if isinstance(value, list):return [shift(v) for v in value]
            if isinstance(value,str) and value.startswith('2026-10-30T'):
                return (datetime.fromisoformat(value.replace('Z','+00:00'))+timedelta(seconds=index*30)).isoformat().replace('+00:00','Z')
            return value
        result=shift(result)
        def sample(second):
            when=datetime(2026,10,30,tzinfo=timezone.utc)+timedelta(seconds=index*30+second)
            return {'pair':pair,'condition':condition,'phase':'before_start' if second==0 else 'drain' if second==21 else 'running',
                    'collected_at':when.isoformat(),
                    'statistics':{'counters':{k:index*1000+second for k in model.COUNTERS}, 'backlog_bytes':0,'queued_packets':0}}
        phases.append({'pair':pair,'condition':condition,'state':'complete','result':result,
                       'samples':[sample(s) for s in (0,2,3,4,21)], 'statistics_delta':{'available':False}})
    return phases


class AssessmentTests(unittest.TestCase):
    def test_qualified_measurements_are_not_native_or_technical_certification(self):
        data=campaign();original=deepcopy(data);decision=model.assess(data)
        self.assertTrue(decision['measurements_valid'],decision)
        self.assertEqual(decision['load_scenario'],'qualified')
        self.assertEqual(decision['connections'],'confirmed')
        self.assertNotIn('technical_valid',decision)
        self.assertEqual(decision['coopace_benefit'],'not_assessed')
        self.assertEqual(data,original)
        self.assertEqual(decision['phases'][1]['received_bytes_per_second'],419430.4)
        self.assertEqual(decision['phases'][1]['probe_window_samples'],3)
        self.assertEqual(decision['phases'][1]['statistics_delta']['counters']['bytes'],21)

    def test_nearest_rank_and_signed_pair_differences_ignore_stored_summary(self):
        data=campaign()
        for phase in data:
            latency=phase['result']['latency'];latency['connect_ms']={'p50':999,'p95':999,'p99':999}
            values=range(1,11) if phase['condition']=='idle' else range(0,10)
            for attempt,value in zip(latency['attempts'],values):attempt['connect_ms']=value
        result=model.assess(data)
        self.assertTrue(result['measurements_valid'],result)
        self.assertEqual(result['phases'][0]['latency']['p50'],5)
        self.assertEqual(result['phases'][0]['latency']['p95'],10)
        for pair in result['pairs']:
            for key in ('p50','p95','p99'):self.assertEqual(pair[key+'_loaded_minus_idle_ms'],-1)

    def test_failed_and_partial_connections_preserve_missing_quantiles(self):
        for failures in (3,10):
            with self.subTest(failures=failures):
                data=campaign()
                for phase in data:
                    latency=phase['result']['latency'];latency.update(successful=10-failures,failed=failures)
                    phase['result']['measurement_exit_code']=1 if failures==10 else 0
                    if phase['condition']=='loaded':phase['result']['has_successful_probe']=failures<10
                    for attempt in latency['attempts'][:failures]:attempt.update(connect_ms=None,failure='timeout')
                result=model.assess(data)
                self.assertTrue(result['measurements_valid'],result)
                self.assertEqual(result['connections'],'degraded')
                self.assertEqual(result['load_scenario'],'qualified')
                self.assertEqual(result['phases'][0]['latency']['p50'],None if failures==10 else 1)
                if failures==10:self.assertIsNone(result['pairs'][0]['p95_loaded_minus_idle_ms'])

    def test_exact_inclusive_rate_boundaries_and_neighbors(self):
        for rate in (350000,525000):self.assertTrue(model.rate_in_range(rate,1_000_000_000))
        self.assertFalse(model.rate_in_range(349999,1_000_000_000))
        self.assertFalse(model.rate_in_range(525001,1_000_000_000))
        self.assertFalse(model.rate_in_range(350000,1_000_000_001))
        self.assertFalse(model.rate_in_range(525000,999_999_999))

    def test_no_bytes_progress_is_unqualified_but_exploitable(self):
        data=campaign()
        for phase in data:
            if phase['condition']=='loaded':
                for sample in phase['samples'][1:4]:sample['statistics']['counters']['bytes']=phase['samples'][1]['statistics']['counters']['bytes']
        result=model.assess(data)
        self.assertTrue(result['measurements_valid'],result)
        self.assertEqual(result['load_scenario'],'not_qualified')
        self.assertEqual(result['connections'],'confirmed')

    def test_rate_outside_range_does_not_invalidate_measurements(self):
        data=campaign()
        for phase in data:
            if phase['condition']=='loaded':
                receive=phase['result']['receive']
                receive.update(receive_elapsed_ms=24000,elapsed_ms=24000,average_bytes_per_second=8388608/24)
                end=datetime.fromisoformat(receive['started_at'].replace('Z','+00:00'))+timedelta(seconds=24)
                receive.update(last_read_at=end.isoformat().replace('+00:00','Z'),finished_at=end.isoformat().replace('+00:00','Z'))
                phase['samples'][-1]['collected_at']=(end+timedelta(seconds=1)).isoformat()
        result=model.assess(data)
        self.assertTrue(result['measurements_valid'],result)
        self.assertEqual(result['load_scenario'],'not_qualified')

    def test_small_difference_survives_large_individual_values(self):
        data=campaign()
        for phase in data:
            for attempt in phase['result']['latency']['attempts']:
                attempt['connect_ms']=10**16+(1 if phase['condition']=='loaded' else 0)
        result=model.assess(data)
        self.assertTrue(result['measurements_valid'],result)
        self.assertEqual(result['pairs'][0]['p50_loaded_minus_idle_ms'],1)

    def test_invalid_data_are_non_exploitable_and_connections_not_assessed(self):
        def reset(p):p[1]['samples'][2]['statistics']['counters']['bytes']=0
        def insufficient(p):p[1]['samples']=p[1]['samples'][:2]+p[1]['samples'][-1:]
        def wrong_time(p):p[1]['samples'][1]['collected_at']='invalid'
        def duration(p):p[1]['result']['receive']['finished_at']=p[1]['result']['receive']['first_read_at']
        def volume(p):p[1]['result']['receive']['received_bytes']=1
        def overlap(p):p[1]['result']['send']['first_write_at']=p[1]['result']['latency']['started_at']
        def counts(p):p[0]['result']['latency']['successful']=False
        def foreign(p):p[1]['samples'][2]['pair']=True
        def duplicate(p):p[1]['samples'][2]['collected_at']=p[1]['samples'][1]['collected_at']
        def interrupted(p):p[0]['state']='interrupted'
        def outside_phase(p):p[1]['samples'][-1]['collected_at']=p[1]['result']['latency']['finished_at']
        for mutate in (reset,insufficient,wrong_time,duration,volume,overlap,counts,foreign,duplicate,interrupted,outside_phase):
            with self.subTest(case=mutate.__name__):
                data=campaign();mutate(data);result=model.assess(data)
                self.assertFalse(result['measurements_valid'],result)
                self.assertEqual(result['load_scenario'],'non_exploitable')
                self.assertEqual(result['connections'],'not_assessed')
                self.assertTrue(result['reasons'])
        self.assertFalse(model.assess(campaign()[::-1])['measurements_valid'])
        self.assertFalse(model.assess([])['measurements_valid'])

    def test_crash_has_no_measurement_verdict(self):
        result=model.assess(None,crash=True)
        self.assertIsNone(result['measurements_valid'])
        self.assertEqual(result['load_scenario'],'not_assessed')
        self.assertEqual(result['connections'],'not_assessed')
        with self.assertRaises(model.Error):model.assess([],crash=1)

    def test_receive_duration_includes_wait_for_eof_after_last_payload(self):
        data=campaign()
        for phase in data:
            if phase['condition']=='loaded':
                receive=phase['result']['receive']
                last=datetime.fromisoformat(receive['first_read_at'].replace('Z','+00:00'))+timedelta(seconds=10)
                receive['last_read_at']=last.isoformat().replace('+00:00','Z')
        result=model.assess(data)
        self.assertTrue(result['measurements_valid'],result)
        self.assertEqual(result['load_scenario'],'qualified')
        self.assertEqual(result['phases'][1]['received_bytes_per_second'],419430.4)

    def test_serialized_utc_difference_does_not_replace_monotonic_duration(self):
        data=campaign()
        for phase in data:
            if phase['condition']=='loaded':
                receive=phase['result']['receive']
                end=datetime.fromisoformat(receive['finished_at'].replace('Z','+00:00'))+timedelta(microseconds=10)
                receive['finished_at']=end.isoformat().replace('+00:00','Z')
        result=model.assess(data)
        self.assertTrue(result['measurements_valid'],result)
        self.assertEqual(result['phases'][1]['received_bytes_per_second'],419430.4)

    def test_inconsistent_reported_rate_or_nonpositive_duration_is_still_refused(self):
        for case in ('rate','zero','negative'):
            with self.subTest(case=case):
                data=campaign();receive=data[1]['result']['receive']
                if case=='rate':receive['average_bytes_per_second']*=2
                if case=='zero':receive['receive_elapsed_ms']=0
                if case=='negative':receive['receive_elapsed_ms']=-1
                self.assertFalse(model.assess(data)['measurements_valid'])

    def test_native_0440c5d_receipt_regression_without_reclassifying_original_run(self):
        fixture=json.loads((Path(__file__).with_name('fixtures')/'go-campaign-0440c5d-measurements.json').read_text())
        self.assertEqual(fixture['original_state'],'failed')
        self.assertFalse(fixture['native_certificate'])
        phases=fixture['phases'];result=model.assess(phases)
        self.assertTrue(result['measurements_valid'],result)
        self.assertEqual(result['load_scenario'],'qualified')
        self.assertEqual(result['connections'],'confirmed')
        for phase,summary in zip(phases,result['phases']):
            if phase['condition']=='loaded':
                receive=phase['result']['receive']
                wrong=(model.utc_ns(receive['last_read_at'])-model.utc_ns(receive['first_read_at']))/1000000
                self.assertFalse(math.isclose(wrong,receive['receive_elapsed_ms'],rel_tol=1e-9))
                self.assertTrue(math.isclose(summary['received_bytes_per_second'],receive['average_bytes_per_second'],rel_tol=1e-9))


if __name__=='__main__':unittest.main()
