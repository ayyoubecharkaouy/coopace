"""Three idle/loaded pairs under one owned TBF, with an independent guard."""

from datetime import datetime, timezone
from decimal import Decimal
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time


spec = importlib.util.spec_from_file_location("campaign_active", Path(__file__).with_name("lab_active.py"))
active = importlib.util.module_from_spec(spec)
spec.loader.exec_module(active)
queue, processes, guards = active.queue, active.series, active.guard_module
Error = active.Error
PHASES = [(index, condition) for index, order in enumerate(processes.ORDERS, 1) for condition in order]


def exclusive(path):
    return os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644), "w")


class Ledger:
    def __init__(self, stream):
        self.stream, self.size = stream, 0

    def write(self, event):
        line = json.dumps({"recorded_at": datetime.now(timezone.utc).isoformat(), **event},
                          ensure_ascii=False, allow_nan=False) + "\n"
        self.size += len(line.encode())
        if self.size > 8 * 1024 * 1024:
            raise Error("Journal de campagne trop volumineux.")
        self.stream.write(line)
        self.stream.flush()


class Topology(active.ActiveQueue):
    def control(self, args, *, timeout=2, allowed=(0,)):
        self.owner.check()
        for name, identity in self.owner.owned:
            if identity is None or self.namespaces.identity(name) != identity:
                raise Error("Possession des espaces non confirmée avant le contrôle de passage.")
        result = queue.run_command(args, self.owner, timeout=timeout, allowed=allowed)
        self.owner.check()
        return result

    def passage(self, ping):
        ip, client = self.namespaces.ip, self.owner.owned[0][0]
        switch = [ip, "netns", "exec", self.gateway, self.sysctl]
        self.control([*switch, "-q", "-w", "net.ipv4.ip_forward=0"])
        if self.control([*switch, "-n", "net.ipv4.ip_forward"]).strip() != b"0":
            raise Error("Forwarding désactivé non confirmé.")
        negative = self.control([ip, "netns", "exec", client, ping, "-4", "-n", "-c", "1",
                                 "-w", "3", "-W", "1", "10.203.0.6"], timeout=4, allowed=(1,))
        self.control([*switch, "-q", "-w", "net.ipv4.ip_forward=1"])
        if self.control([*switch, "-n", "net.ipv4.ip_forward"]).strip() != b"1":
            raise Error("Forwarding activé non confirmé.")
        positive = self.control([ip, "netns", "exec", client, ping, "-4", "-n", "-c", "3",
                                 "-w", "5", "-W", "1", "10.203.0.6"], timeout=6)
        if not re.search(rb"\b3 packets transmitted,\s*3 (?:packets )?received\b", positive):
            raise Error("Trois réponses ICMP non confirmées.")
        return {"without_forwarding_exit_code": 1, "with_forwarding_exit_code": 0,
                "without_forwarding_stdout": negative.decode("utf-8"),
                "with_forwarding_stdout": positive.decode("utf-8")}


def emit(event, **fields):
    print(json.dumps({"event": event, **fields}, allow_nan=False), flush=True)


def acknowledge(runner):
    data = bytearray()
    deadline = time.monotonic() + 8
    while True:
        runner.check()
        if time.monotonic() >= deadline:
            raise Error("Accusé du superviseur absent.")
        try:
            block = os.read(sys.stdin.fileno(), 16)
            if not block:
                raise Error("Canal du superviseur fermé.")
            data.extend(block)
        except BlockingIOError:
            pass
        if len(data) > 3 or b"\n" in data:
            if data != b"OK\n":
                raise Error("Accusé du superviseur invalide.")
            return
        time.sleep(0.01)


def idle(ip, client, server, binaries, runner):
    target = runner.start([ip, "netns", "exec", server, str(binaries / "coopace-lab-tcp"),
                           "--listen", active.TARGET, "--connections", "100", "--duration", "30s"])
    try:
        target.ready("READY " + active.TARGET, runner)
        raw, code = runner.execute([ip, "netns", "exec", client, str(binaries / "coopace"),
                                    "latency", "--target", active.TARGET, "--count", "10", "--timeout", "1s",
                                    "--interval", "250ms", "--condition", "idle", "--json"],
                                   timeout=16, allowed=(0, 1))
        if not target.running():
            raise Error("Cible arrêtée pendant la mesure idle.")
        value = active.latency_document(processes.document(raw), "idle", code)
        return {"latency": value, "measurement_exit_code": code}
    finally:
        target.stop()


