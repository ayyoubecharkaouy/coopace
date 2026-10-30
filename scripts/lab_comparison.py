"""Offline validation and frozen v1 decisions for six TBF/CAKE campaigns."""

from decimal import Decimal
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import time


spec = importlib.util.spec_from_file_location("comparison_cake", Path(__file__).with_name("lab_cake_campaign.py"))
cake_model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cake_model)
campaign, cake = cake_model.campaign, cake_model.cake
Error = campaign.Error
ORDER = ((1, "tbf"), (1, "cake"), (2, "cake"), (2, "tbf"), (3, "tbf"), (3, "cake"))


def require(condition, message):
    if not condition:
        raise Error(message)


def read(path, limit=8 * 1024 * 1024):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as stream:
        raw = stream.read(limit + 1)
    require(len(raw) <= limit, "Pièce comparative trop volumineuse.")
    return raw


def document(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "Champ JSON comparatif dupliqué.")
            result[key] = value
        return result
    def invalid(_value):
        raise Error("Nombre JSON comparatif non fini.")
    def finite(value):
        result = float(value)
        require(math.isfinite(result), "Nombre JSON comparatif non fini.")
        return result
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                           parse_constant=invalid, parse_float=finite)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise Error("Document comparatif illisible.") from error
    require(isinstance(value, dict), "Objet JSON comparatif requis.")
    return value


class Offline:
    def __init__(self):
        self.deadline, self.command_child = time.monotonic() + 3, None

    def check(self):
        require(time.monotonic() < self.deadline, "Comparaison hors ligne trop longue.")


def compare(binaries, folder, pair):
    return campaign.queue.run_command([str(binaries / "coopace"), "latency", "compare",
        "--idle", str(folder / f"phase-{pair}-idle.json"),
        "--loaded", str(folder / f"phase-{pair}-loaded.json")], Offline(), timeout=2).decode("utf-8")


