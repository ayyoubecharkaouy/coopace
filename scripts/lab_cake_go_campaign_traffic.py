"""Private six-phase campaign driver; owns tools, never network resources."""

import argparse
import importlib.util
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import time

spec = importlib.util.spec_from_file_location("campaign_wire", Path(__file__).with_name("lab_cake_go_campaign_protocol.py"))
protocol = importlib.util.module_from_spec(spec)
spec.loader.exec_module(protocol)
traffic, require, Error = protocol.traffic, protocol.require, protocol.Error
active = traffic.active
TOOL_LIMIT = 256 * 1024
STDERR_LIMIT = 256 * 1024


class ToolSet(traffic.ToolSet):
    def __init__(self, raw, session):
        value = protocol._document(raw.encode("utf-8") + b"\n", 16384)
        require(set(value) == {"schema_version", "kind", "session_id", "tools"}
                and type(value["schema_version"]) is int and value["schema_version"] == 1
                and value["kind"] == "lab_cake_go_campaign_tools" and value["session_id"] == protocol.session_id(session),
                "Inventaire de campagne hors session.")
        # Reuse canonical paths, fingerprints and fixed commands, with a
        # separately validated campaign envelope and an additional idle probe.
        value = {**value, "kind": "lab_cake_go_active_tools"}
        super().__init__(json.dumps(value), session)
        idle_probe = list(self.commands[-1])
        idle_probe[idle_probe.index("--condition") + 1] = "idle"
        self.commands.append(idle_probe)
        self.phase_index, self.started, self.allowed = 0, 0, ()

    def begin_phase(self, pair, condition):
        require(self.phase_index < len(protocol.PHASES) and (pair, condition) == protocol.PHASES[self.phase_index]
                and self.started == len(self.allowed), "Ordre des outils ou phase précédente incomplet.")
        self.allowed = tuple(self.commands[:4]) if condition == "loaded" else (self.commands[0], self.commands[4])
        self.phase_index += 1
        self.started = 0

    def before_start(self, args):
        require(self.started < len(self.allowed) and args == self.allowed[self.started], "Commande de phase interdite ou répétée.")
        super().before_start(args)
        self.started += 1


class Process:
    def __init__(self, args, errors):
        self.process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.output, self.eof, self.errors = bytearray(), set(), errors
        self.output_bytes = 0
        self.failure = None
        try:
            for stream in (self.process.stdout, self.process.stderr):
                os.set_blocking(stream.fileno(), False)
        except BaseException:
            self.process.kill()
            self.process.wait(timeout=1)
            self.process.stdout.close()
            self.process.stderr.close()
            raise

    def drain(self):
        for name in ("stdout", "stderr"):
            if name in self.eof:
                continue
            try:
                data = os.read(getattr(self.process, name).fileno(), 8192)
            except BlockingIOError:
                continue
            if not data:
                self.eof.add(name)
            elif name == "stderr":
                self.errors(data)
            else:
                require(self.output_bytes + len(data) <= TOOL_LIMIT, "Sortie d’outil trop volumineuse.")
                self.output_bytes += len(data)
                self.output.extend(data)

    def running(self):
        return self.process.poll() is None

    def ready(self, expected, runner):
        deadline = time.monotonic() + 5
        while True:
            runner.check()
            if b"\n" in self.output:
                line, rest = self.output.split(b"\n", 1)
                require(line == expected.encode("ascii"), "Disponibilité d’outil invalide.")
                self.output = bytearray(rest)
                return
            require(self.running() and time.monotonic() < deadline, "Outil indisponible avant mesure.")
            time.sleep(.01)

    def finish(self, runner, timeout, allowed=(0,)):
        deadline = time.monotonic() + timeout
        while True:
            runner.check()
            code = self.process.poll()
            if code is not None and len(self.eof) == 2:
                require(code in allowed, "Code de sortie d’outil incompatible.")
                return bytes(self.output), code
            require(time.monotonic() < deadline, "Délai d’outil dépassé.")
            time.sleep(.01)

    def stop(self, deadline=None):
        if self.failure is not None:
            raise Error("Arrêt d’outil précédemment non confirmé.") from self.failure
        if self.process.stdout.closed:
            return
        deadline = deadline if deadline is not None else time.monotonic() + 1
        try:
            if self.running():
                try:
                    self.process.terminate()
                except ProcessLookupError:
                    pass
                grace = min(deadline, time.monotonic() + .2)
                while self.running() and time.monotonic() < grace:
                    time.sleep(.005)
                if self.running():
                    self.process.kill()
            self.process.wait(timeout=max(.001, deadline - time.monotonic()))
            while len(self.eof) < 2:
                self.drain()
                require(time.monotonic() < deadline, "Fin des captures d’outil non confirmée.")
                if len(self.eof) < 2:
                    time.sleep(.005)
        except BaseException as error:
            self.failure = error
            # Even a capture error must not leave a live tool unowned.
            if self.running():
                self.process.kill()
                self.process.wait(timeout=max(.001, deadline - time.monotonic()))
            raise
        finally:
            self.process.stdout.close()
            self.process.stderr.close()


