"""A Go session stays applied during one bounded, measured direct-veth flow."""

from datetime import datetime,timezone
import json
import os
from pathlib import Path
import signal
import time
import importlib.util
spec=importlib.util.spec_from_file_location('session_active_flow',Path(__file__).with_name('lab_gateway_session_flow.py'))
traffic=importlib.util.module_from_spec(spec);spec.loader.exec_module(traffic)
base,runtime,require=traffic.base,traffic.runtime,traffic.require


def source_hashes():
    return {**base.source_hashes(),**{name:runtime.digest(runtime.read(Path(__file__).with_name(name)))
        for name in ('lab_gateway_session_flow.py','lab_gateway_session_active.py','lab-gateway-session-active.py',
                     'lab_gateway_session_active_review.py')}}


class Engine(base.recovery.Engine):
    def capture(self,name):
        if name!='pre-restore.json' or not self.applied:return super().capture(name)
        # Keep the public snapshot truthful: legacy nonempty classes remain
        # unavailable, with an additional independent no-statistics class dump.
        raw,_=self.call('ip',['netns','exec',self.gateway,self.tools.executable('gateway'),
                            'snapshot','--interface','wan','--json'],extra=('gateway','ip','tc'),timeout=20)
        source=runtime.document(raw);self.evidence.save(name,raw)
        checked=self.evaluate(name+'.import.json',['restore-plan','--snapshot',str(self.evidence.folder/name),'--json'],allowed=(0,3))
        require(checked.get('before_sha256')==self.evidence.files[name],'Empreinte de capture incohérente.')
        body=source['snapshot'];readings=body['readings']
        require(body['interface']==self.baseline['snapshot']['interface'],'Identité du veth modifiée.')
        for row in readings:
            require(row['path']==self.tools.specs[row['tool']]['path'],'Outil de capture différent.')
            if row['section']=='classes':
                require((row['available'] is True and row['value']==[]) or
                        (row['available'] is False and row['value'] is None),'Classes JSON non prises en charge.')
            else:
                require(row['available'] is True,'Lecture sélectionnée indisponible.')
                if row['section'].startswith('filters_'):require(row['value']==[],'Filtre étranger ; retrait refusé.')
        require(readings[1]['available'] is True,'Racine inconnue.')
        base.recovery.owned_cake(json.dumps(readings[1]['value']).encode())
        classes=self.tc(['class','show','dev','wan'])
        self.evidence.save(name+'.classes.txt',classes)
        ids=traffic.cake_flow_classes(classes)
        self.evidence.record('cake_intrinsic_flows_verified',flow_ids=ids,source=name+'.classes.txt',
                             snapshot_partial=source['partial'])
        return source


