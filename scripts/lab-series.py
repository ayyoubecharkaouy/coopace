"""Three bounded idle/loaded pairs inside namespaces owned by lab-network.sh."""

import argparse
import calendar
from datetime import datetime
import json
import math
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import tempfile
import time


ORDERS = (("idle", "loaded"), ("loaded", "idle"), ("idle", "loaded"))
TARGET = "10.203.0.6:46001"
LOAD_TARGET = "10.203.0.6:46002"
LIMIT = 256 * 1024


class ExperimentError(Exception):
    pass


class Interrupted(ExperimentError):
    def __init__(self, code):
        super().__init__(f"Interruption des séries (code {code}).")
        self.code = code


class Process:
    def __init__(self, args):
        # No shell, no descendant commands in the selected Coopace binaries.
        self.process = subprocess.Popen(args, stdout=subprocess.PIPE)
        try:
            os.set_blocking(self.process.stdout.fileno(), False)
        except OSError:
            self.process.kill()
            self.process.wait()
            self.process.stdout.close()
            raise
        self.output = bytearray()

    def drain(self):
        while True:
            try:
                data = os.read(self.process.stdout.fileno(), 8192)
            except BlockingIOError:
                break
            if not data:
                break
            self.output.extend(data)
            if len(self.output) > LIMIT:
                raise ExperimentError("Sortie d'un outil trop volumineuse.")

    def running(self):
        return self.process.poll() is None

    def ready(self, expected, runner):
        deadline = time.monotonic() + 5
        while True:
            runner.check()
            self.drain()
            if b"\n" in self.output:
                line, rest = self.output.split(b"\n", 1)
                if line != expected.encode("ascii"):
                    raise ExperimentError("Annonce de disponibilité invalide.")
                self.output = bytearray(rest)
                return
            if not self.running() or time.monotonic() >= deadline:
                raise ExperimentError("Outil indisponible avant la mesure.")
            time.sleep(0.02)

    def finish(self, runner, timeout, allowed=(0,)):
        deadline = time.monotonic() + timeout
        while True:
            runner.check()
            self.drain()
            code = self.process.poll()
            if code is not None:
                self.drain()
                if code not in allowed:
                    raise ExperimentError(f"Un outil a échoué (code {code}).")
                return bytes(self.output), code
            if time.monotonic() >= deadline:
                raise ExperimentError("Délai d'un outil dépassé.")
            time.sleep(0.02)

    def stop(self):
        try:
            if self.running():
                try:
                    self.process.terminate()
                except ProcessLookupError:
                    pass
                try:
                    self.process.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    try:
                        self.process.kill()
                    except ProcessLookupError:
                        pass
                    self.process.wait()
        finally:
            self.process.stdout.close()


class Runner:
    def __init__(self, timeout=90):
        self.deadline = time.monotonic() + timeout
        self.interruption = 0
        self.children = []

    def check(self):
        if self.interruption:
            raise Interrupted(self.interruption)
        if time.monotonic() >= self.deadline:
            raise ExperimentError("Délai applicatif global des séries dépassé.")

    def start(self, args):
        self.check()
        child = Process(args)
        # Signal handlers only record a flag, including while Popen is returning.
        # The child is registered before a pending signal can cause an exit.
        self.children.append(child)
        self.check()
        return child

    def execute(self, args, timeout=8, allowed=(0,)):
        child = self.start(args)
        try:
            return child.finish(self, timeout, allowed)
        finally:
            child.stop()

    def pause(self):
        deadline = time.monotonic() + 0.5
        while time.monotonic() < deadline:
            self.check()
            time.sleep(0.02)

    def close(self):
        # Each known process is stopped/reaped before the namespace owner exits.
        first_error = None
        for child in reversed(self.children):
            try:
                child.stop()
            except OSError as error:
                first_error = first_error or error
        if first_error:
            raise ExperimentError(f"Arrêt d'un processus non confirmé : {first_error}")


