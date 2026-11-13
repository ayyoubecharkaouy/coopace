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

if __name__=='__main__':unittest.main()
