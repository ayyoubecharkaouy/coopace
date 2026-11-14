"""Bounded direct-veth flow while the unprivileged Go session remains applied."""

import math
import os
from pathlib import Path
import re
import subprocess
import time

import importlib.util
spec=importlib.util.spec_from_file_location('session_flow_base',Path(__file__).with_name('lab_gateway_session.py'))
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
runtime,require=base.runtime,base.require
VOLUME=4*1024*1024
TARGET='10.203.0.6:41001'
ADDRESSES=(('wan','10.203.0.5'),('eth0','10.203.0.6'))


def cake_flow_classes(raw):
    """iproute2 6.1 class show lacks JSON: read only the no-statistics headers.

    CAKE's class walker exposes intrinsic flow IDs, not configurable classes.
    Every nonempty line must name one flow of our single-tin root 10:.
    """
    require(isinstance(raw,bytes) and len(raw)<=65536,'Classes CAKE trop volumineuses.')
    try:text=raw.decode('ascii')
    except UnicodeError as error:raise runtime.Error('Classes CAKE non ASCII.') from error
    result=[]
    for line in text.splitlines():
        if not line.strip():continue
        match=re.fullmatch(r'class cake 10:([0-9a-f]{1,3}) parent 10:[ \t]*',line)
        require(match is not None,'Classe étrangère, option ou format non pris en charge.')
        value=int(match[1],16)
        require(1<=value<=1024 and value not in result,'Identifiant de flux CAKE invalide ou répété.')
        result.append(value)
    require(len(result)<=1024,'Trop de flux CAKE.')
    return result


def checked_flow(send_raw,receive_raw):
    send,receive=runtime.document(send_raw),runtime.document(receive_raw)
    for value,method,endpoint,timeout,count_field in (
        (send,'synthetic_tcp_send','target',15000,'written_bytes'),
        (receive,'synthetic_tcp_receive','listen',18000,'received_bytes')):
        expected={'schema_version':1,'method':method,endpoint:TARGET,'requested_bytes':VOLUME,
                  count_field:VOLUME,'timeout_ms':timeout,'block_bytes':16384}
        for key,item in expected.items():require(base.same_document(value.get(key),item),'Rapport de transfert incompatible : '+key)
    require(type(send.get('requested_bytes_per_second')) is int and send['requested_bytes_per_second']==1048576,
            'Plafond applicatif différent.')
    for value,key,limit in ((send,'elapsed_ms',15000),(receive,'receive_elapsed_ms',18000)):
        duration,rate=value.get(key),value.get('average_bytes_per_second')
        require(type(duration) in (int,float) and math.isfinite(duration) and 0<duration<limit
                and type(rate) in (int,float) and math.isfinite(rate) and rate>0
                and math.isclose(rate,VOLUME*1000/duration,rel_tol=1e-9),'Débit ou durée incohérent.')
    require(send['elapsed_ms']>=4000 and send['average_bytes_per_second']<=1048576,'Cadence applicative incompatible.')
    require(type(receive.get('elapsed_ms')) in (int,float) and math.isfinite(receive['elapsed_ms'])
            and receive['receive_elapsed_ms']<=receive['elapsed_ms']<18000,'Durée de réception incohérente.')
    return {'send':send,'receive':receive}


