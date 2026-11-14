"""Active bundle freezing and one-shot runner, with no privileged invocation."""
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
spec=importlib.util.spec_from_file_location('test_active_prepare',ROOT/'scripts/prepare-gateway-session-active.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)

class PreparationTests(unittest.TestCase):
    def test_active_runner_pins_transfer_binary_and_keeps_reviews_and_no_clobber(self):
        s=p.RUNNER.format(project=shlex.quote("/tmp/project with ' quotes"),case=shlex.quote('/tmp/case with spaces'),python='/usr/bin/python3')
        subprocess.run(['sh','-n'],input=s,text=True,check=True)
        for text in ('set -C','run.lock','--allow-lab','--worker "$coopace_case/coopace-session-worker"',
                     '--load "$coopace_case/coopace-lab-load"','for coopace_mode in check check-crash;','review --gateway',
                     'prepare-gateway-session-active.py','lab-gateway-session-active.py'):
            self.assertIn(text,s)
        self.assertNotIn('lab-queue-recovery.py',s)
    def test_changed_load_and_environment_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);load=folder/'load';load.write_bytes(b'frozen')
            value={'schema_version':1,'kind':'prepared_gateway_session_active_lab','revision':'revision',
                'kernel':platform.release(),'python_version':platform.python_version(),
                'inputs_sha256':{str(load):p.runtime.digest(load.read_bytes())},
                'tools':{'load':{'path':str(load),'sha256':p.runtime.digest(load.read_bytes())}},'source_sha256':p.model.source_hashes()}
            raw=json.dumps(value).encode();(folder/'prepared.json').write_bytes(raw);(folder/'prepared.sha256').write_text(p.runtime.digest(raw)+'\n')
            with patch.object(p,'command',return_value='revision'):
                self.assertEqual(p.verify(folder),value)
                with patch.object(p.platform,'release',return_value='changed-kernel'):
                    with self.assertRaisesRegex(Exception,'noyau.*changé|noyau.*changed-kernel'):p.verify(folder)
                load.write_bytes(b'changed')
                with self.assertRaisesRegex(Exception,'Entrée figée'):p.verify(folder)
    def test_dirty_tree_never_creates_a_case(self):
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'new'
            with patch.object(p,'command',return_value=' M source.py'):
                with self.assertRaises(Exception):p.prepare(target)
            self.assertFalse(target.exists())

if __name__=='__main__':unittest.main()
