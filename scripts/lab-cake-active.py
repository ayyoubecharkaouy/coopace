"""Bounded CAKE transfer/probe control with independent cleanup."""

import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


spec = importlib.util.spec_from_file_location("lab_cake_active", Path(__file__).with_name("lab_cake_active.py"))
model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", nargs="?", choices=("plan", "check", "check-crash"), default="plan")
    parser.add_argument("--binaries", type=Path, default=Path(__file__).resolve().parents[1] / ".local/bin")
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args(argv)
    if args.mode == "plan":
        print(model.plan())
        return 0
    if args.evidence is None:
        parser.error("--evidence FICHIER_NEUF est requis")
    try:
        evidence = args.evidence.parent.resolve(strict=True) / args.evidence.name
        namespaces = model.active.guard_module.preflight()
        tc, sysctl = shutil.which("tc"), shutil.which("sysctl")
        if not tc or not sysctl:
            raise model.active.Error("Outils tc et sysctl requis ; aucun espace créé.")
        binaries = args.binaries.resolve(strict=True)
        for name in ("coopace", "coopace-lab-tcp", "coopace-lab-load"):
            path = binaries / name
            if not path.is_file() or not os.access(path, os.X_OK):
                raise model.active.Error(f"Binaire exécutable requis : {path} ; aucun espace créé.")
        result = model.run(args.mode, namespaces, tc, sysctl, binaries, evidence)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return 0
    except model.active.guard_module.Interrupted as error:
        print(str(error), file=sys.stderr)
        return error.code
    except (OSError, ValueError, KeyError, model.active.Error, model.cake.Error,
            model.active.guard_module.GuardError, model.active.series.ExperimentError,
            subprocess.SubprocessError) as error:
        print(f"Contrôle CAKE actif interrompu : {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
