"""Preparation guards and one-shot shell flow, with a fake sudo only."""

import importlib.util
import json
import os
from pathlib import Path
import platform
import shlex
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SOURCE=Path(__file__).resolve().parents[1]/'prepare-cake-go-active.py'
spec=importlib.util.spec_from_file_location('prepare',SOURCE)
prepare=importlib.util.module_from_spec(spec);spec.loader.exec_module(prepare)


class PreparationTests(unittest.TestCase):
    def test_dirty_tree_is_refused_before_build_or_directory_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            destination=Path(directory)/'unused'
            with patch.object(prepare.os,'geteuid',return_value=1000),patch.object(prepare,'command',return_value=b' M source\n') as command:
                with self.assertRaisesRegex(prepare.model.Error,'non propre'):prepare.prepare(destination)
                command.assert_called_once_with(['git','status','--porcelain'])
            self.assertFalse(destination.exists())

    def run_shell(self,scenario):
        with tempfile.TemporaryDirectory(prefix='coopace prepare ') as directory:
            root=Path(directory);case=root/'case with spaces';case.mkdir();tools=root/'tools';tools.mkdir()
            for name,body in {
                'id':'printf "1000\\n"',
                'git':'printf "'+('wrong' if scenario=='revision' else 'a'*40)+'\\n"',
                'sha256sum':'exit '+('1' if scenario=='inputs' else '0'),
                'sudo':'printf "called\\n" >> '+shlex.quote(str(root/'sudo.calls'))+'\nexit 7',
            }.items():
                p=tools/name;p.write_text('#!/bin/sh\n'+body+'\n');p.chmod(0o700)
            (case/'prepared.json').write_text(json.dumps({'kernel':platform.release(),'python_version':platform.python_version()}))
            if scenario=='existing':(case/'runtime.json').write_text('preserved')
            runner=prepare.RUNNER
            for token,value in (('PROJECT',root),('CASE',case),('PYTHON',os.sys.executable),('WORKER',case/'bin/worker'),('REVISION','a'*40)):
                runner=runner.replace('='+token+'\n','='+shlex.quote(str(value))+'\n')
            path=case/'run.sh';path.write_text(runner)
            subprocess.run(['sh','-n',str(path)],check=True)
            process=subprocess.run(['sh',str(path)],capture_output=True,text=True,
                                   env={**os.environ,'PATH':str(tools)+':'+os.environ['PATH']},timeout=5)
            self.assertFalse((case/'run.lock').exists())
            calls=(root/'sudo.calls').read_text() if (root/'sudo.calls').exists() else ''
            if scenario=='existing':self.assertEqual((case/'runtime.json').read_text(),'preserved')
            return process,calls,(case/'check-crash').exists(),(case/'check.exit').read_text() if (case/'check.exit').exists() else None

    def test_existing_results_changed_inputs_and_revision_never_call_sudo(self):
        for scenario in ('existing','inputs','revision'):
            with self.subTest(scenario=scenario):
                process,calls,second,code=self.run_shell(scenario)
                self.assertEqual(process.returncode,2,process.stderr)
                self.assertEqual(calls,'');self.assertFalse(second);self.assertIsNone(code)

    @unittest.skipUnless(hasattr(os,'setns'),'Python setns precondition')
    def test_failed_first_control_is_preserved_and_stops_the_second(self):
        process,calls,second,code=self.run_shell('first_fails')
        self.assertEqual(process.returncode,7,process.stderr)
        self.assertEqual(calls,'called\n');self.assertFalse(second);self.assertEqual(code,'7\n')


if __name__=='__main__':unittest.main()