def worker(ip, client, server, binaries):
    # Same namespace grammar as the independently supervised functional control.
    match = re.fullmatch(r"cg-([a-z0-9_]{8})-c", client)
    if not match or server != f"cg-{match[1]}-s":
        raise Error("Espaces du superviseur requis.")
    runner = processes.Runner(timeout=150)
    def interrupted(signum, _frame):
        runner.interruption = runner.interruption or 128 + signum
    for signum in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, interrupted)
    os.set_blocking(sys.stdin.fileno(), False)
    try:
        for index, condition in PHASES:
            emit("begin", pair=index, condition=condition)
            acknowledge(runner)
            if condition == "loaded":
                result = active.measure_loaded(ip, client, server, binaries, runner,
                    lambda pids: emit("ready", pair=index, condition=condition, helper_pids=pids))
            else:
                result = idle(ip, client, server, binaries, runner)
            emit("end", pair=index, condition=condition, result=result)
            acknowledge(runner)
    finally:
        runner.close()
    runner.check()
    emit("complete")


def timestamp(value):
    return processes.timestamp_ns(value[:-6] + "Z" if value.endswith("+00:00") else value)


def delta(readings):
    values = [reading["statistics"] for reading in readings]
    if not all(queue.statistics_delta(a, b)["available"] for a, b in zip(values, values[1:])):
        return {"available": False, "reason": "counter_decreased", "counters": None}
    return queue.statistics_delta(values[0], values[-1])


def qualify(phases):
    """Frozen v1 criteria; no averaging of percentiles or erased failures."""
    checks = []
    technical = len(phases) == 6
    for index in range(1, 4):
        members = {p["condition"]: p for p in phases if p["pair"] == index}
        if set(members) != {"idle", "loaded"}:
            technical = False
            continue
        loaded, idle_phase = members["loaded"], members["idle"]
        flow, latency = loaded["result"], loaded["result"]["latency"]
        technical = technical and flow["probe_window_inside_application_writes"]
        settle = (processes.timestamp_ns(latency["started_at"]) -
                  processes.timestamp_ns(flow["send"]["first_write_at"])) / 1_000_000
        technical = technical and settle >= 1000
        for phase in members.values():
            technical = technical and phase["statistics_delta"]["available"]
        start, end = (processes.timestamp_ns(latency[key]) for key in ("started_at", "finished_at"))
        window = [s for s in loaded["samples"] if start <= timestamp(s["collected_at"]) <= end]
        positive = [s for s in window if s["statistics"]["backlog_bytes"] > 0]
        spaced = []
        for reading in positive:
            if not spaced or reading["elapsed_since_start_ms"] - spaced[-1]["elapsed_since_start_ms"] >= 200:
                spaced.append(reading)
        progress = delta(window) if len(window) >= 2 else {"available": False, "counters": None}
        fed = (progress["available"] and progress["counters"]["bytes"] > 0 and len(spaced) >= 3)
        rate = flow["receive"]["average_bytes_per_second"]
        idle_dist, loaded_dist = idle_phase["result"]["latency"].get("connect_ms"), latency.get("connect_ms")
        # JSON milliseconds have nanosecond resolution. Keep an exact 10ms
        # boundary from being rounded below the threshold by binary floats.
        difference = (Decimal(str(loaded_dist["p50"])) - Decimal(str(idle_dist["p50"]))) if idle_dist and loaded_dist else None
        checks.append({"pair": index, "settle_ms": settle, "queue_fed": fed, "positive_spaced_samples": len(spaced),
                       "received_bytes_per_second": rate, "receive_rate_in_range": 350000 <= rate <= 525000,
                       "p50_loaded_minus_idle_ms": float(difference) if difference is not None else None,
                       "latency_increase_at_least_10_ms": difference is not None and difference >= 10})
    observed = (technical and len(checks) == 3 and all(c["queue_fed"] and c["receive_rate_in_range"] for c in checks)
                and sum(c["latency_increase_at_least_10_ms"] for c in checks) >= 2)
    return {"technical_valid": bool(technical), "congestion": "observed" if observed else
            "not_demonstrated" if technical else "non_exploitable", "pairs": checks}


