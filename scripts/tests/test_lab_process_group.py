"""Real group anchors and reaping, with no namespaces or network operations."""

import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "lab_process_group.py"
HARNESS = r'''
import importlib.util,os,subprocess,sys,time
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('groups',sys.argv[1]);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
scenario=sys.argv[2]
group=m.ProcessGroup()
child=subprocess.Popen([sys.executable,'-I','-c','pass'],stdout=subprocess.PIPE,start_new_session=True)
group.attach(child)
deadline=time.monotonic()+3
while not group.exited():
 assert time.monotonic()<deadline
 time.sleep(.005)
killpg=os.killpg;waitpid=os.waitpid;signals=[]
def signal_group(pid,sig):
 assert child.returncode is None,'leader released before signal'
 assert os.waitid(os.P_PID,pid,os.WEXITED|os.WNOHANG|os.WNOWAIT) is not None
 signals.append(sig);killpg(pid,sig)
def wait(pid,flags):
 if scenario=='uncertain_after_reap' and pid==-child.pid:raise OSError('injected post-reap failure')
 return waitpid(pid,flags)
if scenario in ('external_wait','external_waitpid'):
 if scenario=='external_wait':child.wait()
 else:os.waitpid(child.pid,0)
 with patch.object(m.os,'killpg',side_effect=AssertionError('signal after external reap')):
  try:group.stop(time.monotonic()+1)
  except (m.GroupError,ChildProcessError):pass
  else:raise AssertionError('external reap accepted')
else:
 with patch.object(m.os,'killpg',side_effect=signal_group),patch.object(m.os,'waitpid',side_effect=wait):
  try:group.stop(time.monotonic()+2)
  except OSError:
   assert scenario=='uncertain_after_reap' and group.leader_reaped
  else:assert scenario=='normal'
 assert len(signals)==2 and group.driver_code==0
with patch.object(m.os,'killpg',side_effect=AssertionError('signal on repeated stop')):
 if scenario=='normal':
  group.stop(time.monotonic()+1);group.require_stopped()
 else:
  try:group.stop(time.monotonic()+1)
  except m.GroupError:pass
  else:raise AssertionError('uncertain stop became successful')
try:group.attach(child)
except m.GroupError:pass
else:raise AssertionError('group reused')
assert not __import__('pathlib').Path('/proc',str(child.pid)).exists()
print(group.state)
'''


@unittest.skipUnless(sys.platform == "linux", "Linux group ownership")
class ProcessGroupTests(unittest.TestCase):
    def test_repeated_stop_never_signals_after_leader_reap(self):
        self.run_case("normal", "stopped")

    def test_uncertain_descendants_after_reap_permanently_block_retry(self):
        self.run_case("uncertain_after_reap", "failed")

    def test_externally_reaped_leader_cannot_anchor_a_signal(self):
        for scenario in ("external_wait", "external_waitpid"):
            with self.subTest(scenario=scenario):
                self.run_case(scenario, "failed")

    def run_case(self, scenario, state):
        result = subprocess.run([sys.executable, "-I", "-B", "-c", HARNESS, str(SOURCE), scenario],
                                capture_output=True, text=True, timeout=6)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), state)


if __name__ == "__main__":
    unittest.main()
