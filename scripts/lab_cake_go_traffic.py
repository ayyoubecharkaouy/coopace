"""Internal traffic driver: session-bound READY, then an explicit continue frame.

The caller owns namespaces, provenance and the process group. This module never
creates/deletes namespaces or changes a qdisc; it only uses the fixed lab flow.
"""

import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import sys
import time


spec = importlib.util.spec_from_file_location("go_traffic_active", Path(__file__).with_name("lab_active.py"))
active = importlib.util.module_from_spec(spec)
spec.loader.exec_module(active)
Error = active.series.ExperimentError
FRAME_LIMIT = 1024
OUTPUT_LIMIT = active.OUTPUT_LIMIT
HANDSHAKE_TIMEOUT = 5


def require(condition, message):
    if not condition:
        raise Error(message)


def session_id(value):
    require(isinstance(value, str) and re.fullmatch(r"[a-z0-9_]{8}", value),
            "Jeton de session du laboratoire requis.")
    return value


def helper_pids(value):
    require(isinstance(value, list) and len(value) == 3
            and all(type(pid) is int and pid > 0 for pid in value) and len(set(value)) == 3,
            "Trois PID d’outils positifs et distincts sont requis.")
    return value


def line_document(raw, limit):
    require(isinstance(raw, bytes) and 0 < len(raw) <= limit
            and raw.endswith(b"\n") and raw.count(b"\n") == 1,
            "Ligne interne absente, tronquée, multiple ou trop grande.")
    return active.series.document(raw[:-1])


def frame(value, limit=FRAME_LIMIT, prefix=b""):
    raw = prefix + json.dumps(value, separators=(",", ":"), allow_nan=False).encode("utf-8") + b"\n"
    require(len(raw) <= limit, "Message interne trop volumineux.")
    return raw


def ready_frame(session, pids):
    return frame({"schema_version": 1, "kind": "lab_cake_go_active_ready",
                  "session_id": session_id(session), "helper_pids": helper_pids(pids)}, prefix=b"READY ")


def parse_ready(raw, session):
    session_id(session)
    require(isinstance(raw, bytes) and len(raw) <= FRAME_LIMIT and raw.startswith(b"READY "),
            "Annonce de disponibilité absente ou trop grande.")
    value = line_document(raw[6:], FRAME_LIMIT - 6)
    require(set(value) == {"schema_version", "kind", "session_id", "helper_pids"}
            and type(value["schema_version"]) is int and value["schema_version"] == 1
            and value["kind"] == "lab_cake_go_active_ready" and value["session_id"] == session,
            "Annonce incompatible avec la session.")
    helper_pids(value["helper_pids"])
    return value


def continue_frame(session):
    return frame({"schema_version": 1, "kind": "lab_cake_go_active_control",
                  "session_id": session_id(session), "action": "continue"})


def parse_continue(raw, session):
    session_id(session)
    value = line_document(raw, FRAME_LIMIT)
    require(set(value) == {"schema_version", "kind", "session_id", "action"}
            and type(value["schema_version"]) is int and value["schema_version"] == 1
            and value["kind"] == "lab_cake_go_active_control" and value["session_id"] == session
            and value["action"] == "continue", "Accusé incompatible avec la session.")
    return value


def validated_flow(value):
    fields = {"send", "receive", "latency", "measurement_exit_code",
              "probe_window_inside_application_writes", "has_successful_probe"}
    require(isinstance(value, dict) and set(value) == fields
            and type(value["measurement_exit_code"]) is int,
            "Résultat de trafic incomplet ou incompatible.")
    result = active.flow_documents(*(json.dumps(value[key], allow_nan=False).encode()
                                     for key in ("send", "receive", "latency")),
                                   value["measurement_exit_code"])
    for key in ("probe_window_inside_application_writes", "has_successful_probe"):
        require(type(value[key]) is bool and value[key] == result[key],
                "Indicateur de trafic incompatible avec les rapports.")
    return result


def flow_frame(session, value):
    return frame({"schema_version": 1, "kind": "lab_cake_go_active_flow",
                  "session_id": session_id(session), "flow": validated_flow(value)}, OUTPUT_LIMIT)


def parse_flow(raw, session):
    session_id(session)
    value = line_document(raw, OUTPUT_LIMIT)
    require(set(value) == {"schema_version", "kind", "session_id", "flow"}
            and type(value["schema_version"]) is int and value["schema_version"] == 1
            and value["kind"] == "lab_cake_go_active_flow" and value["session_id"] == session,
            "Résultat de trafic hors session.")
    return validated_flow(value["flow"])


