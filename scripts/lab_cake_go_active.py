"""One namespace owner for Go DOWN, activation, traffic and final cleanup."""

from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import time

spec = importlib.util.spec_from_file_location("go_active_collect", Path(__file__).with_name("lab_cake_go_collect.py"))
collect = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collect)
go, require, Error = collect.go, collect.require, collect.Error


def source_fingerprints():
    return {**collect.topology.source_fingerprints(), **{
        str(Path(__file__).with_name(name)): hashlib.sha256(go.read(Path(__file__).with_name(name), 1024 * 1024)).hexdigest()
        for name in ("lab_cake_go_active.py", "lab-cake-go-active.py", "lab_cake_go_collect.py",
                     "lab_cake_go_traffic.py", "lab-cake-go-traffic.py")}}


def git_commit():
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[1],
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=2, check=True)
    commit = result.stdout.decode("ascii").strip()
    require(len(commit) == 40 and all(c in "0123456789abcdef" for c in commit), "Révision Git invalide.")
    return commit


class Inventory:
    fingerprint = staticmethod(go.tool)
    source_fingerprints = staticmethod(source_fingerprints)

    def __init__(self, owner, worker, tc, sysctl, binaries):
        self.owner, self.binaries, self.session = owner, binaries.resolve(strict=True), None
        paths = {"worker": worker, "ip": owner.namespaces.ip, "tc": tc, "sysctl": sysctl, "python": sys.executable,
                 "agent": self.binaries / "coopace", "target": self.binaries / "coopace-lab-tcp", "load": self.binaries / "coopace-lab-load"}
        self.tools = {n: self.fingerprint(path) for n, path in paths.items()}
        for name, filename in (("agent", "coopace"), ("target", "coopace-lab-tcp"), ("load", "coopace-lab-load")):
            require(self.tools[name]["path"] == str(self.binaries / filename), "Binaire de trafic canonique sans redirection requis.")
        owner.namespaces.ip = self.tools["ip"]["path"]
        self.sources, self.commit = self.source_fingerprints(), git_commit()

    def metadata(self):
        versions = {}
        for name, flags in (("python", ["--version"]), ("ip", ["-V"]), ("tc", ["-V"]), ("sysctl", ["--version"])):
            self.verify()
            raw = self.owner.namespaces.execute([self.tools[name]["path"], *flags], self.owner)
            versions[name] = {"available": True, "output": raw.decode("utf-8", errors="strict").strip()}
        for name in ("worker", "agent", "target", "load"):
            versions[name] = {"available": False, "reason": "no_uniform_version_command",
                              "runtime_metadata": "journal_or_flow_when_available"}
        return {"tools": self.tools, "versions": versions, "source_sha256": self.sources, "git_commit": self.commit,
                "kernel": platform.release(), "python": sys.version, "binaries": str(self.binaries),
                "bootstrap_sha256": hashlib.sha256(go.BOOTSTRAP.encode()).hexdigest()}

    def verify(self):
        self.owner.check()
        for spec in self.tools.values():
            require(self.fingerprint(spec["path"]) == spec, "Exécutable modifié pendant le contrôle combiné.")
        require(self.source_fingerprints() == self.sources, "Sources modifiées pendant le contrôle combiné.")


class Journal:
    def __init__(self, path, limit=4 * 1024 * 1024):
        self.capture = collect.Capture(path, limit)
        self.started, self.sequence = time.monotonic_ns(), 0

    def write(self, event):
        self.sequence += 1
        value = {"schema_version": 1, "kind": "lab_cake_go_active_journal", "sequence": self.sequence,
                 "recorded_at": datetime.now(timezone.utc).isoformat(), "elapsed_ns": time.monotonic_ns() - self.started,
                 "data": event}
        self.capture.append(json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode() + b"\n")

    def close(self):
        self.capture.close()
        return self.capture.summary()


