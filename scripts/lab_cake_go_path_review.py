"""Offline replay of the six IPv4 passage commands and their TCP gate."""

import importlib.util
from pathlib import Path


def sibling(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


base = sibling("path_common_review", "lab_cake_go_active_review.py")
readers = sibling("path_capture_readers", "lab_cake_go_path.py")
require, equal, Error = base.require, base.equal, base.Error


def expected_commands(names, tools):
    c, g, _ = names
    switch = [tools["ip"]["path"], "netns", "exec", g, tools["sysctl"]["path"]]
    probe = [tools["ip"]["path"], "netns", "exec", c, tools["ping"]["path"], "-4", "-n"]
    return (
        ("disable", [*switch, "-q", "-w", "net.ipv4.ip_forward=0"], 2, 0),
        ("read_disabled", [*switch, "-n", "net.ipv4.ip_forward"], 2, 0),
        ("blocked_probe", [*probe, "-c", "1", "-W", "1", "10.203.0.6"], 4, 1),
        ("enable", [*switch, "-q", "-w", "net.ipv4.ip_forward=1"], 2, 0),
        ("read_enabled", [*switch, "-n", "net.ipv4.ip_forward"], 2, 0),
        ("passing_probe", [*probe, "-c", "3", "-W", "1", "10.203.0.6"], 6, 0),
    )


def validate_path(folder, report, rows, normalized, tools):
    path = report["path_check"]
    require(set(path) == {"schema_version", "kind", "state", "path_verified", "probe_attempted", "commands",
                          "without_forwarding", "with_forwarding", "before", "after", "statistics_delta"}
            and type(path["schema_version"]) is int and path["schema_version"] == 1
            and path["kind"] == "lab_cake_go_ipv4_passage" and path["state"] == "verified"
            and path["path_verified"] is True and path["probe_attempted"] is True, "Passage IPv4 incomplet.")
    data = [r["data"] for r in rows]
    def one(event):
        found = [i for i, d in enumerate(data) if d.get("event") == event]
        require(len(found) == 1, "Transition de passage absente ou répétée : " + event)
        return found[0]
    begin, verified = one("path_begin"), one("path_verified")
    require(one("activation_verified") < begin < verified < one("traffic_launch_intent"), "Passage hors de la fenêtre avant TCP.")
    equal(data[begin], {"event": "path_begin", "tools": tools, "source_sha256": report["environment"]["source_sha256"]},
          "Contexte de passage différent.")
    version = report["environment"]["versions"]["ping"]
    require(set(version) == {"available", "stdout", "stderr"} and version["available"] is True
            and isinstance(version["stdout"], str) and version["stdout"].startswith("ping from iputils ")
            and isinstance(version["stderr"], str), "Producteur ping non confirmé.")
    intents = [i for i, d in enumerate(data) if d.get("event") == "path_tool_intent"]
    results = [i for i, d in enumerate(data) if d.get("event") == "path_tool_result"]
    require(len(intents) == len(results) == len(path["commands"]) == 6, "Six commandes de passage requises.")
    recalculated, pids = {}, []
    fields = {"event", "index", "label", "arguments", "started_at", "finished_at", "duration_ns", "error", "pid",
              "exit_code", "stdout_truncated", "stderr_truncated", "process_stopped", "stdout_base64", "stderr_base64"}
    previous = begin
    for index, (label, arguments, timeout, code) in enumerate(expected_commands(report["namespaces"], tools), 1):
        intent_at, result_at = intents[index - 1], results[index - 1]
        require(previous < intent_at and result_at == intent_at + 1 and result_at < verified, "Ordre de commande de passage incohérent.")
        equal(data[intent_at], {"event": "path_tool_intent", "index": index, "label": label,
                               "arguments": arguments, "timeout_seconds": timeout, "expected_exit_code": code},
              "Commande de passage différente du contrat.")
        result = data[result_at]
        require(set(result) == fields, "Champs de résultat de passage incompatibles.")
        equal({k: result[k] for k in ("event", "index", "label", "arguments", "exit_code", "error")},
              {"event": "path_tool_result", "index": index, "label": label, "arguments": arguments,
               "exit_code": code, "error": ""}, "Résultat de passage incompatible.")
        require(result["process_stopped"] is True and result["stdout_truncated"] is False and result["stderr_truncated"] is False,
                "Commande non récupérée ou capture tronquée.")
        require(type(result["pid"]) is int and result["pid"] > 0, "PID de passage absent.")
        pids.append(result["pid"])
        duration = result["duration_ns"]
        require(type(duration) is int and 0 <= duration <= timeout * 1_000_000_000, "Durée de passage hors borne conservatrice.")
        base.go.protocol.timestamp(result["started_at"])
        base.go.protocol.timestamp(result["finished_at"])
        started = base.collect.traffic.active.series.timestamp_ns(result["started_at"].replace("+00:00", "Z"))
        finished = base.collect.traffic.active.series.timestamp_ns(result["finished_at"].replace("+00:00", "Z"))
        require(finished >= started, "Dates de commande de passage inversées.")
        stdout = base.go.protocol.source_bytes(result["stdout_base64"], readers.OUTPUT_LIMIT)
        base.go.protocol.source_bytes(result["stderr_base64"], readers.OUTPUT_LIMIT)
        if index in (2, 5):
            readers.validate_forwarding(stdout, 0 if index == 2 else 1)
        elif index in (3, 6):
            key = "without_forwarding" if index == 3 else "with_forwarding"
            recalculated[key] = readers.validate_probe(stdout, result["exit_code"], forwarding=0 if index == 3 else 1)
        else:
            require(stdout == b"", "Sortie inattendue de sysctl -q -w.")
        equal(result, path["commands"][index - 1], "Résultat du rapport différent du journal.")
        # Every step is followed by independently parsed link/CAKE reads, even
        # while forwarding is disabled; full topology reads require forwarding 1.
        next_intent = intents[index] if index < 6 else verified
        intervening = data[result_at + 1:next_intent]
        require(any(d.get("event") == "activation_qdisc" for d in intervening), "Continuité CAKE de passage absente.")
        gateway = report["namespaces"][1]
        link_args = [tools["ip"]["path"], "-n", gateway, "-j", "-d", "link", "show"]
        link_results = [d for d in intervening if d.get("event") == "activation_tool_result" and d.get("arguments") == link_args]
        require(link_results, "Continuité du lien pendant le passage absente.")
        expected_links = base.collect.topology.links(report["topology"]["topology"][gateway]["links"], ("lo", "lan", "wan"), True)
        for captured in link_results:
            raw_links = base.go.protocol.source_bytes(captured["stdout_base64"], 65536)
            equal(base.collect.topology.links(base.collect.cake.queue.document(raw_links), ("lo", "lan", "wan"), True),
                  expected_links, "Lien modifié pendant le passage.")
        previous = result_at
    # A sequential OS may reuse a PID after wait; identity is checked per
    # invocation, so a repeated PID alone is not grounds for refusal.
    for key, value in recalculated.items():
        equal(value, path[key], "Résumé ICMP non conforme aux captures.")
    for label in ("before", "after"):
        equal(path[label], report["topology"][label + "_path"], "Relevé de passage différent de la topologie.")
        require(any(base.canonical(path[label]) == base.canonical(v) for v in normalized), "Relevé de passage sans lecture brute.")
    for boundary, label in ((begin, "before"), (verified, "after")):
        last_reading = [d["reading"] for d in data[:boundary] if d.get("event") == "activation_qdisc"][-1]
        equal(path[label], last_reading, "Relevé de passage différent de sa frontière.")
    delta = base.collect.cake.queue.statistics_delta(base.reading(path["before"]), base.reading(path["after"]))
    require(delta["available"], "Différence CAKE du passage indisponible.")
    equal(delta, path["statistics_delta"], "Différence CAKE du passage incohérente.")
    equal(data[verified], {"event": "path_verified", **recalculated, "statistics_delta": delta}, "Transition de passage non recalculée.")
    before_time, after_time = [path[k]["elapsed_since_start_ms"] for k in ("before", "after")]
    require(before_time <= after_time <= report["queue_samples"][0]["elapsed_since_start_ms"], "Relevés ICMP et TCP hors ordre.")
    return {"recorded_pids": pids, "commands": 6, **recalculated, "statistics_delta": delta}


def validate_control(folder, report, tools, sources, build):
    return base.validate_control(folder, report, tools, sources, build, path_validator=validate_path)


def review(case):
    return base.review(case, path_validator=validate_path)
