"""Read-only evidence review of one measured flow and its Go-session recovery."""
import json
from pathlib import Path
import re
import subprocess
import importlib.util
spec=importlib.util.spec_from_file_location('active_review_model',Path(__file__).with_name('lab_gateway_session_active.py'))
model=importlib.util.module_from_spec(spec);spec.loader.exec_module(model)
runtime,require,base=model.runtime,model.require,model.base
protocol=runtime.sibling('active_review_frames','lab_gateway_session_review.py')


def review(folder,gateway):
    folder=Path(folder).resolve(strict=True);r=runtime.document(runtime.read(folder/'report.json'));files=r.get('artifacts_sha256')
    require(r.get('kind')=='lab_gateway_session_active' and type(r.get('schema_version')) is int and r['schema_version']==1
            and r.get('state')=='complete' and r.get('mode') in ('check','check-crash'),'Contrôle actif complet requis.')
    crash=r['mode']=='check-crash'
    for key in ('applied_verified','root_removed','restoration_verified','cleanup_verified','traffic_generated'):
        require(r.get(key) is True,'Preuve active absente : '+key)
    require(r.get('real_gateway_restoration_validated') is False and r.get('session_state')=='restored_and_closed'
        and r.get('traffic_scope')=='gateway_to_server_virtual_ipv4' and r.get('congestion')=='not_assessed','Portée active incohérente.')
    require(isinstance(files,dict) and len(files)>20,'Inventaire actif manquant.')
    for name,sha in files.items():
        require(isinstance(name,str) and Path(name).name==name and name not in ('.','..','report.json')
                and isinstance(sha,str) and re.fullmatch('[a-f0-9]{64}',sha),'Entrée de preuve invalide.')
        require(runtime.digest(runtime.read(folder/name))==sha,'Preuve modifiée : '+name)
    for name in ('environment.json','events.jsonl','worker.jsonl','worker.stderr','events.frames','control.frames',
                 'before.json','pre-add.json','applied.json','pre-restore.json','after.json','comparison.json',
                 'pre-restore.json.classes.txt','flow-receiver.stdout','flow-sender.stdout'):
        require(name in files,'Preuve requise absente : '+name)
    env=runtime.document(runtime.read(folder/'environment.json'))
    require(env.get('kind')=='lab_gateway_session_active_environment' and env.get('source_sha256')==model.source_hashes(),'Sources actives différentes.')
    gateway=Path(gateway).resolve(strict=True)
    require(str(gateway)==env['tools']['gateway']['path'],'Passerelle différente.')
    for name in ('gateway','worker','load'):
        tool=env['tools'][name];require(runtime.digest(runtime.read(tool['path'],64*1024*1024))==tool['sha256'],'Binaire différent : '+name)
    names=r['namespaces'];token=names[0][3:-2]
    require(re.fullmatch('[a-z0-9_]{8}',token) and names==[f'cg-{token}-{role}' for role in ('c','g','s')],'Réservation non liée.')
    commands=protocol.frames(runtime.read(folder/'control.frames'));events=protocol.frames(runtime.read(folder/'events.frames'))
    phases=['ready','apply_requested','applied']+([] if crash else ['release_requested'])
    require(len(events)==len(phases) and len(commands)==len(phases),'Dialogue incomplet.')
    init=commands[0]
    require(type(init.get('operator_uid')) is int and init['operator_uid']>0,'UID opérateur invalide.')
    expected={'schema_version':1,'kind':'gateway_session_init','session_id':token,'scope':'owned_lab','reference':'cake-ipv4-lab-4mbit-v1',
        'local_lab_consent':True,'operator_uid':init['operator_uid'],'namespace_identity':dict(zip(('device','inode'),r['namespace_identities'][1])),
        'before_path':str(folder/'before.json'),'before_sha256':files['before.json']}
    require(base.same_document(init,expected),'Initialisation non liée.')
    for i,(event,phase) in enumerate(zip(events,phases),1):
        expected={'schema_version':1,'kind':'gateway_session_event','session_id':token,'sequence':i,'phase':phase,'before_sha256':files['before.json']}
        if phase=='applied':expected['snapshot_sha256']=files['applied.json']
        require(base.same_document(event,expected),'Événement Go non lié.')
    for i,(command,action) in enumerate(zip(commands[1:],('begin','applied','stop')),1):
        expected={'schema_version':1,'kind':'gateway_session_command','session_id':token,'sequence':i,'action':action,'before_sha256':files['before.json']}
        if action=='applied':expected.update(snapshot_path=str(folder/'applied.json'),snapshot_sha256=files['applied.json'])
        require(base.same_document(command,expected),'Commande Go non liée.')
    journal=[runtime.document(line) for line in runtime.read(folder/'worker.jsonl').splitlines()]
    require([v['event'] for v in journal]==['launch',*phases]+([] if crash else ['worker_exit']),'Journal Go incomplet.')
    for i,v in enumerate(journal,1):
        require(base.same_document(v.get('sequence'),i) and v.get('kind')=='gateway_session_worker_journal' and v.get('session_id')==token,'Journal Go non lié.')
    require(base.same_document([v['data'] for v in journal[1:1+len(events)]],events),'Journal Go différent des événements.')
    require(base.same_document(journal[0]['data'],{'network_changes_executed':False,'operator_uid':init['operator_uid']})
            and runtime.read(folder/'worker.stderr')==b'','Lancement Go invalide.')
    if not crash:require(base.same_document(journal[-1]['data'],{'awaiting_supervisor_recovery':True,'succeeded':True}),'Sortie Go incorrecte.')
    audit=[runtime.document(line) for line in runtime.read(folder/'events.jsonl').splitlines()]
    require(base.same_document([v['sequence'] for v in audit],list(range(1,len(audit)+1))),'Journal superviseur hors séquence.')
    require(base.same_document([v['event'] for v in audit if v['state']=='session_event'],events),'Dialogue du superviseur différent.')
    def one(state):
        values=[v for v in audit if v['state']==state];require(len(values)==1,'Événement unique requis : '+state);return values[0]
    ordered=['baseline_verified','session_launch_intent','add_intent','owned_cake_verified','flow_addresses_verified',
             'flow_observed_while_go_applied', 'session_kill_intent' if crash else 'flow_complete',
             'driver_group_stopped','flow_addresses_removed','cake_intrinsic_flows_verified','remove_intent',
             'owned_root_removed','selected_initial_state_verified','namespace_bindings_closed']
    sequence=[one(state)['sequence'] for state in ordered];require(sequence==sorted(sequence),'Récupération active hors ordre.')
    phase_positions={v['event']['phase']:v['sequence'] for v in audit if v['state']=='session_event'}
    require(phase_positions['apply_requested']<one('add_intent')['sequence'] and phase_positions['applied']<one('flow_addresses_verified')['sequence'],
            'Application ou transfert prématuré.')
    expected_code=-9 if crash else 0
    require(base.same_document(r.get('driver_exit_code'),expected_code) and base.same_document(r.get('reaped_descendants'),0)
            and base.same_document(r.get('interruption_code'),0),'Sortie Go incorrecte.')
    require(one('driver_group_stopped')['exit_code']==expected_code,'Groupe Go non récupéré.')
    stopped=[v for v in audit if v['state']=='flow_group_stopped']
    require(len(stopped)==2 and {v['role'] for v in stopped}=={'sender','receiver'}
        and all(v['sequence']<one('driver_group_stopped')['sequence'] and v['reaped_descendants']==0 for v in stopped),'Groupes TCP non récupérés.')
    expected_groups={v['role']:{'role':v['role'],'pid':v['pid'],'state':'stopped','exit_code':v['exit_code'],
                              'reaped_descendants':0} for v in stopped}
    groups=r.get('flow_groups',[])
    require(len(groups)==2 and base.same_document({v['role']:v for v in groups},expected_groups),'Groupes du rapport différents du journal.')
    observed=one('flow_observed_while_go_applied')
    require(observed.get('pilot_pid')==r['driver_pid'] and set(observed['helper_pids'])=={v['pid'] for v in stopped},'PID de transfert non liés.')
    if crash:
        kill=one('session_kill_intent');require(kill.get('pid')==r['driver_pid'] and kill.get('during_observed_flow') is True,'Panne hors transfert.')
        require(r['traffic']['flow'] is None,'Transfert complet revendiqué après panne.')
    else:
        flow=model.traffic.checked_flow(runtime.read(folder/'flow-sender.stdout').split(b'\n',1)[1],runtime.read(folder/'flow-receiver.stdout').split(b'\n',1)[1])
        require(base.same_document(flow,r['traffic']['flow']) and all(v['exit_code']==0 for v in stopped),'Transfert incomplet.')
        require(one('flow_complete')['sequence']<phase_positions['release_requested']<one('driver_group_stopped')['sequence'],'Arrêt Go avant fin du transfert.')
    require(all(r['traffic'].get(key) is True for key in ('traffic_generated','observed_with_live_helpers','addresses_removed')),'Phase active incomplète.')
    samples=r['queue_samples'];require(len(samples)>=2 and samples[0]['label']=='before' and any(v['label']=='during' for v in samples),'Relevés du trafic incomplets.')
    for i,sample in enumerate(samples):
        name=f'flow-queue-{i:03d}.json';require(name in files,'Relevé de file absent.')
        raw=runtime.read(folder/name);base.recovery.owned_cake(raw);row=base.recovery.cake.queue.document(raw)[0]
        require(all(base.same_document(sample[k],row[k]) for k in ('bytes','packets','backlog','qlen')),'Compteurs non liés aux relevés.')
        if i:require(sample['bytes']>=samples[i-1]['bytes'] and sample['packets']>=samples[i-1]['packets'],'Compteurs en baisse.')
    during=[v for v in samples if v['label']=='during'];require(any(v['bytes']-samples[0]['bytes']>=16384 and v['packets']>samples[0]['packets'] for v in during),'Trafic non observé.')
    if not crash:require(samples[-1]['label']=='after' and samples[-1]['bytes']-samples[0]['bytes']>=model.traffic.VOLUME,'Volume non observé par CAKE.')
    require(one('cake_intrinsic_flows_verified')['flow_ids']==model.traffic.cake_flow_classes(runtime.read(folder/'pre-restore.json.classes.txt')),'Classes non vérifiées.')
    commands_audit=[v for v in audit if v['state']=='command_intent'];results=[v for v in audit if v['state']=='command_result']
    require([v['command'] for v in commands_audit]==list(range(1,len(commands_audit)+1))==[v['command'] for v in results]
            and all(v.get('group_stopped') is True and v.get('error') is None and v.get('exit_code') in (0,3) for v in results),'Commandes non récupérées.')
    prefix=['netns','exec',names[1],'/proc/self/fd/'+str(env['tool_descriptors']['tc']),'qdisc']
    mutations=[v['arguments'] for v in commands_audit if v.get('tool')=='ip' and v.get('arguments',[])[:5]==prefix]
    require(mutations==[[*prefix,'add','dev','wan','root','handle','10:',*base.recovery.cake.ARGUMENTS],
                        [*prefix,'del','dev','wan','root','handle','10:']],'Mutations de file différentes.')
    identities=r['namespace_identities'];retained=one('namespace_bindings_retained')
    require(len(identities)==3 and len({tuple(v) for v in identities})==3
        and all(len(v)==2 and all(type(n) is int and n>0 for n in v) for v in identities)
        and retained.get('origin_identity') not in identities
        and retained.get('namespaces')==[{'name':name,'identity':identity} for name,identity in zip(names,identities)],
        'Espaces retenus non liés à la session.')
    reference=runtime.document(runtime.read(folder/'before.json'))['snapshot']['interface']
    for name in ('pre-add.json','applied.json','pre-restore.json'):
        imported=subprocess.run([str(gateway),'restore-plan','--snapshot',str(folder/name),'--json'],
            stdin=subprocess.DEVNULL,capture_output=True,timeout=10)
        require(imported.returncode in (0,3),'Capture conservée non importable.')
        require(runtime.document(imported.stdout).get('before_sha256')==files[name],'Import non lié aux octets de la capture.')
        capture=runtime.document(runtime.read(folder/name));body=capture['snapshot'];readings=body['readings']
        require(body['interface']==reference,'Identité du lien modifiée.')
        require(all(row['available'] is True and row['value']==[] for row in readings[3:]),'Filtre étranger dans la capture.')
        classes=readings[2]
        require((classes['available'] is True and classes['value']==[]) or
            (name=='pre-restore.json' and classes['available'] is False and classes['value'] is None),'Classes non prises en charge.')
        require(all(row['available'] is True for row in readings[:2]),'Capture du lien ou de la racine indisponible.')
        if name!='pre-add.json':base.recovery.owned_cake(json.dumps(readings[1]['value']).encode())
    completed=subprocess.run([str(gateway),'restore-check','--before',str(folder/'before.json'),'--after',str(folder/'after.json'),'--json'],
        stdin=subprocess.DEVNULL,capture_output=True,timeout=10,check=True)
    for value in (runtime.document(completed.stdout),runtime.document(runtime.read(folder/'comparison.json'))):
        require(value.get('decision')=='selected_state_matches' and value.get('before_sha256')==files['before.json']
            and value.get('after_sha256')==files['after.json'] and value.get('execution_authorized') is False,'Retour initial non reproductible.')
    for name in names:require(not (Path('/run/netns')/name).exists() and not (Path('/var/run/netns')/name).exists(),'Namespace encore visible.')
    workspace=Path(r['workspace']);require(workspace.name=='coopace-guard.'+token and workspace.is_absolute() and not workspace.exists(),'Réservation encore visible.')
    pids={r['driver_pid'],*[v['pid'] for v in stopped],*[v['pid'] for v in results]}
    require(all(type(pid) is int and pid>1 and not Path('/proc',str(pid)).exists() for pid in pids),'Processus encore visible.')
    return {'schema_version':1,'kind':'lab_gateway_session_active_review','state':'gateway_session_active_evidence_reviewed',
        'mode':r['mode'],'protocol_verified':True,'selected_state_matches':True,'artifacts_verified':len(files),'native_certificate':False,
        'execution_source':'simulated' if env.get('simulation') is True else 'native_control_report',
        'report_sha256':runtime.digest(runtime.read(folder/'report.json')),'real_gateway_restoration_validated':False}
