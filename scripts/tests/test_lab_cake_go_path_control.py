"""Bounded real commands plus full handoff with a simulated IPv4 kernel."""

import base64
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_lab_cake_go_active as fixtures
import test_lab_cake_go_path as captures

SOURCE = fixtures.SOURCE.with_name("lab_cake_go_path_control.py")
spec = importlib.util.spec_from_file_location("path_control_tests", SOURCE)
model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)


class CommandTests(unittest.TestCase):
    def owner(self, seconds=3):
        owner = SimpleNamespace(deadline=time.monotonic() + seconds, closed=False, command_child=None, interrupted=False)
        def check():
            if owner.interrupted or time.monotonic() >= owner.deadline:
                raise RuntimeError("interruption or owner deadline")
        owner.check = check
        return owner

    def execute(self, code, owner=None):
        owner = owner or self.owner()
        result = model.outcome()
        model.execute(owner, [sys.executable, "-I", "-B", "-c", code], 2, result)
        self.assertIsNone(owner.command_child)
        self.assertFalse(Path("/proc", str(result["pid"])).exists())
        return result

    def test_two_pipes_stdin_eof_locale_and_actual_nonzero_status(self):
        result = self.execute('import os,sys; assert sys.stdin.read()==""; '
                              'assert os.environ["LC_ALL"]==os.environ["LANG"]=="C"; '
                              'print("capture"); print("diagnostic",file=sys.stderr); sys.exit(1)')
        self.assertEqual((result["stdout"], result["stderr"], result["exit_code"]), (b"capture\n", b"diagnostic\n", 1))
        self.assertTrue(result["process_stopped"])

    def test_each_pipe_is_bounded_and_child_is_reaped_on_overflow(self):
        for descriptor, name in ((1, "stdout"), (2, "stderr")):
            with self.subTest(pipe=name):
                owner, result = self.owner(), model.outcome()
                with self.assertRaisesRegex(model.Error, "volumineuse"):
                    model.execute(owner, [sys.executable, "-I", "-c",
                                  f'import os,time;os.write({descriptor},b"x"*200000);time.sleep(60)'], 2, result)
                self.assertEqual(len(result[name]), model.readers.OUTPUT_LIMIT)
                self.assertTrue(result[name + "_truncated"])
                self.assertTrue(result["process_stopped"])
                self.assertIsNone(owner.command_child)
                self.assertFalse(Path("/proc", str(result["pid"])).exists())

    def test_command_deadline_and_owner_interruption_reap_real_children(self):
        for scenario in ("command_deadline", "owner_deadline", "interruption"):
            with self.subTest(scenario=scenario):
                owner = self.owner(.05 if scenario == "owner_deadline" else 5)
                original = owner.check
                def check():
                    if scenario == "interruption" and owner.command_child is not None:
                        owner.interrupted = True
                    original()
                owner.check = check
                result = model.outcome()
                with self.assertRaises((model.Error, RuntimeError)):
                    model.execute(owner, [sys.executable, "-I", "-c", 'import time;time.sleep(60)'], 2, result)
                self.assertTrue(result["process_stopped"])
                self.assertIsNone(owner.command_child)
                self.assertFalse(Path("/proc", str(result["pid"])).exists())

    def test_launch_failure_preserves_no_pid_and_does_not_replace_a_child(self):
        owner, result = self.owner(), model.outcome()
        with self.assertRaises(FileNotFoundError):
            model.execute(owner, ["/missing-coopace-path-tool"], 2, result)
        self.assertIsNone(owner.command_child)
        self.assertIsNone(result["pid"])
        owner.command_child = object()
        with self.assertRaises(model.Error):
            model.execute(owner, [sys.executable], 2, result)

    def test_uncertain_wait_keeps_child_owned_for_final_cleanup(self):
        owner, result = self.owner(.05), model.outcome()
        child = subprocess.Popen([sys.executable, "-I", "-c", "import time;time.sleep(60)"],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            with patch.object(model.subprocess, "Popen", return_value=child), \
                 patch.object(child, "wait", side_effect=subprocess.TimeoutExpired("child", 1)):
                with self.assertRaises(subprocess.TimeoutExpired):
                    model.execute(owner, [sys.executable], 2, result)
            self.assertIs(owner.command_child, child)
            self.assertFalse(result["process_stopped"])
        finally:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=2)

    def test_version_capture_requires_iputils_and_keeps_both_pipes(self):
        inventory = model.Inventory.__new__(model.Inventory)
        inventory.owner, inventory.tools, inventory.verify = self.owner(), {"ping": {"path": "/ping"}}, lambda: None
        def version(owner, arguments, timeout, result):
            result.update(stdout=b"ping from iputils 20240117\n", stderr=b"details\n", exit_code=0, process_stopped=True)
        with patch.object(model.active.Inventory, "metadata", return_value={"versions": {}}), \
             patch.object(model, "execute", side_effect=version):
            self.assertEqual(inventory.metadata()["versions"]["ping"]["stderr"], "details\n")
        def other(owner, arguments, timeout, result):
            result.update(stdout=b"BusyBox ping\n", exit_code=0)
        with patch.object(model.active.Inventory, "metadata", return_value={"versions": {}}), \
             patch.object(model, "execute", side_effect=other), self.assertRaises(model.Error):
            inventory.metadata()

    def test_out_of_order_or_repeated_command_is_refused_before_execution(self):
        checker = model.PathCheck.__new__(model.PathCheck)
        checker.report, checker.next_command, checker.commands = {"state": "running"}, 0, (None,) * 6
        with self.assertRaises(model.Error):
            checker.command(2)
        checker.report["state"] = "verified"
        with self.assertRaises(model.Error):
            checker.command(0)


