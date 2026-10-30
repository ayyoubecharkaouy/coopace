"""One supervised synthetic flow, separate from the three-pair campaign."""

import importlib.util
import json
import math
import os
from pathlib import Path
import re
import signal
import sys
import time


def sibling(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard_module = sibling("active_guard", "lab-guard.py")
queue = guard_module.lab_queue
series = sibling("active_processes", "lab-series.py")
Error = queue.QueueError
TARGET = series.TARGET
LOAD_TARGET = series.LOAD_TARGET
VOLUME = 8_388_608
OUTPUT_LIMIT = 256 * 1024
SAMPLE_BUDGET = 1024 * 1024


class ActiveQueue(queue.QueueCheck):
    def __init__(self, namespaces, tc, sysctl):
        super().__init__(namespaces, tc, collect_statistics=True)
        self.sysctl = sysctl

    def prepare(self, owner):
        super().prepare(owner)
        client = owner.owned[0][0]
        rows = self.links(client)
        if len(rows) != 1 or rows[0].get("ifname") != "lo":
            raise Error("Espace client neuf requis.")
        ip = self.namespaces.ip
        self.execute([ip, "-n", self.gateway, "link", "add", "lan", "type", "veth",
                      "peer", "name", "eth0", "netns", client])
        for namespace, interface, address in (
                (client, "eth0", "10.203.0.2/30"), (self.gateway, "lan", "10.203.0.1/30"),
                (self.gateway, "wan", "10.203.0.5/30"), (self.server, "eth0", "10.203.0.6/30")):
            self.execute([ip, "-n", namespace, "address", "add", address, "dev", interface])
            self.execute([ip, "-n", namespace, "link", "set", "dev", interface, "up"])
        for namespace in (client, self.gateway, self.server):
            self.execute([ip, "-n", namespace, "link", "set", "dev", "lo", "up"])
        for namespace, network, via in ((client, "10.203.0.4/30", "10.203.0.1"),
                                        (self.server, "10.203.0.0/30", "10.203.0.5")):
            self.execute([ip, "-n", namespace, "route", "add", network, "via", via, "dev", "eth0"])
        prefix = [ip, "netns", "exec", self.gateway, self.sysctl]
        self.execute([*prefix, "-q", "-w", "net.ipv4.ip_forward=1"])
        if self.execute([*prefix, "-n", "net.ipv4.ip_forward"]).strip() != b"1":
            raise Error("Forwarding IPv4 de la passerelle non confirmé.")
        wan = next((row for row in self.links(self.gateway) if row.get("ifname") == "wan"), {})
        if "UP" not in wan.get("flags", []):
            raise Error("Activation de wan non confirmée.")
        self.report["link_state"] = "UP"
        self.verify("after_activation")


def expected_fields(value, expected):
    if any(value.get(key) != item or isinstance(value.get(key), bool) for key, item in expected.items()):
        raise Error("Rapport incompatible avec le contrôle actif.")


def positive(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def flow_documents(send_raw, receive_raw, latency_raw, code):
    send, receive, latency = (series.document(raw) for raw in (send_raw, receive_raw, latency_raw))
    expected_fields(send, {"schema_version": 1, "method": "synthetic_tcp_send", "target": LOAD_TARGET,
                          "requested_bytes": VOLUME, "written_bytes": VOLUME, "timeout_ms": 25000,
                          "requested_bytes_per_second": 1048576, "block_bytes": 16384})
    expected_fields(receive, {"schema_version": 1, "method": "synthetic_tcp_receive", "listen": LOAD_TARGET,
                             "requested_bytes": VOLUME, "received_bytes": VOLUME, "timeout_ms": 28000,
                             "block_bytes": 16384})
    for value, duration_key, maximum in ((send, "elapsed_ms", 25000),
                                         (receive, "receive_elapsed_ms", 28000)):
        duration, average = value.get(duration_key), value.get("average_bytes_per_second")
        if not positive(duration) or not duration < maximum or not positive(average):
            raise Error("Durée ou débit applicatif invalide.")
        if not math.isclose(average, VOLUME * 1000 / duration, rel_tol=1e-9):
            raise Error("Débit incompatible avec la durée applicative.")
    if send["elapsed_ms"] < 8000 or send["average_bytes_per_second"] > 1048576:
        raise Error("Plafond applicatif non respecté.")
    total = receive.get("elapsed_ms")
    if not positive(total) or not receive["receive_elapsed_ms"] <= total < 28000:
        raise Error("Durée totale de réception incohérente.")
    stamp = series.timestamp_ns
    first, last = (stamp(send.get(key)) for key in ("first_write_at", "last_write_at"))
    if not stamp(send.get("started_at")) <= first < last <= stamp(send.get("finished_at")):
        raise Error("Fenêtre d'écritures invalide.")
    if not (stamp(receive.get("started_at")) <= stamp(receive.get("first_read_at"))
            <= stamp(receive.get("last_read_at")) <= stamp(receive.get("finished_at"))):
        raise Error("Fenêtre de réception invalide.")
    latency_document(latency, "loaded", code)
    start, end = stamp(latency["started_at"]), stamp(latency["finished_at"])
    return {"send": send, "receive": receive, "latency": latency, "measurement_exit_code": code,
            "probe_window_inside_application_writes": first <= start <= end <= last,
            "has_successful_probe": latency["successful"] > 0}


def latency_document(latency, condition, code):
    stamp = series.timestamp_ns
    expected_fields(latency, {"schema_version": 1, "method": "tcp_connect", "target": TARGET,
                             "declared_condition": condition, "requested_attempts": 10,
                             "timeout_ms": 1000, "pause_between_attempts_ms": 250})
    successful, failed, attempts = (latency.get(key) for key in ("successful", "failed", "attempts"))
    if (type(successful) is not int or type(failed) is not int or not 0 <= successful <= 10
            or failed != 10 - successful or not isinstance(attempts, list) or len(attempts) != 10
            or code != (0 if successful else 1)):
        raise Error("Tentatives TCP ou code de sortie incohérents.")
    start, end = stamp(latency.get("started_at")), stamp(latency.get("finished_at"))
    if start > end:
        raise Error("Fenêtre de sondes inversée.")
    counted = 0
    previous = start
    for attempt in attempts:
        if not isinstance(attempt, dict):
            raise Error("Tentative TCP invalide.")
        when = stamp(attempt.get("started_at"))
        duration, failure = attempt.get("connect_ms"), attempt.get("failure")
        if not previous <= when <= end:
            raise Error("Tentative hors fenêtre ou hors ordre.")
        previous = when
        if duration is None:
            if failure not in ("timeout", "connection_failed"):
                raise Error("Échec TCP non explicite.")
        elif type(duration) not in (int, float) or not math.isfinite(duration) or duration < 0 or failure:
            raise Error("Durée TCP invalide.")
        else:
            counted += 1
    if counted != successful:
        raise Error("Résumé TCP incompatible avec les tentatives.")
    return latency


def worker(ip, client, server, binaries):
    match = re.fullmatch(r"cg-([a-z0-9_]{8})-c", client)
    if not match or server != f"cg-{match[1]}-s":
        raise Error("Espaces du superviseur requis.")
    runner = series.Runner(timeout=45)
    def interrupted(signum, _frame):
        runner.interruption = runner.interruption or 128 + signum
    for signum in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, interrupted)
    try:
        result = measure_loaded(ip, client, server, binaries, runner,
                                lambda pids: print("READY " + json.dumps(pids), flush=True))
    finally:
        runner.close()
    runner.check()
    print(json.dumps(result, allow_nan=False), flush=True)


def measure_loaded(ip, client, server, binaries, runner, announce):
    def inside(namespace, binary, *args):
        return [ip, "netns", "exec", namespace, str(binaries / binary), *args]
    children_start = len(runner.children)
    try:
        target = runner.start(inside(server, "coopace-lab-tcp", "--listen", TARGET,
                                     "--connections", "100", "--duration", "30s"))
        target.ready("READY " + TARGET, runner)
        receiver = runner.start(inside(server, "coopace-lab-load", "receive", "--listen", LOAD_TARGET,
                                       "--bytes", str(VOLUME), "--duration", "28s", "--json"))
        receiver.ready("READY " + LOAD_TARGET, runner)
        sender = runner.start(inside(client, "coopace-lab-load", "send", "--target", LOAD_TARGET,
                                     "--bytes", str(VOLUME), "--rate", "1048576", "--duration", "25s",
                                     "--announce-start"))
        sender.ready("STARTED", runner)
        announce([child.process.pid for child in (target, receiver, sender)])
        # STARTED is emitted after the first successful application write.
        runner.pause()
        runner.pause()
        if not all(child.running() for child in (target, receiver, sender)):
            raise Error("Un outil s'est arrêté avant les sondes.")
        raw, code = runner.execute(inside(client, "coopace", "latency", "--target", TARGET,
                                         "--count", "10", "--timeout", "1s", "--interval", "250ms",
                                         "--condition", "loaded", "--json"), timeout=16, allowed=(0, 1))
        if not target.running():
            raise Error("La cible TCP s'est arrêtée pendant les sondes.")
        target.stop()
        send_raw, _ = sender.finish(runner, 26)
        receive_raw, _ = receiver.finish(runner, 29)
        result = flow_documents(send_raw, receive_raw, raw, code)
    finally:
        for child in reversed(runner.children[children_start:]):
            child.stop()
    runner.check()
    return result


def announcement(line):
    if not line.startswith(b"READY "):
        raise Error("Annonce du pilote actif absente.")
    try:
        pids = json.loads(line[6:])
    except (ValueError, UnicodeError) as error:
        raise Error("Annonce du pilote illisible.") from error
    if (not isinstance(pids, list) or len(pids) != 3
            or any(type(pid) is not int or pid <= 0 for pid in pids) or len(set(pids)) != 3):
        raise Error("Trois PID de charge distincts requis.")
    return pids


class Observation:
    def __init__(self, active):
        self.active, self.samples, self.size = active, [], 0

    def collect(self, label):
        reading = self.active.read(True)
        reading["phase"] = label
        self.size += len(json.dumps(reading))
        if len(self.samples) >= 240 or self.size > SAMPLE_BUDGET:
            raise Error("Collecte de file trop volumineuse.")
        self.samples.append(reading)
        return reading

    def empty(self, owner):
        deadline, first_empty = time.monotonic() + 3, None
        while True:
            owner.check()
            now = time.monotonic()
            if now >= deadline:
                raise Error("File non vidée avant le délai de 3s.")
            reading = self.collect("drain")
            stats = reading["statistics"]
            now = time.monotonic()
            if stats["backlog_bytes"] == stats["queued_packets"] == 0:
                if first_empty is not None and now - first_empty >= 0.5:
                    return
                first_empty = now if first_empty is None else first_empty
            else:
                first_empty = None
            time.sleep(0.25)


def monitor(owner, observation, crash):
    output, pids, killed = bytearray(), None, False
    ready_deadline, next_sample = time.monotonic() + 15, time.monotonic()
    while True:
        owner.check()
        try:
            output.extend(os.read(owner.child.stdout.fileno(), 8192))
        except BlockingIOError:
            pass
        if len(output) > OUTPUT_LIMIT:
            raise Error("Sortie du pilote actif trop volumineuse.")
        if pids is None and b"\n" in output:
            line, rest = output.split(b"\n", 1)
            pids = announcement(line)
            output = bytearray(rest)
            if crash:
                os.kill(owner.child.pid, signal.SIGKILL)
                killed = True
        if owner.exited():
            # Do not reap the leader: Guard.close must signal its group first.
            while True:
                try:
                    data = os.read(owner.child.stdout.fileno(), 8192)
                except BlockingIOError:
                    break  # descendants may still hold the pipe open after a crash
                if not data:
                    break
                output.extend(data)
                if len(output) > OUTPUT_LIMIT:
                    raise Error("Sortie du pilote actif trop volumineuse.")
            if pids is None or (crash and not killed):
                raise Error("Pilote actif arrêté avant disponibilité.")
            return pids, bytes(output)
        if pids is None and time.monotonic() >= ready_deadline:
            raise Error("Pilote actif indisponible avant le délai.")
        if time.monotonic() >= next_sample:
            observation.collect("running")
            # No catch-up bursts after a slow tc call; retain actual timestamps.
            next_sample = time.monotonic() + 0.25
        time.sleep(0.01)


def run(mode, namespaces, tc, sysctl, binaries, *, tempdir=None, timeout=90):
    guard_module.enable_subreaper()
    owner = guard_module.Guard(namespaces, timeout=timeout, tempdir=tempdir)
    previous = {}
    def interrupted(signum, _frame):
        owner.interruption = owner.interruption or 128 + signum
    for signum in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM):
        previous[signum] = signal.signal(signum, interrupted)
    active = ActiveQueue(namespaces, tc, sysctl)
    observation = Observation(active)
    crash = mode == "check-crash"
    try:
        try:
            owner.create()
            active.prepare(owner)
            observation.collect("before_driver")
            args = [sys.executable, "-I", "-B", str(Path(__file__).with_name("lab-active.py")),
                    "worker", "--ip", namespaces.ip, "--client", owner.owned[0][0],
                    "--server", owner.owned[2][0], "--binaries", str(binaries)]
            owner.start(args)
            pids, raw = monitor(owner, observation, crash)
            result = None
            if not crash:
                value = series.document(raw)
                # Validate full transfer evidence again before publication.
                result = flow_documents(*(json.dumps(value[key]).encode() for key in ("send", "receive", "latency")),
                                        value.get("measurement_exit_code"))
                observation.empty(owner)
            active.verify("after_driver_exit")
        finally:
            owner.close()
        owner.check()
        expected = -signal.SIGKILL if crash else 0
        if owner.driver_code != expected or (crash and owner.reaped_descendants != 3):
            raise Error("Arrêt du pilote ou récupération des outils non conforme.")
        delta = queue.statistics_delta(observation.samples[0]["statistics"],
                                       active.report["after_driver_exit"]["statistics"])
        sequence = [reading["statistics"] for reading in observation.samples]
        sequence.append(active.report["after_driver_exit"]["statistics"])
        monotone = all(queue.statistics_delta(before, after)["available"]
                       for before, after in zip(sequence, sequence[1:]))
        if not monotone:
            delta = {"available": False, "reason": "counter_decreased", "counters": None}
        if not crash and (not delta["available"] or delta["counters"]["bytes"] <= 0):
            raise Error("Progression des compteurs TBF non confirmée.")
        return {"schema_version": 1, "kind": "lab_active_check", "mode": mode,
                "driver_exit_code": owner.driver_code, "driver_pid": owner.child.pid,
                "helper_pids": pids, "reaped_descendants": owner.reaped_descendants,
                "namespaces": [name for name, _identity in owner.owned], "workspace": str(owner.workspace),
                "cleanup_verified": True, "queue": active.report, "queue_samples": observation.samples,
                "traffic_statistics_delta": delta, "flow": result,
                "congestion": "not_assessed", "traffic_coverage": "synthetic_ipv4_only"}
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)