def summarize(report, engine, folder, binaries, comparator=compare):
    """Validate original measurements/evidence, rather than trust decision flags."""
    require(engine in ("tbf", "cake"), "Moteur comparatif inconnu.")
    expected_kind = "lab_bottleneck_campaign" if engine == "tbf" else "lab_cake_campaign"
    require(type(report["schema_version"]) is int and report["schema_version"] == 1
            and report["kind"] == expected_kind and report["mode"] == "run",
            "Campagne comparative incompatible.")
    require(report["cleanup_verified"] is True and type(report["driver_exit_code"]) is int and report["driver_exit_code"] == 0
            and type(report["reaped_descendants"]) is int and report["reaped_descendants"] == 0 and report["interrupted_phase"] is None
            and report["traffic_coverage"] == "synthetic_ipv4_only", "Campagne ou nettoyage non confirmé.")
    token = Path(report["workspace"]).name.removeprefix("coopace-guard.")
    require(re.fullmatch(r"[a-z0-9_]{8}", token) and
            report["namespaces"] == [f"cg-{token}-{role}" for role in ("c", "g", "s")], "Identités des espaces invalides.")
    require(report["workspace"] == f"/tmp/coopace-guard.{token}", "Réservation comparative incompatible.")
    require(report["evidence"] == str(folder / "progress.jsonl"), "Preuves hors de cette campagne.")
    entries = [document(line) for line in read(folder / "progress.jsonl").splitlines()]
    require(entries and entries[0]["event"] == "owned" and entries[-1]["event"] == "cleaned"
            and entries[0]["namespaces"] == report["namespaces"] and entries[0]["workspace"] == report["workspace"]
            and entries[-1]["decision"] == report["decision"], "Journal de possession/nettoyage incohérent.")
    passage = report["passage"]
    require(passage["without_forwarding_exit_code"] == 1 and passage["with_forwarding_exit_code"] == 0
            and re.search(r"\b[1-9][0-9]* packets transmitted,\s*0 (?:packets )?received", passage["without_forwarding_stdout"])
            and re.search(r"\b3 packets transmitted,\s*3 (?:packets )?received", passage["with_forwarding_stdout"]),
            "Contrôles de passage non conformes.")
    evidence_passage = [e for e in entries if e["event"] == "passage"]
    require(len(evidence_passage) == 1 and all(evidence_passage[0][k] == v for k, v in passage.items()),
            "Contrôles de passage absents du journal.")
    topology, phases = report["queue"], report["phases"]
    require(topology["kind"] == engine and topology["namespace"] == report["namespaces"][1]
            and topology["interface"] == "wan" and topology["link_state"] == "UP", "Topologie comparative incompatible.")
    campaign.queue.initial_qdisc(json.dumps(topology["before"]["qdiscs"]).encode())
    if engine == "cake":
        require(topology["arguments"] == list(cake.ARGUMENTS) and
                cake.producer(topology["producer"]["version_output"].encode())["profile"] == cake.PROFILE,
                "Configuration/producteur CAKE incompatible.")
    require([(p["pair"], p["condition"]) for p in phases] == campaign.PHASES, "Six phases ordonnées requises.")
    samples = [s for p in phases for s in p["samples"]]
    readings = [topology[k] for k in ("after_add", "after_activation", "after_passage")] + samples + [topology["after_driver_exit"]]
    for reading in readings:
        raw = json.dumps(reading["qdiscs"]).encode()
        if engine == "cake":
            require(cake.configured_qdisc(raw, cake.PROFILE) == reading["configuration"], "Options CAKE incohérentes.")
            normalized = cake.statistics(raw, cake.PROFILE)
        else:
            normalized = campaign.queue.statistics(raw)
        require(normalized == reading["statistics"], "Statistiques normalisées incohérentes.")
        require(0 <= reading["read_duration_ms"] < 2000, "Durée de relevé invalide.")
    require(all(a["elapsed_since_start_ms"] < b["elapsed_since_start_ms"] and
                campaign.timestamp(a["collected_at"]) < campaign.timestamp(b["collected_at"])
                for a, b in zip(readings, readings[1:])), "Chronologie des relevés incohérente.")
    total = campaign.delta(readings[2:])
    require(campaign.delta(readings)["available"] and total["available"] and total == report["statistics_delta"],
            "Compteurs interrompus ou différences incohérentes.")
    require(campaign.queue.statistics_delta(readings[0]["statistics"], readings[-1]["statistics"]) == topology["statistics_delta"],
            "Différence depuis ajout incohérente.")
    require([e["reading"] for e in entries if e["event"] == "statistics"] == samples, "Échantillons non conservés.")
    if engine == "cake":
        expected = [topology[k] for k in ("before", "after_add", "after_activation", "after_passage")]
        expected.extend({k: v for k, v in s.items() if k != "phase"} for s in samples)
        expected.append(topology["after_driver_exit"])
        require([e["reading"] for e in entries if e["event"] == "qdisc"] == expected, "Relectures CAKE non conservées.")
    result = {"engine": engine, "namespaces": report["namespaces"], "workspace": report["workspace"], "phases": []}
    provenance = set()
    for phase in phases:
        flow, condition = phase["result"], phase["condition"]
        latency = campaign.active.latency_document(flow["latency"], condition, flow["measurement_exit_code"])
        require(document(read(folder / f"phase-{phase['pair']}-{condition}.json", 256 * 1024)) == latency,
                "Rapport de phase incohérent.")
        provenance.add(tuple(latency[k] for k in ("os", "architecture", "go_version", "coopace_version")))
        require(campaign.delta(phase["samples"])["available"] and campaign.delta(phase["samples"]) == phase["statistics_delta"],
                "Différence de phase indisponible.")
        drain = [s for s in phase["samples"] if s["phase"] == "drain"]
        require(len(drain) >= 2 and all(s["statistics"]["backlog_bytes"] == s["statistics"]["queued_packets"] == 0 for s in drain)
                and 500 <= drain[-1]["elapsed_since_start_ms"] - drain[0]["elapsed_since_start_ms"] < 3000,
                "Vidage de phase non confirmé.")
        running = [s for s in phase["samples"] if s["phase"] == "running"]
        require(all(b["elapsed_since_start_ms"] - b["read_duration_ms"] - a["elapsed_since_start_ms"] >= 250
                    for a, b in zip(running, running[1:])), "Pause entre relevés trop courte.")
        row = {"pair": phase["pair"], "condition": condition, "failed": latency["failed"], "connect_ms": latency["connect_ms"]}
        if condition == "loaded":
            checked = campaign.active.flow_documents(*(json.dumps(flow[k]).encode() for k in ("send", "receive", "latency")),
                                                     flow["measurement_exit_code"])
            require(checked == flow and flow["probe_window_inside_application_writes"], "Contexte de charge invalide.")
            require(all(tuple(flow[k][field] for field in ("os", "architecture", "go_version")) ==
                        tuple(latency[field] for field in ("os", "architecture", "go_version")) for k in ("send", "receive")),
                    "Provenance du transfert incompatible avec les sondes.")
            settle = campaign.processes.timestamp_ns(latency["started_at"]) - campaign.processes.timestamp_ns(flow["send"]["first_write_at"])
            require(settle >= 1_000_000_000, "Stabilisation trop courte.")
            start, end = (campaign.processes.timestamp_ns(latency[k]) for k in ("started_at", "finished_at"))
            window = [s for s in phase["samples"] if start <= campaign.timestamp(s["collected_at"]) <= end]
            require(len(window) >= 2, "Relevés absents de la fenêtre loaded.")
            row.update(received_bytes_per_second=flow["receive"]["average_bytes_per_second"],
                       bytes_progress=campaign.delta(window)["counters"]["bytes"] > 0)
        result["phases"].append(row)
    require(len(provenance) == 1, "Provenance des mesures incompatible.")
    result["measurement_provenance"] = list(provenance.pop())
    for pair in (1, 2, 3):
        text = comparator(binaries, folder, pair)
        require(text.strip() and text == next(p["comparison"] for p in phases if p["pair"] == pair and "comparison" in p)
                and text == next(e["text"] for e in entries if e["event"] == "comparison" and e["pair"] == pair),
                "Comparaison stricte non reproduite.")
    decision = campaign.assess(phases, total, False) if engine == "tbf" else cake_model.assess(phases, total, False)
    require(decision == report["decision"] and decision["technical_valid"] is True, "Décision technique non reproduite.")
    result["reference_qualified"] = decision.get("congestion") == "observed" if engine == "tbf" else None
    return result


