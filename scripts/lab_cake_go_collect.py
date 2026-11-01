"""Bounded traffic collection on an already activated, owned CAKE topology."""

import base64
from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import time

spec = importlib.util.spec_from_file_location("collect_topology", Path(__file__).with_name("lab_cake_go_topology.py"))
topology = importlib.util.module_from_spec(spec)
spec.loader.exec_module(topology)
go, cake, require, Error = topology.go, topology.cake, topology.require, topology.Error
traffic = topology.sibling("collect_traffic", "lab_cake_go_traffic.py")


def process_snapshot(pid):
    """Read only the announced PID; do not enumerate or signal foreign processes."""
    root = Path("/proc") / str(pid)
    raw = go.read(root / "stat", 16384)
    split = raw.rfind(b") ")
    require(split > 0 and raw.split(b" ", 1)[0] == str(pid).encode(), "Statut de processus invalide.")
    fields = raw[split + 2:].split()
    require(len(fields) >= 20, "Statut de processus tronqué.")
    stat = {"pid": pid, "state": fields[0].decode("ascii"), "parent": int(fields[1]),
            "group": int(fields[2]), "session": int(fields[3]), "start_ticks": int(fields[19])}
    executable = Path(os.readlink(root / "exe")).resolve(strict=True)
    mapped, named = os.stat(root / "exe"), executable.stat()
    require((mapped.st_dev, mapped.st_ino) == (named.st_dev, named.st_ino), "Exécutable de processus remplacé.")
    command = go.read(root / "cmdline", 16384)
    require(command.endswith(b"\0"), "Arguments de processus tronqués.")
    namespace = os.stat(root / "ns/net")
    stat.update(executable=go.tool(executable), arguments=[v.decode("utf-8") for v in command[:-1].split(b"\0")],
                network_namespace=[namespace.st_dev, namespace.st_ino])
    # Re-read the anchor after the more expensive executable fingerprint.
    again = go.read(root / "stat", 16384)
    final_fields = again[again.rfind(b") ") + 2:].split()
    require(len(final_fields) >= 20 and final_fields[0] not in (b"Z", b"X", b"x")
            and final_fields[1:4] == fields[1:4] and final_fields[19] == fields[19], "PID annoncé remplacé ou arrêté.")
    final_namespace = os.stat(root / "ns/net")
    require((final_namespace.st_dev, final_namespace.st_ino) == (namespace.st_dev, namespace.st_ino),
            "Espace réseau de l’outil modifié pendant la vérification.")
    return stat


def expected_helpers(tools):
    return traffic.helper_commands(tools)


def validate_helper(value, pid, leader, namespace, tool, arguments):
    require(type(value.get("pid")) is int and value["pid"] == pid and pid != leader
            and value.get("state") not in (None, "Z", "X", "x")
            and all(type(value.get(k)) is int and value[k] == leader for k in ("parent", "group", "session"))
            and type(value.get("start_ticks")) is int and value["start_ticks"] > 0,
            "Outil annoncé arrêté, remplacé ou hors groupe.")
    require(value.get("network_namespace") == list(namespace)
            and value.get("executable") == tool and value.get("arguments") == arguments,
            "Identité, espace réseau ou rôle de l’outil annoncé incompatible.")
    return value


class Capture:
    def __init__(self, path, limit):
        self.path, self.limit, self.size = path, limit, 0
        self.digest = hashlib.sha256()
        self.fd = go.exclusive(path)
        info = os.fstat(self.fd)
        self.identity = info.st_dev, info.st_ino

    def append(self, data):
        require(self.size + len(data) <= self.limit, "Sortie du pilote trop volumineuse.")
        view = memoryview(data)
        while view:
            count = os.write(self.fd, view)
            require(count > 0, "Écriture de preuve interrompue.")
            self.digest.update(view[:count])
            view = view[count:]
            self.size += count
        os.fsync(self.fd)

    def close(self):
        if self.fd is not None:
            descriptor, self.fd = self.fd, None
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)

    def summary(self):
        raw = go.read(self.path, self.limit, self.identity)
        require(len(raw) == self.size and hashlib.sha256(raw).hexdigest() == self.digest.hexdigest(), "Pièce du pilote modifiée.")
        return {"file": self.path.name, "bytes": self.size, "sha256": hashlib.sha256(raw).hexdigest()}


