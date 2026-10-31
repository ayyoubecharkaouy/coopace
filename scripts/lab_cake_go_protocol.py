"""Bounded internal Go-worker messages and durable proof validation."""

import base64
from datetime import datetime
import importlib.util
import json
import math
import struct

from pathlib import Path

spec = importlib.util.spec_from_file_location("cake_go_reference", Path(__file__).with_name("lab_cake.py"))
cake = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cake)
Error = cake.Error
REFERENCE = "cake-ipv4-lab-4mbit-v1"
EVENT_LIMIT = 128 * 1024
OUTPUT_LIMIT = 512 * 1024
JOURNAL_LIMIT = 8 * 1024 * 1024
RECORD_LIMIT = 256 * 1024
LINK = ["-j", "-d", "link", "show"]
ADDRESS = ["-j", "address", "show", "dev", "wan"]
SHOW = ["-j", "-s", "-r", "qdisc", "show", "dev", "wan"]
ADD = ["qdisc", "add", "dev", "wan", "root", "handle", "10:", *cake.ARGUMENTS]
CALLS = [("tc", ["-V"]), ("ip", LINK), ("ip", ADDRESS), ("tc", SHOW),
         ("ip", LINK), ("ip", ADDRESS), ("tc", SHOW), ("tc", ADD),
         ("ip", LINK), ("ip", ADDRESS), ("tc", SHOW),
         ("ip", LINK), ("ip", ADDRESS), ("tc", SHOW)]


def require(condition, message):
    if not condition:
        raise Error(message)


def document(raw, limit):
    require(0 < len(raw) <= limit, "Taille du document interne invalide.")
    def unique(pairs):
        value = {}
        for key, item in pairs:
            require(key not in value, "Champ interne dupliqué.")
            value[key] = item
        return value
    def finite(text):
        value = float(text)
        require(math.isfinite(value), "Nombre interne non fini.")
        return value
    def invalid(_):
        raise Error("Nombre interne non fini.")
    try:
        result = json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                            parse_float=finite, parse_constant=invalid)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise Error("JSON interne illisible.") from error
    pending = [(result, 0)]
    while pending:
        value, depth = pending.pop()
        require(depth <= 16, "Document interne trop imbriqué.")
        if isinstance(value, dict):
            pending.extend((v, depth + 1) for v in value.values())
        elif isinstance(value, list):
            pending.extend((v, depth + 1) for v in value)
    require(isinstance(result, dict), "Objet interne requis.")
    return result


def encode(value, limit):
    raw = json.dumps(value, separators=(",", ":"), allow_nan=False).encode()
    require(0 < len(raw) <= limit, "Message de contrôle trop volumineux.")
    return struct.pack("!I", len(raw)) + raw


def event(raw, session, expected):
    value = document(raw, EVENT_LIMIT)
    fields = {"schema_version", "kind", "session_id", "event", "reference"}
    if expected == "applied":
        fields |= {"producer_profile", "qdisc"}
    require(set(value) == fields and type(value["schema_version"]) is int and value["schema_version"] == 1
            and value["kind"] == "lab_cake_worker_event" and value["session_id"] == session
            and value["event"] == expected and value["reference"] == REFERENCE,
            "Événement Go incompatible ou hors ordre.")
    if expected == "applied":
        require(value["producer_profile"] == cake.PROFILE, "Producteur Go incompatible.")
        cake.statistics(json.dumps(value["qdisc"]).encode(), cake.PROFILE)
    return value


def timestamp(value):
    require(isinstance(value, str) and len(value) <= 64, "Horodatage de preuve invalide.")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise Error("Horodatage de preuve illisible.") from error
    require(result.utcoffset() is not None and result.utcoffset().total_seconds() == 0,
            "Horodatage UTC requis.")