def timestamp_ns(value):
    if not isinstance(value, str):
        raise ExperimentError("Horodatage absent.")
    match = re.fullmatch(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d{1,9}))?Z", value)
    if not match:
        raise ExperimentError("Horodatage UTC non canonique.")
    try:
        seconds = calendar.timegm(datetime.strptime(match[1], "%Y-%m-%dT%H:%M:%S").timetuple())
    except ValueError as error:
        raise ExperimentError("Horodatage invalide.") from error
    return seconds * 1_000_000_000 + int((match[2] or "").ljust(9, "0"))


def document(raw):
    def invalid_constant(_value):
        raise ExperimentError("Nombre JSON non fini.")

    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ExperimentError("Champ JSON dupliqué.")
            value[key] = item
        return value

    try:
        value = json.loads(raw, object_pairs_hook=unique, parse_constant=invalid_constant)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise ExperimentError("Rapport JSON illisible.") from error
    if not isinstance(value, dict):
        raise ExperimentError("Objet JSON requis.")
    return value


def latency_document(raw, condition, exit_code):
    value = document(raw)
    expected = {"schema_version": 1, "method": "tcp_connect", "target": TARGET,
                "declared_condition": condition, "requested_attempts": 10,
                "timeout_ms": 250, "pause_between_attempts_ms": 250}
    if any(value.get(key) != item or isinstance(value.get(key), bool) for key, item in expected.items()):
        raise ExperimentError("Paramètres de mesure différents du protocole.")
    if type(value.get("successful")) is not int or not 0 <= value["successful"] <= 10:
        raise ExperimentError("Nombre de réussites invalide.")
    if exit_code != (0 if value["successful"] else 1):
        raise ExperimentError("Code de mesure incompatible avec les réussites.")
    if timestamp_ns(value.get("started_at")) > timestamp_ns(value.get("finished_at")):
        raise ExperimentError("Fenêtre de mesure inversée.")
    # The existing CLI compare subsequently validates the full schema and samples.
    return value


def load_document(raw, latency):
    value = document(raw)
    expected = {"schema_version": 1, "method": "synthetic_tcp_send", "target": LOAD_TARGET,
                "requested_bytes": 8388608, "written_bytes": 8388608,
                "requested_bytes_per_second": 1048576, "block_bytes": 16384, "timeout_ms": 12000}
    if any(value.get(key) != item or isinstance(value.get(key), bool) for key, item in expected.items()):
        raise ExperimentError("Rapport de charge incompatible avec le protocole.")
    elapsed, average = value.get("elapsed_ms"), value.get("average_bytes_per_second")
    if any(type(item) not in (float, int) or not math.isfinite(item) for item in [elapsed, average]):
        raise ExperimentError("Durée ou débit de charge invalide.")
    if not 8000 <= elapsed < 12000 or not 0 < average <= 1048576:
        raise ExperimentError("Durée ou plafond de charge non respecté.")
    if not math.isclose(average, 8388608 / (elapsed / 1000), rel_tol=1e-9):
        raise ExperimentError("Débit incompatible avec la durée.")
    start, first, last, end = (timestamp_ns(value.get(key)) for key in
                              ["started_at", "first_write_at", "last_write_at", "finished_at"])
    if not start <= first < last <= end or abs((end-start)/1_000_000-elapsed) > 1:
        raise ExperimentError("Fenêtre d'écritures de charge incohérente.")
    if not first <= timestamp_ns(latency["started_at"]) <= timestamp_ns(latency["finished_at"]) <= last:
        raise ExperimentError("La charge ne couvre pas toute la fenêtre de latence.")
    return value


