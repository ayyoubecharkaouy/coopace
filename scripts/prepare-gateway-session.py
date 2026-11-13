"""Build and freeze the Go session pilot and its supervised native checks."""

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

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('prepare_session_model',ROOT/'scripts/lab_gateway_session.py')
model=importlib.util.module_from_spec(spec);spec.loader.exec_module(model)
runtime,require=model.runtime,model.require
previous=runtime.sibling('prepare_session_base','prepare-queue-recovery.py')
command=previous.command
RUNNER=(previous.RUNNER.replace('prepare-queue-recovery.py','prepare-gateway-session.py')
    .replace('lab-queue-recovery.py','lab-gateway-session.py')
    .replace('--gateway "$coopace_case/coopace-gateway"',
             '--gateway "$coopace_case/coopace-gateway" --worker "$coopace_case/coopace-session-worker"')
    .replace('--prepared "$coopace_case"','--prepared "$coopace_case" --allow-lab')
    .replace('Deux cycles noqueue → CAKE → noqueue : fin normale, puis panne du pilote.',
             'Deux sessions pilotées par Go : accord local, CAKE, arrêt normal puis SIGKILL et restauration indépendante.')
    .replace('Interfaces virtuelles sans adresse IP ; prévoir environ une minute.',
             'Pilote sans privilèges ; interfaces virtuelles sans IP, aucun transfert. Prévoir environ une minute.'))


def verify(folder):
    folder=Path(folder).resolve(strict=True)
    raw=runtime.read(folder/'prepared.json')
    require(runtime.digest(raw)==runtime.read(folder/'prepared.sha256',1024).decode('ascii').strip(),'Manifeste préparé modifié.')
    manifest=runtime.document(raw)
    require(manifest.get('schema_version')==1 and manifest.get('kind')=='prepared_gateway_session_lab','Manifeste incompatible.')
    require(command(['git','rev-parse','HEAD'])==manifest['revision'],'Révision du dépôt modifiée.')
    require(platform.release()==manifest['kernel'] and platform.python_version()==manifest['python_version'],'Environnement natif modifié.')
    for path,expected in manifest['inputs_sha256'].items():
        require(runtime.digest(runtime.read(path,64*1024*1024))==expected,'Entrée figée modifiée : '+path)
    for tool in manifest['tools'].values():
        require(runtime.digest(runtime.read(tool['path'],64*1024*1024))==tool['sha256'],'Outil figé modifié.')
    require(manifest['source_sha256']==model.source_hashes(),'Sources du contrôle modifiées.')
    return manifest


def prepare(destination=None):
    require(os.geteuid()!=0,'Compiler depuis le compte habituel.')
    require(sys.platform=='linux' and platform.machine()=='x86_64','Préparation Linux amd64 requise.')
    require(not command(['git','status','--porcelain','--untracked-files=all']),'Arbre Git propre requis.')
    revision=command(['git','rev-parse','HEAD'])
    if destination is None:
        parent=ROOT/'.local/experiments';parent.mkdir(parents=True,exist_ok=True)
        destination=parent/('gateway-session-validation-'+revision[:7])
    destination=Path(destination).absolute()
    require(not any(ord(c)<32 for c in str(destination)),'Chemin de dossier invalide.')
    destination.mkdir(mode=0o700)
    builds={}
    for name in ('coopace-gateway','coopace-session-worker'):
        binary=destination/name
        subprocess.run(['sh','scripts/go.sh','build','-buildvcs=true','-trimpath','-o',str(binary),
                        './apps/gateway/cmd/'+name],cwd=ROOT,check=True)
        metadata=json.loads(command(['sh','scripts/go.sh','version','-m','-json',str(binary)]))
        settings={row['Key']:row['Value'] for row in metadata['Settings']}
        require(metadata['Path']=='github.com/ayyoubecharkaouy/coopace/apps/gateway/cmd/'+name
            and settings.get('vcs.revision')==revision and settings.get('vcs.modified')=='false'
            and settings.get('GOOS')=='linux' and settings.get('GOARCH')=='amd64','Provenance Go non conforme.')
        builds[name]=metadata
    paths={'ip':shutil.which('ip'),'tc':shutil.which('tc'),'python':sys.executable,
        'gateway':destination/'coopace-gateway','worker':destination/'coopace-session-worker'}
    require(all(paths.values()),'Outils ip et tc requis pour préparer.')
    tools=runtime.Tools(paths)
    try:
        runner=RUNNER.format(project=shlex.quote(str(ROOT)),case=shlex.quote(str(destination)),
                             python=shlex.quote(tools.specs['python']['path']))
        (destination/'run.sh').write_text(runner);(destination/'run.sh').chmod(0o700)
        sources=command(['git','ls-files','--','*.go','go.mod','.go-version','scripts/*.py','scripts/go.sh']).splitlines()
        inputs={str(ROOT/name):runtime.digest(runtime.read(ROOT/name,64*1024*1024)) for name in sources}
        for path in (destination/'run.sh',destination/'coopace-gateway',destination/'coopace-session-worker'):
            inputs[str(path)]=runtime.digest(runtime.read(path,64*1024*1024))
        manifest={'schema_version':1,'kind':'prepared_gateway_session_lab','revision':revision,
            'prepared_at':datetime.now(timezone.utc).isoformat(),'kernel':platform.release(),'python_version':platform.python_version(),
            'tools':tools.specs,'go_builds':builds,'inputs_sha256':inputs,'source_sha256':model.source_hashes(),
            'state':'not_run','native_steps':['check','check-crash'],'real_gateway_restoration_validated':False}
        raw=(json.dumps(manifest,ensure_ascii=False,allow_nan=False,indent=2)+'\n').encode()
        with (destination/'prepared.json').open('xb') as stream:stream.write(raw)
        with (destination/'prepared.sha256').open('x') as stream:stream.write(runtime.digest(raw)+'\n')
        require(not command(['git','status','--porcelain','--untracked-files=all']),'Arbre modifié pendant préparation.')
        verify(destination)
    finally:tools.close()
    print('Dossier préparé :',destination)
    print('Lancer : sh',shlex.quote(str(destination/'run.sh')))
    return destination


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group();group.add_argument('--artifacts',type=Path);group.add_argument('--verify',type=Path)
    args=parser.parse_args(argv)
    try:
        if args.verify:verify(args.verify)
        else:prepare(args.artifacts)
        return 0
    except Exception as error:print('Préparation de session refusée :',error,file=sys.stderr);return 1


if __name__=='__main__':sys.exit(main())
