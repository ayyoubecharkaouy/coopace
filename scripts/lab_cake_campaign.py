"""Three CAKE idle/loaded pairs; no cross-engine comparison or benefit claim."""

from decimal import Decimal
import importlib.util
from pathlib import Path


spec = importlib.util.spec_from_file_location("cake_campaign_shared", Path(__file__).with_name("lab_campaign.py"))
campaign = importlib.util.module_from_spec(spec)
spec.loader.exec_module(campaign)
cake = campaign.active.sibling("cake_campaign_scheduler", "lab_cake.py")


class Topology(campaign.Passage, cake.CakeCheck):
    def __init__(self, namespaces, tc, sysctl, record):
        super().__init__(namespaces, tc)
        self.sysctl, self.record = sysctl, record

    def prepare(self, owner):
        super().prepare(owner)
        campaign.active.activate(self, owner, self.sysctl)

    def read(self, include_statistics=False):
        reading = super().read(include_statistics)
        self.record({"event": "qdisc", "include_statistics": include_statistics,
                     "driver_pid": self.owner.child.pid if self.owner.child is not None else None,
                     "reading": reading})
        return reading


def assess(phases, total_delta, crash):
    decision = {"technical_valid": None, "load_scenario": "not_assessed",
                "congestion": "not_assessed", "comparison": "not_assessed", "pairs": []}
    if crash:
        return decision
    technical = ([(p["pair"], p["condition"]) for p in phases] == campaign.PHASES
                 and total_delta["available"])
    for index in range(1, 4):
        members = {p["condition"]: p for p in phases if p["pair"] == index}
        if set(members) != {"idle", "loaded"}:
            technical = False
            continue
        loaded, idle = members["loaded"], members["idle"]
        flow, latency = loaded["result"], loaded["result"]["latency"]
        settle = (campaign.processes.timestamp_ns(latency["started_at"]) -
                  campaign.processes.timestamp_ns(flow["send"]["first_write_at"])) / 1_000_000
        technical = (technical and flow["probe_window_inside_application_writes"] and settle >= 1000
                     and all(p["statistics_delta"]["available"] for p in members.values()))
        start, end = (campaign.processes.timestamp_ns(latency[key]) for key in ("started_at", "finished_at"))
        window = [s for s in loaded["samples"] if start <= campaign.timestamp(s["collected_at"]) <= end]
        progress = (campaign.delta(window) if len(window) >= 2 else
                    {"available": False, "reason": "insufficient_samples", "counters": None})
        technical = technical and progress["available"]
        rate = flow["receive"]["average_bytes_per_second"]
        idle_dist, loaded_dist = idle["result"]["latency"].get("connect_ms"), latency.get("connect_ms")
        difference = (Decimal(str(loaded_dist["p50"])) - Decimal(str(idle_dist["p50"]))) if idle_dist and loaded_dist else None
        decision["pairs"].append({"pair": index, "settle_ms": settle, "probe_window_samples": len(window),
            "probe_window_statistics_delta": progress,
            "bytes_progress_during_probes": bool(progress["available"] and progress["counters"]["bytes"] > 0),
            "received_bytes_per_second": rate, "receive_rate_in_range": 350000 <= rate <= 525000,
            "p50_loaded_minus_idle_ms": float(difference) if difference is not None else None})
    qualified = (technical and len(decision["pairs"]) == 3 and
                 all(p["bytes_progress_during_probes"] and p["receive_rate_in_range"] for p in decision["pairs"]))
    decision.update(technical_valid=bool(technical), load_scenario=("qualified" if qualified else
                    "not_qualified" if technical else "non_exploitable"))
    return decision


def run(namespaces, tc, sysctl, ping, binaries, artifacts, **options):
    return campaign.run(namespaces, tc, sysctl, ping, binaries, artifacts,
                        topology_factory=Topology, assessment=assess, kind="lab_cake_campaign", **options)


def plan():
    return ("Trois paires CAKE 4mbit : idle/loaded, loaded/idle, idle/loaded ; trois espaces neufs.\n"
            "Même configuration statique que le contrôle CAKE actif ; profil iproute2-6.1.0.\n"
            "Contrôles ICMP sans/avec forwarding ; dix sondes TCP par phase (1s, pause 250ms).\n"
            "Trois transferts de 8 Mio, réception JSON, stabilisation >=1s, file vide entre phases.\n"
            "Statistiques et options CAKE conservées ; progression des octets pendant les sondes.\n"
            "Qualification de charge séparée : débit reçu entre 350000 et 525000 octets/s.\n"
            "Aucun backlog durable exigé ; aucune comparaison TBF/CAKE dans cette campagne.\n"
            "Pilote 150s, superviseur 180s, nettoyage 10s ; check-crash après première écriture loaded.\n"
            "Le mode plan ne crée aucune ressource et n'exige aucun privilège.")
