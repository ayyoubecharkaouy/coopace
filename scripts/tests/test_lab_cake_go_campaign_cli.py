"""Campaign entry: inert plan, explicit inputs, preflight and exit contract."""
from contextlib import ExitStack, redirect_stderr, redirect_stdout
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SOURCE=Path(__file__).resolve().parents[1]/'lab-cake-go-campaign.py'
spec=importlib.util.spec_from_file_location('campaign_cli_tests',SOURCE)
cli=importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)


class CommandTests(unittest.TestCase):
    def invoke(self,args):
        stdout,stderr=io.StringIO(),io.StringIO()
        with redirect_stdout(stdout),redirect_stderr(stderr):
            try:code=cli.main(args)
            except SystemExit as error:code=error.code
        return code,stdout.getvalue(),stderr.getvalue()

    def prepared(self,stack,root,mode='run'):
        worker=root/'worker';worker.write_bytes(b'placeholder');worker.chmod(0o700)
        binaries=root/'bin';binaries.mkdir();artifacts=root/'artifacts';artifacts.mkdir()
        stack.enter_context(patch.object(cli.os,'setns',create=True))
        stack.enter_context(patch.object(cli.platform,'machine',return_value='x86_64'))
        stack.enter_context(patch.object(cli.sys,'platform','linux'))
        preflight=stack.enter_context(patch.object(cli.go.guards,'preflight',return_value='owned-context'))
        stack.enter_context(patch.object(cli.shutil,'which',side_effect=lambda name:'/tools/'+name))
        run=stack.enter_context(patch.object(cli.model,'run'))
        run.return_value={'kind':'lab_cake_go_campaign','state':'complete','technical_valid':None if mode=='check-crash' else True,
                          'load_scenario':'not_assessed' if mode=='check-crash' else 'not_qualified','connections':'degraded'}
        args=[mode,'--worker',str(worker),'--binaries',str(binaries),'--artifacts',str(artifacts)]
        return args,preflight,run

    def test_default_and_explicit_plan_never_preflight_resolve_paths_or_execute(self):
        with patch.object(cli.go.guards,'preflight',side_effect=AssertionError('preflight')), \
             patch.object(cli.model,'run',side_effect=AssertionError('run')), \
             patch.object(cli.shutil,'which',side_effect=AssertionError('tools')):
            for args in ([],['plan'],['plan','--artifacts','/missing/coopace/plan']):
                code,out,err=self.invoke(args)
                self.assertEqual(code,0,err);self.assertIn('60 tentatives TCP',out)
                self.assertIn('ne crée aucune ressource',out)

    def test_subprocess_help_plan_and_usage_require_no_network_tools(self):
        with tempfile.TemporaryDirectory() as root:
            for args,code in (([],0),(['plan'],0),(['--help'],0),(['run'],2),(['check-crash'],2),(['check'],2)):
                result=subprocess.run([sys.executable,'-I','-B',str(SOURCE),*args],cwd=root,
                                      env={**os.environ,'PATH':root},capture_output=True,text=True,timeout=5)
                self.assertEqual(result.returncode,code,result.stderr)
            self.assertEqual(list(Path(root).iterdir()),[])

    def test_each_execution_input_is_mandatory_before_preflight(self):
        for mode in ('run','check-crash'):
            for missing in ('--worker','--binaries','--artifacts'):
                args=[mode]
                for flag in ('--worker','--binaries','--artifacts'):
                    if flag!=missing:args.extend([flag,'/missing'])
                with patch.object(cli.go.guards,'preflight') as preflight:
                    code,out,_=self.invoke(args)
                    self.assertEqual(code,2);self.assertEqual(out,'');preflight.assert_not_called()

    def test_success_routes_canonical_paths_and_preserves_unqualified_results(self):
        for mode in ('run','check-crash'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as root,ExitStack() as stack:
                args,preflight,run=self.prepared(stack,Path(root),mode)
                code,out,err=self.invoke(args)
                self.assertEqual(code,0,err);self.assertEqual(json.loads(out),run.return_value)
                preflight.assert_called_once_with()
                run.assert_called_once_with(mode,'owned-context',(Path(root)/'worker').resolve(),'/tools/tc','/tools/sysctl','/tools/ping',
                                            (Path(root)/'bin').resolve(),(Path(root)/'artifacts').resolve())

    def test_existing_artifacts_and_invalid_paths_are_refused_without_preflight(self):
        for case in ('occupied','artifact_file','missing_worker','binary_file','not_executable'):
            with self.subTest(case=case),tempfile.TemporaryDirectory() as root,ExitStack() as stack:
                root=Path(root);args,preflight,run=self.prepared(stack,root)
                if case=='occupied':(root/'artifacts'/'keep').write_text('preserve')
                if case=='artifact_file':(root/'artifacts').rmdir();(root/'artifacts').write_text('preserve')
                if case=='missing_worker':(root/'worker').unlink()
                if case=='binary_file':(root/'bin').rmdir();(root/'bin').write_text('preserve')
                if case=='not_executable':(root/'worker').chmod(0o600)
                code,out,_=self.invoke(args)
                self.assertEqual(code,1);self.assertEqual(out,'');preflight.assert_not_called();run.assert_not_called()
                if case=='occupied':self.assertEqual((root/'artifacts'/'keep').read_text(),'preserve')

    def test_platform_preflight_and_missing_tool_stop_before_run(self):
        for case in ('platform','privileges','tools'):
            with self.subTest(case=case),tempfile.TemporaryDirectory() as root,ExitStack() as stack:
                args,preflight,run=self.prepared(stack,Path(root))
                if case=='platform':stack.enter_context(patch.object(cli.platform,'machine',return_value='unsupported'))
                if case=='privileges':preflight.side_effect=cli.go.guards.GuardError('no privileges')
                if case=='tools':stack.enter_context(patch.object(cli.shutil,'which',return_value=None))
                code,out,_=self.invoke(args)
                self.assertEqual(code,1);self.assertEqual(out,'');run.assert_not_called()

    def test_failures_interruptions_and_inconsistent_returns_never_print_success(self):
        for case,expected in (('error',1),('measurement',1),('interrupt',143),('kind',1),('state',1),('verdict',1)):
            with self.subTest(case=case),tempfile.TemporaryDirectory() as root,ExitStack() as stack:
                args,_,run=self.prepared(stack,Path(root))
                if case=='error':run.side_effect=OSError('capture failed')
                if case=='measurement':run.side_effect=cli.model.verdict.Error('non exploitable')
                if case=='interrupt':run.side_effect=cli.go.guards.Interrupted(143)
                if case=='kind':run.return_value['kind']='lab_cake_go_campaign_collection'
                if case=='state':run.return_value['state']='failed'
                if case=='verdict':run.return_value['technical_valid']=False
                code,out,err=self.invoke(args)
                self.assertEqual(code,expected);self.assertEqual(out,'');self.assertTrue(err)

    def test_entry_is_part_of_runtime_source_fingerprints(self):
        fingerprints=cli.model.source_fingerprints()
        self.assertEqual(fingerprints[str(SOURCE)],hashlib.sha256(SOURCE.read_bytes()).hexdigest())


if __name__=='__main__':unittest.main()