class Process:
    """One pinned helper, an unreaped leader and bounded raw evidence."""
    def __init__(self,flow,role,namespace,args):
        self.flow,self.role=flow,role
        tools,owner=flow.engine.tools,flow.owner
        tools.verify(('ip','load'))
        self.group=runtime.guards.processes.ProcessGroup()
        owner.process_groups.append(self.group)
        self.child=None;self.streams=[]
        self.stdout,self.stderr=bytearray(),bytearray()
        flow.helpers.append(self)
        flow.evidence.record('flow_launch_intent',role=role,namespace=namespace,arguments=args)
        self.child=subprocess.Popen([tools.specs['ip']['path'],'netns','exec',namespace,tools.executable('load'),*args],
            executable=tools.executable('ip'),pass_fds=tuple(tools.files.values()),start_new_session=True,
            stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            env={'LANG':'C','LC_ALL':'C'})
        self.group.attach(self.child)
        for stream,data in ((self.child.stdout,self.stdout),(self.child.stderr,self.stderr)):
            fd=os.dup(stream.fileno());os.set_blocking(fd,False);self.streams.append([fd,data,False])
        flow.evidence.record('flow_launched',role=role,pid=self.child.pid)

    def drain(self):
        for row in self.streams:
            fd,data,eof=row
            if eof:continue
            try:block=os.read(fd,4096)
            except BlockingIOError:continue
            data.extend(block);require(len(data)<=65536,'Sortie du transfert trop volumineuse.')
            if not block:row[2]=True

    def ready(self,prefix):
        deadline=min(self.flow.owner.deadline,time.monotonic()+3)
        while b'\n' not in self.stdout:
            self.flow.check();self.drain()
            require(not self.group.exited() and time.monotonic()<deadline,'Outil de transfert indisponible.')
            time.sleep(.005)
        require(bytes(self.stdout).split(b'\n',1)[0]==prefix,'Annonce de transfert incorrecte.')

    def stop(self):
        self.group.stop(time.monotonic()+3)
        try:
            deadline=time.monotonic()+1
            while self.streams and not all(row[2] for row in self.streams):
                require(time.monotonic()<deadline,'Fermeture des sorties non confirmée.')
                self.drain()
            require(all(row[2] for row in self.streams),'Sortie du transfert non fermée.')
        finally:
            for fd,_data,_eof in self.streams:os.close(fd)
            self.streams.clear()
            if self.child is not None:self.child.stderr.close()
        self.flow.evidence.save('flow-'+self.role+'.stdout',bytes(self.stdout))
        self.flow.evidence.save('flow-'+self.role+'.stderr',bytes(self.stderr))
        self.flow.evidence.record('flow_group_stopped',role=self.role,pid=self.child.pid if self.child else None,
            exit_code=self.group.driver_code,reaped_descendants=self.group.reaped_descendants)


