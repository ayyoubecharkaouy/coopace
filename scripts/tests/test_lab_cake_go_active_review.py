"""Review complete synthetic evidence without publishing native validation."""

from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import test_lab_cake_go_active as fixtures

SOURCE=fixtures.SOURCE.with_name('lab_cake_go_active_review.py')
spec=importlib.util.spec_from_file_location('review',SOURCE)
review=importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


@unittest.skipUnless(sys.platform=='linux','Linux process evidence')
class ReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory=tempfile.TemporaryDirectory()
        cls.root=Path(cls.directory.name)
        cls.cases={}
        for scenario,mode in (('normal','check'),('normal','check-crash'),('all_failed','check')):
            root=cls.root/(scenario+'-'+mode);root.mkdir();(root/'bin').mkdir();(root/'pids').mkdir()
            docs=deepcopy(fixtures.flow_fixtures.documents())
            docs[2]['connect_ms']={k:1 for k in ('min','p50','p95','p99','max')}
            for doc in docs:doc.update(go_version='simulated',os='linux',architecture='amd64')
            if scenario=='all_failed':
                docs[2].update(successful=0,failed=10)
                for attempt in docs[2]['attempts']:attempt.update(connect_ms=None,failure='timeout')
            (root/'documents.json').write_text(json.dumps(docs))
            (root/'scenario').write_text('crash' if mode=='check-crash' else scenario)
            for name in ('coopace','coopace-lab-tcp','coopace-lab-load'):
                p=root/'bin'/name;p.write_text('#!'+sys.executable+'\n'+fixtures.traffic_fixtures.HELPER);p.chmod(0o700)
            (root/'netns').write_text('import os,sys\nassert sys.argv[1]=="exec"\nos.execv(sys.argv[3],sys.argv[3:])\n')
            harness=fixtures.HARNESS.replace('tempdir=root,session_factory=Session','tempdir=None,session_factory=Session')
            harness=harness.replace("'versions':'simulated'","'versions':'simulated','bootstrap_sha256':hashlib.sha256(combined.go.BOOTSTRAP.encode()).hexdigest()")
            p=subprocess.run([sys.executable,'-I','-B','-c',harness,str(fixtures.topology_fixtures.fixtures.SOURCE),
                              str(root),scenario,mode,fixtures.topology_fixtures.WORKER],cwd=root,
                             capture_output=True,text=True,timeout=20)
            if p.returncode:raise RuntimeError(p.stderr)
            folder=root/mode;(root/'artifacts').rename(folder)
            cls.cases[scenario,mode]=(folder,review.document(folder/'report.json'))

    @classmethod
    def tearDownClass(cls):cls.directory.cleanup()

    def validate(self,folder,report):
        return review.validate_control(folder,report,report['environment']['tools'],
                                       report['environment']['source_sha256'],{'go_version':'simulated'})

    def test_replays_both_modes_and_creates_no_native_certificate(self):
        for mode in ('check','check-crash'):
            folder,report=self.cases['normal',mode]
            value=self.validate(folder,report)
            self.assertEqual(value['go_tool_calls'],14)
            self.assertEqual(value['traffic_driver_exit_code'],-9 if mode=='check-crash' else 0)
            self.assertEqual(value['reaped_traffic_helpers'],3 if mode=='check-crash' else 0)
            self.assertFalse((folder/'validation.json').exists())

    def test_complete_collection_with_failed_probes_is_not_native_positive(self):
        folder,report=self.cases['all_failed','check']
        self.assertEqual(report['state'],'complete')
        with self.assertRaisesRegex(review.Error,'Dix sondes'):self.validate(folder,report)

    def test_modified_summary_group_scope_or_counter_is_rejected(self):
        folder,original=self.cases['normal','check']
        changes=[lambda r:r.update(cleanup_verified=False),lambda r:r.update(schema_version=True),
                 lambda r:r.update(traffic_coverage='household'),lambda r:r['groups'][1].update(driver_exit_code=1),
                 lambda r:r['traffic_group'].update(helper_pids=[1,2,3]),
                 lambda r:r['traffic_statistics_delta']['counters'].update(bytes=1),
                 lambda r:r['topology']['activation_statistics_delta']['counters'].update(bytes=999),
                 lambda r:r.update(flow={}),lambda r:r['go_phase']['journal']['build'].update(go_version='fake')]
        for change in changes:
            with self.subTest(change=change):
                report=deepcopy(original);change(report)
                with self.assertRaises((review.Error,KeyError,ValueError)):self.validate(folder,report)

    def test_raw_pipe_journal_and_file_changes_are_rejected(self):
        folder,report=self.cases['normal','check']
        for name in ('driver.stdout.bin','supervisor.jsonl','go/events.bin','go/worker.jsonl'):
            p=folder/name;original=p.read_bytes()
            try:
                p.write_bytes(original+b'{}\n')
                with self.subTest(name=name),self.assertRaises((review.Error,ValueError,KeyError)):
                    self.validate(folder,report)
            finally:p.write_bytes(original)

    def test_forged_percentiles_are_recomputed_even_when_summary_hash_matches(self):
        folder,original=self.cases['normal','check'];report=deepcopy(original)
        p=folder/'driver.stdout.bin';data=p.read_bytes()
        try:
            first,last=data.split(b'\n',1);value=json.loads(last)
            value['flow']['latency']['connect_ms']['p95']=999
            updated=first+b'\n'+json.dumps(value).encode()+b'\n';p.write_bytes(updated)
            report['flow']=value['flow'];report['traffic_group']['flow']=deepcopy(value['flow'])
            report['traffic_group']['stdout']=review.fingerprint(p)
            with self.assertRaisesRegex(review.Error,'Percentiles'):self.validate(folder,report)
        finally:p.write_bytes(data)

    def test_manifest_rejects_changed_input_and_duplicate_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);p=root/'input';p.write_bytes(b'frozen')
            manifest={'input':hashlib.sha256(p.read_bytes()).hexdigest()}
            prep={'project':str(root),'inputs_sha256':manifest,'tracked_inputs':[]}
            lines=''.join(f'{h}  {name}\n' for name,h in manifest.items())
            (root/'inputs.sha256').write_text(lines)
            self.assertEqual(review.verify_inputs(root,prep),1)
            p.write_bytes(b'changed')
            with self.assertRaises(review.Error):review.verify_inputs(root,prep)
            p.write_bytes(b'frozen');(root/'inputs.sha256').write_text(lines+lines)
            with self.assertRaises(review.Error):review.verify_inputs(root,prep)


if __name__=='__main__':unittest.main()
