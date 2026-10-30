"""Supervised TBF campaign implementing docs/VIRTUAL_BOTTLENECK.md v1."""

import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

spec = importlib.util.spec_from_file_location("lab_campaign", Path(__file__).with_name("lab_campaign.py"))
campaign = importlib.util.module_from_spec(spec)
spec.loader.exec_module(campaign)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", nargs="?", choices=("plan", "run", "check-crash", "worker"), default="plan")
    parser.add_argument("--artifacts", type=Path)
    parser.add_argument("--binaries", type=Path, default=Path(__file__).resolve().parents[1] / ".local/bin")
    parser.add_argument("--ip")
    parser.add_argument("--client")
    parser.add_argument("--server")
    args = parser.parse_args(argv)
    if args.mode == "plan":
        print("Trois paires : idle/loaded, loaded/idle, idle/loaded ; même TBF 4mbit.\n"
              "Contrôles ICMP sans/avec forwarding ; dix sondes TCP par phase (1s, pause 250ms).\n"
              "Trois transferts de 8 Mio, réception JSON ; file vide entre phases.\n"
              "Statistiques périodiques, rapports intermédiaires conservés, qualification séparée.\n"
              "Pilote 150s, superviseur 180s, nettoyage 10s.\n"
              "check-crash tue le pilote après la première écriture de la première phase loaded.\n"
              "Le mode plan ne crée aucune ressource et n'exige aucun privilège.")
        return 0
    try:
        if args.mode == "worker":
            if not all((args.ip, args.client, args.server)):
                parser.error("worker exige --ip, --client et --server")
            campaign.worker(args.ip, args.client, args.server, args.binaries)
            return 0
        os.environ["LC_ALL"] = "C"
        if args.artifacts is None:
            parser.error("--artifacts DOSSIER est requis")
        artifacts = args.artifacts.resolve(strict=True)
        if not artifacts.is_dir():
            raise campaign.Error("Dossier d'expérience existant requis.")
        namespaces = campaign.guards.preflight()
        cap = re.search(r"^CapEff:\s*([0-9a-fA-F]+)$", Path("/proc/self/status").read_text(), re.M)
        if not cap or not int(cap[1], 16) & (1 << 13):
            raise campaign.Error("CAP_NET_RAW requise pour les contrôles ICMP ; aucun espace créé.")
        tc, sysctl, ping = (shutil.which(name) for name in ("tc", "sysctl", "ping"))
        if not all((tc, sysctl, ping)):
            raise campaign.Error("Outils tc, sysctl et ping requis ; aucun espace créé.")
        binaries = args.binaries.resolve(strict=True)
        for name in ("coopace", "coopace-lab-tcp", "coopace-lab-load"):
            if not (binaries / name).is_file() or not os.access(binaries / name, os.X_OK):
                raise campaign.Error("Trois binaires exécutables requis ; aucun espace créé.")
        result = campaign.run(namespaces, tc, sysctl, ping, binaries, artifacts, crash=args.mode == "check-crash")
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return 0 if result["decision"]["technical_valid"] is not False else 1
    except campaign.guards.Interrupted as error:
        print(str(error), file=sys.stderr)
        return error.code
    except (OSError, ValueError, KeyError, TypeError, campaign.Error, campaign.guards.GuardError,
            campaign.processes.ExperimentError, subprocess.SubprocessError) as error:
        print(f"Campagne interrompue : {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
