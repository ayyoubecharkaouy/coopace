"""TBF configuration check on a fresh, DOWN veth owned by the lab guard."""

from datetime import datetime, timezone
import json
import math
import os
import subprocess
import time


LIMIT = 64 * 1024
RATE = 500_000  # tc JSON reports bytes/s; requested 4mbit is 4,000,000 bits/s.
BURST = 65_536
QUEUE_LIMIT = 131_072
COUNTERS = ("bytes", "packets", "drops", "overlimits", "requeues")


class QueueError(Exception):
    pass


def document(raw):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise QueueError(f"Champ JSON dupliqué : {key}.")
            value[key] = item
        return value

    def invalid(_value):
        raise QueueError("Nombre JSON non fini.")

    def finite(value):
        result = float(value)
        if not math.isfinite(result):
            raise QueueError("Nombre JSON non fini.")
        return result

    if len(raw) > LIMIT:
        raise QueueError("Réponse réseau trop volumineuse.")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                           parse_constant=invalid, parse_float=finite)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise QueueError("Réponse JSON réseau illisible.") from error
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise QueueError("Liste JSON d'objets réseau requise.")
    return value


def run_command(args, owner):
    """Bound stdout and time; these fixed ip/tc commands do not spawn helpers."""
    owner.check()
    deadline = min(owner.deadline, time.monotonic() + 2)
    child = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE)
    owner.command_child = child
    output = bytearray()
    try:
        os.set_blocking(child.stdout.fileno(), False)
        eof = False
        while True:
            owner.check()
            if time.monotonic() >= deadline:
                raise QueueError("Délai de commande ip/tc dépassé.")
            if not eof:
                try:
                    data = os.read(child.stdout.fileno(), 8192)
                    if not data:
                        eof = True
                    output.extend(data)
                except BlockingIOError:
                    pass
            if len(output) > LIMIT:
                raise QueueError("Réponse réseau trop volumineuse.")
            code = child.poll()
            if code is not None and eof:
                if code != 0:
                    raise QueueError(f"Commande ip/tc échouée (code {code}).")
                return bytes(output)
            time.sleep(0.005)
    finally:
        try:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=1)
            owner.command_child = None
        finally:
            child.stdout.close()


def initial_qdisc(raw):
    rows = document(raw)
    # A fresh DOWN veth can still use the kernel's invisible noop scheduler;
    # noqueue normally appears after activation. The caller verifies creation
    # and DOWN state before this read, so an empty successful dump is expected.
    if not rows:
        return rows
    if len(rows) != 1:
        raise QueueError("État initial vide ou unique file noqueue attendu.")
    row = rows[0]
    if (row.get("kind") != "noqueue" or row.get("handle") != "0:"
            or row.get("root") is not True or "parent" in row
            or row.get("dev", "wan") != "wan"):
        raise QueueError("File initiale inattendue ; aucun remplacement.")
    return rows


def configured_qdisc(raw):
    rows = document(raw)
    if len(rows) != 1:
        raise QueueError("Une seule file TBF racine est attendue.")
    row = rows[0]
    if (row.get("kind") != "tbf" or row.get("handle") != "10:"
            or row.get("root") is not True or "parent" in row
            or row.get("dev", "wan") != "wan"):
        raise QueueError("Type, interface ou identifiant TBF non conforme.")
    options = row.get("options")
    if not isinstance(options, dict):
        raise QueueError("Options TBF absentes.")
    for key, expected in (("rate", RATE), ("limit", QUEUE_LIMIT)):
        if type(options.get(key)) is not int or options[key] != expected:
            raise QueueError(f"Paramètre TBF {key} non conforme.")
    burst = options.get("burst")
    # tc reconstructs burst from kernel timing ticks. Preserve the effective
    # value; allow at most one byte of representation/quantization difference.
    if type(burst) not in (int, float) or not BURST - 1 <= burst <= BURST + 1:
        raise QueueError("Paramètre TBF burst non conforme.")
    for key in ("overhead", "mpu"):
        if key in options and (type(options[key]) is not int or options[key] != 0):
            raise QueueError("Compensation TBF inattendue.")
    if options.get("linklayer", "ethernet") != "ethernet":
        raise QueueError("Type de liaison TBF inattendu.")
    return rows


def statistics(raw):
    row = configured_qdisc(raw)[0]
    for field in (*COUNTERS, "backlog", "qlen"):
        value = row.get(field)
        if type(value) is not int or not 0 <= value <= 2**64 - 1:
            raise QueueError(f"Statistique TBF {field} absente ou invalide.")
    return {"counters": {field: row[field] for field in COUNTERS},
            "backlog_bytes": row["backlog"], "queued_packets": row["qlen"]}


def statistics_delta(before, after):
    # Called only for two validated readings of the same owned TBF, with no
    # replacement between them. A decreasing counter invalidates the window;
    # backlog/qlen are instantaneous gauges and may decrease normally.
    if any(after["counters"][field] < before["counters"][field] for field in COUNTERS):
        return {"available": False, "reason": "counter_decreased", "counters": None}
    return {"available": True, "reason": None,
            "counters": {field: after["counters"][field] - before["counters"][field]
                         for field in COUNTERS}}