def phase_evidence(folder, expected=None):
    result = {}
    for name, limit in (("worker.jsonl", go.protocol.JOURNAL_LIMIT), ("events.bin", go.protocol.OUTPUT_LIMIT),
                        ("worker.stderr", go.protocol.OUTPUT_LIMIT)):
        raw = go.read(folder / name, limit)
        result[name] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    require(expected is None or expected == result, "Preuves de phase Go modifiées pendant le trafic.")
    return result


def run(mode, namespaces, worker, tc, sysctl, binaries, artifacts, *, timeout=180, tempdir=None,
        session_factory=go.Session, inventory_factory=Inventory, collector_factory=collect.Collector,
        path_factory=None, journal_factory=Journal, report_kind=None, finalizer=None):
    require(mode in ("check", "check-crash") or (mode == "run" and report_kind == "lab_cake_go_campaign_collection"),
            "Mode combiné inconnu.")
    require(artifacts.is_dir() and not any(artifacts.iterdir()), "Dossier de preuves neuf et vide requis.")
    go.guards.enable_subreaper()
    owner = go.GoGuard(namespaces, timeout=timeout, tempdir=tempdir)
    result = {"schema_version": 1, "kind": "lab_cake_go_active_check", "state": "failed", "mode": mode,
              "reference": go.protocol.REFERENCE, "session_id": None, "cleanup_verified": False,
              "traffic_generated": False, "go_phase": None, "traffic_group": None, "topology": None,
              "queue_samples": [], "traffic_statistics_delta": None, "flow": None,
              "congestion": "not_assessed", "traffic_coverage": "synthetic_ipv4_only"}
    if path_factory is not None:
        result.update(kind="lab_cake_go_path_check", path_check=None)
    if report_kind is not None:
        result["kind"] = report_kind
    previous, journal, inventory, collector, phase_session, failure = {}, None, None, None, None, None
    def interrupted(signum, _frame):
        owner.interruption = owner.interruption or 128 + signum
    try:
        for signum in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM):
            previous[signum] = signal.signal(signum, interrupted)
        try:
            try:
                journal = journal_factory(artifacts / "supervisor.jsonl")
                inventory = inventory_factory(owner, worker, tc, sysctl, binaries)
                environment = inventory.metadata()
                purpose = report_kind.removeprefix("lab_") if report_kind is not None else "cake_go_path_then_traffic" if path_factory is not None else "cake_go_then_traffic"
                environment["invocation"] = {"mode": mode, "purpose": purpose, "reference": go.protocol.REFERENCE}
                go.save(artifacts / "environment.json", environment)
                result["environment"] = environment
                folder = artifacts / "go"
                folder.mkdir(mode=0o700)
                if os.geteuid() == 0:
                    parent = artifacts.stat()
                    os.chown(folder, parent.st_uid, parent.st_gid)
                journal.write({"event": "environment_verified", "tools": inventory.tools, "source_sha256": inventory.sources})
                inventory.verify()
                owner.create()
                inventory.session = owner.workspace.name.removeprefix("coopace-guard.")
                result["session_id"] = inventory.session
                journal.write({"event": "resources_owned", "namespaces": owner.owned, "session_id": inventory.session})
                down = go.DownLink(namespaces, inventory.tools["tc"]["path"])
                down.prepare(owner)
                go_tools = {n: inventory.tools[n] for n in ("worker", "ip", "tc", "python")}
                result["go_phase"] = go.run_phase(owner, go_tools, folder, down, session_factory=session_factory)
                phase_session = owner.session
                frozen = phase_evidence(folder)
                journal.write({"event": "go_phase_finished", "phase": result["go_phase"], "evidence": frozen})
                inventory.verify()
                activated = collect.topology.activate_after_phase(owner, down, inventory.tools["sysctl"], journal.write)
                if path_factory is not None:
                    result["topology"] = activated.report
                    path_check = path_factory(owner, activated, inventory, journal.write)
                    result["path_check"] = path_check.report
                    path_check.run()
                    require(path_check.report.get("state") == "verified" and path_check.report.get("path_verified") is True,
                            "Passage IPv4 non confirmé ; trafic TCP interdit.")
                    inventory.verify()
                collector = collector_factory(owner, activated, inventory, artifacts, journal.write)
                result["traffic_group"] = collector.report
                collector.run(mode)
                result.update(topology=activated.report, queue_samples=collector.report["queue_samples"],
                              traffic_statistics_delta=collector.report["traffic_statistics_delta"], flow=collector.report["flow"])
                phase_evidence(folder, frozen)
                # Session.validate uses owner.child, which now names the traffic
                # leader. Revalidate using the immutable PID of the old Go group.
                summary = go.protocol.journal(go.read(folder / "worker.jsonl", go.protocol.JOURNAL_LIMIT, phase_session.journal_identity),
                                              phase_session.token, phase_session.tools, phase_session.target, phase_session.original,
                                              result["go_phase"]["worker_pid"], "finished", phase_session.applied)
                require(summary == result["go_phase"]["journal"], "Résumé de phase Go modifié.")
                inventory.verify()
                journal.write({"event": "combined_evidence_verified"})
            finally:
                owner.close()
                result["cleanup_verified"] = True
            owner.check()
            inventory.verify()
        except BaseException as error:
            failure = error
            result["error"] = str(error)
        finally:
            if collector is not None:
                try:
                    collector.close()
                except BaseException as error:
                    failure = failure or error
                    result["error"] = str(failure)
                result.update(traffic_generated=collector.report["traffic_generated"],
                              queue_samples=collector.report["queue_samples"], flow=collector.report["flow"],
                              traffic_statistics_delta=collector.report["traffic_statistics_delta"], topology=collector.topology.report)
            result.update(namespaces=[n for n, _ in owner.owned], workspace=str(owner.workspace) if owner.workspace else None,
                          groups=[{"driver_pid": g.child.pid if g.child else None, "driver_exit_code": g.driver_code,
                                   "reaped_descendants": g.reaped_descendants, "state": g.state} for g in owner.process_groups])
            if failure is None:
                result["state"] = "complete"
            if journal is not None:
                try:
                    journal.write({"event": "control_complete" if failure is None else "control_failed",
                                   "cleanup_verified": result["cleanup_verified"], "error": result.get("error", "")})
                    result["supervisor_journal"] = journal.close()
                except BaseException as error:
                    failure = failure or error
                    result.update(state="failed", error=str(failure))
                    journal.capture.close()
            if finalizer is not None:
                try:
                    finalizer(result, artifacts, operational_success=failure is None)
                    if failure is None:
                        inventory.verify()
                        owner.check()
                except BaseException as error:
                    failure = failure or error
                    result.update(state="failed", error=str(failure))
                    if result.get("kind") == "lab_cake_go_campaign":
                        result.update(technical_valid=False, load_scenario="non_exploitable", connections="not_assessed")
            go.save(artifacts / "report.json", result)
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)
    if failure is not None:
        raise failure
    return result


def plan():
    return ("Contrôle CAKE Go puis trafic : trois espaces neufs conservés entre les deux phases.\n"
            "Go ajoute et relit CAKE 4mbit sur wan DOWN ; son groupe est récupéré avant activation.\n"
            "Même wan activé, trois outils vérifiés, puis accusé avant dix sondes et réception de 8 Mio.\n"
            "check-crash tue seulement le pilote de trafic en attente ; trois outils orphelins à récupérer.\n"
            "Relevés CAKE bornés, compteurs monotones, vidage normal et nettoyage global avant succès.\n"
            "Superviseur 180s, pilote 45s et nettoyage 10s ; aucune interface physique ni accès Internet.\n"
            "Preuves exclusives dans --artifacts ; référence native combinée documentée, foyer non validé.\n"
            "Le mode plan ne crée aucune ressource et ne requiert aucun privilège.")
