"""CAKE schema and independent cleanup with fake namespaces and real processes."""

from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_lab_guard import HARNESS as GUARD_HARNESS


SOURCE = Path(__file__).resolve().parents[1] / "lab-cake.py"
spec = importlib.util.spec_from_file_location("cake_cli", SOURCE)
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)
cake = cli.cake


def fixture():
    # Based on the reviewed iproute2 v6.1.0 serializers, not a native CAKE dump.
    return [{"kind": "cake", "handle": "10:", "root": True,
             "options": {"bandwidth": 500000, "diffserv": "besteffort", "flowmode": "flows",
                         "nat": False, "wash": False, "ingress": False, "ack-filter": "disabled",
                         "split_gso": True, "rtt": 100000, "raw": True, "overhead": 0,
                         "memlimit": 1048576, "fwmark": "0"},
             "bytes": 0, "packets": 0, "drops": 0, "overlimits": 0, "requeues": 0,
             "backlog": 0, "qlen": 0, "memory_used": 0, "memory_limit": 1048576,
             "tins": [{"sent_bytes": 0, "sent_packets": 0, "drops": 0, "ecn_mark": 0,
                       "backlog_bytes": 0, "target_us": 5000, "interval_us": 100000}]}]


def raw(value):
    return json.dumps(value).encode()


HARNESS = GUARD_HARNESS[:GUARD_HARNESS.index('(root / "proc").mkdir()')]+r'''
spec = importlib.util.spec_from_file_location("cake_cli", source.with_name("lab-cake.py"))
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)
cake = cli.cake
class CakeNamespaces(FakeNamespaces):
    def execute(self, args, owner):
        if args == ["unused-tc", "-V"]:
            return b"tc utility, iproute2-9.0.0\n" if scenario == "unsupported_profile" else b"tc utility, iproute2-6.1.0, libbpf 1.3.0\n"
        if args[1:2] == ["-n"]:
            return super().execute(args, owner)
        self.queue_calls.append(args)
        (root / "queue-calls.json").write_text(json.dumps(self.queue_calls))
        assert args[:5] == [self.ip, "netns", "exec", owner.owned[1][0], "unused-tc"]
        if args[5:] in (["-j", "-r", "qdisc", "show", "dev", "wan"],
                        ["-j", "-s", "-r", "qdisc", "show", "dev", "wan"]):
            if not self.queue_active:
                return b'[{"kind":"fq_codel","root":true,"handle":"0:"}]' if scenario == "queue_bad_initial" else b"[]"
            if scenario == "queue_read_failure" or (scenario == "queue_post_exit_failure" and any((root/"proc").iterdir())):
                raise cake.Error("injected read failure")
            rows = json.loads((root / "fixture.json").read_text())
            self.statistic_reads += 1
            if scenario == "wrong_configuration":
                rows[0]["options"]["bandwidth"] = 4000000
            if scenario == "missing_statistic":
                rows[0].pop("drops")
            if scenario == "wrong_tins":
                rows[0]["tins"] *= 2
            if scenario == "reset":
                rows[0]["bytes"] = 100 if self.statistic_reads == 1 else 1
            return json.dumps(rows).encode()
        assert args[5:] == ["qdisc", "add", "dev", "wan", "root", "handle", "10:", *cake.ARGUMENTS]
        self.queue_active = True
        (root / "queue-active.json").write_text("true")
        if scenario == "queue_add_failure":
            raise cake.Error("injected partial add failure")
        if scenario == "queue_interrupt_after_add":
            os.kill(os.getpid(), signal.SIGTERM)
        return b""
(root / "proc").mkdir()
backend = CakeNamespaces()
try:
    result = cli.run_check(mode, backend, "unused-tc", timeout=.7 if scenario == "deadline" else 5, tempdir=root)
    print(json.dumps(result))
except cli.guard.Interrupted as error:
    print(str(error), file=sys.stderr)
    raise SystemExit(error.code)
except Exception as error:
    print(str(error), file=sys.stderr)
    raise SystemExit(1)
'''