ADAPTER = r'''
spec=importlib.util.spec_from_file_location('path_runtime',source.with_name('lab_cake_go_path_control.py'))
path_runtime=importlib.util.module_from_spec(spec);spec.loader.exec_module(path_runtime)
path_kernel_execute=Kernel.execute
def path_kernel(self,args,owner):
 raw=path_kernel_execute(self,args,owner)
 if 'qdisc' in args and (root/'path_started').exists() and not self.forward:
  rows=json.loads(raw);rows[0]['bytes']=self.count;rows[0]['packets']=self.up_reads
  return json.dumps(rows).encode()
 return raw
Kernel.execute=path_kernel
class PathInventory(Inventory):
 source_fingerprints=staticmethod(path_runtime.source_fingerprints)
 def __init__(self,*args):
  super().__init__(*args);self.tools['ping']=self.fingerprint(sys.executable)
class PathCheck(path_runtime.PathCheck):
 def run(self):
  if scenario=='path_unverified':return
  return super().run()
 @staticmethod
 def executor(owner,args,timeout,result):
  kernel.calls.append(args)
  (root/'path_started').touch()
  stdout=b'';stderr=b'';code=0
  negative='-c' in args and args[args.index('-c')+1]=='1'
  positive='-c' in args and args[args.index('-c')+1]=='3'
  if '-w' in args and args[-1].startswith('net.ipv4.ip_forward='):
   kernel.forward=int(args[-1][-1])
   if not kernel.forward and scenario=='path_write_error':code=2
   if not kernel.forward and scenario=='path_link_changed':kernel.rows[owner.owned[1][0]]['wan']['mtu']=1400
  elif args[-2:]==['-n','net.ipv4.ip_forward']:
   stdout=(str(kernel.forward)+'\n').encode()
   if not kernel.forward and scenario=='path_read_mismatch':stdout=b'1\n'
  elif negative or positive:
   kernel.count+=200
   stdout=NEGATIVE if negative else POSITIVE;code=1 if negative else 0
   # iputils -w waits for replies and may retry despite -c 1. Model that
   # documented behavior instead of assuming -c always caps transmissions.
   if negative and '-w' in args:stdout=NEGATIVE.replace(b'1 packets',b'3 packets')
   if negative and scenario=='path_negative_reply':stdout=NEGATIVE.replace(b'0 received',b'1 received');code=0
   if negative and scenario=='path_negative_empty':stdout=b''
   if negative and scenario=='path_negative_technical':code=2;stderr=b'Operation not permitted\n'
   if negative and scenario=='path_negative_count':stdout=NEGATIVE.replace(b'1 packets',b'3 packets')
   if positive and scenario=='path_positive_partial':stdout=POSITIVE.replace(b'3 received',b'2 received')
   if negative and scenario=='path_interrupt':owner.interruption=143
   if negative and scenario=='path_deadline':owner.deadline=time.monotonic()-1
   if negative and scenario=='path_tool_changed':inventory_for_test.tools['ping']['sha256']='0'*64
  else:raise AssertionError(args)
  result.update(stdout=stdout,stderr=stderr,exit_code=code,process_stopped=True)
 def __init__(self,*args):
  global inventory_for_test
  super().__init__(*args);inventory_for_test=self.inventory
path_write=combined.Journal.write
def path_record(self,event):
 if scenario=='path_intent_failure' and event['event']=='path_tool_intent':raise OSError('injected path intent failure')
 if scenario=='path_result_failure' and event['event']=='path_tool_result':raise OSError('injected path result failure')
 if scenario=='path_final_failure' and event['event']=='path_verified':raise OSError('injected path final evidence failure')
 return path_write(self,event)
combined.Journal.write=path_record
'''
ADAPTER = "NEGATIVE=" + repr(captures.NEGATIVE) + "\nPOSITIVE=" + repr(captures.POSITIVE) + "\n" + ADAPTER
HARNESS = fixtures.HARNESS.replace("kernel=Kernel();failure=None", ADAPTER + "\nkernel=Kernel();failure=None")
HARNESS = HARNESS.replace("inventory_factory=Inventory,collector_factory=Collector,",
                          "inventory_factory=PathInventory,collector_factory=Collector,path_factory=PathCheck,")


