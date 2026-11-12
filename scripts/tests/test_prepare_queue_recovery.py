"""Manifest and one-shot shell launcher checks without privileged execution."""

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
spec=importlib.util.spec_from_file_location('test_prepare_recovery',ROOT/'scripts/prepare-queue-recovery.py')
prepare=importlib.util.module_from_spec(spec);spec.loader.exec_module(prepare)


class PreparationTests(unittest.TestCase):
    def test_runner_is_valid_shell_and_contains_both_modes_reviews_and_no_clobber(self):
        script=prepare.RUNNER.format(project=shlex.quote("/tmp/project with ' quotes"),case=shlex.quote('/tmp/case with spaces'),python='/usr/bin/python3')
        subprocess.run(['sh','-n'],input=script,text=True,check=True)
        self.assertIn('set -C',script)
        self.assertIn('for coopace_mode in check check-crash;',script)
        self.assertIn('run.lock',script)
        self.assertIn('review --gateway',script)
        self.assertIn('--prepared',script)

    def test_manifest_verification_rejects_changed_input_and_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            data=folder/'source.py';data.write_bytes(b'original')
            tool=folder/'tool';tool.write_bytes(b'executable')
            manifest={'schema_version':1,'kind':'prepared_queue_recovery_lab','revision':'revision',
                'kernel':platform.release(),'python_version':platform.python_version(),
                'inputs_sha256':{str(data):prepare.runtime.digest(data.read_bytes())},
                'tools':{'gateway':{'path':str(tool),'sha256':prepare.runtime.digest(tool.read_bytes())}},
                'source_sha256':prepare.model.source_hashes()}
            raw=json.dumps(manifest).encode()
            (folder/'prepared.json').write_bytes(raw)
            (folder/'prepared.sha256').write_text(prepare.runtime.digest(raw)+'\n')
            with patch.object(prepare,'command',return_value='revision'):
                self.assertEqual(prepare.verify(folder),manifest)
                data.write_bytes(b'changed')
                with self.assertRaises(Exception):prepare.verify(folder)
                data.write_bytes(b'original')
                (folder/'prepared.json').write_bytes(raw+b' ')
                with self.assertRaises(Exception):prepare.verify(folder)

    def test_preparation_requires_clean_tree_before_creating_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'new'
            with patch.object(prepare,'command',return_value=' M source.py'):
                with self.assertRaises(Exception):prepare.prepare(target)
            self.assertFalse(target.exists())


if __name__=='__main__':unittest.main()
