"""Frozen inputs and one-shot session launcher, without privileged execution."""
import importlib.util
import json
from pathlib import Path
import platform
import shlex
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('test_prepare_session',ROOT/'scripts/prepare-gateway-session.py')
prepare=importlib.util.module_from_spec(spec);spec.loader.exec_module(prepare)

class SessionPreparationTests(unittest.TestCase):
    def test_runner_preserves_no_clobber_review_and_both_frozen_binaries(self):
        script=prepare.RUNNER.format(project=shlex.quote("/tmp/project with ' quotes"),case=shlex.quote('/tmp/case with spaces'),python='/usr/bin/python3')
        subprocess.run(['sh','-n'],input=script,text=True,check=True)
        for text in ('set -C','run.lock','for coopace_mode in check check-crash;','--allow-lab',
                     'review --gateway','--worker "$coopace_case/coopace-session-worker"','prepare-gateway-session.py','lab-gateway-session.py'):
            self.assertIn(text,script)
        self.assertNotIn('lab-queue-recovery.py',script)

    def test_manifest_rejects_changed_worker_and_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);worker=folder/'worker';worker.write_bytes(b'frozen worker')
            manifest={'schema_version':1,'kind':'prepared_gateway_session_lab','revision':'revision',
                'kernel':platform.release(),'python_version':platform.python_version(),
                'inputs_sha256':{str(worker):prepare.runtime.digest(worker.read_bytes())},
                'tools':{'worker':{'path':str(worker),'sha256':prepare.runtime.digest(worker.read_bytes())}},
                'source_sha256':prepare.model.source_hashes()}
            raw=json.dumps(manifest).encode();(folder/'prepared.json').write_bytes(raw)
            (folder/'prepared.sha256').write_text(prepare.runtime.digest(raw)+'\n')
            with patch.object(prepare,'command',return_value='revision'):
                self.assertEqual(prepare.verify(folder),manifest)
                worker.write_bytes(b'changed')
                with self.assertRaises(Exception):prepare.verify(folder)
                worker.write_bytes(b'frozen worker');(folder/'prepared.json').write_bytes(raw+b' ')
                with self.assertRaises(Exception):prepare.verify(folder)

    def test_dirty_tree_is_refused_before_creating_case(self):
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'new'
            with patch.object(prepare,'command',return_value=' M source.py'):
                with self.assertRaises(Exception):prepare.prepare(target)
            self.assertFalse(target.exists())

    def test_environment_mismatch_names_expected_and_current_values_before_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            manifest={'schema_version':1,'kind':'prepared_gateway_session_lab','revision':'revision',
                'kernel':'prepared-kernel','python_version':'prepared-python'}
            # No input/tool fields: a mismatch must fail before those reads.
            raw=json.dumps(manifest).encode();(folder/'prepared.json').write_bytes(raw)
            (folder/'prepared.sha256').write_text(prepare.runtime.digest(raw)+'\n')
            for kernel,python,labels in (
                ('current-kernel','prepared-python',('noyau',)),
                ('prepared-kernel','current-python',('Python',)),
                ('current-kernel','current-python',('noyau','Python')),
            ):
                with self.subTest(kernel=kernel,python=python):
                    with patch.object(prepare,'command',return_value='revision'), \
                         patch.object(prepare.platform,'release',return_value=kernel), \
                         patch.object(prepare.platform,'python_version',return_value=python):
                        with self.assertRaises(prepare.runtime.Error) as caught:prepare.verify(folder)
                    message=str(caught.exception)
                    self.assertIn('nouveau dossier',message)
                    for label,expected,current in (('noyau','prepared-kernel',kernel),('Python','prepared-python',python)):
                        if label in labels:
                            self.assertIn(f"{label} : préparé {expected!r}, actuel {current!r}",message)
                        else:self.assertNotIn(label+' :',message)

if __name__=='__main__':unittest.main()
