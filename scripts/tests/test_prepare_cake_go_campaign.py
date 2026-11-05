"""Campaign bundle: simulated build and native-launcher generation, real hashes."""
from contextlib import ExitStack
import ast
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import test_prepare_cake_go_active as existing

prepare=existing.prepare
ENTRY=existing.SOURCE.with_name('prepare-cake-go-campaign.py')
spec=importlib.util.spec_from_file_location('campaign_prepare_cli',ENTRY)
cli=importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)
REVISION='c'*40


class PreparationTests(unittest.TestCase):
    def environment(self,stack,root,scenario='normal'):
        (root/'scripts').mkdir();(root/'docs').mkdir();(root/'sdk/bin').mkdir(parents=True)
        (root/'.go-version').write_text('1.27.3\n')
        for name in ('LAB_CAKE_GO_CAMPAIGN_PREPARE.md','LAB_CAKE_GO_PATH_NATIVE.md','LAB_CAKE_GO_ACTIVE_NATIVE.md'):
            (root/'docs'/name).write_text('fixed protocol\n')
        for name in ('prepare-cake-go-campaign.py','prepare-cake-go-path.py'):(root/'scripts'/name).write_text('fixed wrapper\n')
        for name in ('go','ip','tc','sysctl','ping'):
            p=root/'sdk/bin'/name;p.write_bytes(b'\x7fELFfixture');p.chmod(0o700)
        tracked=['.go-version','docs/LAB_CAKE_GO_CAMPAIGN_PREPARE.md','scripts/prepare-cake-go-campaign.py']
        calls=[]
        def command(args,**kwargs):
            calls.append(args)
            if args==['git','status','--porcelain']:return b' M source\n' if scenario=='dirty' else b''
            if args==['git','rev-parse','HEAD']:
                return 'd'*40 if scenario=='revision' and calls.count(args)>1 else REVISION
            if args==['git','ls-files','-z']:
                if scenario=='tool_changed':(root/'sdk/bin/tc').write_bytes(b'\x7fELFchanged')
                return ('\0'.join(tracked)+'\0').encode()
            if args[-2:]==['env','GOROOT']:return str(root/'sdk')+'\n'
            if 'version' in args:
                return 'binary: go1.27.3\n vcs.revision='+REVISION+'\n vcs.modified='+('true' if scenario=='provenance' else 'false')+'\n GOOS=linux\n GOARCH=amd64\n'
            if args[0]==str(root/'sdk/bin/tc'):return b'tc utility, iproute2-6.1.0\n'
            if args[-1]=='plan':return b'fixed plan\n'
            raise AssertionError(args)
        original_run=subprocess.run
        def run(args,**kwargs):
            calls.append(args)
            if 'build' in args:
                p=Path(args[args.index('-o')+1]);p.write_bytes(b'\x7fELFbinary');p.chmod(0o700)
                return subprocess.CompletedProcess(args,0)
            if args[0]=='sha256sum':return original_run(args,**kwargs)
            if args[:2]==['sh','-n']:return original_run(args,**kwargs)
            if args[0]==str(root/'sdk/bin/ping'):
                return subprocess.CompletedProcess(args,0,stdout=b'ping from iputils 20221126\n' if scenario!='ping' else b'unknown ping\n',stderr=b'')
            if str(args[0]).endswith(('coopace','coopace-lab-load','coopace-lab-tcp','coopace-cake-worker')):
                return subprocess.CompletedProcess(args,0,stdout=b'help\n',stderr=b'')
            raise AssertionError(args)
        stack.enter_context(patch.object(prepare,'ROOT',root))
        stack.enter_context(patch.object(prepare.os,'geteuid',return_value=1000))
        stack.enter_context(patch.object(prepare.os,'setns',create=True))
        stack.enter_context(patch.object(prepare.sys,'platform','linux'))
        stack.enter_context(patch.object(prepare.platform,'machine',return_value='x86_64'))
        stack.enter_context(patch.object(prepare,'command',side_effect=command))
        stack.enter_context(patch.object(prepare.subprocess,'run',side_effect=run))
        stack.enter_context(patch.object(prepare.shutil,'which',side_effect=lambda name:str(root/'sdk/bin'/name)))
        stack.enter_context(patch.object(prepare,'supervisor_sources',return_value={'fixed.py':'a'*64}))
        stack.enter_context(patch('sys.stdout',new=io.StringIO()))
        return calls

    def test_campaign_freezes_four_builds_sources_tools_manifests_and_launcher(self):
        with tempfile.TemporaryDirectory(prefix='campaign prepare ') as directory,ExitStack() as stack:
            root=Path(directory);calls=self.environment(stack,root);case=prepare.prepare(campaign=True)
            data=json.loads((case/'prepared.json').read_text())
            self.assertEqual(case.name,'go-campaign-native-validation-ccccccc')
            self.assertEqual(data['kind'],'lab_cake_go_campaign_preparation')
            self.assertEqual(data['native_steps'],['run','check-crash'])
            self.assertEqual(data['state'],'not_run');self.assertEqual(data['native_execution'],'not_run')
            self.assertTrue(data['native_launcher_available'])
            self.assertEqual(len(data['build_info']),4);self.assertEqual(len(data['tools']),9)
            self.assertTrue(data['ping_version']['stdout'].startswith('ping from iputils'))
            self.assertEqual(data['source_commit'],REVISION)
            for name,digest in data['inputs_sha256'].items():
                p=Path(name) if Path(name).is_absolute() else root/name
                self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),digest,name)
            self.assertEqual((case/'prepared.sha256').read_text().split()[0],hashlib.sha256((case/'prepared.json').read_bytes()).hexdigest())
            for name in ('run','check-crash','validation.json','runtime.json'):
                self.assertFalse((case/name).exists(),name)
            self.assertTrue((case/'prepare-campaign.py').is_file())
            ast.parse((case/'review-native.py').read_text())
            self.assertIn('lab-cake-go-campaign-review.py',(case/'review-native.py').read_text())
            self.assertIn('for coopace_mode in run check-crash;',(case/'run.sh').read_text())
            self.assertIn(str(case.relative_to(root)/'run.sh'),data['inputs_sha256'])
            self.assertIn(str(case.relative_to(root)/'review-native.py'),data['inputs_sha256'])
            self.assertFalse(any('sudo' in str(c[0]) or 'netns' in c for c in calls))
            self.assertEqual(len([c for c in calls if 'build' in c]),4)

    def test_legacy_profiles_still_generate_valid_launchers_and_review_wrappers(self):
        for path_control in (False,True):
            with self.subTest(path_control=path_control),tempfile.TemporaryDirectory() as directory,ExitStack() as stack:
                root=Path(directory);self.environment(stack,root);case=prepare.prepare(root/'case',path_control=path_control)
                data=json.loads((case/'prepared.json').read_text())
                self.assertEqual(data['native_steps'],['check','check-crash'])
                self.assertNotIn('native_launcher_available',data)
                ast.parse((case/'review-native.py').read_text())
                self.assertIn('lab-cake-go-path.py' if path_control else 'lab-cake-go-active.py',(case/'run.sh').read_text())

    def test_existing_destination_dirty_tree_and_bad_provenance_are_preserved(self):
        for scenario in ('existing','dirty','provenance','ping','revision','tool_changed'):
            with self.subTest(scenario=scenario),tempfile.TemporaryDirectory() as directory,ExitStack() as stack:
                root=Path(directory);calls=self.environment(stack,root,scenario);case=root/'case'
                if scenario=='existing':case.mkdir();(case/'keep').write_text('preserve')
                with self.assertRaises(Exception):prepare.prepare(case,campaign=True)
                if scenario=='existing':self.assertEqual((case/'keep').read_text(),'preserve')
                if scenario=='dirty':self.assertFalse(case.exists())
                if scenario in ('dirty','existing'):self.assertFalse(any('build' in c for c in calls))
                self.assertFalse((case/'prepared.json').exists())

    def test_profiles_and_sources_remain_distinct(self):
        self.assertEqual(prepare.profile()['kind'],'lab_cake_go_active_preparation')
        self.assertEqual(prepare.profile(True)['kind'],'lab_cake_go_path_preparation')
        with self.assertRaises(prepare.model.Error):prepare.profile(True,True)
        sources=prepare.supervisor_sources(campaign=True)
        self.assertIn(str(ENTRY.with_name('lab-cake-go-campaign.py')),sources)

    def test_wrapper_selects_only_campaign_profile_and_preserves_error_status(self):
        with patch.object(cli.model,'prepare') as run:
            self.assertEqual(cli.main(['--artifacts','case']),0)
            run.assert_called_once_with(Path('case'),campaign=True)
        with patch.object(cli.model,'prepare',side_effect=ValueError('refused')),patch('sys.stderr',new=io.StringIO()):
            self.assertEqual(cli.main([]),1)


if __name__=='__main__':unittest.main()