class Channel:
    def __init__(self, session, input_fd, output_fd):
        self.session = protocol.session_id(session)
        self.dialogue = protocol.Dialogue(session)
        self.reader = protocol.LineReader(session, "controls")
        self.input_fd, self.output_fd = input_fd, output_fd
        self.accepting, self.eof, self.written = False, False, 0
        self.control_deadline = None
        os.set_blocking(input_fd, False)
        os.set_blocking(output_fd, False)

    def observe(self):
        if self.accepting or self.eof:
            return
        try:
            data = os.read(self.input_fd, 1)
        except BlockingIOError:
            return
        require(not data, "Contrôle prématuré ou supplémentaire.")
        self.reader.finish()
        self.dialogue.finish_controls()
        self.eof = True

    def send(self, raw, runner, *, boundary=True):
        runner.check()
        require(not self.accepting and self.written + len(raw) <= protocol.EVENT_BUDGET, "Écriture de campagne interdite ou trop grande.")
        self.dialogue.event(raw)
        deadline, offset = time.monotonic() + 5, 0
        while offset < len(raw):
            runner.check()
            require(time.monotonic() < deadline, "Délai d’écriture de campagne dépassé.")
            try:
                count = os.write(self.output_fd, raw[offset:])
            except BlockingIOError:
                time.sleep(.005)
                continue
            require(count > 0, "Écriture interrompue.")
            offset += count
            self.written += count
            if offset == len(raw):
                # A control is legitimate as soon as the peer sees LF.
                self.accepting = boundary
                self.control_deadline = time.monotonic() + 5 if boundary else None
        runner.check()

    def await_control(self, action, runner, helpers=()):
        require(self.accepting and self.dialogue.state == action, "Attente de contrôle hors frontière.")
        deadline = self.control_deadline
        while True:
            runner.check()
            require(time.monotonic() < deadline, "Délai d’accusé de campagne dépassé.")
            require(all(child.running() for child in helpers), "Outil arrêté pendant l’attente de continue.")
            try:
                data = os.read(self.input_fd, protocol.FRAME_LIMIT + 1)
            except BlockingIOError:
                time.sleep(.005)
                continue
            require(data, "EOF avant accusé de campagne.")
            values = self.reader.feed(data)
            if not values:
                continue
            require(len(values) == 1 and not self.reader.pending, "Contrôles groupés ou données supplémentaires.")
            self.dialogue.control(protocol._wire(values[0]))
            self.accepting = False
            runner.check()
            return


class CampaignRunner(active.series.Runner):
    def __init__(self, channel, tools, deadline=None):
        super().__init__(timeout=150)
        if deadline is not None:
            self.deadline = min(self.deadline, deadline)
        self.channel, self.tools = channel, tools
        self.ready_deadline, self.available = None, False
        self.error_total, self.error_pending = 0, bytearray()

    def errors(self, data):
        require(self.error_total + len(data) <= STDERR_LIMIT - 2048, "Budget stderr des outils dépassé.")
        self.error_total += len(data)
        self.error_pending.extend(data)

    def flush_errors(self):
        if self.error_pending and select.select([], [2], [], 0)[1]:
            # At most PIPE_BUF, with a single writer: no blocking pipe write
            # after select. Inherited tool stderr is captured separately.
            count = os.write(2, self.error_pending[:4096])
            require(count > 0, "Écriture stderr interrompue.")
            del self.error_pending[:count]

    def check(self):
        super().check()
        self.channel.observe()
        require(self.available or self.ready_deadline is None or time.monotonic() < self.ready_deadline,
                "Disponibilité de phase absente après 15s.")
        for child in self.children:
            if not child.process.stdout.closed:
                child.drain()
        self.flush_errors()

    def begin_phase(self, pair, condition):
        require(not self.children, "Outils précédents non récupérés.")
        self.tools.begin_phase(pair, condition)
        self.ready_deadline, self.available = time.monotonic() + 15, False

    def start(self, args, *, stdin=None):
        self.check()
        self.tools.before_start(args)
        child = Process(args, self.errors)
        self.children.append(child)
        self.check()
        return child

    def close(self):
        deadline, failure = time.monotonic() + 10, None
        for child in reversed(self.children):
            try:
                child.stop(deadline)
            except BaseException as error:
                failure = failure or error
        if failure is not None:
            raise Error("Récupération des outils de phase non confirmée : " + str(failure)) from failure
        self.children.clear()
        self.ready_deadline = None

    def finish_errors(self):
        deadline = time.monotonic() + 5
        while self.error_pending:
            self.check()
            require(time.monotonic() < deadline, "Délai de sortie stderr dépassé.")
            time.sleep(.005)


