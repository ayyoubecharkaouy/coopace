"""Restore a fresh lab veth to its selected initial state before deleting it."""

from datetime import datetime, timezone
import os
from pathlib import Path
import signal
import time

import importlib.util
spec = importlib.util.spec_from_file_location("queue_recovery_runtime", Path(__file__).with_name("lab_recovery_runtime.py"))
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)
Error, require, guards, cake = runtime.Error, runtime.require, runtime.guards, runtime.cake


DISABLE_IPV6 = r"""from pathlib import Path
for name in ('all','default'):
    path=Path('/proc/sys/net/ipv6/conf')/name/'disable_ipv6'
    path.write_text('1\n')
    assert path.read_text().strip()=='1'
"""


def source_hashes():
    names = ("lab-queue-recovery.py", "lab_queue_recovery.py", "lab_recovery_runtime.py",
             "lab-guard.py", "lab_process_group.py", "lab_queue.py", "lab_cake.py")
    return {name:runtime.digest(runtime.read(Path(__file__).with_name(name))) for name in names}

ROOT_FIELDS = {"kind", "handle", "root", "dev", "refcnt", "options", "bytes", "packets",
    "drops", "overlimits", "requeues", "backlog", "qlen", "memory_used", "memory_limit",
    "capacity_estimate", "min_network_size", "max_network_size", "min_adj_size",
    "max_adj_size", "avg_hdr_offset", "tins"}
OPTION_FIELDS = {"bandwidth", "diffserv", "flowmode", "nat", "wash", "ingress", "ack-filter",
    "split_gso", "rtt", "raw", "overhead", "memlimit", "fwmark", "mpu", "atm"}


def owned_cake(raw):
    configuration = cake.configured_qdisc(raw, cake.PROFILE)
    row = cake.queue.document(raw)[0]
    require(set(row) <= ROOT_FIELDS and set(row["options"]) <= OPTION_FIELDS,
            "Champ CAKE non pris en charge ; retrait refusé.")
    cake.statistics(raw, cake.PROFILE)
    return configuration


