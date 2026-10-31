"""CAKE Go on a disposable DOWN veth under the independent lab guard."""

import argparse
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

spec = importlib.util.spec_from_file_location("cake_go_control", Path(__file__).with_name("lab_cake_go.py"))
model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", nargs="?", choices=("plan", "check", "check-crash"), default="plan")
    parser.add_argument("--worker", type=Path)
    parser.add_argument("--artifacts", type=Path)
    args = parser.parse_args(argv)
    if args.mode == "plan":
        print(model.plan()); return 0
    if args.worker is None or args.artifacts is None:
        parser.error("--worker BINAIRE et --artifacts DOSSIER_NEUF sont requis")
    try:
        model.require(hasattr(os, "setns") and platform.machine() == "x86_64", "Python avec setns et Linux amd64 requis.")
        namespaces = model.guards.preflight()
        tc = shutil.which("tc")
        model.require(tc is not None, "Outil tc requis ; aucun espace créé.")
        result = model.run(args.mode, namespaces, args.worker.resolve(strict=True), tc, args.artifacts.resolve(strict=True))
        print(json.dumps(result, ensure_ascii=False, allow_nan=False)); return 0
    except model.guards.Interrupted as error:
        print(str(error), file=sys.stderr); return error.code
    except (OSError, ValueError, KeyError, TypeError, model.Error, model.guards.GuardError, model.guards.lab_queue.QueueError, subprocess.SubprocessError) as error:
        print(f"Contrôle CAKE Go interrompu : {error}", file=sys.stderr); return 1


if __name__ == "__main__":
    sys.exit(main())
