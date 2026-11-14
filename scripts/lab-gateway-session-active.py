"""Run/review one Go session with a bounded direct-veth transfer and recovery."""
import argparse
import importlib.util
import json
from pathlib import Path
import platform
import shutil
import sys
spec=importlib.util.spec_from_file_location('gateway_session_active',Path(__file__).with_name('lab_gateway_session_active.py'))
model=importlib.util.module_from_spec(spec);spec.loader.exec_module(model)
runtime,require=model.runtime,model.require


def run(mode,gateway,worker,load,artifacts,consent,prepared=None):
    require(consent,'--allow-lab requis pour les ressources jetables.')
    native=model.base.recovery.guards.preflight();require(platform.machine()=='x86_64','Linux amd64 requis.')
    manifest=None
    if prepared is not None:manifest=runtime.sibling('session_active_preparation','prepare-gateway-session-active.py').verify(prepared)
    tc=shutil.which('tc');require(tc is not None,'Outil tc requis.')
    tools=runtime.Tools({'ip':native.ip,'tc':tc,'gateway':gateway,'worker':worker,'load':load,'python':sys.executable})
    evidence=None
    try:
        if manifest is not None:require(tools.specs==manifest['tools'],'Outils différents des entrées figées.')
        evidence=runtime.Evidence(Path(artifacts).resolve(strict=True));require(evidence.folder.stat().st_uid>0,'Dossier du compte opérateur requis.')
        evidence.save('environment.json',{'schema_version':1,'kind':'lab_gateway_session_active_environment',
            'kernel':platform.release(),'python_version':platform.python_version(),'tools':tools.specs,
            'tool_descriptors':dict(tools.files),'source_sha256':model.source_hashes(),'simulation':False,
            'prepared_revision':manifest['revision'] if manifest else None})
        model.base.recovery.guards.enable_subreaper()
        namespaces=runtime.Namespaces(runtime.Runner(tools,evidence));owner=runtime.RecoveryGuard(namespaces,timeout=120)
        namespaces.owner=owner
        return model.cycle(mode,owner,model.Engine(owner,namespaces.runner,evidence),evidence,consent)
    finally:
        if evidence is not None:evidence.finish()
        tools.close()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',nargs='?',choices=('plan','check','check-crash','review'),default='plan')
    for name in ('gateway','worker','load','artifacts','prepared'):parser.add_argument('--'+name,type=Path)
    parser.add_argument('--allow-lab',action='store_true');args=parser.parse_args(argv)
    if args.mode=='plan':
        print('Session Go appliquée pendant un transfert IPv4 de 4 Mio sur le veth possédé, à travers CAKE.\n'
              'Adresses temporaires sans forwarding ; fin normale ou SIGKILL de Go après observation du trafic.\n'
              'Arrêt des outils, retrait des adresses, retour à noqueue et nettoyage ; aucun accès Internet.')
        return 0
    if args.gateway is None or args.artifacts is None:parser.error('--gateway et --artifacts requis')
    if args.mode!='review' and (args.worker is None or args.load is None):parser.error('--worker et --load requis')
    try:
        if args.mode=='review':result=runtime.sibling('session_active_review','lab_gateway_session_active_review.py').review(args.artifacts,args.gateway)
        else:result=run(args.mode,args.gateway,args.worker,args.load,args.artifacts,args.allow_lab,args.prepared)
        print(json.dumps(result,ensure_ascii=False,allow_nan=False))
        return 0 if args.mode=='review' or result['state']=='complete' else result.get('interruption_code') or 1
    except Exception as error:print('Session avec trafic refusée :',error,file=sys.stderr);return 1


if __name__=='__main__':sys.exit(main())
