"""Unprivileged Go session decisions over the validated lab recovery engine."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import struct
import subprocess
import time

import importlib.util
spec = importlib.util.spec_from_file_location("session_recovery", Path(__file__).with_name("lab_queue_recovery.py"))
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)
runtime, require = recovery.runtime, recovery.require

# Enter the namespace before the Go runtime creates threads, then permanently
# drop UID/GID. Go receives no executable descriptors or CAP_NET_ADMIN.
BOOTSTRAP = r'''
import fcntl, os, sys
sources=[int(v) for v in sys.argv[1].split(',')]
uid,gid=int(sys.argv[2]),int(sys.argv[3])
assert uid>0 and gid>0
copies=[fcntl.fcntl(fd,fcntl.F_DUPFD_CLOEXEC,32) for fd in sources]
for destination,source in zip(range(3,8),copies[:5]):os.dup2(source,destination,inheritable=True)
executable=copies[5]
for name in os.listdir('/proc/self/fd'):
    fd=int(name)
    if fd not in {0,1,2,3,4,5,6,7,executable}:
        try:os.close(fd)
        except OSError:pass
os.setns(5,os.CLONE_NEWNET)
os.setgroups([]);os.setgid(gid);os.setuid(uid)
os.execve('/proc/self/fd/'+str(executable),sys.argv[4:],{'LANG':'C','LC_ALL':'C'})
'''


def source_hashes():
    return {**recovery.source_hashes(), **{name:runtime.digest(runtime.read(Path(__file__).with_name(name)))
        for name in ("lab_gateway_session.py", "lab-gateway-session.py", "lab_gateway_session_review.py", "lab_queue_recovery_review.py")}}


def same_document(value, expected):
    # Python's equality aliases True/1 and 1/1.0; the wire contract does not.
    return json.dumps(value, sort_keys=True, allow_nan=False) == json.dumps(expected, sort_keys=True, allow_nan=False)


class Pilot:
    def __init__(self, owner, engine, evidence, consent):
        self.owner, self.engine, self.evidence, self.consent = owner, engine, evidence, consent
        self.token = owner.workspace.name.removeprefix("coopace-guard.")
        self.fds, self.control, self.events = [], None, None
        self.buffer, self.raw_events, self.raw_control, self.stderr = bytearray(), bytearray(), bytearray(), bytearray()
        self.event_sequence = 0
        self.uid = evidence.folder.stat().st_uid
        self.gid = evidence.folder.stat().st_gid
        self.journal_identity = None

    def keep(self, fd):
        self.fds.append(fd)
        return fd

    def start(self):
        require(self.uid > 0 and self.gid > 0, "Compte opérateur ordinaire requis.")
        tools, owner = self.engine.tools, self.owner
        tools.verify()
        control_read, control_write = os.pipe2(os.O_CLOEXEC)
        self.keep(control_read); self.control = self.keep(control_write)
        event_read, event_write = os.pipe2(os.O_CLOEXEC)
        self.events = self.keep(event_read); self.keep(event_write)
        journal = self.keep(os.open(self.evidence.folder/"worker.jsonl",
            os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_APPEND|os.O_CLOEXEC, 0o600))
        os.fchown(journal, self.uid, self.gid)
        info = os.fstat(journal)
        self.journal_identity = info.st_dev, info.st_ino
        os.fsync(journal)
        directory = os.open(self.evidence.folder, os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(directory)
        finally:os.close(directory)
        target = next(fd for name, _identity, fd in self.engine.retained if name == self.engine.gateway)
        sources = [control_read, event_write, target, self.engine.original, journal, tools.files['worker']]
        require(owner.child is None and owner.process_group.state == 'new', "Groupe de session neuf requis.")
        self.evidence.record('session_launch_intent', session_id=self.token, operator_uid=self.uid,
                             local_lab_consent=self.consent, bootstrap_sha256=runtime.digest(BOOTSTRAP.encode()))
        owner.child = subprocess.Popen([tools.specs['python']['path'], '-I', '-S', '-c', BOOTSTRAP,
            ','.join(map(str,sources)), str(self.uid), str(self.gid), tools.specs['worker']['path'],
            '--session-id', self.token], executable=tools.executable('python'),
            pass_fds=tuple(dict.fromkeys([*sources,tools.files['python']])), start_new_session=True,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={'LANG':'C','LC_ALL':'C'})
        for fd in (control_read,event_write,journal):
            os.close(fd);self.fds.remove(fd)
        for fd in (self.control,self.events,owner.child.stdout.fileno(),owner.child.stderr.fileno()):os.set_blocking(fd,False)
        dev, ino = dict(owner.owned)[self.engine.gateway]
        self.send({'schema_version':1,'kind':'gateway_session_init','session_id':self.token,
            'scope':'owned_lab','reference':'cake-ipv4-lab-4mbit-v1','local_lab_consent':self.consent,
            'operator_uid':self.uid,'namespace_identity':{'device':dev,'inode':ino},
            'before_path':str(self.evidence.folder/'before.json'), 'before_sha256':self.evidence.files['before.json']})

    def drain(self):
        child = self.owner.child
        if child is None:return
        if not child.stdout.closed:
            try:raw=os.read(child.stdout.fileno(),1)
            except BlockingIOError:raw=b''
            require(not raw, 'Sortie stdout inattendue du pilote.')
        if not child.stderr.closed:
            try:raw=os.read(child.stderr.fileno(),4097)
            except BlockingIOError:raw=b''
            self.stderr.extend(raw)
            require(len(self.stderr)<=4096,'Diagnostic du pilote trop volumineux.')

    def send(self,value):
        raw=json.dumps(value,allow_nan=False,separators=(',',':')).encode()
        require(0<len(raw)<=16384,'Trame de contrôle trop volumineuse.')
        frame=struct.pack('>I',len(raw))+raw
        self.raw_control.extend(frame)
        require(len(self.raw_control)<=65536,'Budget de contrôle dépassé.')
        deadline=min(self.owner.deadline,time.monotonic()+5)
        while frame:
            self.owner.check();self.drain()
            require(time.monotonic()<deadline,'Canal de contrôle bloqué.')
            try:n=os.write(self.control,frame)
            except BlockingIOError:n=0
            frame=frame[n:]
            if not n:time.sleep(.005)

    def command(self,sequence,action,**fields):
        self.send({'schema_version':1,'kind':'gateway_session_command','session_id':self.token,
            'sequence':sequence,'action':action,'before_sha256':self.evidence.files['before.json'],**fields})

    def receive(self,phase,sha=None):
        deadline=min(self.owner.deadline,time.monotonic()+10)
        while True:
            self.owner.check();self.drain()
            require(time.monotonic()<deadline,'Événement de session absent.')
            if len(self.buffer)>=4:
                size=struct.unpack('>I',self.buffer[:4])[0]
                require(0<size<=16384,'Taille de trame invalide.')
                if len(self.buffer)>=size+4:
                    value=runtime.document(bytes(self.buffer[4:size+4]));del self.buffer[:size+4]
                    expected={'schema_version':1,'kind':'gateway_session_event','session_id':self.token,
                        'sequence':self.event_sequence+1,'phase':phase,'before_sha256':self.evidence.files['before.json']}
                    if sha is not None:expected['snapshot_sha256']=sha
                    require(same_document(value,expected),'Événement de session inattendu ou non lié à la référence.')
                    self.event_sequence+=1
                    self.evidence.record('session_event',event=value)
                    return value
            try:raw=os.read(self.events,4096)
            except BlockingIOError:raw=None
            if raw is not None:
                require(raw,'Canal événement fermé prématurément.')
                self.buffer.extend(raw);self.raw_events.extend(raw)
                require(len(self.raw_events)<=65536,'Budget événement dépassé.')
            else:time.sleep(.005)

    def wait_exit(self):
        deadline=min(self.owner.deadline,time.monotonic()+5)
        while not self.owner.process_group.exited():
            self.owner.check();self.drain()
            require(time.monotonic()<deadline,'Le pilote ne termine pas.')
            time.sleep(.005)
        self.drain()

    def close(self):
        # Called only after the entire group has stopped: retain/reject any
        # extra frame instead of silently discarding unread protocol output.
        trailing=bool(self.buffer)
        if self.events is not None:
            while True:
                try:raw=os.read(self.events,4096)
                except BlockingIOError:break
                if not raw:break
                trailing=True;self.raw_events.extend(raw)
                if len(self.raw_events)>65536:break
        for fd in self.fds:os.close(fd)
        self.fds.clear()
        self.drain()
        if self.owner.child is not None:self.owner.child.stderr.close()
        for name,data in (('control.frames',self.raw_control),('events.frames',self.raw_events),('worker.stderr',self.stderr)):
            self.evidence.save(name,bytes(data))
        if self.journal_identity is not None:
            info=os.stat(self.evidence.folder/'worker.jsonl',follow_symlinks=False)
            require((info.st_dev,info.st_ino)==self.journal_identity and info.st_nlink==1 and info.st_mode&0o7777==0o600,
                    'Identité du journal modifiée.')
            self.evidence.files['worker.jsonl']=runtime.digest(runtime.read(self.evidence.folder/'worker.jsonl'))
        require(not trailing and len(self.raw_events)<=65536,'Sortie événement supplémentaire ou incomplète.')


def cycle(mode,owner,engine,evidence,consent):
    result={'schema_version':1,'kind':'lab_gateway_session','mode':mode,'state':'failed',
        'started_at':datetime.now(timezone.utc).isoformat(),'traffic_generated':False,
        'real_gateway_restoration_validated':False,'cleanup_verified':False}
    pilot, failure, cleanup_failure, interruption = None,None,None,0
    previous, recovering = {},False
    sources=source_hashes()
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
            result['producer']=recovery.cake.producer(engine.tc(['-V']))
            pilot=Pilot(owner,engine,evidence,consent);pilot.start()
            pilot.receive('ready')
            pilot.command(1,'begin');pilot.receive('apply_requested')
            require(consent and sources==source_hashes(),'Consentement ou sources non conformes.')
            engine.apply()
            pilot.command(2,'applied',snapshot_path=str(evidence.folder/'applied.json'),snapshot_sha256=evidence.files['applied.json'])
            pilot.receive('applied',evidence.files['applied.json'])
            if mode=='check-crash':
                evidence.record('session_kill_intent',pid=owner.child.pid)
                os.kill(owner.child.pid,signal.SIGKILL)
            else:
                pilot.command(3,'stop');pilot.receive('release_requested')
            pilot.wait_exit()
        except BaseException as error:failure=error
        finally:
            recovering=True;owner.interruption=0;owner.deadline=time.monotonic()+30
            try:
                owner.stop_group(time.monotonic()+3)
                evidence.record('driver_group_stopped',exit_code=owner.driver_code,reaped_descendants=owner.reaped_descendants)
                try:
                    if pilot is not None:pilot.close()
                finally:
                    # A broken diagnostic/journal never suppresses recovery.
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
        require(owner.driver_code==(-signal.SIGKILL if mode=='check-crash' else 0) and owner.reaped_descendants==0,
                'Arrêt du pilote Go non conforme.')
        require(engine.applied and engine.removed and engine.restored,'Restauration de session incomplète.')
        engine.tools.verify();require(source_hashes()==sources,'Sources de session modifiées.')
        result['state']='complete';result['session_state']='restored_and_closed'
    except BaseException as error:
        result['error']=str(error)
        if cleanup_failure is not None:result['cleanup_error']=str(cleanup_failure)
    finally:
        result.update(restoration_verified=engine.restored,applied_verified=engine.applied,root_removed=engine.removed,
            driver_exit_code=owner.driver_code,driver_pid=owner.child.pid if owner.child else None,
            reaped_descendants=owner.reaped_descendants,namespaces=[name for name,_identity in owner.owned],
            namespace_identities=[list(identity) if identity else None for _name,identity in owner.owned],
            workspace=str(owner.workspace) if owner.workspace else None,interruption_code=interruption,
            finished_at=datetime.now(timezone.utc).isoformat())
        try:evidence.finish();result['artifacts_sha256']=dict(evidence.files);evidence.save('report.json',result)
        finally:
            for signum,handler in previous.items():signal.signal(signum,handler)
    return result
