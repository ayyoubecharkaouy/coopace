"""Freeze four Go binaries and a one-shot native CAKE/traffic validation bundle."""

import argparse
from datetime import datetime, timezone
import hashlib
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
spec=importlib.util.spec_from_file_location('native_active_model',ROOT/'scripts/lab_cake_go_active.py')
model=importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)

RUNNER=r'''#!/bin/sh
set -u
set -C
coopace_project=PROJECT
coopace_case=CASE
coopace_python=PYTHON
coopace_worker=WORKER
coopace_revision=REVISION
if [ "$(id -u)" = 0 ]; then
    printf '%s\n' 'Lancer avec le compte habituel ; seuls les deux contrôles appellent sudo.' >&2
    exit 2
fi
cd "$coopace_project" || exit 1
if ! mkdir "$coopace_case/run.lock"; then
    printf '%s\n' 'Un lancement est déjà réservé ; conserver les preuves.' >&2
    exit 2
fi
trap 'rmdir "$coopace_case/run.lock"' EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
for coopace_file in runtime.json check check-crash check.stdout.json check.log check.exit check-crash.stdout.json check-crash.log check-crash.exit review.stdout.json review.log review.exit validation.json; do
    if [ -e "$coopace_case/$coopace_file" ] || [ -L "$coopace_case/$coopace_file" ]; then
        printf '%s\n' 'Des résultats existent déjà ; conserver cet essai et préparer un autre dossier.' >&2
        exit 2
    fi
done
coopace_inputs() {
    sha256sum --check --status "$coopace_case/inputs.sha256" &&
    (cd "$coopace_case" && sha256sum --check --status prepared.sha256) &&
    [ "$(git rev-parse HEAD)" = "$coopace_revision" ]
}
if ! coopace_inputs; then
    printf '%s\n' 'Entrées ou révision modifiées ; aucun contrôle lancé.' >&2
    exit 2
fi
if ! "$coopace_python" -I -B -c 'from datetime import datetime,timezone; import json,os,platform,sys; from pathlib import Path; p=json.loads(Path(sys.argv[1]).read_text()); assert platform.release()==p["kernel"] and platform.python_version()==p["python_version"] and hasattr(os,"setns"); print(json.dumps({"started_at":datetime.now(timezone.utc).isoformat(),"kernel":platform.release(),"python_version":platform.python_version()}))' "$coopace_case/prepared.json" > "$coopace_case/runtime.json"; then
    printf '%s\n' 'Préconditions modifiées ; aucun contrôle lancé.' >&2
    exit 1
fi
printf '%s\n' 'Deux contrôles Go puis trafic : fin normale, puis mort forcée du pilote de trafic.'
printf '%s\n' 'Un transfert complet de 8 Mio attendu ; prévoir environ une minute, puis relecture hors ligne.'
for coopace_mode in check check-crash; do
    if ! coopace_inputs; then
        printf '%s\n' 'Entrées modifiées ; arrêt et conservation des résultats.' >&2
        exit 2
    fi
    mkdir -m 700 "$coopace_case/$coopace_mode" || exit 1
    if sudo -- "$coopace_python" -I -B "$coopace_project/scripts/lab-cake-go-active.py" "$coopace_mode" --worker "$coopace_worker" --binaries "$coopace_case/bin" --artifacts "$coopace_case/$coopace_mode" > "$coopace_case/$coopace_mode.stdout.json" 2> "$coopace_case/$coopace_mode.log"; then
        coopace_result=0
    else
        coopace_result=$?
    fi
    printf '%s\n' "$coopace_result" > "$coopace_case/$coopace_mode.exit" || exit 1
    printf 'Code %s : %s\n' "$coopace_mode" "$coopace_result"
    if [ "$coopace_result" != 0 ]; then
        printf 'Contrôle arrêté ; résultats conservés : %s\n' "$coopace_case"
        exit "$coopace_result"
    fi
done
if "$coopace_python" -I -B "$coopace_case/review-native.py" > "$coopace_case/review.stdout.json" 2> "$coopace_case/review.log"; then
    coopace_result=0
else
    coopace_result=$?
fi
printf '%s\n' "$coopace_result" > "$coopace_case/review.exit" || exit 1
printf 'Code relecture : %s\n' "$coopace_result"
printf 'Résultats : %s\n' "$coopace_case"
exit "$coopace_result"
'''



def runner_template(path_control=False):
    if not path_control:
        return RUNNER
    return RUNNER.replace('scripts/lab-cake-go-active.py', 'scripts/lab-cake-go-path.py').replace(
        'Deux contrôles Go puis trafic : fin normale, puis mort forcée du pilote de trafic.',
        'Deux contrôles Go puis passage IPv4 et trafic : fin normale, puis panne du pilote de trafic.').replace(
        'Un transfert complet de 8 Mio attendu ; prévoir environ une minute, puis relecture hors ligne.',
        'Blocage sans forwarding puis trois réponses avec forwarding dans chaque contrôle ; un transfert de 8 Mio attendu. Prévoir une à deux minutes.')


