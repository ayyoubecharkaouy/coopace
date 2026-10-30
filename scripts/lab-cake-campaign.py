"""Supervised CAKE campaign implementing one arm of the comparison protocol."""

import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


spec = importlib.util.spec_from_file_location("lab_cake_campaign", Path(__file__).with_name("lab_cake_campaign.py"))
model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", nargs="?", choices=("plan", "run", "check-crash"), default="plan")
    parser.add_argument("--artifacts", type=Path)
    parser.add_argument("--binaries", type=Path, default=Path(__file__).resolve().parents[1] / ".local/bin")
    args = parser.parse_args(argv)
    if args.mode == "plan":
        print(model.plan())
        return 0
    if args.artifacts is None:
        parser.error("--artifacts DOSSIER est requis")
    campaign = model.campaign
    try:
        os.environ["LC_ALL"] = "C"
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
            path = binaries / name
            if not path.is_file() or not os.access(path, os.X_OK):
                raise campaign.Error(f"Binaire exécutable requis : {path} ; aucun espace créé.")
        result = model.run(namespaces, tc, sysctl, ping, binaries, artifacts, crash=args.mode == "check-crash")
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return 1 if result["decision"]["technical_valid"] is False else 0
    except campaign.guards.Interrupted as error:
        print(str(error), file=sys.stderr)
        return error.code
    except (OSError, ValueError, KeyError, TypeError, campaign.Error, model.cake.Error,
            campaign.guards.GuardError, campaign.processes.ExperimentError, subprocess.SubprocessError) as error:
        print(f"Campagne CAKE interrompue : {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
