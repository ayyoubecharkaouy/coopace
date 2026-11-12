"""Build and freeze a one-shot native queue-recovery lab bundle."""

import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("prepare_recovery_model", ROOT/"scripts/lab_queue_recovery.py")
model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)
runtime, require = model.runtime, model.require

RUNNER = r'''#!/bin/sh
set -eu
set -C
coopace_project={project}
coopace_case={case}
coopace_python={python}
cd "$coopace_project"
if [ "$(id -u)" = 0 ]; then
    printf '%s\n' 'Lancer avec le compte habituel ; seuls les contrôles utilisent sudo.' >&2
    exit 2
fi
if ! mkdir "$coopace_case/run.lock"; then
    printf '%s\n' 'Un lancement est déjà réservé ; conserver les preuves.' >&2
    exit 2
fi
trap 'rmdir "$coopace_case/run.lock"' EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
for coopace_existing in check check-crash check.stdout.json check.log check.exit check-crash.stdout.json check-crash.log check-crash.exit check.review.json check.review.log check.review.exit check-crash.review.json check-crash.review.log check-crash.review.exit; do
    if [ -e "$coopace_case/$coopace_existing" ] || [ -L "$coopace_case/$coopace_existing" ]; then
        printf '%s\n' 'Des résultats existent déjà ; préparer un autre dossier.' >&2
        exit 2
    fi
done
printf '%s\n' 'Deux cycles noqueue → CAKE → noqueue : fin normale, puis panne du pilote.'
printf '%s\n' 'Interfaces virtuelles sans adresse IP ; prévoir environ une minute.'
for coopace_mode in check check-crash; do
    "$coopace_python" -I -B "$coopace_project/scripts/prepare-queue-recovery.py" --verify "$coopace_case"
    mkdir -m 700 "$coopace_case/$coopace_mode"
    if sudo -- "$coopace_python" -I -B "$coopace_project/scripts/lab-queue-recovery.py" "$coopace_mode" --gateway "$coopace_case/coopace-gateway" --artifacts "$coopace_case/$coopace_mode" --prepared "$coopace_case" > "$coopace_case/$coopace_mode.stdout.json" 2> "$coopace_case/$coopace_mode.log"; then
        coopace_code=0
    else
        coopace_code=$?
    fi
    printf '%s\n' "$coopace_code" > "$coopace_case/$coopace_mode.exit"
    printf 'Code %s : %s\n' "$coopace_mode" "$coopace_code"
    if [ "$coopace_code" != 0 ]; then
        printf 'Résultats conservés : %s\n' "$coopace_case"
        exit "$coopace_code"
    fi
    "$coopace_python" -I -B "$coopace_project/scripts/prepare-queue-recovery.py" --verify "$coopace_case"
    if "$coopace_python" -I -B "$coopace_project/scripts/lab-queue-recovery.py" review --gateway "$coopace_case/coopace-gateway" --artifacts "$coopace_case/$coopace_mode" > "$coopace_case/$coopace_mode.review.json" 2> "$coopace_case/$coopace_mode.review.log"; then
        coopace_code=0
    else
        coopace_code=$?
    fi
    printf '%s\n' "$coopace_code" > "$coopace_case/$coopace_mode.review.exit"
    printf 'Code relecture %s : %s\n' "$coopace_mode" "$coopace_code"
    [ "$coopace_code" = 0 ] || exit "$coopace_code"
done
"$coopace_python" -I -B "$coopace_project/scripts/prepare-queue-recovery.py" --verify "$coopace_case"
printf 'Résultats : %s\n' "$coopace_case"
'''


def command(args):
    return subprocess.check_output(args, cwd=ROOT, text=True).strip()


def verify(folder):
    folder = Path(folder).resolve(strict=True)
    raw = runtime.read(folder/"prepared.json")
    require(runtime.digest(raw) == runtime.read(folder/"prepared.sha256",1024).decode("ascii").strip(),
            "Manifeste préparé modifié.")
    manifest = runtime.document(raw)
    require(manifest.get("kind") == "prepared_queue_recovery_lab" and manifest.get("schema_version") == 1,
            "Manifeste incompatible.")
    require(command(["git","rev-parse","HEAD"]) == manifest["revision"], "Révision du dépôt modifiée.")
    require(platform.release() == manifest["kernel"] and platform.python_version() == manifest["python_version"],
            "Environnement natif modifié.")
    for name, expected in manifest["inputs_sha256"].items():
        require(runtime.digest(runtime.read(name,64*1024*1024)) == expected, "Entrée figée modifiée : " + name)
    for tool in manifest["tools"].values():
        require(runtime.digest(runtime.read(tool["path"],64*1024*1024)) == tool["sha256"], "Outil figé modifié.")
    require(manifest["source_sha256"] == model.source_hashes(), "Sources du contrôle modifiées.")
    return manifest