class Campaign:
    def __init__(self, owner, topology, ledger, artifacts, binaries, *, crash=False):
        self.owner, self.topology, self.ledger = owner, topology, ledger
        self.artifacts, self.binaries, self.crash = artifacts, binaries, crash
        self.phases, self.current, self.ready = [], None, False
        self.complete, self.crash_sent, self.helper_pids = False, False, []
        self.buffer, self.output_bytes, self.sample_bytes, self.sample_count = bytearray(), 0, 0, 0
        self.next_sample = time.monotonic()

    def collect(self, label):
        reading = self.topology.read(True)
        reading["phase"] = label
        self.sample_count += 1
        self.sample_bytes += len(json.dumps(reading))
        if self.sample_count > 720 or self.sample_bytes > 4 * 1024 * 1024:
            raise Error("Collecte périodique de campagne trop volumineuse.")
        self.ledger.write({"event": "statistics", "pair": self.current["pair"],
                           "condition": self.current["condition"], "reading": reading})
        self.current["samples"].append(reading)
        return reading

    def drain_queue(self):
        deadline, empty_since = time.monotonic() + 3, None
        while True:
            self.owner.check()
            if time.monotonic() >= deadline:
                raise Error("File non vidée avant la phase suivante.")
            stats = self.collect("drain")["statistics"]
            now = time.monotonic()
            if stats["backlog_bytes"] == stats["queued_packets"] == 0:
                if empty_since is not None and now - empty_since >= 0.5:
                    return
                empty_since = now if empty_since is None else empty_since
            else:
                empty_since = None
            time.sleep(0.25)

    def ack(self):
        # Exactly one small acknowledgement per protocol boundary; no pipe backlog.
        self.owner.child.stdin.write(b"OK\n")
        self.owner.child.stdin.flush()

    def event(self, value):
        kind = value.get("event")
        self.ledger.write({"event": "driver", "message": value})
        if kind == "complete":
            if self.current is not None or len(self.phases) != 6 or self.complete:
                raise Error("Fin de campagne prématurée ou dupliquée.")
            self.complete = True
            return
        if self.complete or len(self.phases) >= 6:
            raise Error("Événement après fin de campagne.")
        expected = PHASES[len(self.phases)]
        if (value.get("pair"), value.get("condition")) != expected:
            raise Error("Ordre des phases non conforme au protocole.")
        if kind == "begin" and self.current is None:
            self.current = {"pair": expected[0], "condition": expected[1], "samples": []}
            self.ready = False
            self.collect("before")
            self.ack()
        elif kind == "ready" and self.current is not None and expected[1] == "loaded" and not self.ready:
            self.helper_pids = active.announcement(b"READY " + json.dumps(value.get("helper_pids")).encode())
            self.current["helper_pids"] = self.helper_pids
            self.ready = True
            if self.crash:
                os.kill(self.owner.child.pid, signal.SIGKILL)
                self.crash_sent = True
        elif kind == "end" and self.current is not None:
            result = value["result"]
            if expected[1] == "loaded":
                if not self.ready:
                    raise Error("Charge sans annonce de disponibilité.")
                result = active.flow_documents(*(json.dumps(result[key]).encode() for key in ("send", "receive", "latency")),
                                               result.get("measurement_exit_code"))
            else:
                active.latency_document(result["latency"], "idle", result.get("measurement_exit_code"))
            self.current["result"] = result
            self.collect("after")
            self.drain_queue()
            self.current["statistics_delta"] = delta(self.current["samples"])
            with exclusive(self.artifacts / f"phase-{expected[0]}-{expected[1]}.json") as output:
                json.dump(result["latency"], output, allow_nan=False)
                output.write("\n")
            self.phases.append(self.current)
            self.current = None
            if len(self.phases) % 2 == 0:
                index = expected[0]
                comparison = queue.run_command([str(self.binaries / "coopace"), "latency", "compare",
                    "--idle", str(self.artifacts / f"phase-{index}-idle.json"),
                    "--loaded", str(self.artifacts / f"phase-{index}-loaded.json")], self.owner)
                if not comparison.strip():
                    raise Error("Comparaison stricte absente.")
                text = comparison.decode("utf-8")
                self.phases[-1]["comparison"] = text
                self.ledger.write({"event": "comparison", "pair": index, "text": text})
            self.ack()
        else:
            raise Error("Événement du pilote inattendu.")

    def monitor(self):
        while True:
            self.owner.check()
            try:
                data = os.read(self.owner.child.stdout.fileno(), 8192)
            except BlockingIOError:
                data = b""
            self.output_bytes += len(data)
            self.buffer.extend(data)
            if self.output_bytes > 1024 * 1024 or len(self.buffer) > 256 * 1024:
                raise Error("Sortie du pilote de campagne trop volumineuse.")
            while b"\n" in self.buffer:
                line, rest = self.buffer.split(b"\n", 1)
                self.buffer = bytearray(rest)
                self.event(processes.document(line))
            # Draining can take several iterations after exit; do not reap leader.
            if self.owner.exited() and not data:
                if self.crash_sent:
                    return
                if not self.complete or self.buffer:
                    raise Error("Pilote arrêté avant fin de campagne.")
                return
            if self.current is not None and not self.crash_sent and time.monotonic() >= self.next_sample:
                self.collect("running")
                self.next_sample = time.monotonic() + 0.25
            time.sleep(0.01)