def measure(root, client, server, condition, runner):
    binaries = root / ".local/bin"
    def inside(namespace, binary, *args):
        return ["ip", "netns", "exec", namespace, str(binaries / binary), *args]

    target = runner.start(inside(server, "coopace-lab-tcp", "--listen", TARGET,
                                  "--connections", "100", "--duration", "15s"))
    receiver = sender = None
    try:
        target.ready("READY " + TARGET, runner)
        if condition == "loaded":
            receiver = runner.start(inside(server, "coopace-lab-load", "receive", "--listen", LOAD_TARGET,
                                             "--bytes", "8388608", "--duration", "15s"))
            receiver.ready("READY " + LOAD_TARGET, runner)
            sender = runner.start(inside(client, "coopace-lab-load", "send", "--target", LOAD_TARGET,
                                           "--bytes", "8388608", "--rate", "1048576", "--duration", "12s", "--announce-start"))
            sender.ready("STARTED", runner)
        if not target.running():
            raise ExperimentError("La cible de latence s'est arrêtée avant la mesure.")
        raw, code = runner.execute(inside(client, "coopace", "latency", "--target", TARGET,
                                            "--count", "10", "--timeout", "250ms", "--interval", "250ms",
                                            "--condition", condition, "--json"), allowed=(0, 1))
        latency = latency_document(raw, condition, code)
        if not target.running():
            raise ExperimentError("La cible de latence s'est arrêtée pendant la mesure.")
        # We do not require every probe to succeed: failures are experimental data.
        print("Arrêt volontaire de la cible de latence après la série.", file=sys.stderr, flush=True)
        target.stop()
        load = None
        if sender is not None:
            load_raw, _ = sender.finish(runner, 13)
            receiver.finish(runner, 16)
            load = load_document(load_raw, latency)
        return {"latency": latency, "measurement_exit_code": code, "load": load}, raw
    finally:
        for child in [sender, receiver, target]:
            if child is not None:
                child.stop()


def experiment(root, client, server, workspace, runner):
    match = re.fullmatch(r"cp-([A-Za-z0-9]{8})-c", client)
    if not match or server != f"cp-{match[1]}-s":
        raise ExperimentError("Noms des espaces propres au laboratoire requis.")
    info = workspace.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o077:
        raise ExperimentError("Réservation temporaire privée requise, sans lien symbolique.")
    pairs = []
    # TemporaryDirectory owns only its exclusive child, never the caller's directory.
    with tempfile.TemporaryDirectory(prefix="series-", dir=workspace) as directory:
        for index, order in enumerate(ORDERS, 1):
            pair = {"index": index, "order": list(order)}
            paths = {}
            for condition in order:
                runner.pause()
                print(f"Paire {index}/3 — condition {condition}.", file=sys.stderr, flush=True)
                phase, raw = measure(root, client, server, condition, runner)
                pair[condition] = phase
                path = Path(directory) / f"{index}-{condition}.json"
                path.write_bytes(raw)
                paths[condition] = path
            comparison, _ = runner.execute([str(root / ".local/bin/coopace"), "latency", "compare",
                                              "--idle", str(paths["idle"]), "--loaded", str(paths["loaded"])])
            if not comparison.strip():
                raise ExperimentError("Comparaison descriptive absente.")
            pair["comparison"] = comparison.decode("utf-8")
            pairs.append(pair)
    return {"schema_version": 1, "kind": "synthetic_latency_series", "pairs": pairs,
            "cooldown_ms": 500, "count_per_phase": 10, "timeout_ms": 250, "interval_ms": 250,
            "total_synthetic_bytes": 3 * 8388608, "overlap_check": "application_write_window",
            "saturation": "unverified", "traffic_coverage": "synthetic_ipv4_only"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", required=True)
    parser.add_argument("--server", required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args(argv)
    runner = Runner()
    # Do not raise from handlers: every newly spawned child must be registered.
    def interrupted(signum, _frame):
        if not runner.interruption:
            runner.interruption = {signal.SIGHUP: 129, signal.SIGINT: 130, signal.SIGTERM: 143}[signum]
    for signum in [signal.SIGHUP, signal.SIGINT, signal.SIGTERM]:
        signal.signal(signum, interrupted)
    try:
        try:
            result = experiment(Path(__file__).resolve().parents[1], args.client, args.server, args.workspace, runner)
        finally:
            runner.close()
        runner.check()
    except (ExperimentError, OSError, ValueError) as error:
        print(f"Échec des séries : {error}", file=sys.stderr)
        return error.code if isinstance(error, Interrupted) else 1
    json.dump(result, sys.stdout, ensure_ascii=False, allow_nan=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