def profile(path_control=False, campaign=False):
    model.require(not (path_control and campaign), 'Profils IPv4 et campagne incompatibles.')
    if campaign:
        return {'prefix':'go-campaign-native-validation-', 'entry':'lab-cake-go-campaign.py',
                'protocol':'LAB_CAKE_GO_CAMPAIGN_PREPARE.md', 'review_entry':None,
                'kind':'lab_cake_go_campaign_preparation', 'steps':['run','check-crash']}
    return {'prefix':'go-path-native-validation-' if path_control else 'go-active-native-validation-',
            'entry':'lab-cake-go-path.py' if path_control else 'lab-cake-go-active.py',
            'review_entry':'lab-cake-go-path-review.py' if path_control else 'lab-cake-go-active-review.py',
            'protocol':'LAB_CAKE_GO_PATH_NATIVE.md' if path_control else 'LAB_CAKE_GO_ACTIVE_NATIVE.md',
            'kind':'lab_cake_go_path_preparation' if path_control else 'lab_cake_go_active_preparation',
            'steps':['check','check-crash']}


def supervisor_sources(path_control=False, campaign=False):
    if not (path_control or campaign):
        return model.source_fingerprints()
    filename='lab_cake_go_campaign.py' if campaign else 'lab_cake_go_path_control.py'
    spec=importlib.util.spec_from_file_location('frozen_control',ROOT/'scripts'/filename)
    control=importlib.util.module_from_spec(spec);spec.loader.exec_module(control)
    return control.source_fingerprints()


def command(args,**kwargs):
    return subprocess.check_output(args,cwd=ROOT,timeout=120,**kwargs)


def write(path,data):
    if isinstance(data,str):data=data.encode('utf-8')
    descriptor=model.go.exclusive(path)
    with os.fdopen(descriptor,'wb') as stream:
        stream.write(data);stream.flush();os.fsync(stream.fileno())