@unittest.skipUnless(sys.platform == "linux", "Linux owned groups")
class PassageIntegrationTests(unittest.TestCase):
    def run_case(self, scenario="normal", mode="check"):
        runner = fixtures.CombinedTests(methodName="runTest")
        with patch.object(fixtures, "HARNESS", HARNESS):
            return runner.run_case(scenario, mode)

    def test_passage_precedes_tcp_and_preserves_separate_statistics_in_both_modes(self):
        for mode in ("check", "check-crash"):
            with self.subTest(mode=mode):
                process, report, journal, _ = self.run_case(mode=mode)
                self.assertEqual(process.returncode, 0, process.stderr)
                self.assertEqual(report["kind"], "lab_cake_go_path_check")
                passage = report["path_check"]
                self.assertTrue(passage["path_verified"])
                self.assertEqual(passage["without_forwarding"]["received"], 0)
                self.assertEqual(passage["with_forwarding"]["received"], 3)
                self.assertEqual([r["exit_code"] for r in passage["commands"]], [0, 0, 1, 0, 0, 0])
                self.assertTrue(all(r["process_stopped"] for r in passage["commands"]))
                events = [r["data"]["event"] for r in journal]
                self.assertLess(events.index("activation_verified"), events.index("path_begin"))
                self.assertLess(events.index("path_verified"), events.index("traffic_launch_intent"))
                self.assertEqual(report["topology"]["after_path"], passage["after"])
                self.assertNotEqual(report["traffic_statistics_delta"], passage["statistics_delta"])
                self.assertEqual(report["traffic_group"]["driver_exit_code"], 0 if mode == "check" else -9)

    def test_path_errors_never_launch_tcp_and_preserve_raw_evidence(self):
        for scenario in ("path_write_error", "path_read_mismatch", "path_negative_reply", "path_negative_empty",
                         "path_negative_technical", "path_negative_count", "path_positive_partial", "path_link_changed"):
            with self.subTest(scenario=scenario):
                process, report, journal, _ = self.run_case(scenario)
                self.assertNotEqual(process.returncode, 0)
                self.assertEqual(report["path_check"]["state"], "failed")
                self.assertFalse(report["path_check"]["path_verified"])
                self.assertIsNone(report["traffic_group"])
                self.assertTrue(report["cleanup_verified"])
                self.assertNotIn("traffic_launch_intent", [r["data"]["event"] for r in journal])
                labels = [r["label"] for r in report["path_check"]["commands"]]
                if "negative" in scenario:
                    self.assertNotIn("enable", labels)
                    self.assertNotIn("passing_probe", labels)
                if scenario == "path_negative_technical":
                    self.assertEqual(base64.b64decode(report["path_check"]["commands"][-1]["stderr_base64"]),
                                     b"Operation not permitted\n")

    def test_interrupt_deadline_provenance_or_journal_failure_stops_before_tcp(self):
        for scenario in ("path_interrupt", "path_deadline", "path_tool_changed", "path_intent_failure",
                         "path_result_failure", "path_final_failure"):
            with self.subTest(scenario=scenario):
                process, report, journal, _ = self.run_case(scenario)
                self.assertNotEqual(process.returncode, 0, process.stderr)
                self.assertTrue(report["cleanup_verified"])
                self.assertFalse(report["path_check"]["path_verified"])
                self.assertNotIn("traffic_launch_intent", [r["data"]["event"] for r in journal])
                if scenario == "path_intent_failure":
                    self.assertEqual(report["path_check"]["commands"], [])

    def test_failed_go_phase_cannot_start_path_or_tcp(self):
        process, report, journal, _ = self.run_case("wrong_session")
        self.assertNotEqual(process.returncode, 0)
        self.assertIsNone(report["path_check"])
        self.assertNotIn("path_begin", [r["data"]["event"] for r in journal])

    def test_unverified_path_factory_cannot_open_the_tcp_gate(self):
        process, report, journal, _ = self.run_case("path_unverified")
        self.assertNotEqual(process.returncode, 0)
        self.assertFalse(report["path_check"]["path_verified"])
        self.assertIsNone(report["traffic_group"])
        self.assertNotIn("traffic_launch_intent", [r["data"]["event"] for r in journal])

    def test_plan_is_unprivileged_and_checks_require_explicit_inputs(self):
        for args, expected in ((["plan"], 0), (["check"], 2), (["check-crash"], 2)):
            result = subprocess.run([sys.executable, "-I", "-B", str(SOURCE.with_name("lab-cake-go-path.py")), *args],
                                    capture_output=True, text=True, timeout=4)
            self.assertEqual(result.returncode, expected, result.stderr)


if __name__ == "__main__":
    unittest.main()