class Engine:
    def __init__(self, owner, runner, evidence):
        self.owner, self.runner, self.evidence = owner, runner, evidence
        self.tools = runner.tools
        self.gateway = self.server = None
        self.retained = []
        self.original = None
        self.baseline = None
        self.add_attempted = False
        self.applied = False
        self.removed = False
        self.restored = False
        self.sources = None

    def retain(self):
        self.original = os.open("/proc/self/ns/net", os.O_RDONLY)
        try:
            original = runtime.network_namespace_identity(self.original)
            for name, expected in self.owner.owned:
                descriptor = os.open(self.owner.namespaces.directory / name, os.O_RDONLY | os.O_NOFOLLOW)
                self.retained.append((name, expected, descriptor))
                current = runtime.network_namespace_identity(descriptor)
                require(current == expected and expected != original,
                        "Namespace de laboratoire distinct et possédé requis.")
            self.binding()
            self.evidence.record("namespace_bindings_retained", origin_identity=list(original), namespaces=[
                {"name":name,"identity":list(identity)} for name, identity, _fd in self.retained])
        except BaseException:
            self.release()
            raise

    def binding(self):
        self.owner.check()
        require(self.original is not None and len(self.retained) == 3, "Descripteurs de namespaces absents.")
        original, current = runtime.network_namespace_identity(self.original), os.stat("/proc/self/ns/net")
        require(original == (current.st_dev, current.st_ino),
                "Le superviseur a changé d'espace réseau.")
        for name, expected, fd in self.retained:
            require(self.owner.namespaces.identity(name) == expected == runtime.network_namespace_identity(fd),
                    "Identité de namespace modifiée ; opération refusée.")

    def release(self):
        for _name, _expected, fd in self.retained:
            os.close(fd)
        self.retained.clear()
        if self.original is not None:
            os.close(self.original)
            self.original = None

    def call(self, tool, args, **options):
        self.binding()
        result = self.runner.run(self.owner, tool, args, **options)
        self.binding()
        return result

    def ip(self, namespace, args):
        return self.call("ip", ["-n", namespace, *args])[0]

    def tc(self, args):
        return self.call("ip", ["netns", "exec", self.gateway,
            self.tools.executable("tc"), *args], extra=("tc",))[0]

    def links(self, namespace):
        return cake.queue.document(self.ip(namespace, ["-j", "-d", "link", "show"]))

    def clean_endpoints(self, *, fresh=False):
        for namespace, interface in ((self.gateway, "wan"), (self.server, "eth0")):
            rows = self.links(namespace)
            expected = {"lo"} if fresh else {"lo", interface}
            require(len(rows) == len(expected) and {r.get("ifname") for r in rows} == expected,
                    "Interfaces étrangères au laboratoire.")
            if not fresh:
                row = next(row for row in rows if row["ifname"] == interface)
                require("UP" in row.get("flags", []) and row.get("linkinfo", {}).get("info_kind") == "veth",
                        "Veth actif possédé requis.")
            addresses = cake.queue.document(self.ip(namespace, ["-j", "address", "show"]))
            require(len(addresses) == len(expected) and {r.get("ifname") for r in addresses} == expected
                    and all(row.get("addr_info") == [] for row in addresses), "Adresse IP inattendue dans le laboratoire.")

    def setup(self):
        self.gateway, self.server = self.owner.owned[1][0], self.owner.owned[2][0]
        self.sources = source_hashes()
        self.retain()
        self.clean_endpoints(fresh=True)
        for namespace in (self.gateway, self.server):
            self.call("ip", ["netns", "exec", namespace, self.tools.executable("python"),
                "-I", "-c", DISABLE_IPV6], extra=("python",))
        self.ip(self.gateway, ["link", "add", "wan", "type", "veth", "peer", "name", "eth0", "netns", self.server])
        self.ip(self.server, ["link", "set", "dev", "eth0", "up"])
        self.ip(self.gateway, ["link", "set", "dev", "wan", "up"])
        self.clean_endpoints()
        self.baseline = self.capture("before.json")
        plan = self.evaluate("plan.json", ["restore-plan", "--snapshot", str(self.evidence.folder / "before.json"), "--json"])
        require(plan.get("decision") == "candidate_for_lab_validation" and plan.get("profile") == "noqueue-root-v1"
                and plan.get("before_sha256") == self.evidence.files["before.json"], "Référence noqueue non reconnue.")
        self.evidence.record("baseline_verified", sha256=self.evidence.files["before.json"])

    def capture(self, name):
        raw, _ = self.call("ip", ["netns", "exec", self.gateway, self.tools.executable("gateway"),
            "snapshot", "--interface", "wan", "--json"], extra=("gateway", "ip", "tc"), timeout=20)
        source = runtime.document(raw)
        require(source.get("kind") == "gateway_queue_snapshot" and source.get("mode") == "read_only"
                and source.get("partial") is False, "Capture de laboratoire partielle ou incompatible.")
        self.evidence.save(name, raw)
        # The public importer validates order, metadata, exact commands, times,
        # target identity and legacy-class evidence even for an installed CAKE.
        checked = self.evaluate(name + ".import.json", ["restore-plan", "--snapshot", str(self.evidence.folder / name), "--json"], allowed=(0, 3))
        require(checked.get("before_sha256") == self.evidence.files[name], "Empreinte de capture incohérente.")
        for reading in source["snapshot"]["readings"]:
            require(reading.get("path") == self.tools.specs[reading["tool"]]["path"], "Outil du snapshot inattendu.")
            if reading["section"] in ("classes", "filters_root", "filters_ingress", "filters_egress"):
                require(reading.get("available") is True and reading.get("value") == [], "Classe ou filtre inattendu.")
        if self.baseline is not None:
            require(source["snapshot"]["interface"] == self.baseline["snapshot"]["interface"],
                    "Identité ou état du veth modifié.")
        return source

    def evaluate(self, name, args, allowed=(0,)):
        raw, _code = self.call("gateway", args, allowed=allowed)
        result = runtime.document(raw)
        expected = "queue_recovery_plan" if args[0] == "restore-plan" else "queue_recovery_check"
        require(result.get("kind") == expected and result.get("schema_version") == 1
                and result.get("execution_authorized") is False and result.get("network_changes_executed") is False,
                "L'évaluateur doit rester en lecture seule.")
        self.evidence.save(name, raw)
        return result

    def current_root(self):
        return self.tc(["-j", "-s", "-r", "qdisc", "show", "dev", "wan"])

    def apply(self):
        require(self.baseline is not None and not self.add_attempted, "Installation unique après référence requise.")
        # A second complete observation catches changes since the saved baseline.
        self.capture("pre-add.json")
        checked = self.evaluate("pre-add-check.json", ["restore-check", "--before", str(self.evidence.folder / "before.json"),
            "--after", str(self.evidence.folder / "pre-add.json"), "--json"])
        require(checked.get("decision") == "selected_state_matches"
                and checked.get("before_sha256") == self.evidence.files["before.json"]
                and checked.get("after_sha256") == self.evidence.files["pre-add.json"], "État initial modifié avant installation.")
        require(source_hashes() == self.sources, "Sources modifiées avant installation.")
        self.evidence.record("add_intent", interface="wan", handle="10:", arguments=list(cake.ARGUMENTS))
        self.add_attempted = True
        self.tc(["qdisc", "add", "dev", "wan", "root", "handle", "10:", *cake.ARGUMENTS])
        owned_cake(self.current_root())
        self.capture("applied.json")
        self.applied = True
        self.evidence.record("owned_cake_verified", interface="wan", handle="10:")

    def verify_driver_namespace(self):
        helper = self.owner.descendant
        require(helper is not None and os.getpgid(helper) == self.owner.child.pid, "Groupe du descendant non confirmé.")
        expected = dict(self.owner.owned)[self.gateway]
        actual = os.stat(f"/proc/{helper}/ns/net")
        require((actual.st_dev, actual.st_ino) == expected, "Pilote hors de l'espace possédé.")
        self.evidence.record("driver_namespace_verified", driver_pid=self.owner.child.pid, descendant_pid=helper,
                             identity=list(expected))

    def restore(self):
        require(self.add_attempted, "Aucune installation possédée à restaurer.")
        self.clean_endpoints()
        current = self.capture("pre-restore.json")
        roots = current["snapshot"]["readings"][1]["value"]
        if len(roots) == 1 and roots[0].get("kind") == "noqueue":
            # An uncertain/failed add can leave the original state intact.
            require(not self.applied, "CAKE vérifié disparu avant restauration ; possession perdue.")
            self.evidence.record("rollback_not_needed")
        else:
            owned_cake(self.current_root())
            require(source_hashes() == self.sources, "Sources modifiées avant retrait.")
            self.evidence.record("remove_intent", interface="wan", handle="10:")
            self.tc(["qdisc", "del", "dev", "wan", "root", "handle", "10:"])
            self.removed = True
            self.evidence.record("owned_root_removed")
        self.clean_endpoints()
        self.capture("after.json")
        result = self.evaluate("comparison.json", ["restore-check", "--before", str(self.evidence.folder / "before.json"),
            "--after", str(self.evidence.folder / "after.json"), "--json"])
        require(result.get("decision") == "selected_state_matches"
                and result.get("before_sha256") == self.evidence.files["before.json"]
                and result.get("after_sha256") == self.evidence.files["after.json"], "Retour aux champs initiaux non confirmé.")
        self.restored = self.removed
        self.evidence.record("selected_initial_state_verified", root_removed=self.removed)


