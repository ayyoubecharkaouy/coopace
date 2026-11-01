"""Retain owned fake namespaces across real, independently reaped groups."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("phase_fixtures", Path(__file__).with_name("test_lab_cake_go.py"))
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)

NEXT_WORKER = r'''
import os,signal,subprocess,sys,time
from pathlib import Path
root=Path(sys.argv[1]);(root/'proc'/str(os.getpid())).touch()
children=[]
for _ in range(3):
 child=subprocess.Popen([sys.executable,'-I','-c','import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);print("READY",flush=True);time.sleep(60)'],stdout=subprocess.PIPE)
 assert child.stdout.readline()==b'READY\n';child.stdout.close();children.append(child)
 (root/'proc'/str(child.pid)).touch()
print('READY '+str(children[0].pid),flush=True)
time.sleep(60)
'''

HARNESS = fixtures.HARNESS[:fixtures.HARNESS.index("try:\n result=m.run")] + r'''
from unittest.mock import patch
import time
m.guards.enable_subreaper()
owner=m.GoGuard(Namespaces(),tempdir=root,timeout=.6 if scenario=='hang' else 8)
tools={name:m.tool(sys.executable) for name in ('worker','python','ip','tc')}
owner.namespaces.ip=tools['ip']['path']
if scenario=='existing_evidence':(artifacts/'events.bin').write_bytes(b'preserve existing evidence')
if scenario=='late_deadline':
 original_persist=Session.persist
 def expire_after_persist(self):
  original_persist(self);self.owner.deadline=time.monotonic()-1
 Session.persist=expire_after_persist
if scenario=='cleanup_failure':
 original_monitor=Session.monitor
 def fail_after_monitor(self,mode):
  original_monitor(self,mode)
  raise m.Error('injected phase failure before handoff')
 Session.monitor=fail_after_monitor
before=None;phase=None;error=None;transition_blocked=False
try:
 owner.create();link=m.DownLink(owner.namespaces,tools['tc']['path']);link.prepare(owner)
 if scenario=='uncertain_stop':
  original=owner.process_group.stop
  def fail_after_wait(deadline):
   original(deadline);owner.process_group.state='failed';owner.process_group.failure=OSError('injected uncertainty')
   raise m.guards.GuardError('injected uncertainty')
  owner.process_group.stop=fail_after_wait
 phase=m.run_phase(owner,tools,artifacts,link,session_factory=Session,mode=mode)
 assert len(list((root/'namespaces').iterdir()))==3 and owner.workspace.exists()
 assert not owner.closed and phase['cleanup']=='deferred_to_supervisor' and 'cleanup_verified' not in phase
 assert owner.session.fds==[] and (artifacts/'events.bin').exists()
 assert not Path('/proc',str(owner.child.pid)).exists()
 before={'names':list(owner.owned),'workspace':owner.workspace,'deadline':owner.deadline,'group':owner.process_group}
 with patch.object(m.guards.processes.os,'killpg',side_effect=AssertionError('signal on repeated phase close')):
  owner.stop_group(time.monotonic()+1)
 if mode=='check-crash':
  try:owner.advance_group()
  except m.Error:transition_blocked=True
  else:raise AssertionError('crashed Go phase allowed transition')
 else:
  owner.advance_group()
  assert owner.deadline==before['deadline'] and owner.workspace==before['workspace'] and owner.owned==before['names']
  owner.start([sys.executable,'-I','-B','-c',sys.argv[6],str(root)])
  owner.monitor('check-crash')
finally:
 try:owner.close()
 except Exception as caught:error=str(caught)
 if owner.phase_failure is not None:
  try:owner.advance_group()
  except (m.Error,m.guards.GuardError):transition_blocked=True
  else:raise AssertionError('failed Go phase allowed transition')
  if owner.close_error is not None:
   try:owner.close()
   except m.guards.GuardError:pass
   else:raise AssertionError('failed cleanup became successful')
 summary={'phase':phase,'transition_blocked':transition_blocked,'close_error':error,
          'groups':[{'pid':g.child.pid if g.child else None,'state':g.state,'code':g.driver_code,'descendants':g.reaped_descendants} for g in owner.process_groups],
          'remaining_names':len(list((root/'namespaces').iterdir())),'workspace_retained':owner.workspace.exists(),
          'phase_failed':owner.phase_failure is not None}
 (root/'summary.json').write_text(json.dumps(summary))
 if scenario=='existing_evidence':assert (artifacts/'events.bin').read_bytes()==b'preserve existing evidence'
'''


@unittest.skipUnless(sys.platform == "linux", "Linux phase supervision")
class GoPhaseTests(unittest.TestCase):
    def run_case(self, scenario="normal", mode="check"):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worker = fixtures.FAKE_WORKER + ("\nraise SystemExit(7)\n" if scenario == "exit_mismatch" else "")
            result = subprocess.run([sys.executable, "-I", "-B", "-c", HARNESS, str(fixtures.SOURCE),
                                     str(root), scenario, mode, worker, NEXT_WORKER],
                                    capture_output=True, text=True, timeout=15)
            summary = json.loads((root / "summary.json").read_text())
            for pid in (root / "proc").iterdir():
                self.assertFalse(Path("/proc", pid.name).exists(), result.stderr)
            return result, summary

    def test_completed_phase_retains_resources_then_reaps_three_new_orphans(self):
        result, report = self.run_case()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(report["phase"]["state"], "finished")
        self.assertEqual(report["phase"]["journal"]["tool_calls"], 14)
        self.assertEqual([(g["code"], g["descendants"]) for g in report["groups"]], [(0, 0), (-9, 3)])
        self.assertEqual(report["remaining_names"], 0)
        self.assertFalse(report["workspace_retained"])

    def test_go_crash_is_terminal_even_after_successful_group_recovery(self):
        result, report = self.run_case(mode="check-crash")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(report["transition_blocked"])
        self.assertEqual(len(report["groups"]), 1)
        self.assertEqual(report["remaining_names"], 0)

    def test_failed_phase_cannot_start_next_group(self):
        for scenario in ("wrong_session", "bad_journal", "post_read_failure", "hang", "orphan", "cleanup_failure",
                         "uncertain_stop", "exit_mismatch", "late_deadline", "existing_evidence"):
            with self.subTest(scenario=scenario):
                result, report = self.run_case(scenario)
                self.assertNotEqual(result.returncode, 0, result.stderr)
                self.assertTrue(report["phase_failed"])
                self.assertTrue(report["transition_blocked"])
                self.assertEqual(len(report["groups"]), 1)
                expected = 3 if scenario == "uncertain_stop" else 1 if scenario == "cleanup_failure" else 0
                self.assertEqual(report["remaining_names"], expected, result.stderr)
                self.assertEqual(report["workspace_retained"], bool(expected))

    def test_failed_reference_close_is_permanent_without_retrying_fd_numbers(self):
        m = fixtures.model
        owner = SimpleNamespace(workspace=Path("/tmp/coopace-guard.abcd1234"))
        session = m.Session(owner, {}, Path("/tmp"), None)
        descriptor = session.keep(os.open("/dev/null", os.O_RDONLY))
        close = os.close
        try:
            with patch.object(m.os, "close", side_effect=OSError("injected close failure")):
                with self.assertRaises(m.Error):
                    session.close()
            with patch.object(m.os, "close", side_effect=AssertionError("retrying a possibly reused FD")):
                with self.assertRaises(m.Error):
                    session.close()
        finally:
            close(descriptor)

    def test_failed_owner_close_remains_failed_and_cannot_spawn_a_new_child(self):
        m = fixtures.model
        with tempfile.TemporaryDirectory() as directory:
            owner = m.GoGuard(m.guards.Namespaces("unused-ip", Path(directory)))
            with patch.object(owner, "stop_group", side_effect=m.guards.GuardError("uncertain")) as stop:
                for _ in range(2):
                    with self.assertRaises(m.guards.GuardError):
                        owner.close()
                self.assertEqual(stop.call_count, 1)
            with patch.object(m.subprocess, "Popen", side_effect=AssertionError("new child after close")):
                with self.assertRaises(m.guards.GuardError):
                    owner.start(["unused"])


if __name__ == "__main__":
    unittest.main()
