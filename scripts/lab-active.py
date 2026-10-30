"""Bounded functional control of a TBF link; not the three-pair campaign."""

import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


spec = importlib.util.spec_from_file_location("lab_active", Path(__file__).with_name("lab_active.py"))
active = importlib.util.module_from_spec(spec)
spec.loader.exec_module(active)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", nargs="?", choices=("plan", "check", "check-crash", "worker"), default="plan")
    parser.add_argument("--binaries", type=Path, default=Path(__file__).resolve().parents[1] / ".local/bin")
    parser.add_argument("--ip")
    parser.add_argument("--client")
    parser.add_argument("--server")
    args = parser.parse_args(argv)
    if args.mode == "plan":
        print("Trois espaces neufs : client -> passerelle TBF 4mbit -> serveur.\n"
              "check : 8 Mio, dix connexions TCP sous charge, réception JSON et statistiques périodiques.\n"
              "check-crash : SIGKILL du pilote après première écriture, puis récupération de ses trois outils.\n"
              "Superviseur indépendant 90s, nettoyage 10s ; aucune route par défaut ni interface physique.\n"
              "Contrôle fonctionnel distinct des trois paires et de leur qualification de congestion.\n"
              "Le mode plan ne crée aucune ressource et n'exige aucun privilège.")
        return 0
    try:
        if args.mode == "worker":
            if not all((args.ip, args.client, args.server)):
                parser.error("worker exige --ip, --client et --server")
            active.worker(args.ip, args.client, args.server, args.binaries)
            return 0
        namespaces = active.guard_module.preflight()
        tc, sysctl = shutil.which("tc"), shutil.which("sysctl")
        if not tc or not sysctl:
            raise active.Error("Outils tc et sysctl requis ; aucun espace créé.")
        binaries = args.binaries.resolve(strict=True)
        for name in ("coopace", "coopace-lab-tcp", "coopace-lab-load"):
            path = binaries / name
            if not path.is_file() or not os.access(path, os.X_OK):
                raise active.Error(f"Binaire exécutable requis : {path} ; aucun espace créé.")
        result = active.run(args.mode, namespaces, tc, sysctl, binaries)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return 0
    except active.guard_module.Interrupted as error:
        print(str(error), file=sys.stderr)
        return error.code
    except (OSError, ValueError, KeyError, active.Error, active.guard_module.GuardError,
            active.series.ExperimentError, subprocess.SubprocessError) as error:
        print(f"Contrôle actif interrompu : {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