def cycle(mode, owner, engine, evidence):
    """The supervisor outlives the driver and owns bounded recovery/cleanup."""
    result = {"schema_version":1, "kind":"lab_queue_recovery", "mode":mode,
        "started_at":datetime.now(timezone.utc).isoformat(), "state":"failed",
        "restoration_verified":False, "cleanup_verified":False, "traffic_generated":False,
        "real_gateway_restoration_validated":False}
    previous, failure, cleanup_failure = {}, None, None
    recovering = False
    interruption = 0
    for signum in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM):
        previous[signum] = signal.getsignal(signum)
        def interrupted(received, _frame):
            nonlocal interruption
            interruption = interruption or 128 + received
            if not recovering:
                owner.interruption = interruption
        signal.signal(signum, interrupted)
    try:
        try:
            owner.create()
            engine.setup()
            banner = engine.tc(["-V"])
            result["producer"] = cake.producer(banner)
            engine.apply()
            evidence.record("driver_starting")
            owner.start_pinned_driver(engine.tools, engine.gateway, mode)
            owner.monitor(mode)
            engine.verify_driver_namespace()
        except BaseException as error:
            failure = error
        finally:
            # Driver cancellation/deadline does not cancel its supervisor's
            # independent, finite recovery window. Further signals are recorded.
            recovering = True
            owner.interruption = 0
            owner.deadline = time.monotonic() + 30
            try:
                owner.stop_group(time.monotonic() + 3)
                evidence.record("driver_group_stopped", exit_code=owner.driver_code,
                    reaped_descendants=owner.reaped_descendants)
                if engine.add_attempted:
                    engine.restore()
            except BaseException as error:
                failure = failure or error
            finally:
                try:
                    engine.release()
                except BaseException as error:
                    failure = failure or error
                try:
                    evidence.record("namespace_bindings_closed")
                except BaseException as error:
                    failure = failure or error
                owner.interruption = 0
                owner.deadline = time.monotonic() + 10
                try:
                    owner.close()
                    result["cleanup_verified"] = True
                except BaseException as error:
                    cleanup_failure = error
        require(failure is None, str(failure))
        require(cleanup_failure is None, str(cleanup_failure))
        require(not interruption, "Supervision interrompue.")
        expected = -signal.SIGKILL if mode == "check-crash" else 0
        require(owner.driver_code == expected and owner.reaped_descendants == 1,
                "Arrêt du pilote ou récupération du descendant non conforme.")
        require(engine.applied and engine.removed and engine.restored, "Cycle de restauration incomplet.")
        engine.tools.verify()
        require(source_hashes() == engine.sources, "Sources modifiées pendant le contrôle.")
        result["state"] = "complete"
    except BaseException as error:
        result["error"] = str(error)
        if cleanup_failure is not None:
            result["cleanup_error"] = str(cleanup_failure)
    finally:
        result.update(restoration_verified=engine.restored, applied_verified=engine.applied,
            root_removed=engine.removed, driver_exit_code=owner.driver_code,
            driver_pid=owner.child.pid if owner.child else None, descendant_pid=owner.descendant,
            reaped_descendants=owner.reaped_descendants, namespaces=[name for name, _identity in owner.owned],
            namespace_identities=[list(identity) if identity else None for _name,identity in owner.owned],
            workspace=str(owner.workspace) if owner.workspace else None, interruption_code=interruption,
            finished_at=datetime.now(timezone.utc).isoformat())
        try:
            evidence.finish()
            result["artifacts_sha256"] = dict(evidence.files)
            evidence.save("report.json", result)
        finally:
            for signum, handler in previous.items():
                signal.signal(signum, handler)
    return result


def plan():
    return ("Restauration de laboratoire : trois namespaces neufs possédés, veth wan/eth0 actif.\n"
        "IPv6 désactivé dans les deux espaces ; aucune adresse, route ni charge de test.\n"
        "Capture Go noqueue, intention durable, CAKE 10: à 4mbit puis pilote séparé.\n"
        "Fin normale ou SIGKILL du pilote ; récupération du groupe avant retrait ciblé.\n"
        "Relecture CAKE possédé, retrait de 10:, capture et comparaison Go avant suppression des espaces.\n"
        "Outils ELF ouverts et vérifiés, commandes bornées, preuves sans écrasement.\n"
        "Aucune interface physique acceptée ; la restauration du foyer reste non validée.")
