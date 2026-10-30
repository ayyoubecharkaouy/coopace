"""Collect or reanalyze the six-campaign TBF/CAKE v1 comparison."""

import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

spec = importlib.util.spec_from_file_location("lab_comparison_run", Path(__file__).with_name("lab_comparison_run.py"))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
model, campaign = runner.model, runner.campaign


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", nargs="?", choices=("plan", "run", "analyze"), default="plan")
    parser.add_argument("--artifacts", type=Path)
    parser.add_argument("--binaries", type=Path, default=Path(__file__).resolve().parents[1] / ".local/bin")
    args = parser.parse_args(argv)
    if args.mode == "plan":
        print("Trois blocs : TBF/CAKE, CAKE/TBF, TBF/CAKE ; six topologies neuves.\n"
              "36 phases, 360 tentatives TCP, 18 transferts de 8 Mio (144 Mio utiles).\n"
              "Au moins 2s après nettoyage avant chaque campagne suivante.\n"
              "Chaque pilote 150s, superviseur 180s, nettoyage 10s ; aucune destruction du superviseur.\n"
              "Neuf comparaisons et critères v1 ; résultats défavorables conservés sans reprise sélective.\n"
              "run exige un dossier existant vide ; analyze relit les preuves sans opération réseau.\n"
              "Le mode plan ne crée aucune ressource et n'exige aucun privilège.")
        return 0
    if args.artifacts is None:
        parser.error("--artifacts DOSSIER est requis")
    try:
        artifacts = args.artifacts.resolve(strict=True)
        if args.mode == "analyze":
            result = runner.analyze(artifacts)
        else:
            os.environ["LC_ALL"] = "C"
            namespaces = campaign.guards.preflight()
            cap = re.search(r"^CapEff:\s*([0-9a-fA-F]+)$", Path("/proc/self/status").read_text(), re.M)
            model.require(cap and int(cap[1], 16) & (1 << 13), "CAP_NET_RAW requise ; aucun espace créé.")
            tc, sysctl, ping = (shutil.which(name) for name in ("tc", "sysctl", "ping"))
            model.require(all((tc, sysctl, ping)), "Outils tc, sysctl et ping requis ; aucun espace créé.")
            binaries = args.binaries.resolve(strict=True)
            for name in ("coopace", "coopace-lab-tcp", "coopace-lab-load"):
                path = binaries / name
                model.require(path.is_file() and os.access(path, os.X_OK), f"Binaire exécutable requis : {path}.")
            result = runner.run(namespaces, tc, sysctl, ping, binaries, artifacts)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return 0
    except campaign.guards.Interrupted as error:
        print(str(error), file=sys.stderr)
        return error.code
    except (OSError, ValueError, KeyError, TypeError, StopIteration, model.Error, model.cake.Error,
            campaign.guards.GuardError, campaign.processes.ExperimentError, subprocess.SubprocessError) as error:
        print(f"Comparaison non exploitable : {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