class Collector:
    def __init__(self, owner, activated, inventory, artifacts, record):
        self.owner, self.topology, self.inventory, self.artifacts, self.record = owner, activated, inventory, artifacts, record
        require(activated.owner is owner and activated.state == "activated" and owner.child is None
                and owner.process_group.state == "new", "Topologie activée et groupe neuf requis.")
        self.session = inventory.session
        self.report = {"driver_pid": None, "driver_exit_code": None, "reaped_descendants": 0,
                       "helper_pids": [], "helpers": [], "traffic_generated": False, "flow": None,
                       "queue_samples": [], "traffic_statistics_delta": None}
        self.pending, self.stdout, self.stderr = bytearray(), None, None
        self.output_fd = self.error_fd = None
        self.output_eof = self.error_eof = False
        self.sample_size, self.ready, self.killed = 0, False, False
        self.exit_seen = None

    def check(self):
        self.owner.check()
        for name, identity in self.topology.names:
            require(self.owner.namespaces.identity(name) == identity, "Espace remplacé pendant la collecte.")

    def collect(self, label):
        self.check()
        value = {**self.topology.read(True), "phase": label}
        size = len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode())
        require(len(self.report["queue_samples"]) < 240 and self.sample_size + size <= 1024 * 1024,
                "Collecte de file trop volumineuse.")
        self.record({"event": "traffic_sample", "reading": value})
        self.sample_size += size
        self.report["queue_samples"].append(value)
        return value

    def arguments(self):
        tools, names = self.inventory.tools, [n for n, _ in self.topology.names]
        return [tools["python"]["path"], "-I", "-B", "-S", str(Path(__file__).with_name("lab-cake-go-traffic.py")),
                "--session-id", self.session, "--client", names[0], "--server", names[2],
                "--ip", tools["ip"]["path"], "--binaries", str(self.inventory.binaries),
                "--tools-json", json.dumps({"schema_version": 1, "kind": "lab_cake_go_active_tools", "session_id": self.session,
                                            "tools": {n: tools[n] for n in ("ip", "agent", "target", "load")}}, separators=(",", ":"))]

    def launch(self):
        self.inventory.verify()
        self.topology.verify("before_traffic")
        self.collect("before_driver")
        self.stdout = Capture(self.artifacts / "driver.stdout.bin", traffic.OUTPUT_LIMIT)
        self.stderr = Capture(self.artifacts / "driver.stderr.bin", traffic.OUTPUT_LIMIT)
        args = self.arguments()
        self.record({"event": "traffic_launch_intent", "arguments": args})
        self.check()
        # Assign/register the leader immediately after Popen; signal handlers only
        # record a flag. No callback can raise between launch and registration.
        child = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        self.owner.child = child
        self.report.update(driver_pid=child.pid, traffic_generated=None)
        self.output_fd = os.dup(child.stdout.fileno())
        self.error_fd = os.dup(child.stderr.fileno())
        for fd in (self.output_fd, self.error_fd, child.stdin.fileno()):
            os.set_blocking(fd, False)
        self.started = time.monotonic()
        self.owner.journal("traffic_running")
        self.record({"event": "traffic_launched", "driver_pid": child.pid})
        self.check()

    def drain(self):
        for fd, capture, flag in ((self.output_fd, self.stdout, "output_eof"), (self.error_fd, self.stderr, "error_eof")):
            if fd is None or getattr(self, flag):
                continue
            try:
                data = os.read(fd, 8192)
            except BlockingIOError:
                continue
            if not data:
                setattr(self, flag, True)
                continue
            capture.append(data)
            if fd == self.output_fd:
                self.pending.extend(data)

    def helpers(self, pids):
        require(not self.owner.exited(), "Pilote arrêté avant décision de disponibilité.")
        result = []
        for i, (pid, arguments) in enumerate(zip(pids, expected_helpers(self.inventory.tools))):
            role = 2 if i < 2 else 0
            spec = self.inventory.tools["target" if i == 0 else "load"]
            value = process_snapshot(pid)
            result.append(validate_helper(value, pid, self.owner.child.pid, self.topology.names[role][1], spec, arguments))
        require(not self.owner.exited(), "Pilote arrêté pendant la vérification des outils.")
        return result

    def decide(self, crash):
        if self.ready or b"\n" not in self.pending:
            if not self.ready:
                require(len(self.pending) < traffic.FRAME_LIMIT, "Annonce trop volumineuse ou tronquée.")
            return
        line, remaining = self.pending.split(b"\n", 1)
        event = traffic.parse_ready(bytes(line) + b"\n", self.session)
        require(not remaining, "Sortie prématurée après disponibilité.")
        self.inventory.verify()
        helpers = self.helpers(event["helper_pids"])
        self.record({"event": "traffic_ready", "announcement": event, "helpers": helpers})
        self.report.update(helper_pids=event["helper_pids"], helpers=helpers, traffic_generated=True)
        self.pending.clear()
        self.ready = True
        if crash:
            self.record({"event": "traffic_kill_intent", "driver_pid": self.owner.child.pid})
            os.kill(self.owner.child.pid, signal.SIGKILL)
            self.killed = True
        else:
            raw = traffic.continue_frame(self.session)
            self.record({"event": "traffic_continue_intent", "frame_base64": base64.b64encode(raw).decode()})
            deadline = min(self.owner.deadline, self.started + 45, time.monotonic() + 5)
            while True:
                self.check()
                require(time.monotonic() < deadline, "Délai d’accusé du superviseur dépassé.")
                try:
                    require(os.write(self.owner.child.stdin.fileno(), raw) == len(raw), "Accusé partiellement écrit.")
                    break  # A frame smaller than PIPE_BUF is written atomically.
                except BlockingIOError:
                    time.sleep(.01)
            self.record({"event": "traffic_continue_sent"})

    def monitor(self, crash):
        next_sample = time.monotonic() + .25
        while True:
            self.check()
            require(time.monotonic() < self.started + 45, "Délai du pilote de trafic dépassé.")
            self.drain()
            self.decide(crash)
            require(self.ready or not self.output_eof, "Pipe fermé avant disponibilité.")
            if self.owner.exited():
                self.exit_seen = time.monotonic()
                require(self.ready and (not crash or self.killed), "Pilote arrêté avant disponibilité vérifiée.")
                return
            require(self.ready or time.monotonic() < self.started + 15, "Annonce de trafic hors délai.")
            if time.monotonic() >= next_sample:
                self.collect("running")
                next_sample = time.monotonic() + .25
            time.sleep(.01)

    def stop(self):
        self.check()
        self.owner.stop_group(min(self.owner.deadline, time.monotonic() + 10))
        self.report.update(driver_exit_code=self.owner.driver_code, reaped_descendants=self.owner.reaped_descendants)
        if self.output_fd is not None:
            deadline = min(self.owner.deadline, time.monotonic() + 1)
            while not (self.output_eof and self.error_eof):
                require(time.monotonic() < deadline, "Pipes non fermés après récupération du groupe.")
                self.drain()
        self.record({"event": "traffic_group_stopped", "driver_pid": self.report["driver_pid"],
                     "driver_exit_code": self.report["driver_exit_code"], "reaped_descendants": self.report["reaped_descendants"]})

    def empty(self):
        deadline, first_empty = min(self.owner.deadline, self.exit_seen + 3), None
        while True:
            self.check()
            require(time.monotonic() < deadline, "File non vidée sous 3s après fin du pilote.")
            reading = self.collect("drain")
            now = time.monotonic()
            require(now < deadline, "Lecture de vidage hors délai.")
            stats = reading["statistics"]
            if stats["backlog_bytes"] == stats["queued_packets"] == 0:
                if first_empty is not None and now - first_empty >= .5:
                    return
                first_empty = now if first_empty is None else first_empty
            else:
                first_empty = None
            until = min(deadline, now + .25)
            while time.monotonic() < until:
                self.check()
                time.sleep(.01)

    def run(self, mode):
        crash = mode == "check-crash"
        # On any error the outer owner performs its independent 10s cleanup.
        # Do not first try to stop with an already expired measurement deadline:
        # an uncertain stop is permanent and would prevent a safe later retry.
        self.launch()
        self.monitor(crash)
        self.stop()
        require(self.report["driver_exit_code"] == (-9 if crash else 0), "Code réel du pilote de trafic incompatible.")
        if crash:
            require(self.report["reaped_descendants"] == 3 and not self.pending, "Panne ou récupération des trois outils non conforme.")
        else:
            require(self.report["reaped_descendants"] == 0, "Outil orphelin après fin normale.")
            self.report["flow"] = traffic.parse_flow(bytes(self.pending), self.session)
            self.empty()
        self.topology.verify("after_traffic_stop")
        after = self.collect("after_crash_stop" if crash else "after_normal_stop")
        delta = cake.queue.statistics_delta(self.report["queue_samples"][0]["statistics"], after["statistics"])
        require(delta["available"] and (crash or delta["counters"]["bytes"] > 0), "Progression du trafic CAKE non confirmée.")
        self.report["traffic_statistics_delta"] = delta
        self.inventory.verify()
        self.check()
        return self.report

    def close(self):
        errors = []
        self.report.update(driver_exit_code=self.owner.driver_code, reaped_descendants=self.owner.reaped_descendants)
        if self.owner.process_group.state == "stopped" and self.output_fd is not None:
            try:
                deadline = time.monotonic() + 1
                while not (self.output_eof and self.error_eof):
                    require(time.monotonic() < deadline, "Pipes non fermés après nettoyage.")
                    self.drain()
            except (OSError, Error) as error:
                errors.append(error)
        for attribute in ("output_fd", "error_fd"):
            fd = getattr(self, attribute)
            if fd is not None:
                setattr(self, attribute, None)
                try: os.close(fd)
                except OSError as error: errors.append(error)
        for key, capture in (("stdout", self.stdout), ("stderr", self.stderr)):
            if capture is not None:
                try:
                    capture.close()
                    self.report[key] = capture.summary()
                except (OSError, Error) as error:
                    errors.append(error)
        if errors:
            raise errors[0]
