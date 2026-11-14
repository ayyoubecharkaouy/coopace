"""Flow evidence/legacy classes plus real bounded process I/O without networking."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('test_session_flow',ROOT/'scripts/lab_gateway_session_flow.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def reports():
    common={'schema_version':1,'requested_bytes':m.VOLUME,'block_bytes':16384,'elapsed_ms':9000,
            'average_bytes_per_second':m.VOLUME*1000/9000}
    return ({**common,'method':'synthetic_tcp_send','target':m.TARGET,'written_bytes':m.VOLUME,
             'timeout_ms':15000,'requested_bytes_per_second':1048576},
            {**common,'method':'synthetic_tcp_receive','listen':m.TARGET,'received_bytes':m.VOLUME,
             'timeout_ms':18000,'receive_elapsed_ms':9000})


class FlowTests(unittest.TestCase):
    def test_intrinsic_classes_are_bounded_unique_and_have_no_options(self):
        self.assertEqual(m.cake_flow_classes(b''),[])
        self.assertEqual(m.cake_flow_classes(b'class cake 10:1 parent 10: \nclass cake 10:400 parent 10:\n'),[1,1024])
        for raw in (b'class cake 20:1 parent 20:',b'class htb 10:1 parent 10:',b'class cake 10:0 parent 10:',
                    b'class cake 10:401 parent 10:',b'class cake 10:1 parent 10: leaf 20:',b'class cake 10:1 parent 10: rate 1mbit',
                    b'class cake 10:1 parent 10:\nclass cake 10:1 parent 10:',b'\xff',b' '*65537,b'[]',b'Sent 1 bytes'):
            with self.subTest(raw=raw[:50]):
                with self.assertRaises(Exception):m.cake_flow_classes(raw)

    def test_flow_reports_require_received_volume_matching_rate_and_finite_durations(self):
        send,receive=reports()
        self.assertEqual(m.checked_flow(json.dumps(send).encode(),json.dumps(receive).encode()),{'send':send,'receive':receive})
        for which,key,value in ((0,'written_bytes',m.VOLUME-1),(1,'received_bytes',m.VOLUME-1),
            (0,'requested_bytes_per_second',1),(1,'average_bytes_per_second',1),(0,'elapsed_ms',True),
            (1,'receive_elapsed_ms',float('nan')),(0,'timeout_ms',15001),(0,'schema_version',True),
            (1,'elapsed_ms',8000)):
            changed=copy.deepcopy([send,receive]);changed[which][key]=value
            with self.subTest(key=key,value=value):
                with self.assertRaises(Exception):m.checked_flow(*(json.dumps(v).encode() for v in changed))

    def process(self,code):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);folder=Path(temp.name)
        class Tools:
            specs={'ip':{'path':sys.executable}}
            files={}
            def verify(self,*args):pass
            def executable(self,_name):return sys.executable
        class Owner:
            process_groups=[]
        class Engine:tools=Tools()
        class Flow:
            engine=Engine();owner=Owner();evidence=m.runtime.Evidence(folder);helpers=[]
        flow=Flow();self.addCleanup(flow.evidence.finish)
        popen=subprocess.Popen
        def substituted(_args,**kwargs):
            kwargs.pop('executable');kwargs.pop('pass_fds')
            return popen([sys.executable,'-I','-c',code],**kwargs)
        with patch.object(m.subprocess,'Popen',side_effect=substituted):helper=m.Process(flow,'sender','simulated',[])
        return flow,helper,folder

    def test_real_process_evidence_is_drained_and_group_reaped(self):
        flow,helper,folder=self.process("import os;os.write(1,b'payload\\n');os.write(2,b'x'*12000)")
        deadline=time.monotonic()+3
        while not helper.group.exited():
            helper.drain();self.assertLess(time.monotonic(),deadline);time.sleep(.005)
        helper.stop()
        self.assertEqual((folder/'flow-sender.stderr').read_bytes(),b'x'*12000)
        self.assertEqual(helper.group.state,'stopped');self.assertEqual(helper.group.driver_code,0)
        self.assertEqual(flow.helpers,[helper])
        self.assertFalse(Path('/proc',str(helper.child.pid)).exists())

    def test_failed_spawn_is_registered_for_cleanup(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        class Tools:
            specs={'ip':{'path':'/missing'}};files={}
            def verify(self,*args):pass
            def executable(self,_name):return '/missing'
        class Engine:tools=Tools()
        class Owner:process_groups=[]
        class Flow:engine=Engine();owner=Owner();helpers=[];evidence=m.runtime.Evidence(Path(temp.name))
        flow=Flow();self.addCleanup(flow.evidence.finish)
        with self.assertRaises(FileNotFoundError):m.Process(flow,'sender','simulated',[])
        self.assertEqual(len(flow.helpers),1);flow.helpers[0].stop()
        self.assertEqual(flow.helpers[0].group.state,'stopped')


class FakeEngine:
    """Only IP/qdisc observation is simulated; the loopback payload is real."""
    gateway='cg-sim-g';server='cg-sim-s'
    def __init__(self):
        self.present={self.gateway:set(),self.server:set()};self.calls=[];self.samples=0
    def binding(self):pass
    def clean_endpoints(self):
        if any(self.present.values()):raise RuntimeError('addresses remain')
    def ip(self,namespace,args):
        self.calls.append((namespace,args))
        interface,address=('wan','10.203.0.5') if namespace==self.gateway else ('eth0','10.203.0.6')
        if args==['-j','address','show']:
            return json.dumps([{'ifname':'lo','addr_info':[]},{'ifname':interface,
                'addr_info':[{'family':'inet','local':v,'prefixlen':30} for v in self.present[namespace]]}]).encode()
        if args[0:2]==['address','add']:self.present[namespace].add(address);return b''
        if args[0:2]==['address','del']:self.present[namespace].remove(address);return b''
        raise AssertionError(args)
    def current_root(self):
        row=json.loads((ROOT/'platforms/linux/testdata/cake/down.json').read_text())
        row[0]['bytes']=0 if self.samples==0 else 5*1024*1024
        row[0]['packets']=0 if self.samples==0 else 4000
        self.samples+=1
        return json.dumps(row).encode()


class ActivationTests(unittest.TestCase):
    def flow(self):
        from types import SimpleNamespace
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        owner=SimpleNamespace(deadline=time.monotonic()+25,check=lambda:None,process_groups=[],
            process_group=SimpleNamespace(exited=lambda:False),child=SimpleNamespace(pid=os.getpid()))
        engine=FakeEngine();evidence=m.runtime.Evidence(Path(temp.name));self.addCleanup(evidence.finish)
        flow=m.Flow(owner,engine,evidence,SimpleNamespace(drain=lambda:None))
        return flow,engine
    def test_only_exact_temporary_addresses_are_added_and_removed(self):
        flow,engine=self.flow();flow.prepare();flow.deactivate()
        self.assertTrue(flow.report['addresses_removed']);self.assertFalse(any(engine.present.values()))
        mutations=[args for _namespace,args in engine.calls if args[:1]==['address']]
        self.assertEqual(mutations,[['address','add','10.203.0.5/30','dev','wan'],['address','add','10.203.0.6/30','dev','eth0'],
                                    ['address','del','10.203.0.5/30','dev','wan'],['address','del','10.203.0.6/30','dev','eth0']])
    def test_foreign_address_prevents_all_deletions(self):
        flow,engine=self.flow();flow.prepare();engine.present[engine.server].add('10.203.0.99')
        with self.assertRaises(Exception):flow.deactivate()
        self.assertFalse(any(args[:2]==['address','del'] for _n,args in engine.calls))
        self.assertIn('10.203.0.99',engine.present[engine.server])
    def test_uncertain_partial_address_setup_is_removed_precisely(self):
        flow,engine=self.flow();call=engine.ip
        def interrupted(namespace,args):
            result=call(namespace,args)
            if namespace==engine.server and args[:2]==['address','add']:raise OSError('uncertain add')
            return result
        engine.ip=interrupted
        with self.assertRaises(OSError):flow.prepare()
        engine.ip=call;flow.deactivate();self.assertFalse(any(engine.present.values()))
    def test_real_go_payload_and_reports_on_loopback_with_simulated_network_control(self):
        import socket
        try:
            listener=socket.socket(socket.AF_INET,socket.SOCK_STREAM);listener.bind(('127.0.0.1',0));port=listener.getsockname()[1];listener.close()
        except PermissionError as error:self.skipTest(str(error))
        flow,engine=self.flow()
        build=tempfile.TemporaryDirectory();self.addCleanup(build.cleanup);binary=str(Path(build.name)/'load')
        subprocess.run(['sh','scripts/go.sh','build','-o',binary,'./scripts/lab-load'],cwd=ROOT,check=True)
        class Tools:
            specs={'ip':{'path':binary}};files={}
            def verify(self,*args):pass
            def executable(self,_name):return binary
        engine.tools=Tools()
        popen=subprocess.Popen
        def local(args,**kwargs):
            kwargs['executable']=binary
            return popen([binary,*args[5:]],**kwargs)
        with patch.object(m,'TARGET',f'127.0.0.1:{port}'),patch.object(m.subprocess,'Popen',side_effect=local):
            try:
                flow.start();flow.finish()
            finally:
                flow.stop();flow.deactivate()
        self.assertEqual(flow.report['flow']['receive']['received_bytes'],m.VOLUME)
        self.assertTrue(flow.report['observed_with_live_helpers']);self.assertTrue(flow.report['addresses_removed'])
        self.assertTrue(all(h.group.driver_code==0 and h.group.state=='stopped' for h in flow.helpers))
        for h in flow.helpers:self.assertFalse(Path('/proc',str(h.child.pid)).exists())

if __name__=='__main__':unittest.main()