class Flow:
    def __init__(self,owner,engine,evidence,pilot):
        self.owner,self.engine,self.evidence,self.pilot=owner,engine,evidence,pilot
        self.helpers=[];self.address_attempted=False;self.active=False;self.samples=[]
        self.report={'traffic_generated':False,'flow':None,'observed_with_live_helpers':False,'addresses_removed':False}

    def check(self):
        self.owner.check();self.engine.binding();self.pilot.drain()
        require(not self.owner.process_group.exited(),'Pilote Go arrêté pendant le transfert.')

    def addresses(self,allow_subset=False):
        for namespace,(interface,address) in zip((self.engine.gateway,self.engine.server),ADDRESSES):
            rows=base.recovery.cake.queue.document(self.engine.ip(namespace,['-j','address','show']))
            require({r.get('ifname') for r in rows}=={'lo',interface} and len(rows)==2,'Interfaces étrangères au transfert.')
            actual=[]
            for row in rows:
                for value in row.get('addr_info',[]):
                    require(row['ifname']==interface and value.get('family')=='inet'
                            and value.get('local')==address and value.get('prefixlen')==30,
                            'Adresse étrangère ; retrait refusé.')
                    actual.append(value)
            require(len(actual)<=1 and (allow_subset or len(actual)==1),'Adresses du transfert non conformes.')

    def prepare(self):
        self.engine.clean_endpoints()
        for namespace,(interface,address) in zip((self.engine.gateway,self.engine.server),ADDRESSES):
            self.address_attempted=True
            self.evidence.record('flow_address_add_intent',namespace=namespace,interface=interface,address=address+'/30')
            self.engine.ip(namespace,['address','add',address+'/30','dev',interface])
        self.addresses();self.active=True
        self.evidence.record('flow_addresses_verified')

    def sample(self,label):
        require(len(self.samples)<100,'Budget des relevés de trafic dépassé.')
        raw=self.engine.current_root();base.recovery.owned_cake(raw)
        row=base.recovery.cake.queue.document(raw)[0]
        value={'label':label,'bytes':row['bytes'],'packets':row['packets'],'backlog':row['backlog'],'qlen':row['qlen']}
        self.evidence.save(f'flow-queue-{len(self.samples):03d}.json',raw)
        if self.samples:
            require(value['bytes']>=self.samples[-1]['bytes'] and value['packets']>=self.samples[-1]['packets'],
                    'Compteurs CAKE en baisse pendant le transfert.')
        self.samples.append(value);self.evidence.record('flow_sample',sample=value)
        return value

    def start(self):
        self.check();self.prepare();self.sample('before')
        receiver=Process(self,'receiver',self.engine.server,
            ['receive','--listen',TARGET,'--bytes',str(VOLUME),'--duration','18s','--json'])
        receiver.ready(('READY '+TARGET).encode())
        self.report['traffic_generated']=None  # A failed launch/announcement can already have written data.
        sender=Process(self,'sender',self.engine.gateway,
            ['send','--target',TARGET,'--bytes',str(VOLUME),'--rate','1048576','--duration','15s','--announce-start'])
        sender.ready(b'STARTED')
        self.report['traffic_generated']=True
        deadline=min(self.owner.deadline,time.monotonic()+3)
        while True:
            self.check()
            for helper in self.helpers:helper.drain()
            sample=self.sample('during')
            require(all(not h.group.exited() for h in self.helpers),'Transfert déjà arrêté avant observation.')
            if sample['bytes']-self.samples[0]['bytes']>=16384 and sample['packets']>self.samples[0]['packets']:break
            require(time.monotonic()<deadline,'Trafic CAKE non observé.')
        self.report.update(traffic_generated=True,observed_with_live_helpers=True)
        self.evidence.record('flow_observed_while_go_applied',pilot_pid=self.owner.child.pid,
            helper_pids=[h.child.pid for h in self.helpers])

    def finish(self):
        deadline=min(self.owner.deadline,time.monotonic()+18)
        while True:
            self.check()
            for helper in self.helpers:helper.drain()
            if all(h.group.exited() and all(r[2] for r in h.streams) for h in self.helpers):break
            require(time.monotonic()<deadline,'Transfert non terminé dans sa fenêtre.')
            time.sleep(.01)
        receiver,sender=self.helpers
        require(os.waitid(os.P_PID,sender.child.pid,os.WEXITED|os.WNOWAIT).si_status==0
                and os.waitid(os.P_PID,receiver.child.pid,os.WEXITED|os.WNOWAIT).si_status==0,'Échec d’un outil de transfert.')
        flow=checked_flow(bytes(sender.stdout).split(b'\n',1)[1],bytes(receiver.stdout).split(b'\n',1)[1])
        last=self.sample('after')
        require(last['bytes']-self.samples[0]['bytes']>=VOLUME,'Volume non observé par CAKE.')
        self.report['flow']=flow
        self.evidence.record('flow_complete',received_bytes=VOLUME)

    def stop(self):
        failure=None
        for helper in reversed(self.helpers):
            try:helper.stop()
            except BaseException as error:failure=failure or error
        if failure is not None:raise failure

    def deactivate(self):
        if not self.address_attempted:return
        self.addresses(allow_subset=True)
        for namespace,(interface,address) in zip((self.engine.gateway,self.engine.server),ADDRESSES):
            rows=base.recovery.cake.queue.document(self.engine.ip(namespace,['-j','address','show']))
            if any(r.get('ifname')==interface and r.get('addr_info') for r in rows):
                self.evidence.record('flow_address_del_intent',namespace=namespace,interface=interface,address=address+'/30')
                self.engine.ip(namespace,['address','del',address+'/30','dev',interface])
        self.engine.clean_endpoints();self.active=False;self.report['addresses_removed']=True
        self.evidence.record('flow_addresses_removed')