def cycle(mode,owner,engine,evidence,consent,*,pilot_factory=base.Pilot,flow_factory=traffic.Flow):
    require(mode in ('check','check-crash'),'Mode actif inconnu.')
    result={'schema_version':1,'kind':'lab_gateway_session_active','mode':mode,'state':'failed',
        'started_at':datetime.now(timezone.utc).isoformat(),'cleanup_verified':False,
        'traffic_generated':False,'real_gateway_restoration_validated':False,
        'traffic_scope':'gateway_to_server_virtual_ipv4','congestion':'not_assessed'}
    pilot,flow,failure,cleanup_failure=None,None,None,None
    previous={};interruption=0;recovering=False;sources=source_hashes()
    for signum in (signal.SIGHUP,signal.SIGINT,signal.SIGTERM):
        previous[signum]=signal.getsignal(signum)
        def interrupted(received,_frame):
            nonlocal interruption
            interruption=interruption or 128+received
            if not recovering:owner.interruption=interruption
        signal.signal(signum,interrupted)
    try:
        try:
            owner.create();engine.setup()
            result['producer']=base.recovery.cake.producer(engine.tc(['-V']))
            pilot=pilot_factory(owner,engine,evidence,consent);pilot.start();pilot.receive('ready')
            pilot.command(1,'begin');pilot.receive('apply_requested')
            require(consent and source_hashes()==sources,'Accord ou sources non conformes.')
            engine.apply()
            pilot.command(2,'applied',snapshot_path=str(evidence.folder/'applied.json'),snapshot_sha256=evidence.files['applied.json'])
            pilot.receive('applied',evidence.files['applied.json'])
            flow=flow_factory(owner,engine,evidence,pilot);flow.start()
            if mode=='check-crash':
                evidence.record('session_kill_intent',pid=owner.child.pid,during_observed_flow=True)
                os.kill(owner.child.pid,signal.SIGKILL)
            else:
                flow.finish();pilot.command(3,'stop');pilot.receive('release_requested')
            pilot.wait_exit()
        except BaseException as error:failure=error
        finally:
            recovering=True;owner.interruption=0;owner.deadline=time.monotonic()+40
            groups_stopped=False
            try:
                try:
                    if flow is not None:flow.stop()
                finally:
                    owner.stop_group(time.monotonic()+3);groups_stopped=True
                    evidence.record('driver_group_stopped',exit_code=owner.driver_code,reaped_descendants=owner.reaped_descendants)
            except BaseException as error:failure=failure or error
            try:
                if groups_stopped:
                    try:
                        if pilot is not None:pilot.close()
                    finally:
                        try:
                            if flow is not None:flow.deactivate()
                        finally:
                            if engine.add_attempted:engine.restore()
            except BaseException as error:failure=failure or error
            finally:
                try:engine.release();evidence.record('namespace_bindings_closed')
                except BaseException as error:failure=failure or error
                owner.interruption=0;owner.deadline=time.monotonic()+10
                try:owner.close();result['cleanup_verified']=True
                except BaseException as error:cleanup_failure=error
        require(failure is None,str(failure));require(cleanup_failure is None,str(cleanup_failure))
        require(not interruption,'Supervision interrompue.')
        require(owner.driver_code==(-signal.SIGKILL if mode=='check-crash' else 0) and owner.reaped_descendants==0,'Arrêt Go non conforme.')
        require(flow.report['traffic_generated'] and flow.report['observed_with_live_helpers'] and flow.report['addresses_removed'],
                'Trafic ou remise en état des adresses non confirmé.')
        require(engine.applied and engine.removed and engine.restored,'Retour à la file initiale incomplet.')
        if mode=='check':
            require(flow.report['flow'] is not None and all(h.group.driver_code==0 for h in flow.helpers),'Transfert incomplet.')
        engine.tools.verify();require(source_hashes()==sources,'Sources actives modifiées.')
        result.update(state='complete',session_state='restored_and_closed')
    except BaseException as error:
        result['error']=str(error)
        if cleanup_failure is not None:result['cleanup_error']=str(cleanup_failure)
    finally:
        result.update(restoration_verified=engine.restored,applied_verified=engine.applied,root_removed=engine.removed,
            driver_exit_code=owner.driver_code,driver_pid=owner.child.pid if owner.child else None,
            reaped_descendants=owner.reaped_descendants,namespaces=[n for n,_i in owner.owned],
            namespace_identities=[list(i) if i else None for _n,i in owner.owned],workspace=str(owner.workspace) if owner.workspace else None,
            interruption_code=interruption,finished_at=datetime.now(timezone.utc).isoformat())
        if flow is not None:
            result.update(traffic_generated=flow.report['traffic_generated'],traffic=flow.report,queue_samples=flow.samples,
                flow_groups=[{'role':h.role,'pid':h.child.pid if h.child else None,'state':h.group.state,
                              'exit_code':h.group.driver_code,'reaped_descendants':h.group.reaped_descendants} for h in flow.helpers])
        try:evidence.finish();result['artifacts_sha256']=dict(evidence.files);evidence.save('report.json',result)
        finally:
            for signum,handler in previous.items():signal.signal(signum,handler)
    return result
