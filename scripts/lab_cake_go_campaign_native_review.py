"""Offline global campaign review, including frozen inputs; no certificate writer."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import os
from pathlib import Path
import re
import subprocess


def sibling(name, filename):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(filename))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


phases=sibling('global_campaign_phases','lab_cake_go_campaign_review.py')
path=sibling('global_campaign_path','lab_cake_go_path_review.py')
base=phases.base
go,require,equal,Error=base.go,base.require,base.equal,base.Error
LIMIT=32*1024*1024


def document(file):
    return go.protocol.document(go.read(file,LIMIT),LIMIT)


def campaign_facts(folder,report,tools,owned,build):
    crash=report['mode']=='check-crash';group=report['traffic_group'];worker=report['go_phase']['worker_pid']
    require(type(group['driver_pid']) is int and group['driver_pid']>0 and group['driver_pid']!=worker,
            'Leaders de groupe non distincts.')
    require(type(group['driver_exit_code']) is int and group['driver_exit_code']==(-9 if crash else 0)
            and type(group['reaped_descendants']) is int and group['reaped_descendants']==(3 if crash else 0)
            and group['state']==('crash_verified' if crash else 'collected') and group['traffic_generated'] is True,
            'Fin du pilote de campagne incompatible.')
    equal(report['groups'],[{'driver_pid':worker,'driver_exit_code':0,'reaped_descendants':0,'state':'stopped'},
                            {'driver_pid':group['driver_pid'],'driver_exit_code':-9 if crash else 0,
                             'reaped_descendants':3 if crash else 0,'state':'stopped'}], 'Groupes non récupérés.')
    require(report['flow'] is None and group['flow'] is None,'Flux unique inattendu dans la campagne.')
    equal(group['interrupted_phase'],{'pair':1,'condition':'loaded'} if crash else None,'Frontière de panne différente.')
    rows=[go.protocol.document(line,16*1024*1024)['data'] for line in go.read(folder/'supervisor.jsonl',16*1024*1024).splitlines()]
    launch=[d for d in rows if d['event']=='traffic_launch_intent']
    require(len(launch)==1,'Lancement de campagne absent ou répété.')
    manifest={'schema_version':1,'kind':'lab_cake_go_campaign_tools','session_id':report['session_id'],
              'tools':{n:tools[n] for n in ('ip','agent','target','load')}}
    names=[v[0] for v in owned]
    arguments=[tools['python']['path'],'-I','-B','-S',str(Path(__file__).with_name('lab-cake-go-campaign-traffic.py')),
               '--session-id',report['session_id'],'--client',names[0],'--server',names[2],
               '--ip',tools['ip']['path'],'--binaries',report['environment']['binaries'],
               '--tools-json',base.json.dumps(manifest,separators=(',',':'))]
    equal(launch[0]['arguments'],arguments,'Arguments du pilote différents du contrat.')
    facts=phases.replay(folder,report,tools,owned)
    metrics=facts['measurements']
    equal(report['assessment'],metrics,'Évaluation globale différente du recalcul.')
    require(report['technical_valid'] is (None if crash else True),'Validité technique incompatible.')
    equal(report['load_scenario'],metrics['load_scenario'],'Qualification de charge incohérente.')
    equal(report['connections'],metrics['connections'],'Qualification des connexions incohérente.')
    require(all(report[k]=='not_assessed' for k in ('congestion','comparison','coopace_benefit')), 'Bénéfice non établi déclaré.')
    if not crash:
        require(metrics['measurements_valid'] is True and metrics['load_scenario']=='qualified'
                and metrics['connections']=='confirmed','Charge qualifiée et 60 connexions réussies requises pour la revue positive.')
    for phase in report['phases']:
        if phase['result'] is None:continue
        for key in (('send','receive','latency') if phase['condition']=='loaded' else ('latency',)):
            value=phase['result'][key]
            require(value.get('go_version')==build['go_version'] and value.get('os')=='linux'
                    and value.get('architecture')=='amd64','Métadonnées des outils de phase incompatibles.')
    return facts


def validate_control(folder,report,tools,sources,build):
    """Recompute a single completed control, without a native certificate."""
    try:
        return base.validate_control(folder,report,tools,sources,build,path_validator=path.validate_path,campaign_validator=campaign_facts)
    except Error:raise
    except Exception as error:raise Error('Relecture globale refusée : '+str(error)) from error


def review(case):
    """Verify frozen inputs, both controls and observed cleanup; write nothing."""
    case=case.resolve(strict=True)
    raw=go.read(case/'prepared.json',8*1024*1024)
    seal=go.read(case/'prepared.sha256',1024).decode().strip().split('  ',1)
    require(seal==[hashlib.sha256(raw).hexdigest(),'prepared.json'],'Préparation modifiée.')
    prepared=go.protocol.document(raw,8*1024*1024)
    require(type(prepared['schema_version']) is int and prepared['schema_version']==1
            and prepared['tracked_tree_clean'] is True and type(prepared['native_launcher_available']) is bool
            and prepared['kind']=='lab_cake_go_campaign_preparation' and prepared['state']=='not_run'
            and prepared['native_execution']=='not_run' and prepared['native_steps']==['run','check-crash'], 'Préparation de campagne incompatible.')
    require(isinstance(prepared['source_commit'],str) and re.fullmatch('[0-9a-f]{40}',prepared['source_commit']), 'Commit préparé invalide.')
    count=base.verify_inputs(case,prepared)
    require(set(prepared['tools'])=={'worker','agent','target','load','python','ip','tc','sysctl','ping'},'Neuf outils figés requis.')
    for role,name in (('worker','coopace-cake-worker'),('agent','coopace'),('target','coopace-lab-tcp'),('load','coopace-lab-load')):
        require(prepared['tools'][role]['path']==str((case/'bin'/name).resolve(strict=True)), 'Rôle Go différent du binaire préparé.')
    for tool in prepared['tools'].values():equal(go.tool(tool['path']),tool,'Outil différent de la préparation.')
    snapshot=base.artifacts_snapshot(case)
    runtime=document(case/'runtime.json')
    require(runtime['kernel']==prepared['kernel'] and runtime['python_version']==prepared['python_version'],'Noyau ou Python modifié.')
    require((Path(prepared['project'])/'.go-version').read_text().strip()==prepared['go_version'].removeprefix('go'),'SDK incompatible.')
    build={'go_version':prepared['go_version'],'vcs':'git','vcs_revision':prepared['source_commit'],'vcs_modified':False}
    expected_binaries={'coopace-cake-worker','coopace','coopace-lab-tcp','coopace-lab-load'}
    require(set(prepared['build_info'])==expected_binaries,'Quatre provenances Go requises.')
    for name,info_name in prepared['build_info'].items():
        require(info_name==name+'.build-info.txt','Nom de provenance non canonique.')
        info=subprocess.check_output([prepared['go_executable'],'version','-m',str(case/'bin'/name)],
                                     env={**os.environ,'GOTOOLCHAIN':'local'},text=True,timeout=3)
        require(info==go.read(case/info_name,65536).decode() and info.splitlines()[0].endswith(prepared['go_version'])
                and all(v in info for v in ('vcs.revision='+prepared['source_commit'],'vcs.modified=false','GOOS=linux','GOARCH=amd64')),
                'Provenance de compilation modifiée.')
    results={}
    for mode in ('run','check-crash'):
        require(go.read(case/(mode+'.exit'),64)==b'0\n','Code superviseur non nul.')
        report=document(case/mode/'report.json');equal(report,document(case/(mode+'.stdout.json')),'Stdout différent du rapport.')
        environment=report['environment']
        require(environment['git_commit']==prepared['source_commit'] and environment['kernel']==runtime['kernel']
                and environment['python'].split()[0]==runtime['python_version'],'Environnement d’exécution différent.')
        equal(environment['versions']['ping'],prepared['ping_version'],'Producteur ping modifié.')
        results[mode]=validate_control(case/mode,report,prepared['tools'],prepared['supervisor_sources'],build)
        log=go.read(case/(mode+'.log'),4*1024*1024).decode()
        require(report['workspace'] in log and 'Processus récupérés et espaces du contrôle supprimés.' in log,'Nettoyage non consigné.')
        for name in report['namespaces']:
            require(all(not os.path.lexists(base_dir/name) for base_dir in (Path('/run/netns'),Path('/var/run/netns'))),'Namespace encore visible.')
        require(not os.path.lexists(report['workspace']),'Réservation encore visible.')
        require(all(not Path('/proc',str(pid)).exists() for pid in results[mode]['recorded_pids']),'PID consigné encore visible ; aucune action automatique.')
    require(len({n for result in results.values() for n in result['namespaces']})==6,'Ressources réutilisées entre contrôles.')
    require(base.verify_inputs(case,prepared)==count,'Entrées modifiées pendant la relecture.')
    equal(base.artifacts_snapshot(case),snapshot,'Pièces modifiées pendant la relecture.')
    return {'schema_version':1,'state':'campaign_evidence_reviewed','native_certificate':False,'source_commit':prepared['source_commit'],
            'reviewed_at':datetime.now(timezone.utc).isoformat(),'frozen_inputs_verified':count,'results':results,'artifact_sha256':snapshot}
