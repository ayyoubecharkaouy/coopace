"""Campagne CAKE après Go : plan sans action, puis run/check-crash dans un laboratoire neuf."""

import argparse
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

spec = importlib.util.spec_from_file_location("campaign_control", Path(__file__).with_name("lab_cake_go_campaign.py"))
model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)
go = model.active.go
require = model.active.require


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", nargs="?", choices=("plan", "run", "check-crash"), default="plan")
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
        require(hasattr(os, "setns") and sys.platform == "linux" and platform.machine() == "x86_64",
                      "Python avec setns et Linux amd64 requis.")
        worker = args.worker.resolve(strict=True)
        binaries = args.binaries.resolve(strict=True)
        artifacts = args.artifacts.resolve(strict=True)
        require(worker.is_file() and os.access(worker, os.X_OK) and binaries.is_dir(),
                "Worker exécutable et dossier de binaires requis.")
        require(artifacts.is_dir() and not any(artifacts.iterdir()), "Dossier de preuves neuf et vide requis.")
        namespaces = go.guards.preflight()
        tc, sysctl, ping = [shutil.which(name) for name in ("tc", "sysctl", "ping")]
        require(all((tc, sysctl, ping)), "Outils tc, sysctl et ping requis.")
        result = model.run(args.mode, namespaces, worker, tc, sysctl, ping, binaries, artifacts)
        require(result.get("kind") == "lab_cake_go_campaign" and result.get("state") == "complete"
                and result.get("technical_valid") is (None if args.mode == "check-crash" else True),
                "Rapport global de campagne non conforme.")
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return 0
    except go.guards.Interrupted as error:
        print(str(error), file=sys.stderr)
        return error.code
    except (OSError, ValueError, KeyError, TypeError, model.active.Error, go.guards.GuardError,
            go.guards.lab_queue.QueueError, model.active.collect.traffic.Error,
            model.active.collect.traffic.active.Error, subprocess.SubprocessError) as error:
        print(f"Campagne CAKE après Go interrompue : {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