def prepare(destination=None, *, path_control=False, campaign=False):
    selected=profile(path_control, campaign)
    model.require(os.geteuid()!=0,'Compiler avec le compte habituel, sans sudo.')
    model.require(sys.platform=='linux' and platform.machine()=='x86_64' and hasattr(os,'setns'),
                  'Linux amd64 et Python avec setns requis.')
    model.require(not command(['git','status','--porcelain']),'Arbre Git non propre ; figer les sources avant préparation.')
    revision=command(['git','rev-parse','HEAD'],text=True).strip()
    if destination is None:
        (ROOT/'.local/experiments').mkdir(parents=True,exist_ok=True)
    prefix,entry,review_entry,protocol=(selected[k] for k in ('prefix','entry','review_entry','protocol'))
    case=destination or ROOT/'.local/experiments'/(prefix+revision[:7])
    case=case.parent.resolve(strict=True)/case.name
    case.mkdir(mode=0o700);(case/'bin').mkdir(mode=0o700)
    sdk='go'+(ROOT/'.go-version').read_text().strip()
    go_root=Path(command(['sh','scripts/go.sh','env','GOROOT'],text=True).strip())
    go_executable=(go_root/'bin/go').resolve(strict=True)
    build_info={}
    for name,package,help_args in (
        ('coopace-cake-worker','./apps/gateway/cmd/coopace-cake-worker',['--help']),
        ('coopace','./apps/agent/cmd/coopace',['--help']),
        ('coopace-lab-tcp','./scripts/lab-tcp',['--help']),
        ('coopace-lab-load','./scripts/lab-load',['send','--help'])):
        binary=case/'bin'/name
        subprocess.run(['sh','scripts/go.sh','build','-trimpath','-buildvcs=true','-o',str(binary),package],cwd=ROOT,check=True,timeout=120)
        info=command(['sh','scripts/go.sh','version','-m',str(binary)],text=True)
        model.require(info.splitlines()[0].endswith(sdk) and all(v in info for v in
                      ('vcs.revision='+revision,'vcs.modified=false','GOOS=linux','GOARCH=amd64')),'Provenance de compilation incompatible : '+name)
        build_info[name]=name+'.build-info.txt';write(case/build_info[name],info)
        help_result=subprocess.run([str(binary),*help_args],cwd=ROOT,capture_output=True,check=True,timeout=3)
        write(case/(name+'.help.txt'),help_result.stdout+help_result.stderr)
        print('Binaire figé : '+name,flush=True)
    tools={'worker':model.go.tool(case/'bin/coopace-cake-worker'),'agent':model.go.tool(case/'bin/coopace'),
           'target':model.go.tool(case/'bin/coopace-lab-tcp'),'load':model.go.tool(case/'bin/coopace-lab-load'),
           'python':model.go.tool(sys.executable)}
    for name in (('ip','tc','sysctl','ping') if path_control or campaign else ('ip','tc','sysctl')):
        path=shutil.which(name);model.require(path is not None,'Outil requis : '+name)
        tools[name]=model.go.tool(path)
    tc_version=command([tools['tc']['path'],'-V'],env={**os.environ,'LANG':'C','LC_ALL':'C'})
    model.collect.cake.producer(tc_version)
    write(case/'tc-version.txt',tc_version)
    write(case/'plan.txt',command([tools['python']['path'],'-I','-B',str(ROOT/'scripts'/entry),'plan']))
    write(case/'protocol.md',(ROOT/'docs'/protocol).read_bytes())
    write(case/'prepare.py',Path(__file__).read_bytes())
    if not campaign:
        wrapper='''from pathlib import Path
import importlib.util,json
case=Path(__file__).resolve().parent
prepared=json.loads((case/'prepared.json').read_text())
source=Path(prepared['project'])/'scripts/lab-cake-go-active-review.py'
spec=importlib.util.spec_from_file_location('frozen_review',source)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
raise SystemExit(module.main(['--artifacts',str(case)]))
'''
        wrapper=wrapper.replace('lab-cake-go-active-review.py',review_entry)
        write(case/'review-native.py',wrapper)
        runner=runner_template(path_control)
        for token,value in (('PROJECT',ROOT),('CASE',case),('PYTHON',tools['python']['path']),
                             ('WORKER',case/'bin/coopace-cake-worker'),('REVISION',revision)):
            runner=runner.replace('='+token+'\n','='+shlex.quote(str(value))+'\n')
        write(case/'run.sh',runner);subprocess.run(['sh','-n',str(case/'run.sh')],check=True,timeout=3)
    ping_version=None
    sources=supervisor_sources(path_control, campaign)
    if path_control or campaign:
        ping_result=subprocess.run([tools['ping']['path'],'-V'],capture_output=True,timeout=2,check=True,env={'LANG':'C','LC_ALL':'C'})
        model.require(ping_result.stdout.startswith(b'ping from iputils ') and max(len(ping_result.stdout),len(ping_result.stderr))<=65536,'Producteur ping iputils requis.')
        model.require(model.go.tool(tools['ping']['path'])==tools['ping'],'Ping modifié pendant la préparation.')
        ping_version={'available':True,'stdout':ping_result.stdout.decode('ascii'),'stderr':ping_result.stderr.decode('ascii')}
        write(case/'ping-version.json',json.dumps(ping_version,indent=2)+'\n')
        wrapper_name='prepare-cake-go-campaign.py' if campaign else 'prepare-cake-go-path.py'
        write(case/('prepare-campaign.py' if campaign else 'prepare-path.py'),(ROOT/'scripts'/wrapper_name).read_bytes())
    tracked=command(['git','ls-files','-z']).decode().strip('\0').split('\0')
    paths=[ROOT/name for name in tracked]+list(case.rglob('*'))+[Path(t['path']) for t in tools.values()]+[go_executable]
    inputs={}
    for path in sorted(set(paths)):
        if not path.is_file():continue
        key=str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
        model.require('\n' not in key and '\\' not in key,'Chemin incompatible avec le manifeste.')
        inputs[key]=hashlib.sha256(model.go.read(path,64*1024*1024)).hexdigest()
    if campaign:
        model.require(command(['git','rev-parse','HEAD'],text=True).strip()==revision,
                      'Révision modifiée pendant la préparation de campagne.')
        model.require(supervisor_sources(campaign=True)==sources, 'Sources du superviseur modifiées pendant la préparation.')
        for spec in tools.values():
            model.require(model.go.tool(spec['path'])==spec, 'Outil modifié pendant la préparation de campagne.')
    prepared={'schema_version':1,'kind':selected['kind'],'state':'not_run','project':str(ROOT),
              'source_commit':revision,'tracked_tree_clean':True,'prepared_at':datetime.now(timezone.utc).isoformat(),
              'kernel':platform.release(),'python_version':platform.python_version(),'go_version':sdk,
              'go_executable':str(go_executable),'tools':tools,'supervisor_sources':sources,
              'tracked_inputs':tracked,'inputs_sha256':inputs,'build_info':build_info,'native_steps':selected['steps'],
              'reference':model.go.protocol.REFERENCE,'native_execution':'not_run',
              'limits':['synthetic_ipv4_only','no_Coopace_benefit','no_household_restoration','no_Go_kill_during_tool']}
    if path_control or campaign:prepared['ping_version']=ping_version
    if campaign:prepared['native_launcher_available']=False
    write(case/'prepared.json',json.dumps(prepared,ensure_ascii=False,indent=2)+'\n')
    write(case/'prepared.sha256',hashlib.sha256((case/'prepared.json').read_bytes()).hexdigest()+'  prepared.json\n')
    write(case/'inputs.sha256',''.join(f'{value}  {name}\n' for name,value in inputs.items()))
    subprocess.run(['sha256sum','--check','--status',str(case/'inputs.sha256')],cwd=ROOT,check=True,timeout=15)
    model.require(not command(['git','status','--porcelain']),'Sources modifiées pendant la préparation.')
    print('Préparation terminée : '+str(case),flush=True)
    return case


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts',type=Path,help='dossier neuf ; son parent doit exister')
    args=parser.parse_args(argv)
    try:
        prepare(args.artifacts)
        return 0
    except Exception as error:
        print(f'Préparation refusée : {error}',file=sys.stderr)
        return 1

if __name__=='__main__':sys.exit(main())
