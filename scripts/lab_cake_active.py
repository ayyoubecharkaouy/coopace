"""One supervised CAKE flow, reusing the validated active lab machinery."""

from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path


spec = importlib.util.spec_from_file_location("cake_active_shared", Path(__file__).with_name("lab_active.py"))
active = importlib.util.module_from_spec(spec)
spec.loader.exec_module(active)
cake = active.sibling("cake_active_scheduler", "lab_cake.py")


class ActiveCake(cake.CakeCheck):
    def __init__(self, namespaces, tc, sysctl, record):
        super().__init__(namespaces, tc)
        self.sysctl, self.record = sysctl, record

    def prepare(self, owner):
        self.record({"event": "owned", "namespaces": [name for name, _ in owner.owned],
                     "workspace": str(owner.workspace)})
        super().prepare(owner)
        active.activate(self, owner, self.sysctl)

    def read(self, include_statistics=False):
        reading = super().read(include_statistics)
        child = self.owner.child
        self.record({"event": "qdisc", "include_statistics": include_statistics,
                     "driver_pid": child.pid if child is not None else None, "reading": reading})
        return reading


def run(mode, namespaces, tc, sysctl, binaries, evidence, **limits):
    # The journal belongs to the experiment, never the disposable reservation.
    descriptor = os.open(evidence, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        written = 0
        def record(event):
            nonlocal written
            line = json.dumps({"recorded_at": datetime.now(timezone.utc).isoformat(), **event},
                              ensure_ascii=False, allow_nan=False) + "\n"
            written += len(line.encode("utf-8"))
            if written > 4 * 1024 * 1024:
                raise active.Error("Journal du contrôle CAKE actif trop volumineux.")
            stream.write(line)
            stream.flush()
        def topology(namespaces, tc, sysctl):
            return ActiveCake(namespaces, tc, sysctl, record)
        result = active.run(mode, namespaces, tc, sysctl, binaries, topology_factory=topology, **limits)
        result["kind"] = "lab_cake_active_check"
        result["evidence"] = str(evidence)
        record({"event": "cleaned", "driver_exit_code": result["driver_exit_code"],
                "reaped_descendants": result["reaped_descendants"], "flow": result["flow"]})
        return result


def plan():
    return ("Contrôle CAKE actif : client -> passerelle CAKE 4mbit -> serveur, trois espaces neufs.\n"
            "Même configuration CAKE que le contrôle DOWN ; profil iproute2-6.1.0 identifié.\n"
            "check : réception complète de 8 Mio, dix sondes TCP (1s, pause 250ms), relevés périodiques.\n"
            "check-crash : SIGKILL du pilote après première écriture, puis récupération de ses trois outils.\n"
            "Journal de preuves exclusif conservé hors réservation ; nettoyage avant rapport final.\n"
            "Superviseur 90s, nettoyage 10s ; aucune interface physique ni route par défaut.\n"
            "Aucune comparaison TBF/CAKE ni qualification de bénéfice dans ce contrôle isolé.\n"
            "Le mode plan ne crée aucune ressource et n'exige aucun privilège.")
