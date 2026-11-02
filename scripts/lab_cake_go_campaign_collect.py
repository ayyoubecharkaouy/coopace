"""Collect six campaign phases; no namespace ownership or scientific verdict."""

import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import time


def sibling(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


base = sibling("campaign_base_collect", "lab_cake_go_collect.py")
protocol = sibling("campaign_collect_wire", "lab_cake_go_campaign_protocol.py")
go, require, Error = base.go, base.require, base.Error


def stopped_helper(previous):
    """Read identity only; never signal an announced PID or its replacement."""
    pid = previous["pid"]
    try:
        raw = go.read(Path("/proc", str(pid), "stat"), 16384)
    except FileNotFoundError:
        return {"pid": pid, "previous_start_ticks": previous["start_ticks"], "reason": "absent"}
    split = raw.rfind(b") ")
    require(split > 0 and raw.split(b" ", 1)[0] == str(pid).encode(), "Statut de fin d’outil invalide.")
    fields = raw[split + 2:].split()
    require(len(fields) >= 20, "Statut de fin d’outil tronqué.")
    current = int(fields[19])
    require(current != previous["start_ticks"], "Outil de phase encore présent avant advance.")
    return {"pid": pid, "previous_start_ticks": previous["start_ticks"], "reason": "pid_reused", "current_start_ticks": current}


class Collector(base.Collector):
    def __init__(self, *args):
        super().__init__(*args)
        self.report.update(state="failed", phases=[], interrupted_phase=None, assessment="not_implemented",
                           congestion="not_assessed", comparison="not_assessed", coopace_benefit="not_assessed")
        self.dialogue = protocol.Dialogue(self.session)
        self.reader = protocol.LineReader(self.session, "events")
        self.current, self.line_observed_ns = None, None
        self.complete_seen, self.events_finished = False, False
        self.next_sample, self.phase_started_ns = None, None

    def arguments(self):
        tools, names = self.inventory.tools, [n for n, _ in self.topology.names]
        manifest = {"schema_version": 1, "kind": "lab_cake_go_campaign_tools", "session_id": self.session,
                    "tools": {n: tools[n] for n in ("ip", "agent", "target", "load")}}
        return [tools["python"]["path"], "-I", "-B", "-S", str(Path(__file__).with_name("lab-cake-go-campaign-traffic.py")),
                "--session-id", self.session, "--client", names[0], "--server", names[2],
                "--ip", tools["ip"]["path"], "--binaries", str(self.inventory.binaries),
                "--tools-json", json.dumps(manifest, separators=(",", ":"))]

    def launch(self):
        # Same registration and inherited descriptors as the single-flow
        # collector; only campaign capture limits differ.
        self.inventory.verify()
        self.topology.verify("before_traffic")
        self.collect("before_driver")
        self.stdout = base.Capture(self.artifacts / "driver.stdout.bin", protocol.EVENT_BUDGET)
        self.stderr = base.Capture(self.artifacts / "driver.stderr.bin", 256 * 1024)
        args = self.arguments()
        self.record({"event": "traffic_launch_intent", "arguments": args})
        self.check()
        child = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        self.owner.child = child
        self.report.update(driver_pid=child.pid, traffic_generated=None)
        self.output_fd, self.error_fd = os.dup(child.stdout.fileno()), os.dup(child.stderr.fileno())
        for fd in (self.output_fd, self.error_fd, child.stdin.fileno()):
            os.set_blocking(fd, False)
        self.started = time.monotonic()
        self.owner.journal("campaign_running")
        self.record({"event": "traffic_launched", "driver_pid": child.pid})
        self.check()

    def collect(self, label):
        self.check()
        started = time.monotonic_ns()
        reading = self.topology.read(True)
        finished = time.monotonic_ns()
        phase = self.current
        value = {**reading, "phase": label, "pair": phase["pair"] if phase else None,
                 "condition": phase["condition"] if phase else None,
                 "read_started_monotonic_ns": started, "read_finished_monotonic_ns": finished}
        size = len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode())
        require(len(self.report["queue_samples"]) < 720 and self.sample_size + size <= 4 * 1024 * 1024,
                "Budget de collecte de campagne dépassé.")
        self.record({"event": "campaign_sample", "reading": value})
        self.report["queue_samples"].append(value)
        if phase is not None:
            phase["samples"].append(value)
        self.sample_size += size
        self.next_sample = time.monotonic() + .25
        return value

    def drain(self):
        for fd, capture, flag in ((self.output_fd, self.stdout, "output_eof"), (self.error_fd, self.stderr, "error_eof")):
            if fd is None or getattr(self, flag):
                continue
            try:
                data = os.read(fd, 8192)
            except BlockingIOError:
                continue
            observed = time.monotonic_ns()
            if not data:
                setattr(self, flag, True)
                continue
            capture.append(data)
            if fd == self.output_fd:
                require(len(self.pending) + len(data) <= protocol.END_LIMIT, "Ligne pilote de campagne trop grande.")
                self.pending.extend(data)
                if b"\n" in data:
                    self.line_observed_ns = observed

    def control(self, action):
        self.check()
        require(not self.owner.exited(), "Pilote arrêté avant accusé de campagne.")
        pair, condition = self.current["pair"], self.current["condition"]
        raw = protocol.control_frame(self.session, pair, condition, action)
        self.record({"event": "campaign_control_intent", "pair": pair, "condition": condition,
                     "action": action, "frame_base64": base64.b64encode(raw).decode()})
        self.dialogue.control(raw)
        deadline = min(self.owner.deadline, self.started + 150, time.monotonic() + 5)
        if action == "advance":
            # Include checks and durable intentions after the final empty
            # reading in the same end-to-advance budget.
            deadline = min(deadline, self.current["end_observed_monotonic_ns"] / 1_000_000_000 + 3)
        while True:
            self.check()
            require(time.monotonic() < deadline, "Délai d’accusé de campagne dépassé.")
            try:
                require(os.write(self.owner.child.stdin.fileno(), raw) == len(raw), "Accusé de campagne partiellement écrit.")
                break
            except BlockingIOError:
                self.drain()
                require(not self.pending, "Sortie pilote prématurée avant accusé.")
                time.sleep(.005)
        sent = time.monotonic_ns()
        self.record({"event": "campaign_control_sent", "pair": pair, "condition": condition,
                     "action": action, "sent_monotonic_ns": sent})
        if action == "start":
            self.phase_started_ns = sent
        elif action == "advance" and self.dialogue.phase is None:
            self.owner.child.stdin.close()
            self.dialogue.finish_controls()

    def empty_phase(self, observed):
        deadline = min(self.owner.deadline, observed / 1_000_000_000 + 3)
        first_empty = None
        while True:
            self.check()
            require(time.monotonic() < deadline, "Vidage de phase hors délai depuis end observé.")
            self.drain()
            require(not self.pending and not self.output_eof and not self.owner.exited(), "Pilote avancé ou arrêté pendant le vidage.")
            reading = self.collect("drain")
            now = time.monotonic()
            require(now < deadline, "Lecture de vidage de phase hors délai.")
            stats = reading["statistics"]
            if stats["backlog_bytes"] == stats["queued_packets"] == 0:
                if first_empty is not None and reading["read_finished_monotonic_ns"] - first_empty >= 500_000_000:
                    return reading
                first_empty = reading["read_finished_monotonic_ns"] if first_empty is None else first_empty
            else:
                first_empty = None
            until = min(deadline, now + .25)
            while time.monotonic() < until:
                self.check()
                self.drain()
                require(not self.pending and not self.output_eof and not self.owner.exited(), "Sortie prématurée pendant le vidage.")
                time.sleep(.01)

    def event(self, raw, observed, crash):
        # The expected state identifies a potential end without validating its
        # body first. The timestamp was captured before fsync/JSON processing.
        if self.dialogue.state == "end":
            self.current["end_observed_monotonic_ns"] = observed
            self.record({"event": "phase_end_observed", "pair": self.current["pair"], "condition": self.current["condition"],
                         "observed_monotonic_ns": observed, "line_sha256": hashlib.sha256(raw).hexdigest()})
        values = self.reader.feed(raw)
        require(len(values) == 1 and not self.reader.pending, "Événement de campagne incomplet.")
        value = self.dialogue.event(raw)
        self.record({"event": "campaign_driver_event", "message": value})
        kind = value["event"]
        if kind == "begin":
            require(self.current is None, "Phase précédente non clôturée.")
            self.current = {"pair": value["pair"], "condition": value["condition"], "state": "starting", "samples": [],
                            "helpers": [], "helper_pids": [], "result": None, "statistics_delta": None}
            self.report["phases"].append(self.current)
            self.inventory.verify()
            self.topology.verify("before_phase")
            self.collect("before_start")
            self.control("start")
        elif kind == "ready":
            require(self.phase_started_ns is not None and observed - self.phase_started_ns < 15_000_000_000,
                    "Disponibilité de phase hors délai.")
            self.inventory.verify()
            helpers = self.helpers(value["helper_pids"])
            self.current.update(helpers=helpers, helper_pids=value["helper_pids"], state="measuring")
            self.record({"event": "campaign_helpers_verified", "pair": value["pair"], "condition": value["condition"], "helpers": helpers})
            if value["condition"] == "loaded":
                self.report["traffic_generated"] = True
            if crash and value["pair"] == 1 and value["condition"] == "loaded":
                self.record({"event": "traffic_kill_intent", "driver_pid": self.owner.child.pid})
                os.kill(self.owner.child.pid, signal.SIGKILL)
                self.killed = True
                self.report["interrupted_phase"] = {"pair": 1, "condition": "loaded"}
                self.current["state"] = "interrupted"
            else:
                self.control("continue")
        elif kind == "end":
            self.current.update(result=value["result"], state="draining")
            stopped = [stopped_helper(h) for h in self.current["helpers"]]
            self.record({"event": "campaign_helpers_stopped", "pair": value["pair"], "condition": value["condition"], "helpers": stopped})
            self.current["helpers_stopped"] = stopped
            self.report["traffic_generated"] = True
            last = self.empty_phase(observed)
            delta = base.cake.queue.statistics_delta(self.current["samples"][0]["statistics"], last["statistics"])
            require(delta["available"], "Différence de phase indisponible.")
            self.current["statistics_delta"] = delta
            self.inventory.verify()
            self.record({"event": "campaign_phase_collected", "pair": value["pair"], "condition": value["condition"], "statistics_delta": delta})
            self.control("advance")
            self.current["state"] = "complete"
            self.current = None
        else:
            require(self.current is None and len(self.report["phases"]) == 6, "Fin de campagne incomplète.")
            self.complete_seen = True

    def monitor(self, crash):
        while True:
            self.check()
            require(time.monotonic() < self.started + 150, "Délai du pilote de campagne dépassé.")
            self.drain()
            if b"\n" in self.pending:
                line, rest = self.pending.split(b"\n", 1)
                require(not rest, "Événements groupés avant accusé de campagne.")
                raw, observed = bytes(line) + b"\n", self.line_observed_ns
                self.pending.clear()
                self.event(raw, observed, crash)
            if self.output_eof:
                require(not self.pending, "EOF avec événement de campagne tronqué.")
                if not crash:
                    self.reader.finish()
                    self.dialogue.finish_events()
                    self.events_finished = True
                else:
                    require(self.killed, "EOF avant panne déclenchée.")
            if self.owner.exited() and self.output_eof and self.error_eof:
                require(self.killed if crash else self.complete_seen and self.dialogue.complete, "Pilote arrêté avant fin conforme.")
                return
            if self.current is not None and self.dialogue.state == "ready":
                require(time.monotonic_ns() - self.phase_started_ns < 15_000_000_000, "Aucun ready de phase sous 15s.")
            if not self.killed and not self.complete_seen and time.monotonic() >= self.next_sample:
                self.collect("running" if self.current else "between")
            time.sleep(.005)

    def run(self, mode):
        require(mode in ("run", "check-crash"), "Mode de collecte de campagne inconnu.")
        crash = mode == "check-crash"
        try:
            self.launch()
            self.monitor(crash)
            self.stop()
            require(self.report["driver_exit_code"] == (-9 if crash else 0), "Code réel du pilote de campagne incompatible.")
            require(self.report["reaped_descendants"] == (3 if crash else 0), "Récupération des outils de campagne incompatible.")
            if crash:
                require(len(self.report["phases"]) == 2 and self.report["phases"][0]["state"] == "complete"
                        and self.report["phases"][1]["state"] == "interrupted", "Panne hors de la première phase chargée.")
            else:
                require(len(self.report["phases"]) == 6 and all(p["state"] == "complete" for p in self.report["phases"]),
                        "Six phases récupérées requises.")
            self.topology.verify("after_traffic_stop")
            after = self.collect("after_crash_stop" if crash else "after_normal_stop")
            self.report["traffic_statistics_delta"] = base.cake.queue.statistics_delta(
                self.report["queue_samples"][0]["statistics"], after["statistics"])
            require(self.report["traffic_statistics_delta"]["available"], "Différence de campagne indisponible.")
            self.report["state"] = "crash_verified" if crash else "collected"
            self.inventory.verify()
            self.check()
            return self.report
        except BaseException as error:
            self.report.update(state="failed", error=str(error))
            if self.current is not None and self.current["state"] != "complete":
                self.current.update(state="failed", error=str(error))
            raise
