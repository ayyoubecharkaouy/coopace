"""Go-stage handoff to activation with a simulated kernel and real processes."""

import importlib.util
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("topology_fixtures", Path(__file__).with_name("test_lab_cake_go.py"))
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)
SOURCE = fixtures.SOURCE.with_name("lab_cake_go_topology.py")
spec = importlib.util.spec_from_file_location("topology_model", SOURCE)
model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)
WORKER = fixtures.FAKE_WORKER.replace("output=b'[]'", "output=b'[]'\n  if args==p.LINK:output=(root/'link-fixture.json').read_bytes()\n  if args==p.ADDRESS:output=(root/'address-fixture.json').read_bytes()")

HARNESS = fixtures.HARNESS[:fixtures.HARNESS.index("try:\n result=m.run")] + r'''
from copy import deepcopy
from datetime import datetime,timezone
spec=importlib.util.spec_from_file_location('activation',source.with_name('lab_cake_go_topology.py'))
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
def endpoint(name,index,peer,mac):
 return {'ifname':name,'ifindex':index,'link_index':peer,'mtu':1500,'address':mac,'flags':['BROADCAST','MULTICAST'],
         'link_type':'ether','linkinfo':{'info_kind':'veth'},'operstate':'DOWN'}
def loopback():return {'ifname':'lo','ifindex':1,'link_type':'loopback','flags':['LOOPBACK'],'operstate':'DOWN'}
class Kernel(Namespaces):
 def __init__(self):
  super().__init__();self.rows={};self.addresses={};self.routes={};self.forward=0;self.calls=[];self.count=0;self.up_reads=0
 def command(self,action,name,timeout):
  super().command(action,name,timeout)
  if action=='add':self.rows[name]={'lo':loopback()};self.addresses[name]={};self.routes[name]=[]
 def execute(self,args,owner):
  self.calls.append(args);(root/'calls.json').write_text(json.dumps(self.calls))
  c,g,s=[n for n,_ in owner.owned]
  if args==[self.ip,'-V']:return b'tc utility, iproute2-6.1.0\n'
  if args[1]=='-n':
   n,cmd=args[2],args[3:]
   if cmd in (['-j','link','show'],['-j','-d','link','show']):return json.dumps(list(self.rows[n].values())).encode()
   if cmd==['-j','address','show']:
    rows=[{**row,'addr_info':deepcopy(self.addresses[n].get(name,[]))} for name,row in self.rows[n].items()]
    if self.forward and scenario=='wrong_address':next(r for r in rows if r['ifname']!='lo')['addr_info'][0]['local']='10.203.9.9'
    return json.dumps(rows).encode()
   if cmd==['-j','-4','route','show','table','main']:
    rows=deepcopy(self.routes[n])
    if self.forward and scenario=='wrong_route':rows.append({'dst':'default','gateway':'10.203.0.1','dev':'eth0'})
    return json.dumps(rows).encode()
   if cmd[:2]==['link','add']:
    name=cmd[2];peer=s if name=='wan' else c;index=2 if name=='wan' else 3
    self.rows[g][name]=endpoint(name,index,2,'02:00:00:00:00:0'+str(index))
    self.rows[peer]['eth0']=endpoint('eth0',2,index,'02:00:00:00:01:0'+str(index))
   elif cmd[:2]==['address','add']:
    if scenario=='address_failure':raise a.Error('injected address failure')
    address,interface=cmd[2].split('/')[0],cmd[4]
    self.addresses[n][interface]=[{'family':'inet','local':address,'prefixlen':30,'scope':'global'}]
    network='10.203.0.0/30' if address in ('10.203.0.1','10.203.0.2') else '10.203.0.4/30'
    self.routes[n].append({'dst':network,'dev':interface,'protocol':'kernel','scope':'link','prefsrc':address,'flags':[]})
   elif cmd[:2]==['link','set']:
    row=self.rows[n][cmd[3]];row['flags'].append('UP');row['operstate']='UNKNOWN' if cmd[3]=='lo' else 'UP'
    if scenario=='changed_after_up' and n==g and cmd[3]=='wan':row['address']='02:ee:ee:ee:ee:ee'
    if scenario=='extra_link' and n==g and cmd[3]=='lo':self.rows[g]['foreign']=endpoint('foreign',99,90,'02:ee:ee:ee:ee:01')
   elif cmd[:2]==['route','add']:self.routes[n].append({'dst':cmd[2],'gateway':cmd[4],'dev':'eth0','flags':[]})
   else:raise AssertionError(args)
   return b''
  assert args[1:4]==['netns','exec',g],args
  if args[5:]==['-q','-w','net.ipv4.ip_forward=1']:
   self.forward=1
   if scenario=='namespace_changed':self.changed=True
   return b''
  if args[5:]==['-n','net.ipv4.ip_forward']:return b'0\n' if scenario=='forwarding_failure' else str(self.forward).encode()+b'\n'
  assert args[-4:]==['qdisc','show','dev','wan'],args
  data=deepcopy(fixture) if (root/'added').exists() else []
  if self.forward:
   self.up_reads+=1;self.count+=128
   data[0]['bytes']=0 if scenario=='counter_reset' and self.up_reads>1 else self.count
   data[0]['packets']=self.up_reads
   if scenario=='bad_options':data[0]['options']['bandwidth']=123
  return json.dumps(data).encode()
 def identity(self,name):
  identity=super().identity(name)
  if getattr(self,'changed',False) and name.endswith('-g'):return (identity[0],identity[1]+1)
  return identity
kernel=Kernel();m.guards.enable_subreaper();owner=m.GoGuard(kernel,tempdir=root,timeout=15)
tools={n:m.tool(sys.executable) for n in ('worker','python','ip','tc')};kernel.ip=tools['ip']['path']
events=[];result=None;error=None;activation=None
stream=(root/'activation.jsonl').open('x')
def record(event):
 if scenario=='evidence_failure' and event['event']=='activation_tool_intent' and 'address' in event['arguments'] and 'add' in event['arguments']:raise OSError('injected evidence failure')
 events.append(event);stream.write(json.dumps({'recorded_at':datetime.now(timezone.utc).isoformat(),**event})+'\n');stream.flush();os.fsync(stream.fileno())
try:
 owner.create();down=m.DownLink(kernel,tools['tc']['path']);down.prepare(owner)
 (root/'link-fixture.json').write_text(json.dumps(list(kernel.rows[down.gateway].values())))
 (root/'address-fixture.json').write_text(json.dumps([{**kernel.rows[down.gateway]['wan'],'addr_info':[]}]))
 phase=m.run_phase(owner,tools,artifacts,down,session_factory=Session,mode=mode)
 baseline=deepcopy(owner.owned);deadline=owner.deadline
 if scenario=='changed_before':kernel.rows[down.gateway]['wan']['mtu']=1400
 if scenario=='preexisting_route':kernel.routes[owner.owned[0][0]].append({'dst':'default'})
 if scenario=='bad_tool':tools['python']['sha256']='0'*64
 activation=a.activate_after_phase(owner,down,tools['python'],record)
 assert owner.owned==baseline and owner.deadline==deadline and len(list((root/'namespaces').iterdir()))==3
 assert owner.child is None and len(owner.process_groups)==2 and owner.process_groups[0].driver_code==0
 assert not (root/'proc'/str(phase['worker_pid'])).exists() or not Path('/proc',str(phase['worker_pid'])).exists()
 activation.verify('continuity')
 if scenario=='arbitrary_tc':activation.execute([kernel.ip,'netns','exec',down.gateway,down.tc,'qdisc','del','dev','wan','root'])
 result={'state':activation.state,'queue':activation.report,'mutations':activation.next_mutation,'events':len(events)}
except Exception as caught:error=str(caught)
finally:
 try:owner.close()
 except Exception as caught:error=str(caught)
 stream.close()
 (root/'result.json').write_text(json.dumps({'result':result,'error':error,'remaining_names':len(list((root/'namespaces').iterdir())),
  'closed':owner.closed,'phase_failed':owner.phase_failure is not None,'calls':kernel.calls,'events':events}))
if error:raise SystemExit(error)
'''


