"""Pinned executable checks and bounded real subprocesses without networking."""

import contextlib
import importlib.util
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location("test_recovery_runtime",ROOT/"scripts/lab_recovery_runtime.py")
runtime=importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


class RuntimeTests(unittest.TestCase):
    def test_pinned_python_driver_can_reexec_helper_after_closing_inherited_fds(self):
        program=r'''
import importlib.util,json,os,subprocess,sys,time
from pathlib import Path
root=Path(sys.argv[1])
spec=importlib.util.spec_from_file_location('runtime',root/'scripts/lab_recovery_runtime.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
r.guards.enable_subreaper()
tools=r.Tools({name:sys.executable for name in ('ip','tc','gateway','python')})
owner=r.guards.Guard(r.guards.Namespaces('unused'),timeout=5)
try:
    owner.child=subprocess.Popen([tools.specs['python']['path'],'-I','-c',r.driver_program(tools),'check-crash'],
        executable=tools.executable('python'),pass_fds=tuple(tools.files.values()),
        stdout=subprocess.PIPE,start_new_session=True)
    os.set_blocking(owner.child.stdout.fileno(),False)
    owner.monitor('check-crash')
    owner.stop_group(time.monotonic()+3)
    assert owner.driver_code==-9 and owner.reaped_descendants==1
    assert not Path('/proc',str(owner.descendant)).exists()
finally:
    owner.close();tools.close()
'''
        result=subprocess.run([sys.executable,'-I','-B','-c',program,str(ROOT)],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_namespace_descriptor_type_is_checked_without_mutation(self):
        with tempfile.TemporaryFile() as stream:
            with self.assertRaises((OSError,runtime.Error)):runtime.network_namespace_identity(stream.fileno())
        try:
            fd=os.open('/proc/self/ns/net',os.O_RDONLY)
        except OSError as error:self.skipTest(str(error))
        try:
            expected=os.fstat(fd)
            self.assertEqual(runtime.network_namespace_identity(fd),(expected.st_dev,expected.st_ino))
        finally:os.close(fd)

    def test_script_and_changed_executable_are_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"tool"
            path.write_text("#!/bin/sh\nexit 0\n");path.chmod(0o700)
            with self.assertRaises(runtime.Error):runtime.Tools({"python":path})
            shutil.copyfile(Path(sys.executable).resolve(),path);path.chmod(0o700)
            tools=runtime.Tools({"python":path})
            try:
                tools.verify()
                path.unlink();path.write_bytes(b"\x7fELFchanged");path.chmod(0o700)
                with self.assertRaises(runtime.Error):tools.verify()
            finally:tools.close()

    def test_real_commands_limits_and_timeouts_leave_no_process(self):
        for code,timeout,success in (("print('ok')",2,True),("import time;time.sleep(30)",.05,False),
            ("import os;os.write(1,b'x'*600000)",2,False),("import os;os.write(2,b'x'*5000)",2,False)):
            with self.subTest(code=code),tempfile.TemporaryDirectory() as directory:
                folder=Path(directory)/"evidence";folder.mkdir()
                evidence=runtime.Evidence(folder)
                tools=runtime.Tools({name:sys.executable for name in ("ip","tc","gateway","python")})
                owner=runtime.guards.Guard(runtime.guards.Namespaces("unused"),timeout=5)
                runner=runtime.Runner(tools,evidence)
                try:
                    if success:
                        raw,status=runner.run(owner,"python",["-I","-c",code],timeout=timeout)
                        self.assertEqual((raw,status),(b"ok\n",0))
                    else:
                        with self.assertRaises(runtime.Error):runner.run(owner,"python",["-I","-c",code],timeout=timeout)
                    group=owner.process_groups[-1]
                    self.assertEqual(group.state,"stopped")
                    self.assertFalse(Path("/proc",str(group.child.pid)).exists())
                    self.assertTrue((folder/"command-001.stdout").exists())
                finally:
                    with contextlib.redirect_stderr(io.StringIO()):owner.close()
                    evidence.finish();tools.close()

    def test_evidence_is_exclusive_and_intent_is_flushed(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence=runtime.Evidence(directory)
            try:
                evidence.record("add_intent",handle="10:")
                self.assertIn(b'"add_intent"',runtime.read(Path(directory)/"events.jsonl"))
                evidence.save("before.json",b"{}\n")
                with self.assertRaises(FileExistsError):evidence.save("before.json",b"changed")
                with self.assertRaises(runtime.Error):evidence.save("../escape",b"no")
            finally:evidence.finish()
            with self.assertRaises(runtime.Error):runtime.Evidence(directory)

    def test_json_duplicate_keys_and_nonfinite_numbers_are_rejected(self):
        for raw in (b'{"a":1,"a":2}',b'{"n":1e999}',b'{"n":NaN}',b'[]',b'\xff'):
            with self.assertRaises(runtime.Error):runtime.document(raw)


if __name__=="__main__":unittest.main()