class QueueCheck:
    def __init__(self, namespaces, tc, collect_statistics=False):
        self.namespaces, self.tc = namespaces, tc
        self.owner = None
        self.gateway = None
        self.server = None
        self.collect_statistics = collect_statistics
        self.statistics_started_ns = None

    def execute(self, args):
        self.owner.check()
        # Validate ownership again before each namespace-targeted operation.
        for name, expected in self.owner.owned:
            if expected is None or self.namespaces.identity(name) != expected:
                raise QueueError(f"Possession de {name} non confirmée.")
        value = self.namespaces.execute(args, self.owner)
        self.owner.check()
        return value

    def read(self, include_statistics=False):
        # -r is intentional: TBF omits limit without raw output. Avoid -d,
        # which turns burst into a formatted size/cell string on some versions.
        flags = ["-j", "-s", "-r"] if include_statistics else ["-j", "-r"]
        started_ns = time.monotonic_ns()
        raw = self.execute([self.namespaces.ip, "netns", "exec", self.gateway,
                            self.tc, *flags, "qdisc", "show", "dev", "wan"])
        finished_ns = time.monotonic_ns()
        result = {"collected_at": datetime.now(timezone.utc).isoformat(),
                  "qdiscs": document(raw)}
        if include_statistics:
            result["statistics"] = statistics(raw)
            result["elapsed_since_start_ms"] = (finished_ns - self.statistics_started_ns) / 1_000_000
            result["read_duration_ms"] = (finished_ns - started_ns) / 1_000_000
        return result

    def links(self, namespace):
        return document(self.execute([self.namespaces.ip, "-n", namespace,
                                      "-j", "link", "show"]))

    def prepare(self, owner):
        self.owner = owner
        self.statistics_started_ns = time.monotonic_ns()
        self.gateway, self.server = owner.owned[1][0], owner.owned[2][0]
        for namespace in (self.gateway, self.server):
            rows = self.links(namespace)
            if len(rows) != 1 or rows[0].get("ifname") != "lo":
                raise QueueError("Un espace neuf avec seulement lo est requis.")
        self.execute([self.namespaces.ip, "-n", self.gateway, "link", "add", "wan",
                      "type", "veth", "peer", "name", "eth0", "netns", self.server])
        # Leave both ends DOWN: no IPv4/IPv6 address, forwarding or probe.
        for namespace, interface in ((self.gateway, "wan"), (self.server, "eth0")):
            rows = self.links(namespace)
            names = [row.get("ifname") for row in rows]
            if len(rows) != 2 or not all(isinstance(name, str) for name in names) or set(names) != {"lo", interface}:
                raise QueueError("Extrémités veth non confirmées.")
            row = next(row for row in rows if row["ifname"] == interface)
            flags = row.get("flags")
            if not isinstance(flags, list) or not all(isinstance(flag, str) for flag in flags) or "UP" in flags:
                raise QueueError("Le lien de contrôle doit rester désactivé.")
        self.report = {"namespace": self.gateway, "interface": "wan", "link_state": "DOWN",
                       "kind": "tbf", "handle": "10:", "requested_rate_bits_per_second": 4_000_000,
                       "requested_burst_bytes": BURST, "requested_limit_bytes": QUEUE_LIMIT}
        self.report["before"] = self.read()
        initial_qdisc(json.dumps(self.report["before"]["qdiscs"]).encode())
        owner.queue_report = self.report
        owner.journal("queue_creating")
        self.execute([self.namespaces.ip, "netns", "exec", self.gateway,
                      self.tc, "qdisc", "add", "dev", "wan", "root", "handle", "10:",
                      "tbf", "rate", "4mbit", "burst", str(BURST), "limit", str(QUEUE_LIMIT)])
        self.verify("after_add")

    def verify(self, label):
        reading = self.read(self.collect_statistics)
        configured_qdisc(json.dumps(reading["qdiscs"]).encode())
        self.report[label] = reading
        if self.collect_statistics and label == "after_driver_exit":
            self.report["statistics_delta"] = statistics_delta(
                self.report["after_add"]["statistics"], reading["statistics"])
        self.owner.journal("queue_verified")


def plan():
    return ("Contrôle de file prévu : trois espaces neufs possédés par le superviseur.\n"
            "Un lien veth wan -> eth0 du serveur, laissé DOWN, sans adresse ni route.\n"
            "Lire l'état initial vide ou noqueue, ajouter TBF 10: à 4mbit, burst 65536, limit 131072.\n"
            "check-queue : fin normale ; check-queue-crash : SIGKILL du pilote.\n"
            "check-queue-stats / check-queue-stats-crash ajoutent deux lectures de statistiques et leurs différences.\n"
            "Relire TBF après fin du pilote, récupérer les processus, puis supprimer les espaces.\n"
            "Aucun trafic de mesure ; aucune modification du réseau physique.\n"
            "Le mode plan-queue ne crée aucune ressource et n'exige aucun privilège.")