class CakeSchemaTests(unittest.TestCase):
    def test_identified_producer_and_explicit_omission_reasons(self):
        identity = cake.producer(b"tc utility, iproute2-6.1.0, libbpf 1.3.0\n")
        normalized = cake.configured_qdisc(raw(fixture()), identity["profile"])
        self.assertEqual(normalized["effective"]["bandwidth"], 500000)
        self.assertEqual(normalized["effective"]["mpu"], 0)
        self.assertEqual(set(normalized["omitted_fields"]), {"mpu", "atm", "autorate"})
        value = fixture()
        value[0]["options"].update(mpu=0, atm="noatm")
        self.assertEqual(set(cake.configured_qdisc(raw(value), cake.PROFILE)["omitted_fields"]), {"autorate"})
        with self.assertRaises(cake.Error):
            cake.configured_qdisc(raw(value), "unknown")

    def test_unknown_ambiguous_and_overlong_producer_are_refused(self):
        for value in (b"", b"tc utility, iproute2-6.10.0\n", b"tc utility, iproute2-6.1.0-custom\n",
                      b"tc utility, iproute2-6.1.0\nextra", b"x"*513, b"\xff"):
            with self.subTest(value=value[:70]), self.assertRaises(cake.Error):
                cake.producer(value)

    def test_every_required_option_wrong_type_or_missing_is_rejected(self):
        options = fixture()[0]["options"]
        for key, value in options.items():
            for replacement in (None, True if type(value) is int else 1 if type(value) is bool else "wrong"):
                item = fixture()
                if replacement is None:
                    item[0]["options"].pop(key)
                else:
                    item[0]["options"][key] = replacement
                with self.subTest(key=key, replacement=replacement), self.assertRaises(cake.Error):
                    cake.configured_qdisc(raw(item), cake.PROFILE)

    def test_wrong_values_dynamic_modes_and_foreign_roots_are_rejected(self):
        for key, value in (("bandwidth",4000000),("rtt",100),("memlimit",131072),("nat",True),
                           ("flowmode","triple-isolate"),("raw",False),("split_gso",False),
                           ("ack-filter","enabled"),("autorate","autorate-ingress"),
                           ("mpu",64),("atm","atm"),("overhead",20),("fwmark","0x1")):
            item=fixture(); item[0]["options"][key]=value
            with self.subTest(key=key), self.assertRaises(cake.Error):
                cake.configured_qdisc(raw(item),cake.PROFILE)
        for value in ([],fixture()*2,[{**fixture()[0],"parent":"1:1"}],
                      [{**fixture()[0],"kind":"tbf"}],[{**fixture()[0],"root":1}],
                      [{**fixture()[0],"dev":"eth0"}],[{**fixture()[0],"handle":"11:"}]):
            with self.subTest(value=value),self.assertRaises(cake.Error):
                cake.configured_qdisc(raw(value),cake.PROFILE)

    def test_required_statistics_never_default_to_zero(self):
        for field in (*cake.queue.COUNTERS,"backlog","qlen","memory_used","memory_limit"):
            for value in (None,True,-1,1.5,"0",2**64):
                item=fixture()
                if value is None:
                    item[0].pop(field)
                else:
                    item[0][field]=value
                with self.subTest(field=field,value=value),self.assertRaises(cake.Error):
                    cake.statistics(raw(item),cake.PROFILE)
        item=fixture();item[0]["memory_limit"]=1
        with self.assertRaises(cake.Error):
            cake.statistics(raw(item),cake.PROFILE)

    def test_single_tin_and_optional_values_are_preserved_without_summing(self):
        item=fixture(); item[0]["bytes"]=10; item[0]["tins"][0]["sent_bytes"]=10
        item[0]["memory_used"]=cake.MEMORY_LIMIT+4096  # kernel peak can precede trimming
        result=cake.statistics(raw(item),cake.PROFILE)
        self.assertEqual(result["counters"]["bytes"],10)
        self.assertEqual(result["cake"]["memory_used_reported_bytes"],cake.MEMORY_LIMIT+4096)
        self.assertEqual(result["cake"]["tin_fields"]["way_misses"],
                         {"available":False,"value":None,"reason":"not_reported"})
        for value in (None,[],[{},{}],[False],[{"sent_packets":False}],[{"ecn_mark":None}]):
            bad=fixture();bad[0]["tins"]=value
            with self.subTest(value=value),self.assertRaises(cake.Error):
                cake.statistics(raw(bad),cake.PROFILE)

    def test_strict_json_preserves_unknown_fields_and_rejects_ambiguity(self):
        item=fixture();item[0]["future_field"]={"kept":1}
        self.assertEqual(cake.queue.document(raw(item))[0]["future_field"],{"kept":1})
        for value in (b'[{"kind":"cake","kind":"tbf"}]',b'[NaN]',b'[{"x":1e999}]',b'[] trailing',b' '*65537):
            with self.subTest(value=value[:50]),self.assertRaises(cake.Error):
                cake.statistics(value,cake.PROFILE)


