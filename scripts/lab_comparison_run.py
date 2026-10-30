"""Sequential campaigns under their existing guards; no outer forced timeout."""

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import signal
import sys
import time


spec = importlib.util.spec_from_file_location("comparison_model", Path(__file__).with_name("lab_comparison.py"))
model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)
campaign = model.campaign


def digest(path):
    return hashlib.sha256(model.read(path, 64 * 1024 * 1024)).hexdigest()


def save(path, value):
    with campaign.exclusive(path) as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


def fingerprint(binaries, tools):
    paths = [binaries / name for name in ("coopace", "coopace-lab-tcp", "coopace-lab-load")]
    paths.extend(Path(value).resolve(strict=True) for value in tools.values())
    paths.extend(Path(__file__).with_name(name) for name in (
        "lab-compare.py", "lab_comparison_run.py", "lab_comparison.py", "lab_campaign.py", "lab-campaign.py",
        "lab_cake_campaign.py", "lab_cake.py", "lab_active.py", "lab_queue.py", "lab-guard.py", "lab-series.py"))
    return {"kernel": platform.release(), "python_version": platform.python_version(),
            "executable": str(Path(sys.executable).resolve()), "tools": tools,
            "sha256": {str(p): digest(p) for p in sorted(set(paths))}}


class Control:
    def __init__(self):
        self.interruption = 0

    def interrupted(self, signum, _frame):
        self.interruption = self.interruption or 128 + signum

    def check(self):
        if self.interruption:
            raise campaign.guards.Interrupted(self.interruption)


@contextmanager
def stderr_file(path):
    # The campaign's Go helpers inherit fd 2. Preserve their diagnostics per arm.
    with campaign.exclusive(path) as stream:
        sys.stderr.flush()
        previous = os.dup(2)
        try:
            os.dup2(stream.fileno(), 2)
            yield
        finally:
            sys.stderr.flush()
            os.dup2(previous, 2)
            os.close(previous)


def operation(engine, namespaces, tc, sysctl, ping, binaries, folder):
    execute = campaign.run if engine == "tbf" else model.cake_model.run
    return execute(namespaces, tc, sysctl, ping, binaries, folder)