def run(namespaces, tc, sysctl, ping, binaries, artifacts, *, crash=False, tempdir=None, timeout=180):
    # Evidence belongs to the experiment, outside the disposable reservation.
    with exclusive(artifacts / "progress.jsonl") as stream:
        ledger = Ledger(stream)
        guards.enable_subreaper()
        owner = guards.Guard(namespaces, timeout=timeout, tempdir=tempdir)
        previous = {}
        def interrupted(signum, _frame):
            owner.interruption = owner.interruption or 128 + signum
        for signum in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM):
            previous[signum] = signal.signal(signum, interrupted)
        topology = Topology(namespaces, tc, sysctl)
        campaign = Campaign(owner, topology, ledger, artifacts, binaries, crash=crash)
        try:
            try:
                owner.create()
                ledger.write({"event": "owned", "namespaces": [n for n, _ in owner.owned], "workspace": str(owner.workspace)})
                topology.prepare(owner)
                passage = topology.passage(ping)
                ledger.write({"event": "passage", **passage})
                topology.verify("after_passage")
                owner.start([sys.executable, "-I", "-B", str(Path(__file__).with_name("lab-campaign.py")),
                             "worker", "--ip", namespaces.ip, "--client", owner.owned[0][0],
                             "--server", owner.owned[2][0], "--binaries", str(binaries)], stdin=subprocess.PIPE)
                campaign.monitor()
                topology.verify("after_driver_exit")
            finally:
                owner.close()
            owner.check()
            if owner.driver_code != (-signal.SIGKILL if crash else 0):
                raise Error("Sortie du pilote de campagne non conforme.")
            if crash and (not campaign.crash_sent or owner.reaped_descendants != 3):
                raise Error("Récupération des trois outils non confirmée.")
            readings = [topology.report["after_passage"]]
            for phase in campaign.phases:
                readings.extend(phase["samples"])
            if campaign.current:
                readings.extend(campaign.current["samples"])
            readings.append(topology.report["after_driver_exit"])
            total_delta = delta(readings)
            decision = {"technical_valid": None, "congestion": "not_assessed"} if crash else qualify(campaign.phases)
            if not crash and not total_delta["available"]:
                decision.update(technical_valid=False, congestion="non_exploitable")
            result = {"schema_version": 1, "kind": "lab_bottleneck_campaign", "mode": "check-crash" if crash else "run",
                      "driver_pid": owner.child.pid, "driver_exit_code": owner.driver_code,
                      "reaped_descendants": owner.reaped_descendants, "helper_pids_at_last_ready": campaign.helper_pids,
                      "namespaces": [n for n, _ in owner.owned], "workspace": str(owner.workspace), "cleanup_verified": True,
                      "passage": passage, "queue": topology.report, "phases": campaign.phases, "decision": decision,
                      "statistics_delta": total_delta, "interrupted_phase": campaign.current,
                      "traffic_coverage": "synthetic_ipv4_only", "evidence": str(artifacts / "progress.jsonl")}
            ledger.write({"event": "cleaned", "decision": decision})
            return result
        finally:
            for signum, handler in previous.items():
                signal.signal(signum, handler)