@unittest.skipUnless(sys.platform == "linux", "Linux Go phase handoff")
class TopologyTests(unittest.TestCase):
    def run_case(self, scenario="normal", mode="check"):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            process = subprocess.run([sys.executable,"-I","-B","-c",HARNESS,str(fixtures.SOURCE),str(root),scenario,mode,WORKER],
                                     capture_output=True,text=True,timeout=20)
            report = json.loads((root/"result.json").read_text())
            self.assertEqual(report["remaining_names"], 1 if scenario=="namespace_changed" else 0, process.stderr)
            for pid in (root/"proc").iterdir():
                self.assertFalse(Path("/proc",pid.name).exists(),process.stderr)
            return process,report

    def test_go_phase_activates_same_resources_and_rechecks_cake(self):
        process,report=self.run_case()
        self.assertEqual(process.returncode,0,process.stderr)
        self.assertEqual(report["result"]["state"],"activated")
        self.assertEqual(report["result"]["mutations"],15)
        self.assertEqual(report["result"]["queue"]["link_state"],"UP")
        self.assertEqual(report["result"]["queue"]["down_statistics_delta"]["counters"]["bytes"],0)
        self.assertGreater(report["result"]["queue"]["activation_statistics_delta"]["counters"]["bytes"],0)
        self.assertFalse(any("qdisc" in c and any(v in c for v in ("add","replace","del")) for c in report["calls"]))
        self.assertTrue(any(e["event"]=="activation_verified" for e in report["events"]))

    def test_inconsistent_observations_or_evidence_fail_without_success(self):
        for scenario in ("changed_before","changed_after_up","extra_link","wrong_address","wrong_route","address_failure",
                         "forwarding_failure","bad_options","counter_reset","namespace_changed","evidence_failure","bad_tool","preexisting_route","arbitrary_tc"):
            with self.subTest(scenario=scenario):
                process,report=self.run_case(scenario)
                self.assertNotEqual(process.returncode,0,process.stderr)
                self.assertIsNone(report["result"])
                if scenario in ("changed_before","bad_tool","preexisting_route"):
                    self.assertFalse(any(len(c)>4 and c[1]=="-n" and c[3:5]==["link","add"] and "lan" in c for c in report["calls"]))

    def test_terminal_go_crash_cannot_activate(self):
        process,report=self.run_case(mode="check-crash")
        self.assertNotEqual(process.returncode,0,process.stderr)
        self.assertFalse(any("lan" in c and "add" in c for c in report["calls"]))

    def test_addresses_keep_ipv4_exact_and_only_allow_automatic_local_ipv6(self):
        good = [{"ifname":"wan","ifindex":2,"addr_info":[
            {"family":"inet","local":"10.203.0.5","prefixlen":30,"scope":"global"},
            {"family":"inet6","local":"fe80::1","prefixlen":64,"scope":"link"}]}]
        identities, expected = {"wan":{"ifindex":2}}, {"wan":"10.203.0.5"}
        model.addresses(good, identities, expected)
        for change in (lambda r:r[0].update(ifindex=True),
                       lambda r:r[0]["addr_info"][0].update(prefixlen=True),
                       lambda r:r[0]["addr_info"][1].update(local="2001:db8::1"),
                       lambda r:r[0]["addr_info"].append({"family":"inet","local":"10.203.0.9","prefixlen":30,"scope":"global"})):
            with self.subTest(change=change):
                bad=deepcopy(good);change(bad)
                with self.assertRaises(model.Error):model.addresses(bad,identities,expected)

    def test_routes_require_the_fixed_main_table_and_reject_other_paths(self):
        good = [{"dst":"10.203.0.0/30","dev":"eth0","protocol":"kernel","scope":"link","prefsrc":"10.203.0.2"},
                {"dst":"10.203.0.4/30","dev":"eth0","gateway":"10.203.0.1"}]
        model.routes(good,0)
        for field,value in (("dst","default"),("nexthops",[]),("table",99),("type","blackhole"),("flags",["linkdown"]),("gateway","10.203.0.9")):
            with self.subTest(field=field):
                bad=deepcopy(good);bad[1][field]=value
                with self.assertRaises(model.Error):model.routes(bad,0)


if __name__ == "__main__":
    unittest.main()