class Channel:
    def __init__(self, session, input_fd, output_fd):
        self.session = session_id(session)
        self.input_fd, self.output_fd = input_fd, output_fd
        self.state, self.eof, self.written = "new", False, 0
        os.set_blocking(input_fd, False)
        os.set_blocking(output_fd, False)

    def observe(self):
        # Any additional byte is a duplicate, even when it arrives after continue.
        # EOF is valid only after a complete acknowledgement has been accepted.
        if self.state == "waiting" or self.eof:
            return
        try:
            data = os.read(self.input_fd, 1)
        except BlockingIOError:
            return
        require(not data, "Accusé prématuré ou contrôle supplémentaire interdit.")
        self.eof = True
        require(self.state == "continued", "EOF avant l’accusé complet.")

    def send(self, raw, runner, timeout=HANDSHAKE_TIMEOUT):
        require(self.written + len(raw) <= OUTPUT_LIMIT, "Sortie du pilote trop volumineuse.")
        deadline = time.monotonic() + timeout
        offset = 0
        while offset < len(raw):
            runner.check()
            require(time.monotonic() < deadline, "Délai d’écriture du pilote dépassé.")
            try:
                count = os.write(self.output_fd, raw[offset:])
            except BlockingIOError:
                time.sleep(.01)
                continue
            require(count > 0, "Écriture du pilote interrompue.")
            offset += count
            self.written += count
        runner.check()

    def await_continue(self, pids, runner):
        require(self.state == "new", "Disponibilité déjà annoncée.")
        runner.check()
        require(pids == [child.process.pid for child in runner.children]
                and all(child.running() and os.getpgid(child.process.pid) == os.getpgrp()
                        for child in runner.children), "Outils de charge arrêtés ou hors groupe.")
        raw = ready_frame(self.session, pids)
        # While writing READY, an acknowledgement may legitimately arrive as soon
        # as its newline is visible. Its bytes are read only after that write.
        self.state = "waiting"
        self.send(raw, runner)
        runner.availability_announced = True
        deadline, pending = time.monotonic() + HANDSHAKE_TIMEOUT, bytearray()
        while True:
            runner.check()
            require(time.monotonic() < deadline, "Délai d’accusé dépassé.")
            require(all(child.running() for child in runner.children),
                    "Un outil s’est arrêté pendant l’attente de l’accusé.")
            try:
                data = os.read(self.input_fd, FRAME_LIMIT + 1 - len(pending))
            except BlockingIOError:
                time.sleep(.01)
                continue
            require(data, "EOF avant l’accusé complet.")
            pending.extend(data)
            require(len(pending) <= FRAME_LIMIT, "Accusé trop volumineux.")
            if b"\n" in pending:
                parse_continue(bytes(pending), self.session)
                self.state = "continued"
                runner.check()
                return
            require(len(pending) < FRAME_LIMIT, "Accusé trop volumineux ou tronqué.")


class TrafficRunner(active.series.Runner):
    def __init__(self, channel):
        super().__init__(timeout=45)
        self.channel, self.availability_announced = channel, False
        self.ready_deadline = time.monotonic() + 15

    def check(self):
        super().check()
        require(self.availability_announced or time.monotonic() < self.ready_deadline,
                "Disponibilité non annoncée avant le délai de 15s.")
        self.channel.observe()


def worker(ip, client, server, binaries, session):
    session_id(session)
    require(client == f"cg-{session}-c" and server == f"cg-{session}-s",
            "Espaces client/serveur de cette session requis.")
    require(os.getpid() == os.getpgrp() == os.getsid(0),
            "Le pilote doit être le leader du groupe réservé par le superviseur.")
    channel = Channel(session, sys.stdin.fileno(), sys.stdout.fileno())
    runner = TrafficRunner(channel)
    previous = {}
    def interrupted(signum, _frame):
        runner.interruption = runner.interruption or 128 + signum
    try:
        for signum in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM):
            previous[signum] = signal.signal(signum, interrupted)
        try:
            result = active.measure_loaded(ip, client, server, binaries, runner,
                                           lambda pids: channel.await_continue(pids, runner))
        finally:
            runner.close()
        runner.check()
        channel.send(flow_frame(session, result), runner)
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--client", required=True)
    parser.add_argument("--server", required=True)
    parser.add_argument("--ip", type=Path, required=True)
    parser.add_argument("--binaries", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        ip, binaries = args.ip.resolve(strict=True), args.binaries.resolve(strict=True)
        for path in (ip, *(binaries / name for name in ("coopace", "coopace-lab-tcp", "coopace-lab-load"))):
            require(path.is_file() and os.access(path, os.X_OK), "Exécutables de laboratoire requis.")
        worker(str(ip), args.client, args.server, binaries, args.session_id)
        return 0
    except active.series.Interrupted as error:
        print(str(error), file=sys.stderr)
        return error.code
    except (Error, active.Error, OSError, ValueError, KeyError) as error:
        print(f"Pilote Go puis trafic interrompu : {error}", file=sys.stderr)
        return 1
