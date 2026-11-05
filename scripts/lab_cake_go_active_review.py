"""Offline consistency review of frozen Go/CAKE/traffic evidence; no net commands."""

from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import struct
import subprocess

spec = importlib.util.spec_from_file_location("active_review_model", Path(__file__).with_name("lab_cake_go_active.py"))
model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)
go, collect, require = model.go, model.collect, model.require
Error = model.Error
LIMIT = 8 * 1024 * 1024


def raw(path, limit=LIMIT):
    return go.read(path, limit)


def document(path):
    return go.protocol.document(raw(path), LIMIT)


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def equal(a, b, message):
    require(canonical(a) == canonical(b), message)


def fingerprint(path, limit=LIMIT):
    data = raw(path, limit)
    return {"file": path.name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def reading(value):
    go.protocol.timestamp(value["collected_at"])
    data = json.dumps(value["qdiscs"], allow_nan=False).encode()
    equal(collect.cake.configured_qdisc(data, collect.cake.PROFILE), value["configuration"], "Configuration CAKE incohérente.")
    stats = collect.cake.statistics(data, collect.cake.PROFILE)
    equal(stats, value["statistics"], "Statistiques CAKE incohérentes.")
    for key in ("elapsed_since_start_ms", "read_duration_ms"):
        require(type(value[key]) in (float, int) and math.isfinite(value[key]) and value[key] >= 0, "Horodatage de lecture invalide.")
    require(value["read_duration_ms"] < 2200, "Lecture CAKE hors borne.")
    return stats


def activation_arguments(names, tools):
    c, g, s = names
    ip = tools["ip"]["path"]
    result = [[ip,"-n",g,"link","add","lan","type","veth","peer","name","eth0","netns",c]]
    for n, interface, address in ((c,"eth0","10.203.0.2/30"),(g,"lan","10.203.0.1/30"),
                                   (g,"wan","10.203.0.5/30"),(s,"eth0","10.203.0.6/30")):
        result += [[ip,"-n",n,"address","add",address,"dev",interface], [ip,"-n",n,"link","set","dev",interface,"up"]]
    result += [[ip,"-n",n,"link","set","dev","lo","up"] for n in names]
    result += [[ip,"-n",n,"route","add",network,"via",via,"dev","eth0"] for n,network,via in
               ((c,"10.203.0.4/30","10.203.0.1"),(s,"10.203.0.0/30","10.203.0.5"))]
    result += [[ip,"netns","exec",g,tools["sysctl"]["path"],"-q","-w","net.ipv4.ip_forward=1"]]
    return result


def validate_topology(snapshot, names, down_links, baseline=None, up=True):
    equal(sorted(snapshot), sorted(names), "Espaces de topologie différents.")
    identities = {}
    for role, name in enumerate(names):
        row = snapshot[name]
        expected = ("lo","lan","wan") if up and role == 1 else ("lo","eth0") if up or role == 2 else ("lo","wan") if role == 1 else ("lo",)
        identities[name] = collect.topology.links(row["links"], expected, up)
        collect.topology.addresses(row["addresses"], identities[name], collect.topology.ADDRESSES[role] if up else {})
        if up: collect.topology.routes(row["ipv4_main_routes"], role)
        else: require(row["ipv4_main_routes"] == [], "Route préexistante avant activation.")
    c, g, s = names
    for name, identity in down_links.items():
        equal(identities[g][name], identity, "Identité issue de Go modifiée.")
    require(identities[g]["wan"]["link_index"] == identities[s]["eth0"]["ifindex"]
            and identities[s]["eth0"]["link_index"] == identities[g]["wan"]["ifindex"], "Pair wan non conservé.")
    if up:
        require(identities[g]["lan"]["link_index"] == identities[c]["eth0"]["ifindex"]
                and identities[c]["eth0"]["link_index"] == identities[g]["lan"]["ifindex"], "Pair lan incohérent.")
    if baseline is not None:
        for n, previous in baseline.items():
            for interface, identity in previous.items():
                equal(identities[n][interface], identity, "Interface remplacée pendant le contrôle.")
    return identities


def events(folder, session):
    wire, result = raw(folder/"go/events.bin", go.protocol.OUTPUT_LIMIT), []
    for expected in ("ready", "applied"):
        require(len(wire) >= 4, "Événement Go absent.")
        size = struct.unpack("!I", wire[:4])[0]
        require(0 < size <= go.protocol.EVENT_LIMIT and len(wire) >= size + 4, "Événement Go tronqué.")
        result.append(go.protocol.event(wire[4:4+size], session, expected))
        wire = wire[4+size:]
    require(not wire, "Événement Go supplémentaire.")
    return result


def validate_control(folder, report, expected_tools, expected_sources, expected_build, *, path_validator=None, campaign_validator=None):
    """Recompute one control; caller independently verifies frozen inputs first."""
    fields = {"schema_version","kind","state","mode","reference","session_id","cleanup_verified","traffic_generated",
              "go_phase","traffic_group","topology","queue_samples","traffic_statistics_delta","flow","congestion",
              "traffic_coverage","environment","namespaces","workspace","groups","supervisor_journal"}
    if path_validator is not None:
        fields.add("path_check")
    if campaign_validator is not None:
        require(path_validator is not None, "Relecture IPv4 requise pour la campagne.")
        fields |= {"technical_valid","load_scenario","connections","comparison","coopace_benefit","phases","assessment"}
    expected_kind = "lab_cake_go_campaign" if campaign_validator is not None else "lab_cake_go_path_check" if path_validator is not None else "lab_cake_go_active_check"
    require(set(report) == fields and type(report["schema_version"]) is int and report["schema_version"] == 1
            and report["kind"] == expected_kind and report["state"] == "complete"
            and report["cleanup_verified"] is True and report["traffic_generated"] is True,
            "Contrôle incomplet, non nettoyé ou de type incompatible.")
    mode = report["mode"]
    require(mode in (("run","check-crash") if campaign_validator is not None else ("check","check-crash")) and folder.name == mode, "Mode ou dossier incompatible.")
    crash = mode == "check-crash"
    require(report["reference"] == go.protocol.REFERENCE and report["congestion"] == "not_assessed"
            and report["traffic_coverage"] == "synthetic_ipv4_only", "Portée du rapport incompatible.")
    session = collect.traffic.session_id(report["session_id"])
    names = [f"cg-{session}-{r}" for r in ("c","g","s")]
    equal(report["namespaces"], names, "Noms d’espaces incompatibles.")
    require(report["workspace"] == "/tmp/coopace-guard." + session, "Réservation incompatible.")
    environment = document(folder/"environment.json")
    equal(environment, report["environment"], "Environnement et rapport différents.")
    equal(environment["tools"], expected_tools, "Exécutables différents des entrées figées.")
    equal(environment["source_sha256"], expected_sources, "Sources différentes des entrées figées.")
    equal(environment["invocation"], {"mode":mode,"purpose":"cake_go_campaign_collection" if campaign_validator is not None else "cake_go_path_then_traffic" if path_validator is not None else "cake_go_then_traffic","reference":go.protocol.REFERENCE}, "Invocation différente.")
    require(environment["bootstrap_sha256"] == hashlib.sha256(go.BOOTSTRAP.encode()).hexdigest(), "Bootstrap Go différent.")
    phase, group = report["go_phase"], report["traffic_group"]
    require(type(phase['schema_version']) is int and phase["schema_version"] == 1 and phase["kind"] == "lab_cake_go_down_phase" and phase["state"] == "finished"
            and phase["mode"] == "check" and type(phase["worker_exit_code"]) is int and phase["worker_exit_code"] == 0
            and phase["cleanup"] == "deferred_to_supervisor" and phase["session_id"] == session and phase['reference']==go.protocol.REFERENCE,
            "Phase Go normale non confirmée.")
    equal(phase["namespaces"], names, "Espaces différents entre phases.")
    go_tools = {n:expected_tools[n] for n in ("worker","ip","tc","python")}
    raw_go = raw(folder/"go/worker.jsonl", go.protocol.JOURNAL_LIMIT)
    go_rows = [go.protocol.document(line, go.protocol.RECORD_LIMIT) for line in raw_go.splitlines()]
    header = go_rows[0]["data"]
    equal(header["target_namespace"], phase["namespace_identity"], "Cible Go différente.")
    equal(header["original_namespace"], phase["original_namespace"], "Origine Go différente.")
    require(header["target_namespace"] != header["original_namespace"], "Entrée réseau non distinguée.")
    wire = events(folder, session)
    summary = go.protocol.journal(raw_go, session, go_tools, phase["namespace_identity"], phase["original_namespace"],
                                  phase["worker_pid"], "finished", wire[1])
    equal(summary, phase["journal"], "Journal Go et résumé différents.")
    equal(summary["build"], expected_build, "Provenance du véritable Go incompatible.")
    require(summary["records"] == 36 and summary["tool_calls"] == 14, "Cycle Go incomplet.")
    require(raw(folder/"go/worker.stderr", go.protocol.OUTPUT_LIMIT) == b"", "Diagnostic Go inattendu.")
    links = [go.protocol.source_bytes(r["data"]["stdout_base64"],65536) for r in go_rows
             if r["event"] == "tool_result" and r["data"]["arguments"] == go.protocol.LINK]
    down_links = collect.topology.links(collect.cake.queue.document(links[-1]), ("lo","wan"), False)
    for value in links:
        equal(collect.topology.links(collect.cake.queue.document(value),("lo","wan"),False),down_links,"Lien Go remplacé pendant sa phase.")
    for row in go_rows:
        if row['event']=='tool_result' and row['data']['arguments']==go.protocol.ADDRESS:
            value=collect.cake.queue.document(go.protocol.source_bytes(row['data']['stdout_base64'],65536))
            collect.topology.addresses(value,{'wan':down_links['wan']},{})
    queue = report["topology"]
    require(queue["namespace"] == names[1] and queue["interface"] == "wan" and queue["link_state"] == "UP"
            and queue["kind"] == "cake" and queue["handle"] == "10:", "File active incompatible.")
    equal(queue["producer"], phase["queue"]["producer"], "Producteur CAKE modifié.")
    producer = {**collect.cake.producer(queue["producer"]["version_output"].encode()),"tc_path":expected_tools["tc"]["path"]}
    equal(producer, queue["producer"], "Profil du producteur incompatible.")
    for item in (phase["queue"]["after_add"], phase["queue"]["after_driver_exit"]):
        stats = reading(item)
        require(all(v == 0 for v in stats["counters"].values()) and stats["backlog_bytes"] == stats["queued_packets"] == 0,
                "Trafic inattendu pendant la phase DOWN.")
    equal(queue["after_go_exit"], phase["queue"]["after_driver_exit"], "Relevé de fin Go non conservé.")
    equal(queue["down_statistics_delta"], phase["queue"]["statistics_delta"], "Différence DOWN modifiée.")
    equal(queue["activation_statistics_delta"], collect.cake.queue.statistics_delta(reading(queue["after_go_exit"]), reading(queue["after_activation"])),
          "Différence d’activation non figée.")
    journal_raw = raw(folder/"supervisor.jsonl",(16 if campaign_validator is not None else 4)*1024*1024)
    require(journal_raw.endswith(b"\n"), "Journal superviseur tronqué.")
    rows = [go.protocol.document(line,LIMIT) for line in journal_raw.splitlines()]
    elapsed = -1
    for index,row in enumerate(rows,1):
        require(set(row) == {"schema_version","kind","sequence","recorded_at","elapsed_ns","data"}
                and type(row["schema_version"]) is int and row["schema_version"] == 1
                and row["kind"] == "lab_cake_go_active_journal" and type(row["sequence"]) is int and row["sequence"] == index
                and type(row["elapsed_ns"]) is int and row["elapsed_ns"] >= max(0,elapsed), "Séquence du superviseur incompatible.")
        go.protocol.timestamp(row["recorded_at"]);elapsed=row["elapsed_ns"]
    data = [r["data"] for r in rows]
    def one(event):
        values=[(i,d) for i,d in enumerate(data) if d.get("event") == event]
        require(len(values) == 1, "Transition absente ou répétée : " + event)
        return values[0]
    if campaign_validator is not None:
        stages=("environment_verified","resources_owned","go_phase_finished","activation_begin","activation_verified",
                "traffic_launch_intent","traffic_launched","traffic_group_stopped","combined_evidence_verified","control_complete")
        order=[one(e)[0] for e in stages]
    else:
        order = [one(e)[0] for e in ("environment_verified","resources_owned","go_phase_finished","activation_begin","activation_verified",
                                      "traffic_launch_intent","traffic_launched","traffic_ready",
                                      "traffic_kill_intent" if crash else "traffic_continue_intent","traffic_group_stopped",
                                      "combined_evidence_verified","control_complete")]
    require(order == sorted(set(order)), "Phases hors ordre.")
    require(rows[-1]['elapsed_ns']<190_000_000_000,'Durée globale du superviseur incompatible.')
    require(not any(d.get("event") == "control_failed" for d in data), "Échec dans le journal.")
    equal(one("go_phase_finished")[1]["phase"],phase,"Phase Go du journal différente.")
    equal(one('environment_verified')[1]['tools'],expected_tools,'Exécutables du journal différents.')
    equal(one('environment_verified')[1]['source_sha256'],expected_sources,'Sources du journal différentes.')
    frozen=model.phase_evidence(folder/"go")
    equal(one("go_phase_finished")[1]["evidence"],frozen,"Preuves Go modifiées.")
    owned=one("resources_owned")[1]["namespaces"]
    require([p[0] for p in owned] == names and all(len(p[1]) == 2 and all(type(v) is int and v>0 for v in p[1]) for p in owned), "Identités possédées invalides.")
    equal([phase["namespace_identity"][key] for key in ("device","inode")],owned[1][1],"Identité de passerelle non conservée.")
    # Pair each command with its durable result, and rebuild the topology from
    # actual raw outputs rather than trusting the normalized report alone.
    mutations, outputs, topologies, qdiscs, samples, normalized = [], {}, [], [], [], []
    ip=expected_tools["ip"]["path"];g=names[1]
    show=[ip,"netns","exec",g,expected_tools["tc"]["path"],"-j","-s","-r","qdisc","show","dev","wan"]
    latest_reading=None
    for index,event in enumerate(data):
        name=event.get("event")
        if name == "activation_tool_intent":
            require(index+1 < len(data),"Résultat de commande absent.")
            result=data[index+1]
            require(result.get("event") == "activation_tool_result" and result.get("arguments") == event["arguments"]
                    and result.get("error") == "" and type(result.get("duration_ns")) is int and 0 <= result["duration_ns"] < 2_200_000_000,
                    "Résultat d’activation incompatible.")
            args=event["arguments"];output=go.protocol.source_bytes(result["stdout_base64"],65536)
            outputs[tuple(args)] = output
            if "qdisc" in args:require(args==show,"Mutation ou commande qdisc interdite après Go.")
            if (len(args)>3 and args[1]=="-n" and args[3] in ("link","address","route")) or "-w" in args:mutations.append(args)
            if args==[ip,"netns","exec",g,expected_tools["sysctl"]["path"],"-n","net.ipv4.ip_forward"]:
                require(output.strip()==b"1","Forwarding relu non confirmé.")
        elif name == "activation_tool_result":
            require(index>0 and data[index-1].get("event")=="activation_tool_intent","Résultat sans intention.")
        elif name == "topology_read":
            snapshot=event["snapshot"]
            for n,value in snapshot.items():
                for field,tail in (("links",["-j","-d","link","show"]),("addresses",["-j","address","show"]),
                                   ("ipv4_main_routes",["-j","-4","route","show","table","main"])):
                    equal(value[field],collect.cake.queue.document(outputs[tuple([ip,"-n",n,*tail])]),"Topologie différente des sorties brutes.")
            identities=validate_topology(snapshot,names,down_links,topologies[-1] if topologies else None, event["link_state"]=="UP")
            topologies.append(identities)
        elif name == "activation_qdisc":
            latest_reading=event["reading"]
            equal(latest_reading["qdiscs"],collect.cake.queue.document(outputs[tuple(show)]),"Lecture CAKE différente des octets conservés.")
            stats=reading(latest_reading)
            if qdiscs:require(collect.cake.queue.statistics_delta(qdiscs[-1],stats)["available"],"Compteur CAKE en baisse.")
            qdiscs.append(stats)
            normalized.append(latest_reading)
        elif name == ("campaign_sample" if campaign_validator is not None else "traffic_sample"):
            value=event["reading"]
            extra=("phase","pair","condition","read_started_monotonic_ns","read_finished_monotonic_ns") if campaign_validator is not None else ("phase",)
            equal({k:v for k,v in value.items() if k not in extra},latest_reading,"Échantillon sans lecture brute correspondante.")
            samples.append(value)
    equal(mutations,activation_arguments(names,expected_tools),"Les quinze changements d’activation ne concordent pas.")
    for label in ("before_activation","after_activation","before_traffic","after_traffic_stop"):
        require(any(canonical(queue[label])==canonical(value) for value in normalized),"Relevé du rapport absent des preuves brutes : "+label)
    require(len(topologies)>=3,"Topologie finale non relue.")
    validate_topology(queue["topology"],names,down_links,topologies[-1],True)
    equal(samples,report["queue_samples"],"Échantillons du rapport différents du journal.")
    equal(samples,group["queue_samples"],"Échantillons du groupe différents.")
    require(1<len(samples)<=(720 if campaign_validator is not None else 240) and sum(len(json.dumps(s,ensure_ascii=False,allow_nan=False).encode()) for s in samples)<=(4 if campaign_validator is not None else 1)*1024*1024
            and samples[0]["phase"]=="before_driver" and samples[-1]["phase"]==("after_crash_stop" if crash else "after_normal_stop"),
            "Bornes ou étiquettes de collecte incompatibles.")
    delta=collect.cake.queue.statistics_delta(reading(samples[0]),reading(samples[-1]))
    require(delta["available"] and (crash or delta["counters"]["bytes"]>0),"Progression de trafic non confirmée.")
    equal(delta,report["traffic_statistics_delta"],"Différence de trafic incompatible.")
    equal(delta,group["traffic_statistics_delta"],"Différence du groupe incompatible.")
    if campaign_validator is not None:
        require(one("control_complete")[1]["cleanup_verified"] is True, "Nettoyage non attesté.")
        equal(one("traffic_group_stopped")[1], {"event":"traffic_group_stopped","driver_pid":group["driver_pid"],
              "driver_exit_code":group["driver_exit_code"],"reaped_descendants":group["reaped_descendants"]}, "Arrêt du groupe incohérent.")
        require(one("traffic_launched")[1]["driver_pid"] == group["driver_pid"], "Leader de lancement différent.")
        path_facts=path_validator(folder,report,rows,normalized,expected_tools)
        campaign_facts=campaign_validator(folder,report,expected_tools,owned,expected_build)
        return {"session_id":session,"namespaces":names,"workspace":report["workspace"],
                "recorded_pids":[phase["worker_pid"],group["driver_pid"],*summary["tool_pids"],
                                 *path_facts.pop("recorded_pids"),*campaign_facts.pop("recorded_helper_pids")],
                "go_worker_exit_code":0,"go_tool_calls":14,"go_journal_records":36,
                "traffic_driver_exit_code":group["driver_exit_code"],"reaped_traffic_helpers":group["reaped_descendants"],
                "queue_samples":len(samples),"traffic_statistics_delta":delta,"path_check":path_facts,"campaign":campaign_facts}
    running=[v for v in samples if v["phase"]=="running"]
    require(all(b["elapsed_since_start_ms"]-a["elapsed_since_start_ms"]>=250 for a,b in zip(running,running[1:])),"Cadence de collecte trop rapide.")
    output=raw(folder/"driver.stdout.bin",collect.traffic.OUTPUT_LIMIT)
    first,flow_raw=output.split(b"\n",1)
    ready=collect.traffic.parse_ready(first+b"\n",session)
    equal(ready,one("traffic_ready")[1]["announcement"],"Annonce du pilote différente.")
    equal(ready["helper_pids"],group["helper_pids"],"PID annoncés différents.")
    equal(group["helpers"],one("traffic_ready")[1]["helpers"],"Identités d’outils différentes.")
    require(len(group["helpers"])==3,"Trois outils vérifiés requis.")
    for i,(pid,args,value) in enumerate(zip(ready["helper_pids"],collect.expected_helpers(expected_tools),group["helpers"])):
        collect.validate_helper(value,pid,group["driver_pid"],owned[2 if i<2 else 0][1],expected_tools["target" if i==0 else "load"],args)
    equal(group["stdout"],fingerprint(folder/"driver.stdout.bin",collect.traffic.OUTPUT_LIMIT),"Capture stdout modifiée.")
    equal(group["stderr"],fingerprint(folder/"driver.stderr.bin",collect.traffic.OUTPUT_LIMIT),"Capture stderr modifiée.")
    equal(report["supervisor_journal"],fingerprint(folder/"supervisor.jsonl",4*1024*1024),"Journal superviseur modifié.")
    require(type(group["driver_exit_code"]) is int and group["driver_exit_code"]==(-9 if crash else 0)
            and type(group["reaped_descendants"]) is int and group["reaped_descendants"]==(3 if crash else 0)
            and group["traffic_generated"] is True,"Code ou récupération du pilote incompatible.")
    expected_groups=[{"driver_pid":phase["worker_pid"],"driver_exit_code":0,"reaped_descendants":0,"state":"stopped"},
                     {"driver_pid":group["driver_pid"],"driver_exit_code":-9 if crash else 0,"reaped_descendants":3 if crash else 0,"state":"stopped"}]
    equal(report["groups"],expected_groups,"Groupes non récupérés ou confondus.")
    require(type(phase["worker_pid"]) is int and type(group["driver_pid"]) is int and phase["worker_pid"]!=group["driver_pid"],"Leaders non distincts.")
    if crash:
        require(not flow_raw and report["flow"] is None and group["flow"] is None,"Flux final inattendu après panne.")
        require(not any(v.get("event") in ("traffic_continue_intent","traffic_continue_sent") for v in data),"Accusé envoyé pendant le contrôle de panne.")
    else:
        flow=collect.traffic.parse_flow(flow_raw,session)
        equal(flow,report["flow"],"Flux du rapport différent des octets reçus.")
        equal(flow,group["flow"],"Flux du groupe différent.")
        require(flow["latency"]["successful"]==10 and flow["latency"]["failed"]==0
                and flow["has_successful_probe"] is True and flow["probe_window_inside_application_writes"] is True,
                "Dix sondes réussies et recouvertes requises en natif.")
        for value in (flow["send"],flow["receive"],flow["latency"]):
            require(value.get("go_version")==expected_build["go_version"] and value.get("os")=="linux"
                    and value.get("architecture")=="amd64","Provenance des outils de trafic incompatible.")
        settle=collect.traffic.active.series.timestamp_ns(flow["latency"]["started_at"])-collect.traffic.active.series.timestamp_ns(flow["send"]["first_write_at"])
        require(settle>=1_000_000_000,"Stabilisation avant sondes trop courte.")
        values=sorted(a['connect_ms'] for a in flow['latency']['attempts'] if a['connect_ms'] is not None)
        distribution={'min':values[0],'max':values[-1],**{f'p{p}':values[math.ceil(len(values)*p/100)-1] for p in (50,95,99)}}
        equal(flow['latency']['connect_ms'],distribution,'Percentiles TCP non conformes aux tentatives.')
        drains=[v for v in samples if v["phase"]=="drain"]
        first_empty, drained = None, False
        for value in drains:
            if value['statistics']['backlog_bytes']==value['statistics']['queued_packets']==0:
                if first_empty is None:first_empty=value['elapsed_since_start_ms']
                drained=drained or value['elapsed_since_start_ms']-first_empty>=500
            else:first_empty=None
        require(drained,"Vidage normal non confirmé.")
        require(go.protocol.source_bytes(one("traffic_continue_intent")[1]["frame_base64"],1024)==collect.traffic.continue_frame(session),"Accusé non conforme.")
        require(one("traffic_continue_intent")[0]<one("traffic_continue_sent")[0]<one("traffic_group_stopped")[0],"Accusé hors ordre.")
    require(one("control_complete")[1]["cleanup_verified"] is True,"Nettoyage non attesté en fin de journal.")
    equal(one("traffic_group_stopped")[1],{"event":"traffic_group_stopped","driver_pid":group['driver_pid'],
          "driver_exit_code":group['driver_exit_code'],"reaped_descendants":group['reaped_descendants']},"Arrêt de groupe non concordant.")
    require(one("traffic_launched")[1]['driver_pid']==group['driver_pid'],"PID de lancement différent.")
    recorded_pids=[phase["worker_pid"],group["driver_pid"],*summary["tool_pids"],*ready["helper_pids"]]
    path_facts = None
    if path_validator is not None:
        path_facts = path_validator(folder, report, rows, normalized, expected_tools)
        recorded_pids += path_facts.pop("recorded_pids")
    result = {"session_id":session,"namespaces":names,"workspace":report["workspace"],"recorded_pids":recorded_pids,
            "go_worker_exit_code":0,"go_tool_calls":14,"go_journal_records":36,"traffic_driver_exit_code":group["driver_exit_code"],
            "reaped_traffic_helpers":group["reaped_descendants"],"received_bytes":None if crash else report["flow"]["receive"]["received_bytes"],
            "successful_probes":None if crash else report["flow"]["latency"]["successful"],"queue_samples":len(samples),"traffic_statistics_delta":delta}
    if path_facts is not None:
        result["path_check"] = path_facts
    return result


def verify_inputs(case, prepared):
    root=Path(prepared["project"])
    manifest=prepared["inputs_sha256"]
    lines=raw(case/"inputs.sha256",1024*1024).decode().splitlines()
    require(len(lines)==len(manifest) and {line[66:]:line[:64] for line in lines}==manifest,"Manifeste d’entrées incompatible.")
    for name,expected in manifest.items():
        path=root/name
        require(hashlib.sha256(raw(path,64*1024*1024)).hexdigest()==expected,"Entrée modifiée : "+name)
    for name in prepared["tracked_inputs"]:
        data=subprocess.check_output(["git","show",f'{prepared["source_commit"]}:{name}'],cwd=root,timeout=2)
        require(hashlib.sha256(data).hexdigest()==manifest[name],"Source différente du commit figé : "+name)
    return len(manifest)


def artifacts_snapshot(case):
    excluded={'validation.json','review.stdout.json','review.log','review.exit'}
    return {str(p.relative_to(case)):hashlib.sha256(raw(p,64*1024*1024)).hexdigest()
            for p in sorted(case.rglob('*')) if p.is_file() and p.name not in excluded}


def review(case, *, path_validator=None):
    case=case.resolve(strict=True)
    prepared_raw=raw(case/'prepared.json')
    seal=raw(case/'prepared.sha256',1024).decode().strip().split('  ',1)
    require(len(seal)==2 and seal[1]=='prepared.json' and seal[0]==hashlib.sha256(prepared_raw).hexdigest(),"Préparation modifiée.")
    prepared=go.protocol.document(prepared_raw,LIMIT)
    require(prepared["state"]=="not_run" and prepared["kind"]==("lab_cake_go_path_preparation" if path_validator is not None else "lab_cake_go_active_preparation"),"Préparation incompatible.")
    require(isinstance(prepared['source_commit'],str) and re.fullmatch(r'[0-9a-f]{40}',prepared['source_commit']),"Commit préparé invalide.")
    count=verify_inputs(case,prepared)
    before_artifacts=artifacts_snapshot(case)
    runtime=document(case/"runtime.json")
    require(runtime["kernel"]==prepared["kernel"] and runtime["python_version"]==prepared["python_version"],"Noyau ou Python modifié.")
    require((Path(prepared["project"])/'.go-version').read_text().strip()==prepared["go_version"].removeprefix('go'),"SDK préparé incompatible.")
    expected_build={"go_version":prepared["go_version"],"vcs":"git","vcs_revision":prepared["source_commit"],"vcs_modified":False}
    for name,info_name in prepared['build_info'].items():
        path=case/'bin'/name
        info=subprocess.check_output([prepared['go_executable'],'version','-m',str(path)],env={**os.environ,'GOTOOLCHAIN':'local'},text=True,timeout=3)
        require(info==raw(case/info_name,65536).decode(),"Provenance de compilation modifiée.")
        require(info.splitlines()[0].endswith(prepared['go_version']) and all(s in info for s in
                ('vcs.revision='+prepared['source_commit'],'vcs.modified=false','GOOS=linux','GOARCH=amd64')),"Binaire Go hors révision figée.")
    results={}
    for mode in ('check','check-crash'):
        require(raw(case/(mode+'.exit'),64)==b'0\n',"Code superviseur non nul.")
        report=document(case/mode/'report.json')
        equal(report,document(case/(mode+'.stdout.json')),"Stdout et rapport différents.")
        require(report['environment']['git_commit']==prepared['source_commit'],"Révision d’exécution différente.")
        require(report['environment']['kernel']==runtime['kernel']
                and report['environment']['python'].split()[0]==runtime['python_version'],"Environnement d’exécution différent.")
        results[mode]=validate_control(case/mode,report,prepared['tools'],prepared['supervisor_sources'],expected_build,path_validator=path_validator)
        if path_validator is not None:
            equal(report["environment"]["versions"]["ping"], prepared["ping_version"], "Producteur ping différent de la préparation.")
        log=raw(case/(mode+'.log'),4*1024*1024).decode()
        require(report['workspace'] in log and 'Processus récupérés et espaces du contrôle supprimés.' in log,"Journal de nettoyage incomplet.")
        for name in report['namespaces']:
            require(all(not os.path.lexists(base/name) for base in (Path('/run/netns'),Path('/var/run/netns'))),"Espace encore visible : "+name)
        require(not os.path.lexists(report['workspace']),"Réservation encore visible.")
        require(all(not Path('/proc',str(pid)).exists() for pid in results[mode]['recorded_pids']),"PID consigné encore visible ; aucune action automatique.")
    require(len({name for r in results.values() for name in r['namespaces']})==6,"Noms d’espaces réutilisés.")
    require(verify_inputs(case,prepared)==count,"Entrées modifiées pendant la relecture.")
    equal(artifacts_snapshot(case),before_artifacts,'Pièces modifiées pendant la relecture.')
    validation={"schema_version":1,"state":"native_cake_go_path_validated" if path_validator is not None else "native_cake_go_active_validated","source_commit":prepared['source_commit'],
                "reviewed_at":datetime.now(timezone.utc).isoformat(),"runtime":runtime,"frozen_inputs_verified":count,"results":results,
                "artifact_sha256":before_artifacts,
                "limits":["synthetic_ipv4_only","no_Coopace_benefit","no_household_restoration","no_Go_kill_during_tool"]}
    destination=case/'validation.json'
    if destination.exists():
        previous=document(destination)
        equal({k:v for k,v in validation.items() if k!='reviewed_at'},{k:v for k,v in previous.items() if k!='reviewed_at'},"Validation existante différente ; conservée.")
    else:go.save(destination,validation)
    return validation
