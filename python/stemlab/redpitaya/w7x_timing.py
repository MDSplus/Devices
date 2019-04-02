#!/usr/bin/python
"""
FPGA image available from
https://github.com/zack-vii/Anacleto/projects/w7x_timing/

"""
import numpy as _n, socket as _s, struct as _p

""" STATE CONSTANTS """
# state[0]:error, state[1]:ok
STATE_IDLE   = [  6,  7]
STATE_ARMED  = [ 14, 15]
STATE_DELAY  = [ 22, 23]
STATE_SAMPLE = [114,115]
STATE_LOW    = [ 82, 83]
STATE_HIGH   = [210,211]
STATE_REPEAT = [ 50, 51]

""" REMOTE CONNECTION """

class remote(object):
    @staticmethod
    def _tobyte(val):
        if not isinstance(val,int):
            value = 0;
            for ch in val: value |= 4<<ch
            return value
        return val
    @staticmethod
    def _makeMsg(prog,form,length,*args):
        return b'W7X'+_p.pack('<L',length)+prog[0:1]+_p.pack(form,*args)
    def __init__(self,address):
        host = address.split(':',2)+[5000]
        port = int(host[1])
        self._address = (host[0],port)
        self.connect()
    def connect(self):
        self.sock = _s.socket(_s.AF_INET, _s.SOCK_STREAM)
        self.sock.connect(self._address)
        self.sock.settimeout(3)
    def _exchange_str(self,msg,force_str=False):
        def _tryexchange(msg):
            self.sock.send(msg)
            ret = self.sock.recv(4)
            if len(ret)<4: raise _s.error
            length = _p.unpack('<L',ret)[0]
            if length>0:
                return self.sock.recv(length+255)[:length]
        try:
            ans = _tryexchange(msg)
        except (KeyboardInterrupt,SystemExit): raise
        except _s.error:
            self.connect()
            ans = _tryexchange(msg)
        if force_str:
            return '' if ans is None else ans
        return self if ans is None else ans
    def _exchange(self,msg,format,length):
        def _tryexchange(msg,format,length):
            self.sock.send(msg)
            ret = self.sock.recv(length+255)
            if len(ret)<length: raise _s.error
            return _p.unpack(format,ret)
        try:
            return _tryexchange(msg,format,length)[:length]
        except (KeyboardInterrupt,SystemExit): raise
        except _s.error:
            self.connect()
            return _tryexchange(msg,format,length)[:length]
    @staticmethod
    def _tointargs(*args):
        return tuple((int(arg) if arg is not None else -1) for arg in args)
    def makeClock(self,delay=0,width=-1,period=-1,burst=-1,cycle=-1,repeat=-1):
        args= remote._tointargs(delay,width,period,burst,cycle,repeat)
        msg = remote._makeMsg(b'C','<qqqqql',44,*args)
        return self._exchange_str(msg)
    def makeSequence(self,delay=0,width=-1,period=-1,burst=-1,cycle=-1,repeat=-1,timing=[0]):
        timing = _n.array(timing,_n.int64).tostring()
        length = len(timing)+44
        args= remote._tointargs(delay,width,period,burst,cycle,repeat)
        msg = remote._makeMsg(b'S','<qqqqql',length,*args)+timing
        return self._exchange_str(msg)
    def arm(self):
        return self._exchange_str(remote._makeMsg(b'A','',0))
    def rearm(self):
        return self._exchange_str(remote._makeMsg(b'R','',0))
    def reinit(self,default_delay=-1):
        return self._exchange_str(remote._makeMsg(b'X','<q',8,default_delay))
    def disarm(self):
        return self._exchange_str(remote._makeMsg(b'D','',0))
    def trig(self):
        return self._exchange_str(remote._makeMsg(b'T','',0))
    def extclk(self,value=True):
        return self._exchange_str(remote._makeMsg(b'E','<b',1,1 if value else 0))
    def gate(self,val=0):
        return self._exchange_str(remote._makeMsg(b'G','<B',1,self._tobyte(val)))
    def gate2(self,val=0):
        return self._exchange_str(remote._makeMsg(b'H','<B',1,self._tobyte(val)))
    def invert(self,val=0):
        return self._exchange_str(remote._makeMsg(b'I','<B',1,self._tobyte(val)))
    @property
    def state(self):
        return self._exchange(remote._makeMsg(b's','',0),'<B',1)[0]
    @property
    def control(self):
        return self._exchange(remote._makeMsg(b'c','',0),'<BBBBBBBB',8)
    @property
    def params(self):
        return self._exchange(remote._makeMsg(b'p','',0),'<qqqqqll',48)
    @property
    def error(self):
        return self._exchange_str(remote._makeMsg(b'e','',0),True)
    @property
    def has_ext_clk(self):
        if self.state != STATE_IDLE[1]:
            raise Exception("You should disarm the device first.\nCurrent state: %d",self.state)
        from time import sleep
        self.disarm()
        self.extclk(0)
        idle = self.state
        self.makeClock(1e7)
        self.extclk(1)
        self.arm()
        sleep(0.01)
        hasext = self.state != idle
        self.extclk(0)
        self.disarm()
        return hasext