def prepare(destination=None):
    require(os.geteuid() != 0, "Compiler depuis le compte habituel, sans sudo.")
    require(sys.platform == "linux" and platform.machine() == "x86_64", "Préparation Linux amd64 requise.")
    require(not command(["git","status","--porcelain","--untracked-files=all"]), "Arbre Git propre requis.")
    revision = command(["git","rev-parse","HEAD"])
    if destination is None:
        parent = ROOT/".local/experiments"
        parent.mkdir(parents=True,exist_ok=True)
        destination = parent/("queue-recovery-validation-"+revision[:7])
    destination = Path(destination).absolute()
    require(not any(ord(c)<32 for c in str(destination)), "Chemin de dossier invalide.")
    destination.mkdir(mode=0o700)
    gateway = destination/"coopace-gateway"
    subprocess.run(["sh","scripts/go.sh","build","-buildvcs=true","-trimpath","-o",str(gateway),
                    "./apps/gateway/cmd/coopace-gateway"],cwd=ROOT,check=True)
    metadata = json.loads(command(["sh","scripts/go.sh","version","-m","-json",str(gateway)]))
    settings = {row["Key"]:row["Value"] for row in metadata["Settings"]}
    require(metadata["Path"] == "github.com/ayyoubecharkaouy/coopace/apps/gateway/cmd/coopace-gateway"
            and settings.get("vcs.revision") == revision and settings.get("vcs.modified") == "false"
            and settings.get("GOOS") == "linux" and settings.get("GOARCH") == "amd64",
            "Provenance Go non conforme.")
    paths = {"ip":shutil.which("ip"),"tc":shutil.which("tc"),"python":sys.executable,"gateway":gateway}
    require(all(paths.values()), "Outils ip et tc requis pour préparer.")
    tools = runtime.Tools(paths)
    try:
        runner = RUNNER.format(project=shlex.quote(str(ROOT)),case=shlex.quote(str(destination)),
                               python=shlex.quote(tools.specs["python"]["path"]))
        (destination/"run.sh").write_text(runner)
        (destination/"run.sh").chmod(0o700)
        sources = command(["git","ls-files","--","*.go","go.mod",".go-version","scripts/*.py","scripts/go.sh"]).splitlines()
        inputs = {str(ROOT/name):runtime.digest(runtime.read(ROOT/name,64*1024*1024)) for name in sources}
        inputs[str(destination/"run.sh")] = runtime.digest(runtime.read(destination/"run.sh"))
        inputs[str(gateway)] = tools.specs["gateway"]["sha256"]
        manifest = {"schema_version":1,"kind":"prepared_queue_recovery_lab","revision":revision,
            "prepared_at":datetime.now(timezone.utc).isoformat(),"kernel":platform.release(),
            "python_version":platform.python_version(),"tools":tools.specs,"go_build":metadata,
            "inputs_sha256":inputs,"source_sha256":model.source_hashes(),"state":"not_run",
            "native_steps":["check","check-crash"],"real_gateway_restoration_validated":False}
        raw=(json.dumps(manifest,ensure_ascii=False,allow_nan=False,indent=2)+"\n").encode()
        with (destination/"prepared.json").open("xb") as stream:stream.write(raw)
        with (destination/"prepared.sha256").open("x") as stream:stream.write(runtime.digest(raw)+"\n")
        require(not command(["git","status","--porcelain","--untracked-files=all"]), "Arbre modifié pendant préparation.")
        verify(destination)
    finally:
        tools.close()
    print("Dossier préparé :",destination)
    print("Lancer : sh",shlex.quote(str(destination/"run.sh")))
    return destination


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group()
    group.add_argument("--artifacts",type=Path)
    group.add_argument("--verify",type=Path)
    args=parser.parse_args(argv)
    try:
        if args.verify:verify(args.verify)
        else:prepare(args.artifacts)
        return 0
    except Exception as error:
        print("Préparation de restauration refusée :",error,file=sys.stderr)
        return 1


if __name__=="__main__":
    sys.exit(main())
