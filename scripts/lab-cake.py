"""Check static CAKE configuration/statistics on a fresh DOWN lab veth."""

import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys


def sibling(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = sibling("cake_guard", "lab-guard.py")
cake = sibling("lab_cake", "lab_cake.py")


def run_check(mode, namespaces, tc, **limits):
    result = guard.run_check(mode, namespaces, queue_check=cake.CakeCheck(namespaces, tc), **limits)
    result["kind"] = "lab_cake_check"
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", nargs="?", choices=("plan", "check", "check-crash"), default="plan")
    args = parser.parse_args(argv)
    if args.mode == "plan":
        print(cake.plan())
        return 0
    try:
        namespaces = guard.preflight()
        tc = shutil.which("tc")
        if not tc:
            raise cake.Error("Outil tc absent ; aucun espace créé.")
        result = run_check(args.mode, namespaces, tc)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return 0
    except guard.Interrupted as error:
        print(str(error), file=sys.stderr)
        return error.code
    except (OSError, ValueError, cake.Error, guard.GuardError, guard.lab_queue.QueueError,
            subprocess.SubprocessError) as error:
        print(f"Contrôle CAKE interrompu : {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
