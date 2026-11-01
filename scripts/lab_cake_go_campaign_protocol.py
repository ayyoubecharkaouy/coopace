"""Pure campaign framing and phase order; no process, clock or network action."""

import importlib.util
import json
import math
from pathlib import Path


spec = importlib.util.spec_from_file_location("campaign_single_flow", Path(__file__).with_name("lab_cake_go_traffic.py"))
traffic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(traffic)

PHASES = ((1, "idle"), (1, "loaded"), (2, "loaded"), (2, "idle"), (3, "idle"), (3, "loaded"))
FRAME_LIMIT = 1024
END_LIMIT = 256 * 1024
EVENT_BUDGET = 2 * 1024 * 1024
CONTROL_BUDGET = 18 * FRAME_LIMIT
EVENT_KIND = "lab_cake_go_campaign_event"
CONTROL_KIND = "lab_cake_go_campaign_control"
COMMON = {"schema_version", "kind", "session_id"}
PHASE_FIELDS = {"pair", "condition"}


class Error(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise Error(message)


def session_id(value):
    try:
        return traffic.session_id(value)
    except traffic.Error as error:
        raise Error(str(error)) from error


def _document(raw, limit):
    require(type(raw) is bytes and 0 < len(raw) <= limit and raw.endswith(b"\n")
            and raw.count(b"\n") == 1 and b"\r" not in raw, "Ligne absente, tronquée, multiple ou trop grande.")
    def unique(pairs):
        value = {}
        for key, item in pairs:
            require(key not in value, "Clé JSON dupliquée.")
            value[key] = item
        return value
    def invalid(_):
        raise Error("Nombre JSON non fini.")
    def finite(value):
        number = float(value)
        require(math.isfinite(number), "Nombre JSON non fini.")
        return number
    try:
        value = json.loads(raw[:-1].decode("utf-8"), object_pairs_hook=unique,
                           parse_constant=invalid, parse_float=finite)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise Error("JSON UTF-8 illisible : " + str(error)) from error
    require(isinstance(value, dict), "Objet JSON de dialogue requis.")
    return value


def _header(value, session, kind):
    session_id(session)
    require(type(value.get("schema_version")) is int and value["schema_version"] == 1
            and value.get("kind") == kind and value.get("session_id") == session,
            "Message hors version, direction ou session.")


def _phase(value):
    require(type(value.get("pair")) is int and value["pair"] in (1, 2, 3)
            and value.get("condition") in ("idle", "loaded"), "Phase invalide.")


def _result(value, condition):
    try:
        require(isinstance(value, dict), "Résultat de phase absent.")
        require(type(value.get("measurement_exit_code")) is int, "Code de mesure entier requis.")
        if condition == "loaded":
            return traffic.validated_flow(value)
        require(set(value) == {"latency", "measurement_exit_code"}, "Résultat idle incompatible.")
        traffic.active.latency_document(value["latency"], "idle", value["measurement_exit_code"])
        return value
    except Error:
        raise
    except Exception as error:
        raise Error("Résultat de phase invalide : " + str(error)) from error


def parse_event(raw, session):
    value = _document(raw, END_LIMIT)
    _header(value, session, EVENT_KIND)
    event = value.get("event")
    require(event in ("begin", "ready", "end", "complete"), "Événement de campagne inconnu.")
    fields = COMMON | {"event"}
    if event != "complete":
        fields |= PHASE_FIELDS
        _phase(value)
    if event == "ready":
        fields.add("helper_pids")
    elif event == "end":
        fields.add("result")
    require(set(value) == fields, "Champs d’événement incompatibles.")
    require(len(raw) <= (END_LIMIT if event == "end" else FRAME_LIMIT), "Événement trop grand.")
    if event == "ready":
        pids, count = value["helper_pids"], 1 if value["condition"] == "idle" else 3
        require(isinstance(pids, list) and len(pids) == count and all(type(p) is int and p > 0 for p in pids)
                and len(set(pids)) == count, "PID d’outils invalides pour la phase.")
    elif event == "end":
        value["result"] = _result(value["result"], value["condition"])
    return value


def parse_control(raw, session):
    value = _document(raw, FRAME_LIMIT)
    _header(value, session, CONTROL_KIND)
    require(set(value) == COMMON | PHASE_FIELDS | {"action"}, "Champs de contrôle incompatibles.")
    _phase(value)
    require(value["action"] in ("start", "continue", "advance"), "Action de campagne inconnue.")
    return value


def _wire(value):
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8") + b"\n"
    except (TypeError, ValueError, UnicodeError, RecursionError) as error:
        raise Error("Message impossible à encoder.") from error


def event_frame(session, event, *, pair=None, condition=None, **payload):
    value = {"schema_version": 1, "kind": EVENT_KIND, "session_id": session, "event": event, **payload}
    if pair is not None:
        value["pair"] = pair
    if condition is not None:
        value["condition"] = condition
    raw = _wire(value)
    parse_event(raw, session)
    return raw


def control_frame(session, pair, condition, action):
    raw = _wire({"schema_version": 1, "kind": CONTROL_KIND, "session_id": session,
                 "pair": pair, "condition": condition, "action": action})
    parse_control(raw, session)
    return raw


class LineReader:
    """Byte framing only. EOF and phase acceptance still belong to Dialogue."""
    def __init__(self, session, direction):
        self.session = session_id(session)
        require(direction in ("events", "controls"), "Direction de flux invalide.")
        self.direction = direction
        self.limit = END_LIMIT if direction == "events" else FRAME_LIMIT
        self.budget = EVENT_BUDGET if direction == "events" else CONTROL_BUDGET
        self.max_messages = 19 if direction == "events" else 18
        self.pending, self.total, self.messages = bytearray(), 0, 0
        self.closed, self.failure = False, None

    def feed(self, data):
        require(self.failure is None, "Lecteur déjà refusé.")
        try:
            require(not self.closed and type(data) is bytes, "Flux fermé ou fragment de type incorrect.")
            require(self.total + len(data) <= self.budget, "Budget cumulé du flux dépassé.")
            self.total += len(data)
            result, offset = [], 0
            while offset < len(data):
                newline = data.find(b"\n", offset)
                stop = len(data) if newline < 0 else newline + 1
                require(len(self.pending) + stop - offset <= self.limit, "Ligne fragmentée trop grande.")
                self.pending.extend(data[offset:stop])
                offset = stop
                if newline >= 0:
                    require(self.messages < self.max_messages, "Trop de messages dans le flux.")
                    parse = parse_event if self.direction == "events" else parse_control
                    result.append(parse(bytes(self.pending), self.session))
                    self.messages += 1
                    self.pending.clear()
                else:
                    require(len(self.pending) < self.limit, "Ligne sans place pour LF.")
            return result
        except Exception as error:
            self.failure = error
            raise

    def finish(self):
        require(self.failure is None, "Lecteur déjà refusé.")
        try:
            require(not self.pending, "EOF au milieu d’une ligne.")
            self.closed = True
        except Exception as error:
            self.failure = error
            raise


class Dialogue:
    """Order validator only; it does not authorize starts, probes or cleanup."""
    def __init__(self, session):
        self.session = session_id(session)
        self.index, self.state, self.failure = 0, "begin", None
        self.events_closed, self.controls_closed = False, False

    @property
    def phase(self):
        return PHASES[self.index] if self.index < len(PHASES) else None

    @property
    def complete(self):
        return self.state == "finished" and self.events_closed and self.controls_closed and self.failure is None

    def _accept(self, raw, control):
        require(self.failure is None, "Dialogue déjà refusé.")
        try:
            require(not (self.controls_closed if control else self.events_closed), "Message après EOF.")
            value = parse_control(raw, self.session) if control else parse_event(raw, self.session)
            action = value["action"] if control else value["event"]
            expected_control = self.state in ("start", "continue", "advance")
            require(self.state != "finished" and control == expected_control and action == self.state,
                    "Message prématuré, répété ou hors ordre.")
            if action != "complete":
                require((value["pair"], value["condition"]) == self.phase, "Message d’une autre phase.")
            if control:
                if action == "advance":
                    self.index += 1
                    self.state = "begin" if self.index < len(PHASES) else "complete"
                else:
                    self.state = "ready" if action == "start" else "end"
            else:
                self.state = {"begin": "start", "ready": "continue", "end": "advance", "complete": "finished"}[action]
            return value
        except Exception as error:
            self.failure, self.state = error, "failed"
            raise

    def event(self, raw):
        return self._accept(raw, False)

    def control(self, raw):
        return self._accept(raw, True)

    def _eof(self, control):
        require(self.failure is None, "Dialogue déjà refusé.")
        try:
            require(self.state in (("complete", "finished") if control else ("finished",)), "EOF avant fin du dialogue.")
            if control:
                self.controls_closed = True
            else:
                self.events_closed = True
        except Exception as error:
            self.failure, self.state = error, "failed"
            raise

    def finish_events(self):
        self._eof(False)

    def finish_controls(self):
        self._eof(True)