""" UNIT TEST """

import time,unittest as _u
class Test(_u.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dev = remote(cls._host)
        cls.dev.arm()
        cls.dev.disarm();
        time.sleep(.001)
        if cls.dev.has_ext_clk:
            print("test using external clock.")
            cls.dev.extclk(1)

    def default(self):
        self.dev.makeClock()
        self.assertEqual(self.dev.error.strip(),"MAKE CLOCK: DELAY: 0, WIDTH: 5, PERIOD: 10, BURST: 1, CYCLE: 10, REPEAT: 1, COUNT: 1")

    def arm(self):
        self.dev.disarm();
        self.assertEqual(self.dev.state,STATE_IDLE[1])
        self.dev.gate([2,4])
        self.dev.gate2([5])
        self.dev.invert([3,4])
        self.dev.makeClock(cycle=1000000,burst=1000,repeat=5)
        self.assertEqual(self.dev.error,b"MAKE CLOCK: DELAY: 0, WIDTH: 5, PERIOD: 10, BURST: 1000, CYCLE: 1000000, REPEAT: 5, COUNT: 1\n")
        self.assertEqual(self.dev.params,(0,5,10,1000,1000000,5,1))
        self.dev.makeSequence(1e6,1e3,2e3,10,3e6,3,[0,1e5,2e5,3e5,4e5])
        self.assertEqual(self.dev.error,b"""MAKE SEQUENCE: TIMES: [0, 100000, 200000, 300000, 400000],\nDELAY: 1000000, WIDTH: 1000, PERIOD: 2000, BURST: 10, CYCLE: 3000000, REPEAT: 3, COUNT: 5\n""")
        self.dev.arm()
        self.assertEqual(self.dev.state,STATE_ARMED[1])
        self.dev.trig()
        time.sleep(.05)
        self.assertEqual(self.dev.state,STATE_DELAY[1])
        time.sleep(1.1)
        self.assertEqual(self.dev.state,STATE_IDLE[1])

    def rearm(self):
        self.dev.disarm();
        self.assertEqual(self.dev.state,STATE_IDLE[1])
        self.dev.rearm()
        self.dev.makeClock(delay=1500000,width=1000000)
        self.assertEqual(self.dev.params,(1500000,1000000,2000000,1,2000000,1,1))
        self.assertEqual(self.dev.state,STATE_ARMED[1])
        self.dev.trig()
        time.sleep(.1)
        self.assertEqual(self.dev.state,STATE_DELAY[1])
        time.sleep(.1)
        self.assertEqual(self.dev.state,STATE_HIGH[1])
        time.sleep(.1)
        self.assertEqual(self.dev.state,STATE_LOW[1])
        time.sleep(.1)
        self.assertEqual(self.dev.state,STATE_ARMED[1])
        self.assertEqual(self.dev.params,(1500000,1000000,2000000,1,2000000,1,1))

    def reinit(self):
        self.dev.disarm();
        self.assertEqual(self.dev.state,STATE_IDLE[1])
        self.dev.reinit()
        self.assertEqual(self.dev.state,STATE_ARMED[1])
        self.dev.trig()
        p=self.dev.params;self.assertEqual((p[0],p[3:6]),(600000000,(0,0,0)))
        time.sleep(.1)
        self.assertEqual(self.dev.state,STATE_DELAY[1])
        self.dev.makeClock(delay=1500000,width=1000000)
        self.assertEqual(self.dev.params,(1500000,1000000,2000000,1,2000000,1,1))
        time.sleep(.1)
        self.assertEqual(self.dev.state,STATE_HIGH[1])
        time.sleep(.1)
        self.assertEqual(self.dev.state,STATE_LOW[1])
        time.sleep(.1)
        self.assertEqual(self.dev.state,STATE_ARMED[1])
        p=self.dev.params;self.assertEqual((p[0],p[3:6]),(600000000,(0,0,0)))

    def runTest(self):
        for test in self.tests:
            self.__getattr__(test)()

    tests = ('default','arm','rearm','reinit')
    @classmethod
    def getTests(cls): return tuple(map(cls,Test.tests))

def test(host=None):
    import os
    if host is None:
        Test._host = os.getenv('RedPitaya','RP-F0432C')
    else:
        Test._host = host
    suite=_u.TestSuite(Test.getTests())
    tr=_u.TextTestRunner(stream=os.sys.stderr,verbosity=2)
    tr.run(suite)

""" EXECUTION """

if __name__=="__main__":
    import sys
    if len(sys.argv)==1:
        test()
    elif len(sys.argv)==2:
        test(sys.argv[1])


""" DEVICE """

try:
  from MDSplus import Data,Device,version,DevINV_SETUP,TreeNODATA
  tostr = version.tostr
  class W7X_TIMING(Device) :
    """
    MDSplus Device for the RedPitaya timing module at W7X
    """
    parts=[
           {'path': ':ACTIONSERVER',                    'type': 'TEXT',    'options':('no_write_shot','write_once')},
           {'path': ':ACTIONSERVER:INIT',               'type': 'ACTION',  'options':('no_write_shot','write_once'), 'valueExpr':'Action(node.DISPATCH,node.TASK)'},
           {'path': ':ACTIONSERVER:INIT:DISPATCH',      'type': 'DISPATCH','options':('no_write_shot','write_once'), 'valueExpr':'Dispatch(head.actionserver,"INIT",21)'},
           {'path': ':ACTIONSERVER:INIT:TASK',          'type': 'TASK',    'options':('no_write_shot','write_once'), 'valueExpr':'Method(None,"init",head)'},
           {'path': ':ACTIONSERVER:ARM',                'type': 'ACTION',  'options':('no_write_shot','write_once'), 'valueExpr':'Action(node.DISPATCH,node.TASK)'},
           {'path': ':ACTIONSERVER:ARM:DISPATCH',       'type': 'DISPATCH','options':('no_write_shot','write_once'), 'valueExpr':'Dispatch(head.actionserver,"INIT",51)'},
           {'path': ':ACTIONSERVER:ARM:TASK',           'type': 'TASK',    'options':('no_write_shot','write_once'), 'valueExpr':'Method(None,"arm",head)'},
           {'path': ':ACTIONSERVER:TEST_TRIG',          'type': 'ACTION',  'options':('no_write_shot','write_once'), 'valueExpr':'Action(node.DISPATCH,node.TASK)'},
           {'path': ':ACTIONSERVER:TEST_TRIG:DISPATCH', 'type': 'DISPATCH','options':('no_write_shot','write_once'), 'valueExpr':'Dispatch(head.actionserver,"PULSE",1)'},
           {'path': ':ACTIONSERVER:TEST_TRIG:TASK',     'type': 'TASK',    'options':('no_write_shot','write_once'), 'valueExpr':'Method(None,"trig",head)'},
           {'path': ':ACTIONSERVER:DISARM',             'type': 'ACTION',  'options':('no_write_shot','write_once'), 'valueExpr':'Action(node.DISPATCH,node.TASK)'},
           {'path': ':ACTIONSERVER:DISARM:DISPATCH',    'type': 'DISPATCH','options':('no_write_shot','write_once'), 'valueExpr':'Dispatch(head.actionserver,"DEINIT",21)'},
           {'path': ':ACTIONSERVER:DISARM:TASK',        'type': 'TASK',    'options':('no_write_shot','write_once'), 'valueExpr':'Method(None,"disarm",head)'},
           {'path': ':ACTIONSERVER:REARM',              'type': 'TASK',    'options':('no_write_shot','write_once'), 'valueExpr':'Method(None,"rearm",head)'},
           {'path': ':ACTIONSERVER:REINIT',             'type': 'TASK',    'options':('no_write_shot','write_once'), 'valueExpr':'Method(None,"reinit",head)'},
           {'path': ':ACTIONSERVER:REINIT:DELAY',       'type': 'NUMERIC', 'options':('no_write_shot'),              'valueExpr':'Uint64(60).setUnits("s")', 'help':"time after trigger to wait for program upload"},
           {'path': ':HOST',                            'type': 'TEXT',    'options':('no_write_shot','write_once')},
           {'path': ':COMMENT',                         'type': 'TEXT'},
           {'path': ':CLOCK',                           'type': 'NUMERIC', 'options':('no_write_shot','write_once'), 'valueExpr':'Uint32(100 ).setUnits("ns")', 'help':"Internal clock runs at 10MHz."},
           {'path': ':TRIGGER',                         'type': 'NUMERIC', 'options':('no_write_shot',),             'valueExpr': 'Int64(  0 ).setUnits("s")'},
           {'path': ':INVERT'  ,                        'type': 'NUMERIC', 'options':('no_write_shot',),             'valueExpr':'Uint8Array([])', 'help':"list of outputs [0..5] that should have an inverted signal"},
           {'path': ':GATE',                            'type': 'NUMERIC', 'options':('no_write_shot',),             'valueExpr':'Uint8Array([])', 'help':"list of outputs [0..5] that should have the gate instead of the trigger signal"},
           {'path': ':GATE2',                           'type': 'NUMERIC', 'options':('no_write_shot',),             'valueExpr':'Uint8Array([])', 'help':"list of outputs [0..5] that should be a gat that opens and closes every other trigger"},
           {'path': ':DELAY',                           'type': 'NUMERIC', 'options':('no_write_shot',),             'valueExpr':'Uint64(0).setUnits("s")'},
           {'path': ':WIDTH',                           'type': 'NUMERIC', 'options':('no_write_shot',),},
           {'path': ':PERIOD',                          'type': 'NUMERIC', 'options':('no_write_shot',),},
           {'path': ':BURST',                           'type': 'NUMERIC', 'options':('no_write_shot',),},
           {'path': ':CYCLE',                           'type': 'NUMERIC', 'options':('no_write_shot',),},
           {'path': ':REPEAT',                          'type': 'NUMERIC', 'options':('no_write_shot',),},
           {'path': ':TIMING',                          'type': 'NUMERIC', 'options':('no_write_shot',),             'valueExpr':'Uint64Array([0]).setUnits("us")', 'help':"Empty for clock\\nArray for sequence"},
           {'path': ':STATUS',                          'type': 'ANY',     'options':('no_write_model','write_once'),'help':"Empty for clock\\nArray for sequence"},
          ]

    units_ns = {'ns':1, 'us':1000, 'ms':1000000, 's':1000000000}
    _com = None
    @property
    def com(self):
        if self._com is None:
            self._com = remote(self._host)
        return self._com
    @property
    def _clock(self):
        rec = self.clock.getRecord(None)
        if rec is None: return 100
        value = rec.data().tolist()
        units = str(rec.units).strip().lower()
        return value * self.units_ns.get(units,1)
    def _toticks(self,node):
        try:
            rec = node.getRecord(None)
            if rec is None: return None
            units = str(rec.units).strip().lower()
            value = rec.data().astype(_n.uint64)
            if units in self.units_ns:
                value = value * self.units_ns[units] / self._clock
            return value.tolist()
        except:
            import traceback
            traceback.print_exc()
            return None
    @property
    def _host(self): return str(self.host.data())
    @property
    def _gate(self):   return self.gate.data().tolist()
    @property
    def _gate2(self):  return self.gate2.data().tolist()
    @property
    def _invert(self): return self.invert.data().tolist()
    @property
    def _delay(self):  return self._toticks(self.delay)
    @property
    def _period(self): return self._toticks(self.period)
    @property
    def _width(self):  return self._toticks(self.width)
    @property
    def _burst(self):
        try: return int(self.burst.data())
        except TreeNODATA: return 1
    @property
    def _cycle(self):  return self._toticks(self.cycle)
    @property
    def _repeat(self):
        try: return int(self.repeat.data())
        except TreeNODATA: return 1
    @property
    def _timing(self): return self._toticks(self.timing)
    @property
    def _act_delay(self): return self._toticks(self.actionserver_reinit_delay)
    def setup(self,delay=0,width=None,period=None,burst=None,cycle=None,repeat=None,timing=[0],gate=[],gate2=[],invert=[]):
        from MDSplus import Uint8Array,Uint64Array
        self.delay  = delay
        self.width  = width
        self.period = period
        self.burst  = burst
        self.cycle  = cycle
        self.repeat = repeat
        self.timing = Uint64Array(timing)
        self.gate   = Uint8Array(gate)
        self.gate2  = Uint8Array(gate2)
        self.invert = Uint8Array(invert)
    def init(self):
        from sys import stderr
        try:
            self.com.gate(self._gate)
            self.com.gate2(self._gate2)
            self.com.invert(self._invert)
            report = self.com.makeSequence(self._delay,self._width,self._period,self._burst,self._cycle,self._repeat,self._timing)
            if 'ERROR' in report:
                stderr.write('%s\n'%(report,))
                raise DevINV_SETUP(report)
        finally:
            self.status = [self.com.state,self.com.control,self.com.params]
    def arm(self):    self.com.arm()
    def trig(self):   self.com.trig()
    def disarm(self): self.com.disarm()
    def rearm(self):  self.com.rearm()
    def reinit(self): self.com.reinit(self._act_delay)

  class W7X_TIMING_S(Device):
    _host_idx = 16
    from copy import deepcopy
    parts = deepcopy(W7X_TIMING.parts[_host_idx:]) + [
        {'path': ':MASTER_PATH',                 'type': 'TEXT',    'options': ('no_write_shot','write_once')},
        {'path': ':ACTIONSERVER',                'type': 'TEXT',    'options': ('no_write_shot','write_once')},
        {'path': ':ACTIONSERVER:INIT',           'type': 'ACTION',  'options': ('no_write_shot','write_once'), 'valueExpr': 'Action(Dispatch(head.ACTIONSERVER, "INIT", 1),Method(None, "sync", head))'},
        ]
    for i in range(len(parts)-3):
        parts[i]['valueExpr']='BUILD_PATH(CONCAT(head.master_path,"%s"))'%(parts[i]['path'],)
        parts[i]['options']=('no_write_model','write_once')

    @property
    def master(self):
        from MDSplus import Tree, TreeFILE_NOT_FOUND,TreeFOPENR
        path = self.master_path.record
        expt = str(path).split('::',2)[0].strip('\\')
        try:
            return Tree(expt,self.tree.shot,'ReadOnly').getNode(path)
        except (TreeFOPENR,TreeFILE_NOT_FOUND):
            return Tree(expt,-1,'ReadOnly').getNode(path)

    def sync(self):
        from MDSplus import Data,TreeNode,TreeNodeArray,Compound,DATA,Int32
        from MDSplus import TreeNODATA,TreeTREENF,TreeBADRECORD,TreeNNF
        master = self.master
        mnids  = Int32(master.conglomerate_nids).data().tolist()
        def relink(val):
            if val is None: return None
            if isinstance(val,(Compound,)):
                for i in range(val.getNumDescs()):
                    ans = val.getDescAt(i)
                    if isinstance(ans,(Data,TreeNode)):
                        val.setDescAt(i,relink(ans))
                return val
            if isinstance(val,(TreeNodeArray,)):
                for i in len(val):
                   val[i] = relink(val[i])
                return val
            if isinstance(val,(TreeNode,)):
                if not val.nid in mnids:
                    try:   return self.tree.getNode(val.minpath)
                    except:pass
                return relink(val.getRecord(None))
            return val
        def transfer(src,dst):
            dst.write_once = False
            try:                dst.record = relink(src.getRecord())
            except TreeNODATA:  dst.record = None
            finally: dst.write_once = True
        for to in range(3):
            try:
                master = self.master
                for name in self.part_names:
                    dst = self.head.getNode(name)
                    if dst.no_write_shot: continue
                    try:   src = master.getNode(name)
                    except TreeNNF: continue
                    else:  transfer(src,dst)
            except TreeBADRECORD:
                time.sleep(1)
            else: break
        #if master.tree.shot == -1:
        #    raise TreeTREENF # as warning

  class W7X_TIMING_INV(W7X_TIMING):
    parts = W7X_TIMING.parts + [
           {'path': ':ACTIONSERVER:INVERT',             'type': 'ACTION',  'options':('no_write_shot','write_once','disabled'), 'valueExpr':'Action(node.DISPATCH,node.TASK)'},
           {'path': ':ACTIONSERVER:INVERT:DISPATCH',    'type': 'DISPATCH','options':('no_write_shot','write_once'), 'valueExpr':'Dispatch(head.actionserver,"DEINIT",1)'},
           {'path': ':ACTIONSERVER:INVERT:TASK',        'type': 'TASK',    'options':('no_write_shot','write_once'), 'valueExpr':'Method(None,"invert_gate",head,head.GATE)'},
    ]
    def invert_gate(self,invert):
        if isinstance(invert,Data):
            invert = invert.data().tolist()
        invert = list(set(invert).symmetric_difference(self._invert))
        self.com.invert(invert)

except:
    pass