def decimal(value):
    return Decimal(str(value))


def assess(arms):
    """Input consists solely of the six previously validated summaries."""
    require([(a["block"], a["engine"]) for a in arms] == list(ORDER), "Six campagnes dans l'ordre fixé requises.")
    require(len({name for a in arms for name in a["namespaces"]}) == 18 and
            len({a["workspace"] for a in arms}) == 6, "Topologies réutilisées entre campagnes.")
    require(all(a["measurement_provenance"] == arms[0]["measurement_provenance"] for a in arms),
            "Environnement de mesure différent entre campagnes.")
    pairs, guards, blocks = [], [], []
    reference = all(a["reference_qualified"] for a in arms if a["engine"] == "tbf")
    load = all(p["bytes_progress"] and 350000 <= p["received_bytes_per_second"] <= 525000
               for a in arms for p in a["phases"] if p["condition"] == "loaded")
    for block in (1, 2, 3):
        engines = {a["engine"]: a for a in arms if a["block"] == block}
        satisfied = 0
        for pair in (1, 2, 3):
            members = {engine: {p["condition"]: p for p in a["phases"] if p["pair"] == pair}
                       for engine, a in engines.items()}
            t, c = members["tbf"], members["cake"]
            def p50(phase):
                return decimal(phase["connect_ms"]["p50"]) if phase["connect_ms"] is not None else None
            ti, tl, ci, cl = (p50(p) for p in (t["idle"], t["loaded"], c["idle"], c["loaded"]))
            dt = tl - ti if ti is not None and tl is not None else None
            dc = cl - ci if ci is not None and cl is not None else None
            tr, cr = (decimal(m["loaded"]["received_bytes_per_second"]) for m in (t, c))
            preserved = cr >= decimal("0.90") * tr
            idle_ok = ci is not None and ti is not None and ci <= ti + 2
            if not preserved:
                guards.append({"block": block, "pair": pair, "guard": "received_rate", "status": "regression",
                               "cake": float(cr), "tbf": float(tr), "minimum_ratio": 0.9})
            if not idle_ok:
                guards.append({"block": block, "pair": pair, "guard": "idle_p50",
                               "status": "unavailable" if ci is None or ti is None else "regression",
                               "cake_ms": float(ci) if ci is not None else None, "tbf_ms": float(ti) if ti is not None else None})
            for condition in ("idle", "loaded"):
                if c[condition]["failed"] > t[condition]["failed"]:
                    guards.append({"block": block, "pair": pair, "guard": "failed_connections", "condition": condition,
                                   "status": "regression", "cake": c[condition]["failed"], "tbf": t[condition]["failed"]})
            improved = dt is not None and dc is not None and dt >= 10 and dc <= dt * decimal("0.5") and dt - dc >= 10
            satisfied += int(improved)
            pairs.append({"block": block, "pair": pair, "tbf": t, "cake": c,
                "tbf_penalty_ms": float(dt) if dt is not None else None, "cake_penalty_ms": float(dc) if dc is not None else None,
                "penalty_difference_ms": float(dt - dc) if dt is not None and dc is not None else None,
                "received_rate_ratio": float(cr / tr), "received_rate_preserved": preserved,
                "idle_p50_preserved": idle_ok, "latency_improved": improved})
        blocks.append({"block": block, "improved_pairs": satisfied, "required_pairs": 2, "latency_improved": satisfied >= 2})
    decision = ("reference_unqualified" if not reference else "load_scenario_unqualified" if not load else
                "guard_failed" if guards else "static_cake_improvement_v1" if all(b["latency_improved"] for b in blocks)
                else "improvement_not_demonstrated")
    return {"schema_version": 1, "kind": "lab_static_cake_comparison", "protocol": "cake_comparison_v1",
            "technical_valid": True, "decision": decision, "reference_qualified": bool(reference),
            "load_scenario_qualified": bool(load), "guard_failures": guards, "blocks": blocks, "pairs": pairs,
            "traffic_coverage": "synthetic_ipv4_only", "coopace_gain_assessed": False}
