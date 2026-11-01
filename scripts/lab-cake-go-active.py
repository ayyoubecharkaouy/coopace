"""Opt-in disposable lab: Go DOWN, retained CAKE, then supervised traffic."""

import argparse
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

spec = importlib.util.spec_from_file_location("cake_go_active", Path(__file__).with_name("lab_cake_go_active.py"))
model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", nargs="?", choices=("plan", "check", "check-crash"), default="plan")
    parser.add_argument("--worker", type=Path)
    parser.add_argument("--binaries", type=Path)
    parser.add_argument("--artifacts", type=Path)
    args = parser.parse_args(argv)
    if args.mode == "plan":
        print(model.plan())
        return 0
    if args.worker is None or args.binaries is None or args.artifacts is None:
        parser.error("--worker, --binaries et --artifacts DOSSIER_NEUF sont requis")
    try:
        model.require(hasattr(os, "setns") and sys.platform == "linux" and platform.machine() == "x86_64",
                      "Python avec setns et Linux amd64 requis.")
        namespaces = model.go.guards.preflight()
        tc, sysctl = shutil.which("tc"), shutil.which("sysctl")
        model.require(tc is not None and sysctl is not None, "Outils tc et sysctl requis.")
        result = model.run(args.mode, namespaces, args.worker.resolve(strict=True), tc, sysctl,
                           args.binaries.resolve(strict=True), args.artifacts.resolve(strict=True))
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return 0
    except model.go.guards.Interrupted as error:
        print(str(error), file=sys.stderr)
        return error.code
    except (OSError, ValueError, KeyError, TypeError, model.Error, model.go.guards.GuardError,
            model.go.guards.lab_queue.QueueError, model.collect.traffic.Error,
            model.collect.traffic.active.Error, subprocess.SubprocessError) as error:
        print(f"Contrôle Go puis trafic interrompu : {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
