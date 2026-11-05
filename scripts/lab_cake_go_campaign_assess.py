"""Pure measurement assessment; ownership and native evidence are external."""

from decimal import Decimal
from fractions import Fraction
import importlib.util
import math
from pathlib import Path

spec = importlib.util.spec_from_file_location("assessment_protocol", Path(__file__).with_name("lab_cake_go_campaign_protocol.py"))
protocol = importlib.util.module_from_spec(spec)
spec.loader.exec_module(protocol)
active = protocol.traffic.active
stamp = active.series.timestamp_ns
COUNTERS = ("bytes", "packets", "drops", "overlimits", "requeues")
Error, require = protocol.Error, protocol.require


def utc_ns(value):
    require(isinstance(value, str), "Horodatage absent.")
    try:
        return stamp(value[:-6] + "Z" if value.endswith("+00:00") else value)
    except active.series.ExperimentError as error:
        raise Error(str(error)) from error


def quantiles(latency):
    values = sorted(Decimal(str(a["connect_ms"])) for a in latency["attempts"] if a["connect_ms"] is not None)
    return {name: values[(len(values) * rank + 99) // 100 - 1] if values else None
            for name, rank in (("p50", 50), ("p95", 95), ("p99", 99))}


def distribution(latency):
    """Nearest rank, preserving missing values and individual failures."""
    return {"successful": latency["successful"], "failed": latency["failed"],
            **{key: float(value) if value is not None else None for key, value in quantiles(latency).items()}}


def statistics(readings):
    require(isinstance(readings, list) and 2 <= len(readings) <= 720, "Au moins deux relevés bornés requis.")
    previous_time, previous = None, None
    for reading in readings:
        when = utc_ns(reading["collected_at"])
        require(previous_time is None or when > previous_time, "Relevés hors ordre ou dupliqués.")
        counters = reading["statistics"]["counters"]
        require(set(counters) == set(COUNTERS) and all(type(counters[k]) is int and 0 <= counters[k] < 2**64 for k in COUNTERS),
                "Compteurs invalides.")
        require(previous is None or all(counters[k] >= previous[k] for k in COUNTERS), "Compteur remis à zéro.")
        previous_time, previous = when, counters
    return {"available": True, "reason": None,
            "counters": {k: readings[-1]["statistics"]["counters"][k] - readings[0]["statistics"]["counters"][k] for k in COUNTERS}}


def rate_in_range(volume, elapsed_ns):
    """Exact inclusive boundaries; never classify a rounded display value."""
    return 350000 * elapsed_ns <= volume * 1_000_000_000 <= 525000 * elapsed_ns


def _phase(phase, pair, condition):
    require(type(phase["pair"]) is int and phase["pair"] == pair and phase["condition"] == condition
            and phase["state"] == "complete", "Phase absente, interrompue ou hors ordre.")
    result = protocol._result(phase["result"], condition)
    latency = result["latency"]
    samples = phase["samples"]
    require(all(s.get("pair") == pair and type(s.get("pair")) is int and s.get("condition") == condition for s in samples),
            "Relevé d’une autre phase.")
    delta = statistics(samples)
    require(samples[0].get("phase") == "before_start" and samples[-1].get("phase") == "drain", "Ancres de phase absentes.")
    start, end = utc_ns(latency["started_at"]), utc_ns(latency["finished_at"])
    require(utc_ns(samples[0]["collected_at"]) <= start <= end <= utc_ns(samples[-1]["collected_at"]),
            "Mesure hors des relevés de phase.")
    summary = {"pair": pair, "condition": condition, "latency": distribution(latency), "statistics_delta": delta}
    if condition == "loaded":
        send, receive = result["send"], result["receive"]
        require(all(utc_ns(samples[0]["collected_at"]) <= utc_ns(document["started_at"])
                    <= utc_ns(document["finished_at"]) <= utc_ns(samples[-1]["collected_at"])
                    for document in (send, receive)), "Transfert hors des relevés de phase.")
        settle_ns = start - utc_ns(send["first_write_at"])
        require(settle_ns >= 1_000_000_000 and result["probe_window_inside_application_writes"],
                "Stabilisation ou recouvrement insuffisant.")
        # readReceipt measures from the first progressing Read through EOF,
        # using Go's monotonic clock. last_read_at marks the last payload Read;
        # serialized UTC times do not retain the monotonic clock component.
        require(utc_ns(receive["finished_at"]) > utc_ns(receive["first_read_at"]), "Fenêtre de réception vide.")
        duration = Fraction(Decimal(str(receive["receive_elapsed_ms"]))) * 1_000_000
        rate = Fraction(receive["received_bytes"] * 1_000_000_000) / duration
        require(math.isclose(receive["average_bytes_per_second"], float(rate), rel_tol=1e-9), "Débit de réception incohérent.")
        window = [s for s in samples if start <= utc_ns(s["collected_at"]) <= end]
        progress = statistics(window)
        summary.update(settle_ms=settle_ns / 1_000_000, probe_window_samples=len(window),
                       probe_window_statistics_delta=progress,
                       bytes_progress_during_probes=progress["counters"]["bytes"] > 0,
                       received_bytes_per_second=float(rate), receive_rate_in_range=rate_in_range(receive["received_bytes"], duration))
    return summary


def assess(phases, *, crash=False):
    """Assess measurement data only, never emit technical_valid or a certificate.

    Malformed data produce a non-exploitable assessment with reasons. No input
    is mutated and no stored percentile, delta or qualification is trusted.
    """
    decision = {"schema_version": 1, "kind": "lab_cake_go_campaign_measurements", "measurements_valid": None,
                "load_scenario": "not_assessed", "connections": "not_assessed", "phases": [], "pairs": [], "reasons": [],
                "congestion": "not_assessed", "comparison": "not_assessed", "coopace_benefit": "not_assessed"}
    if type(crash) is not bool:
        raise Error("Mode de panne booléen requis.")
    if crash:
        return decision
    try:
        require(isinstance(phases, list) and len(phases) == 6, "Six phases requises.")
        require(sum(len(p["samples"]) for p in phases) <= 720, "Budget de relevés dépassé.")
        previous_end = None
        for phase, (pair, condition) in zip(phases, protocol.PHASES):
            summary = _phase(phase, pair, condition)
            require(previous_end is None or utc_ns(phase["samples"][0]["collected_at"]) > previous_end,
                    "Phases superposées ou hors ordre.")
            previous_end = utc_ns(phase["samples"][-1]["collected_at"])
            decision["phases"].append(summary)
        # Check continuity even across the boundaries of consecutive phases.
        statistics([s for p in phases for s in p["samples"]])
        for pair in (1, 2, 3):
            members = {s["condition"]: s for s in decision["phases"] if s["pair"] == pair}
            idle, loaded = members["idle"]["latency"], members["loaded"]["latency"]
            exact = {p["condition"]: quantiles(p["result"]["latency"]) for p in phases if p["pair"] == pair}
            differences = {name + "_loaded_minus_idle_ms": float(exact["loaded"][name] - exact["idle"][name])
                           if exact["loaded"][name] is not None and exact["idle"][name] is not None else None
                           for name in ("p50", "p95", "p99")}
            decision["pairs"].append({"pair": pair, **differences,
                                      "idle_failed": idle["failed"], "loaded_failed": loaded["failed"]})
        qualified = all(s["bytes_progress_during_probes"] and s["receive_rate_in_range"]
                        for s in decision["phases"] if s["condition"] == "loaded")
        decision.update(measurements_valid=True, load_scenario="qualified" if qualified else "not_qualified",
                        connections="confirmed" if all(s["latency"]["successful"] == 10 for s in decision["phases"]) else "degraded")
    except (ValueError, TypeError, KeyError, OverflowError, IndexError, AttributeError, RecursionError) as error:
        decision.update(measurements_valid=False, load_scenario="non_exploitable", reasons=[str(error)])
    return decision
