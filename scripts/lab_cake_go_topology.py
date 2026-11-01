"""Activate the fixed lab only after a verified and reaped Go DOWN phase."""

import base64
import hashlib
from copy import deepcopy
import importlib.util
import ipaddress
import json
from pathlib import Path
import re
import time


def sibling(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


go = sibling("topology_go_phase", "lab_cake_go.py")
active = sibling("topology_activation", "lab_active.py")
Error, require, cake = go.Error, go.require, go.cake
ADDRESSES = ({"eth0": "10.203.0.2"}, {"lan": "10.203.0.1", "wan": "10.203.0.5"}, {"eth0": "10.203.0.6"})


def source_fingerprints():
    return {**go.source_fingerprints(), **{str(Path(__file__).with_name(name)): hashlib.sha256(go.read(Path(__file__).with_name(name), 1024*1024)).hexdigest()
            for name in ("lab_cake_go_topology.py", "lab_active.py", "lab-series.py")}}


def link_identity(row, *, up):
    flags = row.get("flags")
    require(isinstance(flags, list) and all(isinstance(f, str) for f in flags)
            and len(flags) == len(set(flags)) and ("UP" in flags) == up, "État de lien inattendu.")
    require(type(row.get("ifindex")) is int and 0 < row["ifindex"] < 2**31, "Indice de lien invalide.")
    if row.get("ifname") == "lo":
        require("LOOPBACK" in flags and row.get("link_type") == "loopback", "Loopback invalide.")
        return {"ifindex": row["ifindex"], "link_type": "loopback"}
    require("LOOPBACK" not in flags and row.get("link_type") == "ether"
            and row.get("linkinfo", {}).get("info_kind") == "veth"
            and row.get("operstate") == ("UP" if up else "DOWN"), "Veth attendu.")
    mac = row.get("address")
    require(isinstance(mac, str) and re.fullmatch(r"[0-9a-f]{2}(?::[0-9a-f]{2}){5}", mac)
            and mac != "00:00:00:00:00:00" and int(mac[:2], 16) & 1 == 0, "MAC veth invalide.")
    for key, maximum in (("link_index", 2**31 - 1), ("mtu", 65535)):
        require(type(row.get(key)) is int and 0 < row[key] <= maximum, "Identité veth incomplète.")
    return {key: row[key] for key in ("ifindex", "link_index", "mtu", "address")}


def links(rows, expected, up):
    require(len(rows) == len(expected) and {r.get("ifname") for r in rows} == set(expected), "Interfaces inattendues.")
    result = {r["ifname"]: link_identity(r, up=up) for r in rows}
    require(len({r["ifindex"] for r in result.values()}) == len(result), "Indices de lien dupliqués.")
    return result


def addresses(rows, identities, expected):
    require(len(rows) == len(identities) and {r.get("ifname") for r in rows} == set(identities), "Interfaces d’adresses inattendues.")
    for row in rows:
        name = row["ifname"]
        require(type(row.get("ifindex")) is int and row["ifindex"] == identities[name]["ifindex"], "Identité d’adresse modifiée.")
        entries = row.get("addr_info")
        require(isinstance(entries, list) and all(isinstance(e, dict) for e in entries), "Adresses indisponibles.")
        ipv4, seen = [], set()
        for entry in entries:
            family, local, prefix = (entry.get(k) for k in ("family", "local", "prefixlen"))
            require(isinstance(local, str) and type(prefix) is int and (family, local, prefix) not in seen, "Adresse ambiguë.")
            seen.add((family, local, prefix))
            if family == "inet":
                if name == "lo":
                    require(local == "127.0.0.1" and prefix == 8 and entry.get("scope") == "host", "IPv4 loopback inattendue.")
                else:
                    require(prefix == 30 and entry.get("scope") == "global", "IPv4 de laboratoire attendue.")
                    ipv4.append(local)
            elif family == "inet6":
                address = ipaddress.IPv6Address(local)
                require((name == "lo" and address.is_loopback and prefix == 128 and entry.get("scope") == "host")
                        or (name != "lo" and address.is_link_local and prefix == 64 and entry.get("scope") == "link"),
                        "Seules les IPv6 locales automatiques sont admises.")
            else:
                raise Error("Famille d’adresse inattendue.")
        require(ipv4 == ([expected[name]] if name in expected else []), "IPv4 effective différente de la topologie.")
        if not expected and name != "lo":
            require(not entries, "Extrémité DOWN déjà adressée.")


def routes(rows, role):
    networks = ("10.203.0.0/30", "10.203.0.4/30")
    expected = (
        {(networks[0], "eth0", None, "10.203.0.2"), (networks[1], "eth0", "10.203.0.1", None)},
        {(networks[0], "lan", None, "10.203.0.1"), (networks[1], "wan", None, "10.203.0.5")},
        {(networks[1], "eth0", None, "10.203.0.6"), (networks[0], "eth0", "10.203.0.5", None)},
    )[role]
    actual = []
    for row in rows:
        require(row.get("type", "unicast") == "unicast" and row.get("table", "main") == "main"
                and not any(k in row for k in ("nexthops", "nhid", "encap", "via")), "Route IPv4 inattendue.")
        flags = row.get("flags", [])
        require(isinstance(flags, list) and not flags, "Route IPv4 inactive ou marquée.")
        via = row.get("gateway")
        require(row.get("protocol", "boot") == ("boot" if via else "kernel")
                and row.get("scope", "global") == ("global" if via else "link"), "Origine de route inattendue.")
        actual.append((row.get("dst"), row.get("dev"), via, row.get("prefsrc")))
    require(len(actual) == len(expected) and set(actual) == expected, "Routes IPv4 différentes de la topologie.")


class Topology(cake.CakeCheck):
    def __init__(self, owner, down, sysctl, record):
        session = owner.session
        require(callable(record) and not owner.closed and owner.phase_verified and owner.phase_failure is None
                and session is not None and session.link is down and down.owner is owner
                and owner.driver_code == 0 and owner._phase_stopped and not session.fds, "Phase Go normale terminée requise.")
        owner.process_group.require_stopped()
        session.validate("finished")
        super().__init__(owner.namespaces, session.tools["tc"]["path"])
        self.owner, self.record, self.sysctl = owner, record, sysctl["path"]
        self.tools = {**deepcopy(session.tools), "sysctl": deepcopy(sysctl)}
        self.sources = source_fingerprints()
        self.producer = deepcopy(down.producer)
        self.gateway, self.server = [name for name, _ in owner.owned][1:]
        self.names = tuple(owner.owned)
        self.statistics_started_ns = down.statistics_started_ns
        self.report = deepcopy(down.report)
        self.last = deepcopy(self.report["after_driver_exit"]["statistics"])
        self.initial_statistics = deepcopy(self.last)
        self.report["after_go_exit"] = self.report.pop("after_driver_exit")
        self.report["down_statistics_delta"] = self.report.pop("statistics_delta")
        self.state, self.failure = "prepared", None
        self.baseline, self.up_baseline = None, None
        raw = go.read(session.folder / "worker.jsonl", go.protocol.JOURNAL_LIMIT, session.journal_identity)
        rows = [go.protocol.document(line, go.protocol.RECORD_LIMIT) for line in raw.splitlines()]
        last = [r["data"] for r in rows if r["event"] == "tool_result" and r["data"]["arguments"] == go.protocol.LINK][-1]
        self.go_links = links(cake.queue.document(go.protocol.source_bytes(last["stdout_base64"], 65536)), ("lo", "wan"), False)
        require(owner.namespaces.ip == self.tools["ip"]["path"], "Chemin ip différent de la phase Go.")
        ip, c, g, s = owner.namespaces.ip, *[name for name, _ in owner.owned]
        self.mutations = [[ip, "-n", g, "link", "add", "lan", "type", "veth", "peer", "name", "eth0", "netns", c]]
        for namespace, interface, address in ((c,"eth0","10.203.0.2"),(g,"lan","10.203.0.1"),(g,"wan","10.203.0.5"),(s,"eth0","10.203.0.6")):
            self.mutations += [[ip,"-n",namespace,"address","add",address+"/30","dev",interface], [ip,"-n",namespace,"link","set","dev",interface,"up"]]
        self.mutations += [[ip,"-n",n,"link","set","dev","lo","up"] for n in (c,g,s)]
        self.mutations += [[ip,"-n",n,"route","add",network,"via",via,"dev","eth0"] for n,network,via in ((c,"10.203.0.4/30","10.203.0.1"),(s,"10.203.0.0/30","10.203.0.5"))]
        self.forward = [ip,"netns","exec",g,self.sysctl,"-n","net.ipv4.ip_forward"]
        self.mutations += [[ip,"netns","exec",g,self.sysctl,"-q","-w","net.ipv4.ip_forward=1"]]
        self.reads = [[ip,"-n",n,*tail] for n in (c,g,s) for tail in (["-j","-d","link","show"],["-j","address","show"],["-j","-4","route","show","table","main"])]
        self.reads += [self.forward, [ip,"netns","exec",g,self.tc,"-j","-s","-r","qdisc","show","dev","wan"]]
        self.next_mutation = 0

    def fail(self, error):
        if self.failure is None:
            self.failure, self.state, self.owner.phase_failure = error, "failed", error

    def verify_tools(self, paths=None):
        for path, expected in {(s["path"], s["sha256"]) for s in self.tools.values() if paths is None or s["path"] in paths}:
            require(go.tool(path) == {"path":path,"sha256":expected}, "Outil modifié pendant l’activation.")

    def execute(self, args):
        try:
            return self._execute(args)
        except BaseException as error:
            self.fail(error)
            raise

    def _execute(self, args):
        require(self.failure is None and not self.owner.closed, "Activation échouée ou propriétaire fermé.")
        require(tuple(self.owner.owned) == self.names, "Ressources remplacées pendant l’activation.")
        require(source_fingerprints() == self.sources, "Sources modifiées pendant l’activation.")
        paths = {args[0]}
        if args[1:3] == ["netns", "exec"]: paths.add(args[4])
        self.verify_tools(paths)
        if args not in self.reads:
            require(self.next_mutation < len(self.mutations) and args == self.mutations[self.next_mutation], "Commande d’activation interdite ou hors ordre.")
            self.next_mutation += 1  # A failed command may already have had an effect.
        self.record({"event":"activation_tool_intent","arguments":list(args)})
        start = time.monotonic_ns()
        try:
            result = super().execute(args)
        except BaseException as error:
            self.record({"event":"activation_tool_result","arguments":list(args),"error":str(error),"stdout_base64":None,"duration_ns":time.monotonic_ns()-start})
            raise
        self.record({"event":"activation_tool_result","arguments":list(args),"error":"","stdout_base64":base64.b64encode(result).decode(),"duration_ns":time.monotonic_ns()-start})
        return result

    def links(self, namespace):
        return cake.queue.document(self.execute([self.namespaces.ip,"-n",namespace,"-j","-d","link","show"]))

    def snapshot(self, up):
        result, identities = {}, {}
        for role, (name, _) in enumerate(self.names):
            names = ("lo", "lan", "wan") if up and role == 1 else ("lo", "eth0") if up or role == 2 else ("lo", "wan") if role == 1 else ("lo",)
            link_rows = self.links(name)
            current = links(link_rows, names, up)
            address_rows = cake.queue.document(self.execute([self.namespaces.ip,"-n",name,"-j","address","show"]))
            addresses(address_rows, current, ADDRESSES[role] if up else {})
            route_rows = cake.queue.document(self.execute([self.namespaces.ip,"-n",name,"-j","-4","route","show","table","main"]))
            if up: routes(route_rows, role)
            else: require(not route_rows, "Route préexistante dans les ressources DOWN.")
            result[name] = {"links":link_rows,"addresses":address_rows,"ipv4_main_routes":route_rows}
            identities[name] = current
        c, g, s = [name for name, _ in self.names]
        require(identities[g]["wan"]["link_index"] == identities[s]["eth0"]["ifindex"]
                and identities[s]["eth0"]["link_index"] == identities[g]["wan"]["ifindex"], "Pair wan/serveur incohérent.")
        for name, identity in self.go_links.items():
            require(identities[g][name] == identity, "Identité issue du journal Go modifiée.")
        if self.baseline is not None:
            for namespace, previous in self.baseline.items():
                require(all(identities[namespace][name] == identity for name,identity in previous.items()), "Lien remplacé pendant l’activation.")
        if up:
            require(identities[g]["lan"]["link_index"] == identities[c]["eth0"]["ifindex"]
                    and identities[c]["eth0"]["link_index"] == identities[g]["lan"]["ifindex"], "Pair lan/client incohérent.")
            require(self.execute(self.forward).strip() == b"1", "Forwarding IPv4 non confirmé.")
            if self.up_baseline is not None: require(identities == self.up_baseline, "Identité active modifiée.")
            self.up_baseline = identities
        else:
            self.baseline = identities
        self.record({"event":"topology_read","link_state":"UP" if up else "DOWN","snapshot":result})
        return result

    def read(self, include_statistics=True):
        try:
            require(include_statistics is True, "Statistiques requises pour la continuité CAKE.")
            reading = super().read(True)
            delta = cake.queue.statistics_delta(self.last, reading["statistics"])
            require(delta["available"], "Compteurs CAKE en baisse pendant la transition.")
            self.last = deepcopy(reading["statistics"])
            self.record({"event":"activation_qdisc","reading":reading})
            return reading
        except BaseException as error:
            self.fail(error)
            raise

    def verify(self, label):
        try:
            require(self.state in ("activating", "activated"), "Phase d’activation incompatible.")
            topology = self.snapshot(True)
            self.report[label] = self.read(True)
            self.report["activation_statistics_delta"] = cake.queue.statistics_delta(self.initial_statistics, self.last)
            self.report["topology"] = topology
            self.owner.queue_report = self.report
        except BaseException as error:
            self.fail(error)
            raise


def activate_after_phase(owner, down, sysctl, record):
    """Return an activated checker; caller retains final cleanup responsibility."""
    try:
        topology = Topology(owner, down, sysctl, record)
        topology.verify_tools()
        topology.record({"event":"activation_context","tools":topology.tools,"source_sha256":topology.sources,
                         "session_id":owner.session.token,"namespaces":[{"name":n,"identity":i} for n,i in topology.names]})
        topology.snapshot(False)
        topology.report["before_activation"] = topology.read(True)
        topology.record({"event":"activation_begin","tools":topology.tools})
        owner.advance_group()
        topology.state = "activating"
        active.activate(topology, owner, topology.sysctl)
        require(topology.next_mutation == len(topology.mutations), "Activation incomplète.")
        require(source_fingerprints() == topology.sources, "Sources modifiées avant confirmation.")
        topology.verify_tools()
        owner.check()
        topology.state = "activated"
        topology.record({"event":"activation_verified","cleanup":"deferred_to_supervisor","traffic_generated":False})
        owner.check()
        return topology
    except BaseException as error:
        owner.phase_failure = error
        owner.close()
        raise
