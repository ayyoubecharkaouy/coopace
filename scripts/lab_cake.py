"""Validate one static CAKE on a fresh DOWN veth owned by the lab guard."""

from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import re
import time


spec = importlib.util.spec_from_file_location("cake_queue_tools", Path(__file__).with_name("lab_queue.py"))
queue = importlib.util.module_from_spec(spec)
spec.loader.exec_module(queue)
Error = queue.QueueError
PROFILE = "iproute2-6.1.0"
MEMORY_LIMIT = 1_048_576
RTT_US = 100_000
ARGUMENTS = ("cake", "bandwidth", "4mbit", "besteffort", "flows", "nonat", "nowash", "raw",
             "mpu", "0", "rtt", "100ms", "split-gso", "no-ack-filter", "egress",
             "memlimit", str(MEMORY_LIMIT), "fwmark", "0")
TIN_FIELDS = ("threshold_rate", "sent_bytes", "backlog_bytes", "target_us", "interval_us",
              "peak_delay_us", "avg_delay_us", "base_delay_us", "sent_packets",
              "way_indirect_hits", "way_misses", "way_collisions", "drops", "ecn_mark",
              "ack_drops", "sparse_flows", "bulk_flows", "unresponsive_flows",
              "max_pkt_len", "flow_quantum")


def producer(raw):
    if len(raw) > 512:
        raise Error("Bannière tc trop volumineuse.")
    try:
        text = raw.decode("ascii").strip()
    except UnicodeError as error:
        raise Error("Bannière tc illisible.") from error
    if not re.fullmatch(r"tc utility, iproute2-6\.1\.0(?:, [^\r\n]+)?", text):
        raise Error("Profil JSON tc non pris en charge ; iproute2-6.1.0 requis pour ce contrôle CAKE.")
    return {"profile": PROFILE, "version_output": raw.decode("ascii")}


def configured_qdisc(raw, profile):
    if profile != PROFILE:
        raise Error("Profil de producteur CAKE inconnu.")
    rows = queue.document(raw)
    if len(rows) != 1:
        raise Error("Une seule racine CAKE est requise.")
    row = rows[0]
    if (row.get("kind") != "cake" or row.get("root") is not True or row.get("handle") != "10:"
            or row.get("dev", "wan") != "wan" or "parent" in row):
        raise Error("Racine, identifiant ou interface CAKE non conforme.")
    options = row.get("options")
    if not isinstance(options, dict):
        raise Error("Options CAKE absentes.")
    expected = {"bandwidth": queue.RATE, "rtt": RTT_US, "memlimit": MEMORY_LIMIT,
                "diffserv": "besteffort", "flowmode": "flows", "nat": False, "wash": False,
                "ingress": False, "ack-filter": "disabled", "split_gso": True, "raw": True,
                "overhead": 0, "fwmark": "0"}
    for key, value in expected.items():
        if type(options.get(key)) is not type(value) or options[key] != value:
            raise Error(f"Option CAKE {key} absente ou non conforme.")
    # These are the documented omissions of this specific q_cake.c producer,
    # not defaults for missing measurements. Preserve their justification.
    omissions = {}
    if "autorate" in options:
        raise Error("Mode autorate CAKE inattendu.")
    omissions["autorate"] = "iproute2_6_1_0_omits_disabled_autorate"
    if "mpu" in options:
        if type(options["mpu"]) is not int or options["mpu"] != 0:
            raise Error("MPU CAKE non conforme.")
    else:
        omissions["mpu"] = "iproute2_6_1_0_omits_zero_mpu"
    if "atm" in options:
        if options["atm"] != "noatm":
            raise Error("Compensation ATM/PTM CAKE inattendue.")
    else:
        omissions["atm"] = "iproute2_6_1_0_omits_noatm_when_raw"
    return {"profile": profile, "effective": {**expected, "mpu": 0, "atm": "noatm", "autorate": False},
            "omitted_fields": omissions}


def unsigned(value, field):
    if type(value) is not int or not 0 <= value <= 2**64 - 1:
        raise Error(f"Statistique CAKE {field} absente ou invalide.")
    return value


