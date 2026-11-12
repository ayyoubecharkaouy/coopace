"""Control/review a noqueue -> owned CAKE -> noqueue cycle in a disposable lab."""

import argparse
import importlib.util
import json
from pathlib import Path
import platform
import shutil
import sys

spec = importlib.util.spec_from_file_location("queue_recovery_model", Path(__file__).with_name("lab_queue_recovery.py"))
model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)
runtime = model.runtime


def run(mode, gateway, artifacts, prepared=None):
    native = model.guards.preflight()
    model.require(platform.machine() == "x86_64", "Contrôle Linux amd64 requis.")
    manifest = None
    if prepared is not None:
        preparation = runtime.sibling("recovery_preparation", "prepare-queue-recovery.py")
        manifest = preparation.verify(prepared)
    tc = shutil.which("tc")
    model.require(tc is not None, "Outil tc absent ; aucun espace créé.")
    tools = runtime.Tools({"ip":native.ip, "tc":tc, "gateway":gateway, "python":sys.executable})
    evidence = None
    try:
        if manifest is not None:
            model.require(tools.specs == manifest["tools"], "Outils différents de la préparation.")
        evidence = runtime.Evidence(Path(artifacts).resolve(strict=True))
        evidence.save("environment.json", {"schema_version":1, "kind":"lab_queue_recovery_environment",
            "kernel":platform.release(), "python_version":platform.python_version(),
            "tools":tools.specs, "tool_descriptors":dict(tools.files), "source_sha256":model.source_hashes(),
            "simulation":False, "prepared_revision":manifest["revision"] if manifest else None})
        model.guards.enable_subreaper()
        namespaces = runtime.Namespaces(runtime.Runner(tools, evidence))
        owner = runtime.RecoveryGuard(namespaces, timeout=90)
        namespaces.owner = owner
        engine = model.Engine(owner, namespaces.runner, evidence)
        return model.cycle(mode, owner, engine, evidence)
    finally:
        if evidence is not None:
            evidence.finish()
        tools.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", nargs="?", choices=("plan", "check", "check-crash", "review"), default="plan")
    parser.add_argument("--gateway", type=Path)
    parser.add_argument("--artifacts", type=Path)
    parser.add_argument("--prepared", type=Path)
    args = parser.parse_args(argv)
    if args.mode == "plan":
        print(model.plan())
        return 0
    if args.gateway is None or args.artifacts is None:
        parser.error("--gateway et --artifacts requis")
    try:
        if args.mode == "review":
            module = runtime.sibling("queue_recovery_review", "lab_queue_recovery_review.py")
            result = module.review(args.artifacts, args.gateway)
        else:
            result = run(args.mode, args.gateway, args.artifacts, args.prepared)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        if args.mode == "review" or result["state"] == "complete":
            return 0
        return result.get("interruption_code") or 1
    except Exception as error:
        print(f"Contrôle de restauration refusé : {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