class CakeProcessTests(unittest.TestCase):
    def run_case(self, scenario="complete", mode="check"):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/"fixture.json").write_text(json.dumps(fixture()))
            completed=subprocess.run([sys.executable,"-I","-B","-c",HARNESS,
                                      str(SOURCE.with_name("lab-guard.py")),directory,scenario,mode],
                                     capture_output=True,text=True,timeout=8)
            for record in (root/"proc").glob("*"):
                self.assertFalse(Path("/proc",record.name).exists(),completed.stderr)
            remaining=list((root/"namespaces").iterdir())
            if scenario=="cleanup_failure":
                self.assertEqual(len(remaining),1)
                self.assertTrue(list(root.glob('coopace-guard.*/owner.json')))
            else:
                self.assertEqual(remaining,[],completed.stderr)
                self.assertEqual(list(root.glob('coopace-guard.*')),[],completed.stderr)
            calls=json.loads((root/"queue-calls.json").read_text()) if (root/"queue-calls.json").exists() else []
            return completed,calls

    def test_normal_and_crash_keep_cake_until_driver_exit_and_reap_descendant(self):
        for mode in ("check","check-crash"):
            completed,calls=self.run_case(mode=mode)
            self.assertEqual(completed.returncode,0,completed.stderr)
            result=json.loads(completed.stdout)
            self.assertEqual(result["kind"],"lab_cake_check")
            self.assertEqual(result["driver_exit_code"],-9 if mode.endswith('crash') else 0)
            self.assertEqual(result["reaped_descendants"],1)
            self.assertTrue(result["cleanup_verified"])
            self.assertFalse(result["traffic_generated"])
            self.assertEqual(result["queue"]["link_state"],"DOWN")
            self.assertEqual(result["queue"]["statistics_delta"]["counters"],{key:0 for key in cake.queue.COUNTERS})
            self.assertFalse(any("up" in args or "route" in args or "address" in args for args in calls))

    def test_rejected_initial_states_never_attempt_scheduler_add(self):
        for scenario in ("unsupported_profile","queue_existing_link","queue_link_up","queue_bad_initial"):
            completed,calls=self.run_case(scenario)
            self.assertEqual(completed.returncode,1,completed.stderr)
            self.assertEqual(completed.stdout,"")
            self.assertFalse(any("cake" in args for args in calls))

    def test_partial_add_read_schema_errors_and_cleanup_failure_never_publish_success(self):
        for scenario in ("queue_add_failure","queue_read_failure","wrong_configuration","missing_statistic",
                         "wrong_tins","queue_post_exit_failure","cleanup_failure","deadline"):
            completed,_=self.run_case(scenario)
            self.assertEqual(completed.returncode,1,completed.stderr)
            self.assertEqual(completed.stdout,"")

    def test_interrupt_after_add_returns_signal_code_after_cleanup(self):
        completed,_=self.run_case("queue_interrupt_after_add")
        self.assertEqual(completed.returncode,143,completed.stderr)
        self.assertEqual(completed.stdout,"")

    def test_counter_reset_is_explicitly_unavailable(self):
        completed,_=self.run_case("reset")
        self.assertEqual(completed.returncode,0,completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["queue"]["statistics_delta"],
                         {"available":False,"reason":"counter_decreased","counters":None})

    def test_plan_is_inert_and_missing_tools_stop_before_run(self):
        with patch.object(cli.guard,"preflight") as preflight,redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main([]),0)
            preflight.assert_not_called()
        with patch.object(cli.guard,"preflight",return_value=object()),patch.object(cli.shutil,"which",return_value=None),\
                patch.object(cli,"run_check") as run,redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(["check"]),1)
            run.assert_not_called()


if __name__=="__main__":
    unittest.main()
