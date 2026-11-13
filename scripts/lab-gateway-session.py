"""Run/review a Go gateway session in fresh owned virtual namespaces."""

import argparse
import importlib.util
import json
from pathlib import Path
import platform
import shutil
import sys

spec=importlib.util.spec_from_file_location('gateway_session_model',Path(__file__).with_name('lab_gateway_session.py'))
model=importlib.util.module_from_spec(spec);spec.loader.exec_module(model)
runtime,require=model.runtime,model.require


def run(mode,gateway,worker,artifacts,consent,prepared=None):
    require(consent,'--allow-lab requis pour cette session jetable.')
    native=model.recovery.guards.preflight()
    require(platform.machine()=='x86_64','Laboratoire Linux amd64 requis.')
    manifest=None
    if prepared is not None:manifest=runtime.sibling('session_preparation','prepare-gateway-session.py').verify(prepared)
    tc=shutil.which('tc');require(tc is not None,'Outil tc requis.')
    tools=runtime.Tools({'ip':native.ip,'tc':tc,'gateway':gateway,'worker':worker,'python':sys.executable})
    evidence=None
    try:
        if manifest is not None:require(tools.specs==manifest['tools'],'Outils différents du dossier figé.')
        evidence=runtime.Evidence(Path(artifacts).resolve(strict=True))
        require(evidence.folder.stat().st_uid>0,'Dossier de preuves possédé par le compte opérateur requis.')
        evidence.save('environment.json',{'schema_version':1,'kind':'lab_gateway_session_environment',
            'kernel':platform.release(),'python_version':platform.python_version(),'tools':tools.specs,
            'tool_descriptors':dict(tools.files),'source_sha256':model.source_hashes(),'simulation':False,
            'prepared_revision':manifest['revision'] if manifest else None})
        model.recovery.guards.enable_subreaper()
        namespaces=runtime.Namespaces(runtime.Runner(tools,evidence))
        owner=runtime.RecoveryGuard(namespaces,timeout=120);namespaces.owner=owner
        return model.cycle(mode,owner,model.recovery.Engine(owner,namespaces.runner,evidence),evidence,consent)
    finally:
        if evidence is not None:evidence.finish()
        tools.close()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',nargs='?',choices=('plan','check','check-crash','review'),default='plan')
    parser.add_argument('--gateway',type=Path);parser.add_argument('--worker',type=Path)
    parser.add_argument('--artifacts',type=Path);parser.add_argument('--prepared',type=Path)
    parser.add_argument('--allow-lab',action='store_true',help='accord local limité aux ressources neuves du laboratoire')
    args=parser.parse_args(argv)
    if args.mode=='plan':
        print('Session Go sans privilèges : capture initiale liée par SHA-256, accord local, demande CAKE au superviseur.\n'
              'Restauration indépendante après sortie normale ou SIGKILL ; veth sans IP dans trois espaces neufs.\n'
              'Aucune interface physique acceptée ; aucun trafic généré.')
        return 0
    if args.gateway is None or args.artifacts is None:parser.error('--gateway et --artifacts requis')
    if args.mode!='review' and args.worker is None:parser.error('--worker requis')
    try:
        if args.mode=='review':result=runtime.sibling('session_review','lab_gateway_session_review.py').review(args.artifacts,args.gateway)
        else:result=run(args.mode,args.gateway,args.worker,args.artifacts,args.allow_lab,args.prepared)
        print(json.dumps(result,ensure_ascii=False,allow_nan=False))
        return 0 if args.mode=='review' or result['state']=='complete' else result.get('interruption_code') or 1
    except Exception as error:
        print('Session refusée :',error,file=sys.stderr);return 1


if __name__=='__main__':sys.exit(main())