def run(namespaces, tc, sysctl, ping, binaries, artifacts, *, execute=operation,
        snapshot=fingerprint, validator=model.summarize, clock=time.monotonic, pause=time.sleep):
    model.require(artifacts.is_dir() and not any(artifacts.iterdir()), "Dossier comparatif existant et vide requis.")
    tools = {"ip": namespaces.ip, "tc": tc, "sysctl": sysctl, "ping": ping, "python3": sys.executable}
    environment = snapshot(binaries, tools)
    save(artifacts / "environment.json", environment)
    control = Control()
    previous = {s: signal.signal(s, control.interrupted) for s in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM)}
    session = {"schema_version": 1, "kind": "lab_comparison_session", "state": "failed",
               "protocol": "cake_comparison_v1", "technical_valid": False,
               "started_at": datetime.now(timezone.utc).isoformat(), "binaries": str(binaries),
               "environment_sha256": digest(artifacts / "environment.json"), "arms": []}
    start, last_cleanup = clock(), None
    try:
        with campaign.exclusive(artifacts / "progress.jsonl") as stream:
            ledger = campaign.Ledger(stream)
            ledger.write({"event": "begin", "order": model.ORDER})
            summaries = []
            for index, (block, engine) in enumerate(model.ORDER, 1):
                control.check()
                if last_cleanup is not None:
                    while True:
                        remaining = 2 - (clock() - last_cleanup)
                        if remaining <= 0:
                            break
                        control.check()
                        pause(min(0.05, remaining))
                control.check()
                model.require(snapshot(binaries, tools) == environment, "Environnement ou entrées modifiés entre campagnes.")
                folder = artifacts / f"{index:02d}-block-{block}-{engine}"
                folder.mkdir(mode=0o755)
                arm = {"index": index, "block": block, "engine": engine, "directory": folder.name,
                       "started_elapsed_ms": (clock() - start) * 1000,
                       "after_previous_cleanup_ms": None if last_cleanup is None else (clock() - last_cleanup) * 1000}
                session["arms"].append(arm)
                ledger.write({"event": "campaign_begin", **arm})
                # Never kill the guard to enforce an outer duration. Each guard
                # owns its 180s deadline and its independent 10s cleanup budget.
                with stderr_file(folder / "campaign.log"):
                    try:
                        report = execute(engine, namespaces, tc, sysctl, ping, binaries, folder)
                    except BaseException as error:
                        print(str(error), file=sys.stderr, flush=True)
                        code = error.code if isinstance(error, campaign.guards.Interrupted) else 1
                        with campaign.exclusive(folder / "campaign.exit") as output:
                            output.write(str(code) + "\n")
                        raise
                last_cleanup = clock()
                arm["cleanup_returned_elapsed_ms"] = (last_cleanup - start) * 1000
                save(folder / "campaign.json", report)
                code = 1 if report["decision"]["technical_valid"] is not True else 0
                with campaign.exclusive(folder / "campaign.exit") as output:
                    output.write(str(code) + "\n")
                arm["report_sha256"] = digest(folder / "campaign.json")
                model.require(code == 0, "Collecte non exploitable ; arrêt des campagnes suivantes.")
                model.require(snapshot(binaries, tools) == environment, "Environnement ou entrées modifiés pendant une campagne.")
                summary = validator(report, engine, folder, binaries)
                summary["block"] = block
                summaries.append(summary)
                # Detect accidental reuse before creating another topology.
                names = [n for a in summaries for n in a["namespaces"]]
                model.require(len(names) == len(set(names)), "Espaces réutilisés entre campagnes.")
                ledger.write({"event": "campaign_complete", **arm})
                print(f"Campagne {index}/6 ({engine}, bloc {block}) : collecte vérifiée.", file=sys.stderr, flush=True)
            control.check()
            result = model.assess(summaries)
            save(artifacts / "comparison.json", result)
            session.update(state="complete", technical_valid=True, decision=result["decision"],
                           comparison_sha256=digest(artifacts / "comparison.json"))
            ledger.write({"event": "complete", "decision": result["decision"]})
            return result
    except BaseException as error:
        session["error"] = str(error)
        session["decision"] = "non_exploitable"
        raise
    finally:
        try:
            session["finished_at"] = datetime.now(timezone.utc).isoformat()
            save(artifacts / "session.json", session)
        finally:
            for signum, handler in previous.items():
                signal.signal(signum, handler)


def analyze(artifacts, *, validator=model.summarize):
    session = model.document(model.read(artifacts / "session.json"))
    model.require(session["schema_version"] == 1 and session["kind"] == "lab_comparison_session"
                  and session["protocol"] == "cake_comparison_v1" and session["state"] == "complete"
                  and session["technical_valid"] is True, "Session incomplète ou non exploitable.")
    model.require(digest(artifacts / "environment.json") == session["environment_sha256"], "Provenance modifiée.")
    environment = model.document(model.read(artifacts / "environment.json"))
    binaries = Path(session["binaries"])
    for name in ("coopace", "coopace-lab-tcp", "coopace-lab-load"):
        path = binaries / name
        model.require(digest(path) == environment["sha256"][str(path)], "Binaire de collecte modifié.")
    arms = session["arms"]
    model.require([(a["block"], a["engine"]) for a in arms] == list(model.ORDER), "Ordre des six campagnes incompatible.")
    summaries = []
    for index, arm in enumerate(arms, 1):
        expected = f"{index:02d}-block-{arm['block']}-{arm['engine']}"
        model.require(arm["index"] == index and arm["directory"] == expected, "Emplacement de campagne incompatible.")
        if index > 1:
            gap = arm["started_elapsed_ms"] - arms[index - 2]["cleanup_returned_elapsed_ms"]
            model.require(gap >= 2000 and arm["after_previous_cleanup_ms"] >= 2000, "Pause entre campagnes non conforme.")
        folder = artifacts / expected
        model.require(digest(folder / "campaign.json") == arm["report_sha256"] and
                      model.read(folder / "campaign.exit") == b"0\n", "Rapport ou code de campagne modifié.")
        summary = validator(model.document(model.read(folder / "campaign.json")), arm["engine"], folder, binaries)
        summary["block"] = arm["block"]
        summaries.append(summary)
    result = model.assess(summaries)
    model.require(digest(artifacts / "comparison.json") == session["comparison_sha256"] and
                  model.document(model.read(artifacts / "comparison.json")) == result, "Bilan non reproduit.")
    return result
