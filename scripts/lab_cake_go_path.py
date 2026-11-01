"""Pure readers for the planned IPv4 passage check; no process or network I/O."""

from decimal import Decimal
import re


TARGET = "10.203.0.6"
OUTPUT_LIMIT = 64 * 1024
SUMMARY = re.compile(
    r"(?P<transmitted>[0-9]{1,10}) packets transmitted, "
    r"(?P<received>[0-9]{1,10}) (?:packets )?received, "
    r"(?:\+(?P<errors>[0-9]{1,10}) errors, )?"
    r"(?P<loss>[0-9]{1,3}(?:\.[0-9]{1,6})?)% packet loss, "
    r"time (?P<elapsed>[0-9]{1,10})ms"
)


class Error(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise Error(message)


def state(value):
    require(type(value) is int and value in (0, 1), "État de forwarding strictement 0 ou 1 requis.")
    return value


def validate_forwarding(stdout, expected):
    """Read the single C-locale line emitted by sysctl -n; not a path proof."""
    state(expected)
    require(type(stdout) is bytes and stdout == f"{expected}\n".encode("ascii"),
            "Relecture du forwarding absente, ambiguë ou différente.")
    return expected


def validate_probe(stdout, exit_code, *, forwarding):
    """Validate one pinned iputils/C capture; a code alone never proves blocking.

    The caller must separately establish tool identity, arguments, owned
    namespace, forwarding readback, ordering, deadline and final cleanup.
    """
    state(forwarding)
    require(type(stdout) is bytes and 0 < len(stdout) <= OUTPUT_LIMIT,
            "Capture ICMP absente, de type incorrect ou trop volumineuse.")
    require(stdout.endswith(b"\n"), "Capture ICMP tronquée avant la fin de ligne.")
    require(type(exit_code) is int and exit_code == (0 if forwarding else 1),
            "Code ICMP incompatible ; erreur technique ou résultat inattendu.")
    try:
        text = stdout.decode("ascii")
    except UnicodeError as error:
        raise Error("Capture ICMP hors du format iputils en locale C.") from error
    require(all(c in "\n\t" or 32 <= ord(c) < 127 for c in text), "Caractère de contrôle ICMP inattendu.")
    lines = text.splitlines()
    require(lines[0] == f"PING {TARGET} ({TARGET}) 56(84) bytes of data.", "Cible ou en-tête ICMP inattendu.")
    headings = [i for i, line in enumerate(lines) if "ping statistics" in line]
    summaries = [i for i, line in enumerate(lines) if "packets transmitted" in line]
    require(len(headings) == len(summaries) == 1
            and lines[headings[0]] == f"--- {TARGET} ping statistics ---"
            and summaries[0] == headings[0] + 1, "Résumé ICMP absent, répété ou mal rattaché.")
    match = SUMMARY.fullmatch(lines[summaries[0]])
    require(match is not None, "Résumé ICMP incomplet ou non pris en charge.")
    transmitted, received = int(match["transmitted"]), int(match["received"])
    errors = int(match["errors"] or "0")
    expected_count, expected_received = (3, 3) if forwarding else (1, 0)
    require(transmitted == expected_count and received == expected_received,
            "Nombre d’envois ou de réponses ICMP incompatible.")
    expected_loss = 0 if forwarding else 100
    require(Decimal(match["loss"]) == expected_loss, "Perte ICMP déclarée incompatible avec les comptes.")
    require(errors <= transmitted and (not forwarding or errors == 0), "Erreurs ICMP incompatibles.")
    return {"target": TARGET, "forwarding": forwarding, "exit_code": exit_code,
            "transmitted": transmitted, "received": received, "reported_errors": errors,
            "reported_packet_loss_percent": expected_loss, "reported_elapsed_ms": int(match["elapsed"])}
