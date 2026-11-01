"""Supervised IPv4 passage before the existing Go/CAKE traffic collector."""

import base64
from datetime import datetime, timezone
import hashlib
import importlib.util
import os
from pathlib import Path
import subprocess
import time


def sibling(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


active = sibling("path_active", "lab_cake_go_active.py")
readers = sibling("path_readers", "lab_cake_go_path.py")
go, require, Error = active.go, active.require, active.Error


def source_fingerprints():
    return {**active.source_fingerprints(), **{
        str(Path(__file__).with_name(name)): hashlib.sha256(go.read(Path(__file__).with_name(name), 1024 * 1024)).hexdigest()
        for name in ("lab_cake_go_path.py", "lab_cake_go_path_control.py", "lab-cake-go-path.py")}}


def outcome():
    return {"pid": None, "exit_code": None, "stdout": b"", "stderr": b"",
            "stdout_truncated": False, "stderr_truncated": False, "process_stopped": False}


def execute(owner, arguments, timeout, result):
    """Capture both pipes; retain an uncertain child for the owner's cleanup.

    Only pinned ip/sysctl/iputils commands (no helpers) reach this runner.
    Tests exercise it separately with real unprivileged processes.
    """
    require(timeout in (2, 4, 6), "Borne de commande de passage inconnue.")
    owner.check()
    require(not owner.closed and owner.command_child is None, "Commande précédente ou propriétaire fermé.")
    deadline = min(owner.deadline, time.monotonic() + timeout)
    child = subprocess.Popen(arguments, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             close_fds=True, env={"LANG": "C", "LC_ALL": "C"})
    owner.command_child = child
    result["pid"] = child.pid
    buffers, eof = {"stdout": bytearray(), "stderr": bytearray()}, set()
    try:
        for stream in (child.stdout, child.stderr):
            os.set_blocking(stream.fileno(), False)
        while True:
            owner.check()
            require(time.monotonic() < deadline, "Délai de commande de passage dépassé.")
            for name in buffers:
                if name in eof:
                    continue
                try:
                    block = os.read(getattr(child, name).fileno(), 8192)
                except BlockingIOError:
                    continue
                if not block:
                    eof.add(name)
                remaining = readers.OUTPUT_LIMIT - len(buffers[name])
                buffers[name].extend(block[:remaining])
                if len(block) > remaining:
                    result[name + "_truncated"] = True
                    raise Error("Capture de commande de passage trop volumineuse : " + name)
            code = child.poll()
            if code is not None and len(eof) == 2:
                result["exit_code"] = code
                return
            time.sleep(0.005)
    finally:
        try:
            if child.poll() is None:
                child.kill()
            result["exit_code"] = child.wait(timeout=1)
            result["process_stopped"] = True
            owner.command_child = None
        finally:
            for name, buffer in buffers.items():
                result[name] = bytes(buffer)
                getattr(child, name).close()


class Inventory(active.Inventory):
    source_fingerprints = staticmethod(source_fingerprints)

    def __init__(self, *args, ping):
        super().__init__(*args)
        self.tools["ping"] = self.fingerprint(ping)

    def metadata(self):
        value = super().metadata()
        self.verify()
        result = outcome()
        execute(self.owner, [self.tools["ping"]["path"], "-V"], 2, result)
        require(result["exit_code"] == 0 and result["stdout"].startswith(b"ping from iputils "), "Producteur iputils requis.")
        self.verify()
        value["versions"]["ping"] = {"available": True, "stdout": result["stdout"].decode("ascii"),
                                    "stderr": result["stderr"].decode("ascii")}
        return value


class PathCheck:
    executor = staticmethod(execute)

    def __init__(self, owner, topology, inventory, record):
        self.owner, self.topology, self.inventory, self.record = owner, topology, inventory, record
        self.names = tuple(topology.names)
        self.tools = inventory.tools
        c, g, s = [name for name, _ in self.names]
        session = active.collect.traffic.session_id(inventory.session)
        require([c, g, s] == [f"cg-{session}-{role}" for role in ("c", "g", "s")], "Espaces de passage incompatibles.")
        ip, sysctl, ping = [self.tools[n]["path"] for n in ("ip", "sysctl", "ping")]
        switch = [ip, "netns", "exec", g, sysctl]
        probe = [ip, "netns", "exec", c, ping, "-4", "-n"]
        self.commands = (
            ("disable", [*switch, "-q", "-w", "net.ipv4.ip_forward=0"], 2, 0),
            ("read_disabled", [*switch, "-n", "net.ipv4.ip_forward"], 2, 0),
            ("blocked_probe", [*probe, "-c", "1", "-w", "3", "-W", "1", readers.TARGET], 4, 1),
            ("enable", [*switch, "-q", "-w", "net.ipv4.ip_forward=1"], 2, 0),
            ("read_enabled", [*switch, "-n", "net.ipv4.ip_forward"], 2, 0),
            ("passing_probe", [*probe, "-c", "3", "-w", "5", "-W", "1", readers.TARGET], 6, 0),
        )
        self.next_command = 0
        self.report = {"schema_version": 1, "kind": "lab_cake_go_ipv4_passage", "state": "prepared",
                       "path_verified": False, "probe_attempted": False, "commands": [],
                       "without_forwarding": None, "with_forwarding": None,
                       "before": None, "after": None, "statistics_delta": None}

    def verify(self):
        self.owner.check()
        require(not self.owner.closed and self.owner.child is None and self.owner.command_child is None
                and self.owner.process_group.state == "new"
                and self.topology.state == "activated" and self.topology.failure is None
                and self.owner.phase_failure is None, "Contexte de passage non disponible.")
        for group in self.owner.process_groups[:-1]:
            group.require_stopped()
        require(tuple(self.owner.owned) == self.names, "Espaces du passage remplacés.")
        for name, identity in self.names:
            require(self.owner.namespaces.identity(name) == identity, "Identité possédée du passage modifiée.")
        self.inventory.verify()

    def continuity(self):
        self.verify()
        gateway = self.names[1][0]
        current = active.collect.topology.links(self.topology.links(gateway), ("lo", "lan", "wan"), True)
        require(current == self.topology.up_baseline[gateway], "Lien remplacé pendant le contrôle de passage.")
        self.topology.read(True)

    def command(self, index):
        require(self.report["state"] == "running" and index == self.next_command and index < len(self.commands),
                "Commande de passage interdite ou hors ordre.")
        self.verify()
        label, args, timeout, expected = self.commands[index]
        self.next_command += 1  # A failed mutation may already have had an effect.
        self.record({"event": "path_tool_intent", "index": index + 1, "label": label, "arguments": args,
                     "timeout_seconds": timeout, "expected_exit_code": expected})
        if label in ("blocked_probe", "passing_probe"):
            self.report["probe_attempted"] = True
        result, failure = outcome(), None
        started_at, started_ns = datetime.now(timezone.utc).isoformat(), time.monotonic_ns()
        try:
            self.executor(self.owner, args, timeout, result)
            require(result["process_stopped"] and not result["stdout_truncated"] and not result["stderr_truncated"],
                    "Capture tronquée ou arrêt de commande non confirmé.")
            require(type(result["exit_code"]) is int and result["exit_code"] == expected, "Code de commande de passage incompatible.")
            self.verify()
        except BaseException as error:
            failure = error
            raise
        finally:
            proof = {"event": "path_tool_result", "index": index + 1, "label": label, "arguments": args,
                     "started_at": started_at, "finished_at": datetime.now(timezone.utc).isoformat(),
                     "duration_ns": time.monotonic_ns() - started_ns, "error": "" if failure is None else str(failure),
                     **{k: v for k, v in result.items() if k not in ("stdout", "stderr")},
                     "stdout_base64": base64.b64encode(result["stdout"]).decode("ascii"),
                     "stderr_base64": base64.b64encode(result["stderr"]).decode("ascii")}
            self.report["commands"].append(proof)
            self.record(proof)
        return result

    def run(self):
        require(self.report["state"] == "prepared", "Contrôle de passage déjà utilisé.")
        try:
            self.verify()
            self.topology.verify("before_path")
            self.report["before"] = self.topology.report["before_path"]
            self.record({"event": "path_begin", "tools": self.tools, "source_sha256": self.inventory.sources})
            self.report["state"] = "running"
            for index in range(len(self.commands)):
                result = self.command(index)
                if index in (1, 4):
                    readers.validate_forwarding(result["stdout"], 0 if index == 1 else 1)
                elif index in (2, 5):
                    key = "without_forwarding" if index == 2 else "with_forwarding"
                    self.report[key] = readers.validate_probe(result["stdout"], result["exit_code"], forwarding=0 if index == 2 else 1)
                self.continuity()
            self.topology.verify("after_path")
            self.verify()
            self.report["after"] = self.topology.report["after_path"]
            self.report["statistics_delta"] = active.collect.cake.queue.statistics_delta(
                self.report["before"]["statistics"], self.report["after"]["statistics"])
            require(self.report["statistics_delta"]["available"], "Compteurs du passage en baisse.")
            self.record({"event": "path_verified", "without_forwarding": self.report["without_forwarding"],
                         "with_forwarding": self.report["with_forwarding"], "statistics_delta": self.report["statistics_delta"]})
            self.report.update(state="verified", path_verified=True)
        except BaseException as error:
            self.report.update(state="failed", path_verified=False, error=str(error))
            self.owner.phase_failure = error
            raise


def run(mode, namespaces, worker, tc, sysctl, ping, binaries, artifacts):
    def inventory(*args):
        return Inventory(*args, ping=ping)
    return active.run(mode, namespaces, worker, tc, sysctl, binaries, artifacts,
                      inventory_factory=inventory, path_factory=PathCheck)


def plan():
    return ("Contrôle IPv4 après Go : même laboratoire jetable et même CAKE.\n"
            "Après activation : forwarding 0 relu, une requête ICMP sans réponse ;\n"
            "puis forwarding 1 relu, trois requêtes et trois réponses exigées.\n"
            "Un échec interdit le pilote TCP ; sinon transfert de 8 Mio et dix sondes, ou panne du pilote.\n"
            "Outils et sources épinglés, captures bornées, continuité CAKE et nettoyage indépendant.\n"
            "Budget global 180s ; aucune interface physique ni accès Internet.\n"
            "Cette extension doit encore être validée en natif ; plan ne crée aucune ressource.")
