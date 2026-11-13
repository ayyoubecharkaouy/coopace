"""Read-only replay of the session protocol and independent recovery evidence."""

import importlib.util
from pathlib import Path
import struct

spec=importlib.util.spec_from_file_location('session_review_model',Path(__file__).with_name('lab_gateway_session.py'))
model=importlib.util.module_from_spec(spec);spec.loader.exec_module(model)
runtime,require=model.runtime,model.require
base=runtime.sibling('session_base_review','lab_queue_recovery_review.py')


def frames(raw):
    require(len(raw)<=65536,'Budget de trames dépassé.')
    result=[]
    while raw:
        require(len(raw)>=4,'Préfixe tronqué.')
        size=struct.unpack('>I',raw[:4])[0]
        require(0<size<=16384 and len(raw)>=size+4,'Trame tronquée ou excessive.')
        result.append(runtime.document(raw[4:4+size]));raw=raw[4+size:]
    return result


def review(folder,gateway):
    folder=Path(folder).resolve(strict=True)
    result=base.review(folder,gateway,session=True,sources=model.source_hashes())
    report=runtime.document(runtime.read(folder/'report.json'))
    require(report.get('session_state')=='restored_and_closed','Session non fermée après restauration.')
    files=report['artifacts_sha256']
    for name in ('control.frames','events.frames','worker.jsonl','worker.stderr'):
        require(name in files,'Preuve de session absente : '+name)
    require(runtime.read(folder/'worker.stderr')==b'','Diagnostic du pilote non vide.')
    controls=frames(runtime.read(folder/'control.frames'));events=frames(runtime.read(folder/'events.frames'))
    crash=report['mode']=='check-crash'
    require(len(controls)==(3 if crash else 4) and len(events)==(3 if crash else 4),'Dialogue incomplet.')
    token=report['namespaces'][0][3:-2]
    init=controls[0]
    expected={'schema_version':1,'kind':'gateway_session_init','session_id':token,'scope':'owned_lab',
        'reference':'cake-ipv4-lab-4mbit-v1','local_lab_consent':True,'operator_uid':init.get('operator_uid'),
        'namespace_identity':dict(zip(('device','inode'),report['namespace_identities'][1])),
        'before_path':str(folder/'before.json'),'before_sha256':files['before.json']}
    require(model.same_document(init,expected) and init['local_lab_consent'] is True and type(init['operator_uid']) is int
            and init['operator_uid']>0,'Contexte initial non lié au laboratoire.')
    phases=['ready','apply_requested','applied']+([] if crash else ['release_requested'])
    for i,(event,phase) in enumerate(zip(events,phases),1):
        expected={'schema_version':1,'kind':'gateway_session_event','session_id':token,'sequence':i,
            'phase':phase,'before_sha256':files['before.json']}
        if phase=='applied':expected['snapshot_sha256']=files['applied.json']
        require(model.same_document(event,expected),'Événement de session incohérent.')
    for i,(command,action) in enumerate(zip(controls[1:],['begin','applied','stop']),1):
        expected={'schema_version':1,'kind':'gateway_session_command','session_id':token,'sequence':i,
            'action':action,'before_sha256':files['before.json']}
        if action=='applied':expected.update(snapshot_path=str(folder/'applied.json'),snapshot_sha256=files['applied.json'])
        require(model.same_document(command,expected),'Commande non liée ou hors séquence.')
    journal=[runtime.document(line) for line in runtime.read(folder/'worker.jsonl').splitlines()]
    expected_journal=['launch',*phases]+([] if crash else ['worker_exit'])
    require([row.get('event') for row in journal]==expected_journal,'Journal du pilote incomplet.')
    for i,row in enumerate(journal,1):
        require(type(row.get('schema_version')) is int and row.get('schema_version')==1 and row.get('kind')=='gateway_session_worker_journal'
            and row.get('session_id')==token and type(row.get('sequence')) is int and row.get('sequence')==i and type(row.get('elapsed_ns')) is int
            and row['elapsed_ns']>=0,'Liaison du journal incohérente.')
    require([r['elapsed_ns'] for r in journal]==sorted(r['elapsed_ns'] for r in journal),'Horloge du journal incohérente.')
    require(model.same_document([r['data'] for r in journal[1:1+len(events)]],events),'Événement émis sans preuve durable identique.')
    require(model.same_document(journal[0]['data'],{'operator_uid':init['operator_uid'],'network_changes_executed':False}),'Privilèges du pilote non confirmés.')
    if not crash:require(model.same_document(journal[-1]['data'],{'awaiting_supervisor_recovery':True,'succeeded':True}),'Sortie du pilote non conforme.')
    audit=[runtime.document(line) for line in runtime.read(folder/'events.jsonl').splitlines()]
    observed=[row['event'] for row in audit if row.get('state')=='session_event']
    require(model.same_document(observed,events),'Dialogue du superviseur différent des trames.')
    def one(state):
        rows=[row for row in audit if row.get('state')==state]
        require(len(rows)==1,'Événement unique requis : '+state)
        return rows[0]
    launch=one('session_launch_intent')
    require(launch['session_id']==token and launch['operator_uid']==init['operator_uid']
        and launch['local_lab_consent'] is True and launch['bootstrap_sha256']==runtime.digest(model.BOOTSTRAP.encode()),'Lancement non lié.')
    event_positions=[row['sequence'] for row in audit if row.get('state')=='session_event']
    require(launch['sequence']<event_positions[0]<event_positions[1]<one('add_intent')['sequence']
        <one('owned_cake_verified')['sequence']<event_positions[2]<one('driver_group_stopped')['sequence'],
        'Application avant autorisation ou récupération prématurée.')
    if crash:
        kill=one('session_kill_intent')
        require(event_positions[2]<kill['sequence']<one('driver_group_stopped')['sequence'] and kill['pid']==report['driver_pid'],
            'Panne non liée au pilote appliqué.')
    else:require(event_positions[2]<event_positions[3]<one('driver_group_stopped')['sequence'],'Arrêt normal hors séquence.')
    environment=runtime.document(runtime.read(folder/'environment.json'))
    require(environment.get('kind')=='lab_gateway_session_environment','Environnement de session manquant.')
    tool=environment['tools']['worker']
    require(runtime.digest(runtime.read(tool['path'],64*1024*1024))==tool['sha256'],'Pilote Go modifié.')
    result.update(kind='lab_gateway_session_review',state='gateway_session_evidence_reviewed',
                  protocol_verified=True,session_state='restored_and_closed')
    return result