def statistics(raw, profile):
    configured_qdisc(raw, profile)
    row = queue.document(raw)[0]
    for key in (*queue.COUNTERS, "backlog", "qlen", "memory_used", "memory_limit"):
        unsigned(row.get(key), key)
    if row["memory_limit"] != MEMORY_LIMIT:
        raise Error("Limite mémoire effective CAKE non conforme.")
    tins = row.get("tins")
    if not isinstance(tins, list) or len(tins) != 1 or not isinstance(tins[0], dict):
        raise Error("Une seule classe de statistiques CAKE est requise.")
    fields = {}
    for key in TIN_FIELDS:
        present = key in tins[0]
        fields[key] = {"available": present,
                       "value": unsigned(tins[0][key], "tins[0]." + key) if present else None,
                       "reason": None if present else "not_reported"}
    return {"counters": {key: row[key] for key in queue.COUNTERS},
            "backlog_bytes": row["backlog"], "queued_packets": row["qlen"],
            "cake": {"memory_used_reported_bytes": row["memory_used"],
                     "memory_limit_bytes": row["memory_limit"], "tin_count": 1, "tin_fields": fields}}


class CakeCheck(queue.QueueCheck):
    def __init__(self, namespaces, tc):
        super().__init__(namespaces, tc, collect_statistics=True)
        self.producer = None

    def read(self, include_statistics=False):
        flags = ["-j", "-s", "-r"] if include_statistics else ["-j", "-r"]
        started = time.monotonic_ns()
        raw = self.execute([self.namespaces.ip, "netns", "exec", self.gateway,
                            self.tc, *flags, "qdisc", "show", "dev", "wan"])
        finished = time.monotonic_ns()
        result = {"collected_at": datetime.now(timezone.utc).isoformat(), "qdiscs": queue.document(raw)}
        if include_statistics:
            result["configuration"] = configured_qdisc(raw, self.producer["profile"])
            result["statistics"] = statistics(raw, self.producer["profile"])
            result["elapsed_since_start_ms"] = (finished - self.statistics_started_ns) / 1_000_000
            result["read_duration_ms"] = (finished - started) / 1_000_000
        return result

    def prepare(self, owner):
        self.owner = owner
        # The version probe is bounded and tracked like other fixed commands;
        # the guard already owns the namespaces if identification fails.
        self.producer = {**producer(self.execute([self.tc, "-V"])), "tc_path": self.tc}
        self.prepare_link(owner)
        self.report = {"namespace": self.gateway, "interface": "wan", "link_state": "DOWN",
                       "kind": "cake", "handle": "10:", "producer": self.producer,
                       "requested_rate_bits_per_second": 4_000_000, "requested_rtt_us": RTT_US,
                       "requested_memory_limit_bytes": MEMORY_LIMIT, "arguments": list(ARGUMENTS),
                       "before": self.read()}
        queue.initial_qdisc(json.dumps(self.report["before"]["qdiscs"]).encode())
        owner.queue_report = self.report
        owner.journal("queue_creating")
        self.execute([self.namespaces.ip, "netns", "exec", self.gateway, self.tc,
                      "qdisc", "add", "dev", "wan", "root", "handle", "10:", *ARGUMENTS])
        self.verify("after_add")

    def verify(self, label):
        reading = self.read(True)
        self.report[label] = reading
        if label == "after_driver_exit":
            self.report["statistics_delta"] = queue.statistics_delta(
                self.report["after_add"]["statistics"], reading["statistics"])
        self.owner.journal("queue_verified")


def plan():
    return ("Contrôle CAKE : trois espaces neufs possédés par le superviseur indépendant.\n"
            "Profil JSON identifié iproute2-6.1.0 ; veth wan/eth0 laissé DOWN, sans adresse ni route.\n"
            "CAKE 10: à 4mbit, besteffort/flows, raw, RTT 100ms, mémoire 1048576 octets.\n"
            "Relire options, classe et compteurs après ajout puis après fin du pilote.\n"
            "check : fin normale ; check-crash : SIGKILL du pilote et récupération de son descendant.\n"
            "Nettoyage avant publication ; aucun trafic de mesure ni changement du réseau physique.\n"
            "Le mode plan ne crée aucune ressource et n'exige aucun privilège.")
