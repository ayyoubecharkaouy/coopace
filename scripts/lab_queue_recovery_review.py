"""Read-only replay of one completed queue-recovery lab's retained evidence."""

import importlib.util
from pathlib import Path
import re
import subprocess

spec = importlib.util.spec_from_file_location("review_queue_recovery_model", Path(__file__).with_name("lab_queue_recovery.py"))
model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)
runtime, require = model.runtime, model.require


def review(folder, gateway, *, session=False, sources=None):
    folder = Path(folder).resolve(strict=True)
    report = runtime.document(runtime.read(folder / "report.json"))
    require(type(report.get("schema_version")) is int and report.get("schema_version") == 1 and report.get("kind") == ("lab_gateway_session" if session else "lab_queue_recovery")
            and report.get("mode") in ("check", "check-crash") and report.get("state") == "complete",
            "Contrôle complet de restauration requis.")
    for field in ("applied_verified", "root_removed", "restoration_verified", "cleanup_verified"):
        require(report.get(field) is True, "Preuve absente : " + field)
    require(report.get("traffic_generated") is False and report.get("real_gateway_restoration_validated") is False,
            "Portée du laboratoire incohérente.")
    expected = -9 if report["mode"] == "check-crash" else 0
    require(type(report.get("driver_exit_code")) is int and report["driver_exit_code"] == expected
            and type(report.get("reaped_descendants")) is int and report.get("reaped_descendants") == (0 if session else 1)
            and type(report.get("interruption_code")) is int and report.get("interruption_code") == 0,
            "Fin du pilote non conforme.")
    files = report.get("artifacts_sha256")
    require(isinstance(files, dict) and len(files) >= 12, "Inventaire de preuves manquant.")
    for name, expected_hash in files.items():
        require(isinstance(name, str) and Path(name).name == name and name not in (".", "..", "report.json")
                and isinstance(expected_hash, str) and re.fullmatch(r"[a-f0-9]{64}", expected_hash),
                "Entrée de preuve invalide.")
        require(runtime.digest(runtime.read(folder / name)) == expected_hash, "Preuve modifiée : " + name)
    for name in ("events.jsonl", "environment.json", "before.json", "plan.json", "pre-add.json", "pre-add-check.json",
                 "applied.json", "pre-restore.json", "after.json", "comparison.json"):
        require(name in files, "Preuve requise absente : " + name)
    environment = runtime.document(runtime.read(folder / "environment.json"))
    require(environment.get("source_sha256") == (sources if sources is not None else model.source_hashes()), "Sources du contrôle modifiées.")
    tool = environment["tools"]["gateway"]
    gateway = Path(gateway).resolve(strict=True)
    require(str(gateway) == tool["path"] and runtime.digest(runtime.read(gateway, 64 * 1024 * 1024)) == tool["sha256"],
            "Binaire Go différent de celui du contrôle.")
    events = [runtime.document(line) for line in runtime.read(folder / "events.jsonl").splitlines()]
    require([event.get("sequence") for event in events] == list(range(1, len(events)+1)), "Séquence du journal incohérente.")
    driver_states = () if session else ("driver_starting", "driver_namespace_verified")
    states = ("namespace_bindings_retained", "baseline_verified", "add_intent", "owned_cake_verified",
        *driver_states, "driver_group_stopped", "remove_intent",
        "owned_root_removed", "selected_initial_state_verified", "namespace_bindings_closed")
    ordered = []
    for state in states:
        positions = [index for index,event in enumerate(events) if event.get("state") == state]
        require(len(positions) == 1, "Événement unique requis : " + state)
        ordered.extend(positions)
    require(ordered == sorted(ordered), "Restauration ou fermeture dans un ordre incorrect.")
    names = report.get("namespaces")
    require(isinstance(names, list) and len(names) == 3 and all(isinstance(name,str) and re.fullmatch(r"cg-[a-z0-9_]{8}-[cgs]",name) for name in names),
            "Noms de namespaces invalides.")
    token = names[0][3:-2]
    require(names == [f"cg-{token}-{role}" for role in ("c","g","s")], "Ressources de plusieurs réservations.")
    retained = events[ordered[0]]
    require(retained.get("namespaces") == [{"name":name,"identity":identity}
        for name,identity in zip(names,report["namespace_identities"])], "Identités retenues incohérentes.")
    identities = report["namespace_identities"]
    require(len(identities) == 3 and all(isinstance(identity,list) and len(identity)==2
        and all(type(v) is int and v > 0 for v in identity) for identity in identities)
        and len({tuple(identity) for identity in identities}) == 3
        and retained.get("origin_identity") not in identities, "Identités de namespaces non distinctes.")
    position = {state: index for state,index in zip(states,ordered)}
    if not session:
        require(events[position["driver_namespace_verified"]].get("identity") == identities[1], "Namespace du pilote non confirmé.")
    stopped = events[position["driver_group_stopped"]]
    require(stopped.get("exit_code") == expected and stopped.get("reaped_descendants") == (0 if session else 1),
            "Récupération du groupe non confirmée.")
    intents = [event for event in events if event.get("state") == "command_intent"]
    results = [event for event in events if event.get("state") == "command_result"]
    require([event.get("command") for event in intents] == list(range(1,len(intents)+1))
            and [event.get("command") for event in results] == list(range(1,len(intents)+1)), "Commandes non appariées.")
    for event in results:
        require(event.get("group_stopped") is True and event.get("error") is None
                and event.get("exit_code") in (0,3), "Commande non terminée correctement.")
    tc = "/proc/self/fd/" + str(environment["tool_descriptors"]["tc"])
    prefix = ["netns", "exec", names[1], tc, "qdisc"]
    mutations = [event for event in intents if event.get("tool") == "ip" and event.get("arguments",[])[:5] == prefix]
    require([event["arguments"] for event in mutations] == [
        [*prefix,"add","dev","wan","root","handle","10:",*model.cake.ARGUMENTS],
        [*prefix,"del","dev","wan","root","handle","10:"]], "Mutations de file non conformes.")
    require(events[position["add_intent"]]["sequence"] < mutations[0]["sequence"] < events[position["owned_cake_verified"]]["sequence"]
            and events[position["remove_intent"]]["sequence"] < mutations[1]["sequence"] < events[position["owned_root_removed"]]["sequence"],
            "Intention non antérieure à sa mutation.")
    root_args = ["netns","exec",names[1],tc,"-j","-s","-r","qdisc","show","dev","wan"]
    root_reads = [event for event in intents if event.get("tool") == "ip" and event.get("arguments") == root_args]
    require(len(root_reads) == 2, "Deux relectures indépendantes de CAKE requises.")
    for event in root_reads:
        name = f"command-{event['command']:03d}.stdout"
        require(name in files, "Relevé CAKE non lié à l'inventaire.")
        model.owned_cake(runtime.read(folder/name))
    plan = runtime.document(runtime.read(folder/"plan.json"))
    require(plan.get("decision") == "candidate_for_lab_validation" and plan.get("profile") == "noqueue-root-v1"
            and plan.get("before_sha256") == files["before.json"], "Profil initial non confirmé.")
    for name in names:
        require(not (Path("/run/netns") / name).exists() and not (Path("/var/run/netns") / name).exists(), "Namespace encore visible.")
    workspace = Path(report["workspace"])
    require(workspace.is_absolute() and workspace.name == "coopace-guard."+token and not workspace.exists(), "Réservation encore visible ou incohérente.")
    pids = [report.get("driver_pid"), *([] if session else [report.get("descendant_pid")]), *[event.get("pid") for event in results]]
    require(all(type(pid) is int and pid > 1 and not Path("/proc",str(pid)).exists() for pid in pids), "PID enregistré encore visible.")
    completed = subprocess.run([str(gateway), "restore-check", "--before", str(folder/"before.json"),
        "--after", str(folder/"after.json"), "--json"], stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10, check=True)
    compared = runtime.document(completed.stdout)
    original = runtime.document(runtime.read(folder/"comparison.json"))
    for value in (original, compared):
        require(value.get("kind") == "queue_recovery_check" and value.get("decision") == "selected_state_matches"
            and value.get("before_sha256") == files["before.json"] and value.get("after_sha256") == files["after.json"]
            and value.get("execution_authorized") is False and value.get("network_changes_executed") is False,
            "Comparaison des états non reproductible.")
    return {"schema_version":1, "kind":"lab_queue_recovery_review", "mode":report["mode"],
        "state":"queue_recovery_evidence_reviewed", "native_certificate":False,
        "execution_source":"simulated" if environment.get("simulation") is True else "native_control_report",
        "artifacts_verified":len(files), "selected_state_matches":True, "cleanup_observed":True,
        "report_sha256":runtime.digest(runtime.read(folder/"report.json")),
        "real_gateway_restoration_validated":False}