def source_bytes(value, limit):
    if value is None:
        return b""
    require(isinstance(value, str) and len(value) <= 4 * ((limit + 2) // 3), "Sortie encodée trop grande.")
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, base64.binascii.Error) as error:
        raise Error("Sortie encodée invalide.") from error
    require(len(raw) <= limit, "Sortie d’outil trop grande.")
    return raw


def _journal(raw, session, tools, target, original, worker_pid, stage, applied=None):
    """Accept only a complete, successful prefix appropriate to the handshake."""
    require(stage in ("ready", "applied", "finished"), "Phase de journal inconnue.")
    require(0 < len(raw) <= JOURNAL_LIMIT and raw.endswith(b"\n"), "Journal Go vide, trop grand ou tronqué.")
    rows = [document(line, RECORD_LIMIT) for line in raw.splitlines()]
    require(rows, "Journal Go absent.")
    elapsed = -1
    for sequence, row in enumerate(rows, 1):
        require(set(row) == {"schema_version", "kind", "session_id", "sequence", "event", "recorded_at", "elapsed_ns", "data"}
                and type(row["schema_version"]) is int and row["schema_version"] == 1
                and row["kind"] == "lab_cake_worker_journal" and row["session_id"] == session
                and type(row["sequence"]) is int and row["sequence"] == sequence
                and type(row["elapsed_ns"]) is int and row["elapsed_ns"] >= 0 and row["elapsed_ns"] >= elapsed,
                "Séquence/identité du journal Go incompatible.")
        elapsed = row["elapsed_ns"]
        timestamp(row["recorded_at"])
    header = rows[0]["data"]
    require(rows[0]["event"] == "launch" and isinstance(header, dict)
            and header["pid"] == worker_pid and type(header["pid"]) is int
            and header["purpose"] == "cake_down_control" and header["reference"] == REFERENCE
            and header["os"] == "linux" and header["architecture"] == "amd64"
            and header["target_namespace"] == target and header["original_namespace"] == original
            and all(header[f"{name}_tool"] == tools[name] for name in ("ip", "tc")),
            "Contexte observé du journal Go incompatible.")
    require(isinstance(header["coopace_version"], str) and isinstance(header["build"], dict)
            and isinstance(header["build"].get("go_version"), str), "Provenance Go absente.")
    expected = ["launch", "context_accepted"]
    count = 4 if stage == "ready" else 11 if stage == "applied" else 14
    for index in range(count):
        if index == 4:
            expected += ["ready", "apply_received"]
        if index == 11:
            expected += ["applied", "finish_received"]
        expected += ["tool_intent", "tool_result"]
    expected += ["ready"] if stage == "ready" else ["applied"] if stage == "applied" else ["final_verified", "worker_exit"]
    require([r["event"] for r in rows] == expected, "Journal Go incomplet, prématuré ou hors ordre.")
    require(rows[1]["data"] == {"reference": REFERENCE}, "Référence du contexte Go incompatible.")
    intents = [r["data"] for r in rows if r["event"] == "tool_intent"]
    results = [r["data"] for r in rows if r["event"] == "tool_result"]
    add_count, pids, readings = 0, [], []
    for index, (intent, result) in enumerate(zip(intents, results)):
        name, args = CALLS[index]
        required = {"path": tools[name]["path"], "sha256": tools[name]["sha256"], "arguments": args}
        require(intent == required and all(result[k] == v for k, v in required.items()), "Outil/arguments du journal Go incompatibles.")
        require(type(result["pid"]) is int and result["pid"] > 0 and result["pid"] != worker_pid
                and type(result["exit_code"]) is int and result["exit_code"] == 0
                and type(result["duration_ns"]) is int and 0 < result["duration_ns"] < 2_200_000_000
                and result["error"] == "" and result["stdout_truncated"] is False and result["stderr_truncated"] is False,
                "Appel d’outil Go non terminé ou non conforme.")
        timestamp(result["started_at"])
        output = source_bytes(result["stdout_base64"], 512 if args == ["-V"] else 65536)
        source_bytes(result["stderr_base64"], 65536)
        pids.append(result["pid"])
        if name == "tc" and args == ["-V"]:
            cake.producer(output)
        elif name == "tc" and args == SHOW:
            if index in (3, 6):
                cake.queue.initial_qdisc(output)
            else:
                cake.statistics(output, cake.PROFILE)
                readings.append(cake.queue.document(output))
        elif name == "tc" and args == ADD:
            add_count += 1
    require(add_count == (0 if stage == "ready" else 1), "Nombre d’ajouts Go incompatible.")
    for row in rows:
        if row["event"] == "applied":
            require(row["data"] == {"producer_profile": cake.PROFILE}, "Profil appliqué non confirmé.")
    if applied is not None:
        require(readings and readings[0] == applied["qdisc"], "Événement applied différent du relevé durable.")
    if stage == "finished":
        exit_data = rows[-1]["data"]
        require(type(exit_data["intended_exit_code"]) is int and exit_data["add_attempted"] is True
                and exit_data["traffic_generated"] is False and exit_data["active_path_verified"] is False,
                "Types de fin Go incompatibles.")
        require(rows[-1]["data"] == {"intended_exit_code": 0, "backend_state": "finished", "add_attempted": True,
                "error": "", "cleanup": "not_attested", "traffic_generated": False, "active_path_verified": False},
                "Fin Go incompatible ; aucun nettoyage n’est attesté par l’enfant.")
    return {"records": len(rows), "tool_calls": count, "tool_pids": pids,
            "build": header["build"], "coopace_version": header["coopace_version"]}


def journal(*args, **kwargs):
    try:
        return _journal(*args, **kwargs)
    except (KeyError, TypeError, ValueError, IndexError) as error:
        raise Error("Structure du journal Go incompatible.") from error