def idle(ip, client, server, binaries, runner, announce):
    target = runner.start([ip, "netns", "exec", server, str(binaries / "coopace-lab-tcp"),
                           "--listen", active.TARGET, "--connections", "100", "--duration", "30s"])
    try:
        target.ready("READY " + active.TARGET, runner)
        announce([target.process.pid])
        raw, code = runner.execute([ip, "netns", "exec", client, str(binaries / "coopace"),
                                    "latency", "--target", active.TARGET, "--count", "10", "--timeout", "1s",
                                    "--interval", "250ms", "--condition", "idle", "--json"], timeout=16, allowed=(0, 1))
        require(target.running(), "Cible idle arrêtée pendant les sondes.")
        return {"latency": active.latency_document(active.series.document(raw), "idle", code), "measurement_exit_code": code}
    finally:
        target.stop()


def worker(ip, client, server, binaries, session, tools, *, deadline=None):
    require(client == f"cg-{protocol.session_id(session)}-c" and server == f"cg-{session}-s",
            "Espaces client/serveur de cette session requis.")
    require(os.getpid() == os.getpgrp() == os.getsid(0), "Leader du groupe de campagne requis.")
    require(tools.session == session and tools.tools["ip"]["path"] == ip
            and all(tools.tools[key]["path"] == str(binaries / filename) for key, filename in
                    (("agent", "coopace"), ("target", "coopace-lab-tcp"), ("load", "coopace-lab-load"))),
            "Chemins du pilote incompatibles avec l’inventaire.")
    channel = Channel(session, sys.stdin.fileno(), sys.stdout.fileno())
    runner = CampaignRunner(channel, tools, deadline)
    previous = {}
    def interrupted(signum, _frame):
        runner.interruption = runner.interruption or 128 + signum
    try:
        for signum in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM):
            previous[signum] = signal.signal(signum, interrupted)
        for pair, condition in protocol.PHASES:
            channel.send(protocol.event_frame(session, "begin", pair=pair, condition=condition), runner)
            channel.await_control("start", runner)
            runner.begin_phase(pair, condition)
            def announce(pids):
                require(pids == [c.process.pid for c in runner.children]
                        and all(c.running() and os.getpgid(c.process.pid) == os.getpgrp() for c in runner.children),
                        "Outils arrêtés ou hors groupe avant ready.")
                channel.send(protocol.event_frame(session, "ready", pair=pair, condition=condition, helper_pids=pids), runner)
                runner.available = True
                channel.await_control("continue", runner, tuple(runner.children))
            try:
                measure = active.measure_loaded if condition == "loaded" else idle
                result = measure(ip, client, server, binaries, runner, announce)
            finally:
                runner.close()
            channel.send(protocol.event_frame(session, "end", pair=pair, condition=condition, result=result), runner)
            channel.await_control("advance", runner)
        runner.check()
        runner.finish_errors()
        channel.send(protocol.event_frame(session, "complete"), runner, boundary=False)
        channel.dialogue.finish_events()
        runner.check()
    finally:
        try:
            runner.close()
        finally:
            for signum, handler in previous.items():
                signal.signal(signum, handler)


def diagnostic(message):
    # Reserve room within the stderr budget and never block error termination
    # when the caller has stopped draining this pipe.
    data = (str(message)[:900] + "\n").encode("utf-8")[:1800].decode("utf-8", "ignore").encode("utf-8")
    try:
        if select.select([], [2], [], 0)[1]:
            os.write(2, data)
    except OSError:
        pass  # The caller may already have closed its diagnostic channel.


def main(argv=None):
    deadline = time.monotonic() + 150
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--client", required=True)
    parser.add_argument("--server", required=True)
    parser.add_argument("--ip", type=Path, required=True)
    parser.add_argument("--binaries", type=Path, required=True)
    parser.add_argument("--tools-json", required=True)
    args = parser.parse_args(argv)
    try:
        ip, binaries = args.ip.resolve(strict=True), args.binaries.resolve(strict=True)
        tools = ToolSet(args.tools_json, args.session_id)
        worker(str(ip), args.client, args.server, binaries, args.session_id, tools, deadline=deadline)
        return 0
    except active.series.Interrupted as error:
        diagnostic(error)
        return error.code
    except (Error, traffic.Error, active.Error, OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        diagnostic("Pilote de campagne interrompu : " + str(error))
        return 1
