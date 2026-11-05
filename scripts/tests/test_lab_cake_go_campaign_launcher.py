"""One-shot shell orchestration with fake sudo; never execute native controls."""
import json
import os
from pathlib import Path
import platform
import shlex
import subprocess
import sys
import tempfile
import unittest

import test_prepare_cake_go_active as common


class LauncherTests(unittest.TestCase):
    def run_shell(self,scenario='normal'):
        with tempfile.TemporaryDirectory(prefix='coopace launcher ') as directory:
            root=Path(directory);case=root/'case with spaces';case.mkdir();tools=root/'tools';tools.mkdir()
            for name,body in {
                'id':'printf "'+('0' if scenario=='root' else '1000')+'\\n"',
                'git':'printf "'+('wrong' if scenario=='revision' else 'a'*40)+'\\n"',
                'sha256sum':"test ! -f "+shlex.quote(str(root/'changed'))+'\nexit '+('1' if scenario=='inputs' else '$?'),
            }.items():
                p=tools/name;p.write_text('#!/bin/sh\n'+body+'\n');p.chmod(0o700)
            sudo=r'''
import json,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
scenario=(root/'scenario').read_text();args=sys.argv[1:]
assert args[0]=='--' and args[2:4]==['-I','-B']
assert args[4]==str(root/'scripts/lab-cake-go-campaign.py')
mode=args[5];assert mode in ('run','check-crash')
options=dict(zip(args[6::2],args[7::2]));case=root/'case with spaces'
assert options=={'--worker':str(case/'bin/worker'),'--binaries':str(case/'bin'),'--artifacts':str(case/mode)}
assert (case/mode).is_dir()
with (root/'calls.jsonl').open('a') as stream:stream.write(json.dumps({'mode':mode,'args':args})+'\n')
if scenario=='after_first' and mode=='run' or scenario=='before_review' and mode=='check-crash':(root/'changed').touch()
print(json.dumps({'mode':mode,'synthetic_test':True}))
if scenario=='first_fails' and mode=='run':raise SystemExit(7)
if scenario=='second_fails' and mode=='check-crash':raise SystemExit(8)
'''
            p=tools/'sudo';p.write_text('#!'+sys.executable+'\n'+sudo);p.chmod(0o700)
            (root/'scenario').write_text(scenario)
            reviewer=r'''
from pathlib import Path
import json
root=Path(__file__).resolve().parent.parent;case=root/'case with spaces'
assert (case/'run.exit').read_text()=='0\n' and (case/'check-crash.exit').read_text()=='0\n'
(root/'review-called').touch()
scenario=(root/'scenario').read_text()
if scenario=='after_review':(root/'changed').touch()
print(json.dumps({'state':'campaign_evidence_reviewed','native_certificate':False,'synthetic_test':True}))
if scenario=='review_fails':raise SystemExit(9)
'''
            (case/'review-native.py').write_text(reviewer)
            (case/'prepared.json').write_text(json.dumps({'kernel':platform.release(),'python_version':platform.python_version(),
                'native_launcher_available':scenario!='not_ready','native_steps':['run','check-crash'],'inputs_sha256':{}}))
            (case/'inputs.sha256').write_text('0'*64+'  omitted-file\n' if scenario=='manifest' else '')
            if scenario=='existing':(case/'runtime.json').write_text('preserve')
            if scenario=='symlink':(case/'review.stdout.json').symlink_to(root/'absent')
            if scenario=='lock':(case/'run.lock').mkdir()
            runner=common.prepare.runner_template(campaign=True)
            for token,value in (('PROJECT',root),('CASE',case),('PYTHON',sys.executable),('WORKER',case/'bin/worker'),('REVISION','a'*40)):
                runner=runner.replace('='+token+'\n','='+shlex.quote(str(value))+'\n')
            script=case/'run.sh';script.write_text(runner)
            subprocess.run(['sh','-n',str(script)],check=True)
            result=subprocess.run(['sh',str(script)],capture_output=True,text=True,timeout=8,env={**os.environ,'PATH':str(tools)+':'+os.environ['PATH']})
            calls=[json.loads(line)['mode'] for line in (root/'calls.jsonl').read_text().splitlines()] if (root/'calls.jsonl').exists() else []
            codes={mode:(case/(mode+'.exit')).read_text() for mode in ('run','check-crash','review') if (case/(mode+'.exit')).exists()}
            if scenario=='existing':self.assertEqual((case/'runtime.json').read_text(),'preserve')
            self.assertEqual((case/'run.lock').exists(),scenario=='lock')
            reviewed=(root/'review-called').exists()
            second=(case/'check-crash').exists()
            again=None
            if scenario=='normal':
                again=subprocess.run(['sh',str(script)],capture_output=True,text=True,timeout=8,env={**os.environ,'PATH':str(tools)+':'+os.environ['PATH']}).returncode
                self.assertEqual(len((root/'calls.jsonl').read_text().splitlines()),2)
            self.assertFalse((case/'validation.json').exists())
            return result,calls,codes,reviewed,second,again

    def test_success_runs_both_modes_then_unprivileged_review_and_refuses_reuse(self):
        result,calls,codes,reviewed,_,again=self.run_shell()
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(calls,['run','check-crash']);self.assertTrue(reviewed)
        self.assertEqual(codes,{'run':'0\n','check-crash':'0\n','review':'0\n'});self.assertEqual(again,2)

    def test_existing_results_symlink_lock_root_or_changed_inputs_never_call_sudo(self):
        for scenario in ('existing','symlink','lock','root','inputs','revision','manifest','not_ready'):
            with self.subTest(scenario=scenario):
                result,calls,codes,reviewed,_,_=self.run_shell(scenario)
                self.assertEqual(result.returncode,2,result.stderr);self.assertEqual(calls,[]);self.assertEqual(codes,{})
                self.assertFalse(reviewed)

    def test_failed_first_control_preserves_code_and_stops_before_second(self):
        result,calls,codes,reviewed,second,_=self.run_shell('first_fails')
        self.assertEqual(result.returncode,7,result.stderr);self.assertEqual(calls,['run'])
        self.assertEqual(codes,{'run':'7\n'});self.assertFalse(reviewed);self.assertFalse(second)

    def test_failed_second_control_never_reviews(self):
        result,calls,codes,reviewed,_,_=self.run_shell('second_fails')
        self.assertEqual(result.returncode,8,result.stderr);self.assertEqual(calls,['run','check-crash'])
        self.assertEqual(codes,{'run':'0\n','check-crash':'8\n'});self.assertFalse(reviewed)

    def test_changed_inputs_between_controls_or_before_review_stop_the_chain(self):
        for scenario,expected in (('after_first',['run']),('before_review',['run','check-crash'])):
            with self.subTest(scenario=scenario):
                result,calls,_,reviewed,_,_=self.run_shell(scenario)
                self.assertEqual(result.returncode,2,result.stderr);self.assertEqual(calls,expected);self.assertFalse(reviewed)

    def test_failed_review_preserves_exit_code(self):
        result,_,codes,reviewed,_,_=self.run_shell('review_fails')
        self.assertEqual(result.returncode,9,result.stderr);self.assertTrue(reviewed);self.assertEqual(codes['review'],'9\n')

    def test_changed_inputs_after_review_prevent_success(self):
        result,_,codes,reviewed,_,_=self.run_shell('after_review')
        self.assertEqual(result.returncode,2,result.stderr);self.assertTrue(reviewed);self.assertEqual(codes['review'],'0\n')


if __name__=='__main__':unittest.main()
