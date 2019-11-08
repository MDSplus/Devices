#!/usr/bin/python
#
# Copyright (c) 2017, Massachusetts Institute of Technology All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# Redistributions of source code must retain the above copyright notice, this
# list of conditions and the following disclaimer.
#
# Redistributions in binary form must reproduce the above copyright notice, this
# list of conditions and the following disclaimer in the documentation and/or
# other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#

# Author: Timo Schroeder, Alexander H Card

# TODO:
# - server side demuxing for normal opperation not reliable, why?
# - find a way to detemine when the device is armed in mgt(dram)
# - properly check if the clock is in range
#  + ACQ480: maxADC=80MHz, maxBUS=50MHz, minBUS=10MHz, maxFPGA_FIR=25MHz
#
#import pdb
import os,sys,time,threading,re,numpy,socket,inspect,json
if sys.version_info<(3,):
    from Queue import Queue
else:
    from queue import Queue
    xrange = range
try:    import hashlib
except: hashlib = None
debug = 0
with_mgtdram = False # untested
def dprint(*line):
    print('%16.6f: %s'%(time.time(),''.join(map(str,line))))
_state_port    = 2235
_bigcat_port   = 4242
_aggr_port     = 4210 # used for streaming...
# requires rate to be sufficiently low for port ~32 MB/s e.g. 8CH @ 2MHz
# or subset of channels via --subset (acq480) or channel mask (acq425)
# e.g. acq480 for 4 channels, 3..6:
# > echo 'STREAM_OPTS="--subset=3,4"'>>/mnt/local/sysconfig/acq400_streamd.conf
_sys_port      = 4220
_gpgw_port     = 4541
_gpgr_port     = 4543
_data_port     = 53000
_mgt_log_port  = 53990
_ao_oneshot_cs = 54200 # sha1sum
_ao_oneshot    = 54201
_ao_oneshot_re = 54202
_zclk_freq = 33333300
class _es_marker:
    """hexdump
    0000000 llll hhhh f154 aa55 LLLL HHHH f154 aa55
    0000010 0000 0000 f15f aa55 LLLL HHHH f15f aa55
    *
    w00     llll   current memory_row_index (low word)
    w01     hhhh   current memory_row_index (high word)
    w02,06  f154   marker for master module
    w03:04: aa55   static marker
    w04:08: LLLL   current sample_clock_count (low word)
    w05:08: HHHH   current sample_clock_count (high word)
    w10:04: f15f   marker for slave module
    -----------------------------------------------
    hexdump -e '"%08_ax %08x |%08x %08x |%08x\n"'
    00000000 IIIIIIIII |aa55f154 CCCCCCCC |aa55f154
    00000010 000000000 |aa55f15f CCCCCCCC |aa55f15f
    *
    IIIIIIII:	sample_count	<4u
    CCCCCCCC:	clock_count	<4u
    """
    index_l= slice( 0,   1,1)
    index_h= slice( 1,   2,1)
    master = slice( 2,   8,4)
    static = slice( 3,None,4)
    count_l= slice( 4,None,8)
    count_h= slice( 5,None,8)
    slave  = slice(10,None,4) # always has all set
    class uint16:
        static = 0xaa55
        mask   = 0xf150
        event0 = 0xf151
        event1 = 0xf152
        ev_rgm = 0xf154
        all    = 0xf15f
    class int16:
        static = 0xaa55-(1<<16)

def s(b): return b if isinstance(b,str)   else b.decode('ASCII')
def b(s): return s if isinstance(s,bytes) else s.encode('ASCII')

###----------------
### nc base classes
###----------------

class nc(object):
    """
    Core n-etwork c-onnection to the DTACQ appliance. All roads lead here (Rome of the DTACQ world).
    This class provides the methods for sending and receiving information/data through a network socket
    All communication with the D-TACQ devices will require this communication layer
    """
    _chain  = None
    _server = None
    _stop = None
    @staticmethod
    def _tupletostr(value):
        """
        This removes the spaces between elements that is inherent to tuples
        """
        return ','.join(map(str,value))

    def __init__(self,server):
        """
        Here server is a tuple of host & port. For example: ('acq2106_064',4220)
        """
        self._server = server
        self._stop  = threading.Event()
    def __str__(self):
        """
        This function provides a readable tag of the server name & port.
        This is what appears when you, for example, use print()
        """
        name = self.__class__.__name__
        return "%s(%s:%d)"%(name,self._server[0],self._server[1])
    def __repr__(self):
        """
        This returns the name in, for example, the interactive shell
        """
        return str(self)
    def chainstart(self):
        if self._chain is not None: raise Exception('chain already started')
        self._chain=[]
    def chainabort(self): self._chain=None
    def chainsend (self):
        chain,self._chain = self._chain,None
        self._com('\n'.join(chain))

    @property
    def sock(self):
        """
        Creates a socket object, and returns it
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect(self._server)
        return sock

    @property
    def on(self): return not self._stop.is_set()
    def stop(self): self._stop.set()

    def lines(self,timeout=60):
        """
        Reads out channel data (from the buffer array) in chunks, then returns a single array of data.
        """
        sock= self.sock
        sock.settimeout(timeout)
        try:
            line = ''
            while self.on:
                buf = sock.recv(1)
                if len(buf)==0: break
                line += buf
                if buf=='\n':
                    yield line
                    line = ''
        finally:
            sock.close()


    def buffer(self,nbytes=4194304,format='int16'):
        """
        Reads out channel data (from the buffer array) in chunks, then returns a single array of data.
        """
        sock= self.sock
        try:
            while self.on:
                chunks = []
                toread = nbytes
                while toread>0:
                    chunk = sock.recv(toread)
                    read = len(chunk)
                    if read==0: break
                    chunks.append(chunk)
                    toread -= read
                if len(chunks)==0: break
                yield numpy.frombuffer(b''.join(chunks),format)
        finally:
            sock.close()

    def _com(self,cmd,ans=False,timeout=5,dbg=[None,None]):
        if isinstance(cmd,(list,tuple)):
            cmd = '\n'.join(cmd)
        if not (self._chain is None or ans):
            self._chain.append(cmd)
            return
        def __com(cmd):
            if cmd.startswith('_'):
                import traceback
                traceback.print_stack()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                sock.connect(self._server)
                if debug>=3: dprint('cmd: %s'%cmd)
                sock.sendall(b(cmd)) # sends the command
                sock.shutdown(socket.SHUT_WR)
                sock.settimeout(13 if cmd.strip().endswith('help2') else timeout)
                ans = []
                while True:
                    ans.append(s(sock.recv(1024))) # receives the answer
                    if len(ans[-1])==0: break
                return ''.join(ans)
            finally:
                sock.close()
        """
        Method of communicating with the device
        Opens a socket connection, reads data in chunks, puts it back together
        """
        if isinstance(self._server,(nc,)):
            return self._server._com(cmd)
        dbg[0] = cmd.strip()
        dbg[1] = __com(dbg[0]).strip()
        if ans: return dbg[1]

    def _exe(self,cmd,value=None):
        """
        Print the command and return object assignment
        """
        res = self(cmd,value)
        if len(res)>0:
            if debug:dprint(res)
            else:     print(res)
        return self

    def __call__(self,cmd,value=None):
        """
        Block of code associated with the self calling.
        General use for calling PV knob values directly.
        """
        if isinstance(value,(list,tuple)):
            value = nc._tupletostr(value)
        command = cmd if value is None else '%s %s'%(cmd,value)
        res = self._com(command,value is None)
        if not res is None:
            if res.startswith('ERROR'):
                raise Exception(res)
            if res.startswith(cmd):
                res = res[len(cmd)+1:]
            return res.strip()


class channel(nc):
    """
    MDSplus-independent way of opening a data channel to stream out data from the carrier.
    Call it independently as: ch = channel([num],host)
    """
    def __str__(self):
        return "Channel(%s,%d)"%self._server
    def __init__(self,ch,server='localhost'):
        super(channel,self).__init__((server,_data_port+ch))
    def read(self,format='int16'):
        ans = [buf for buf in self.buffer()]
        return numpy.concatenate(ans,0)
    def raw(self,rang=None):
        if rang is None:
            return self.read()
        if isinstance(rang,slice):
            slic = rang
        elif isinstance(rang,tuple):
            slic = slice(*rang)
        else:
            slic = slice(None,None,rang)
        return self.read()[slic] #('int32' if data32 else 'int16')

class stream(nc):
    """
    MDSplus-independent class
    ACQ400 FPGA class purposed for streaming data from participating modules
    data reduction either thru duty cycle or subset
    set.site 0 STREAM_OPTS --subset=3,4 # for chans 3,4,5,6
    """
    def __init__(self,server='localhost'):
        super(stream,self).__init__((server,_aggr_port))

class gpg(nc):
    """
    MDSplus-independent class
    ACQ400 FPGA class purposed for programming the General Pulse Generator
    """
    def __init__(self,server='localhost'):
        super(gpg,self).__init__((server,_gpgw_port))
    def write(self,sequence,loop=False):
        if isinstance(sequence,(tuple,list)):
            seqstrs = []
            gate = False
            for tm in sequence:
                gate = not gate
                seqstrs.append("%08d,%s"%(tm,('f' if gate else '0')))
            seqstrs.append("EOFLOOP\n" if loop else "EOF\n")
            sequence = "\n".join(seqstrs)
        if debug: dprint(sequence)
        sequence = memoryview(b(sequence))
        to_send = len(sequence)
        sent = self.sock.send(sequence)
        while sent<to_send:
            sent += self.sock.send(sequence[sent:])
    def write_gate(self,high, period=None, delay=5):
        """gpg.write_gate(high, period=None, delay=5)
           Generate a gate with fixed witdh
           If period is set the gate will repeat infinitely
           The hardware requires the delay top be at least 5 ticks
        """
        if delay<5:
            sys.stderr.write("gpg: warning - delay must be at least 5 ticks")
            delay=5
        high += delay+2
        if period is None:
            self.write((delay,high))
        else: # translate period and set up as loop
            if period>=0xffffff: raise Exception("gpg: error - ticks must be in range [5,16777214]")
            self.write((delay,high,period+1),loop=True)

class line_logger(nc):
    def lines(self,timeout=60):
        """
        Reads out channel data (from the buffer array) in chunks, then returns a single array of data.
        """
        sock= self.sock
        sock.settimeout(timeout)
        try:
            line = ''
            while self.on:
                buf = sock.recv(1)
                if len(buf)==0: break
                line += buf
                if buf=='\n':
                    yield line
                    line = ''
        finally:
            sock.close()
class STATE:
    CLEANUP='CLEANUP'
    STOP='STOP'
    ARM='ARM'
    PRE='PRE'
    POST='POST'
    FIN1='FIN1'
    FIN2='FIN2'
    names = [STOP,ARM,PRE,POST,FIN1,FIN2]
    _loggers = {}
    _lock = threading.Lock()
    @classmethod
    def get_name(cls,id): return cls.names[int(id)]
    class logger(threading.Thread):
        """
        This is a background subprocess (thread). Listens for the status updates provided by the log port: _state_port (via the carrier)
        """
        _initialized = False
        _com = None
        _re_state = re.compile("([0-9]+) ([0-9]+) ([0-9]+) ([0-9]+) ([0-9]+)")
        def __new__(cls, host='localhost',*arg,**kwarg):
            with STATE._lock:
                if host in STATE._loggers:
                    return STATE._loggers[host]
                self = super(STATE.logger,cls).__new__(cls)
                STATE._loggers[host] = self
                return self
        def __init__(self, host='localhost',debug=0):
            if self._initialized: return
            super(STATE.logger,self).__init__(name=host)
            self._initialized = True
            self._stop = threading.Event()
            self.daemon = True
            self.cv = threading.Condition()
            self.debug = debug
            self._state = set()
            self.reset()
            self.start()
        @property
        def com(self):
            if self._com is None:
                self._com = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self._com.settimeout(3)
                self._com.connect((self.name,_state_port))
                self._com.settimeout(1)
            return self._com
        @property
        def on(self): return not self._stop.is_set()
        def stop(self): self._stop.set()
        def run(self):
            sock_timeout = socket.timeout
            sock_error   = socket.error
            try:
                while self.on:
                    try:
                        msg = self.com.recv(1024)
                        if len(msg)==0: raise sock_error
                        msg = msg.strip(b'\r\n')
                        if self.debug>1: dprint(msg)
                    except (SystemExit,KeyboardInterrupt): raise
                    except sock_timeout: continue
                    except sock_error:
                        if not self._com is None:
                            self._com.close()
                            self._com = None
                        time.sleep(1)
                        continue
                    match = self._re_state.match(msg)
                    if match is None: continue
                    with self.cv:
                        if self.debug==1: dprint(match.group(0))
                        statid = int(match.group(1))
                        stat=statid if statid>5 else STATE.get_name(statid)
                        self._state.add(stat)
                        self._pre     = int(match.group(2))
                        self._post    = int(match.group(3))
                        self._elapsed = int(match.group(4))
                        self._reserved= int(match.group(5))
                        self.cv.notify_all()
            finally:
                del(STATE._loggers[self.name])
                with self.cv:
                    self.cv.notify_all()

        def reset(self):
            with self.cv:
                self._state.clear()
                self._pre     = -1
                self._post    = -1
                self._elapsed = -1
                self._reserved= -1
                self.cv.notify_all()
        def wait4state(self,state):
            if not state in STATE._map:
                raise Exception("No such state %s"%state)
            with self.cv:
                while (not state in self._state) and self.on:
                    self.cv.wait(1)
            return self.on
        @property
        def state(self):
            with self.cv:
                return self._state
        @property
        def pre(self):
            with self.cv:
                return self._pre
        @property
        def post(self):
            with self.cv:
                return self._post
        @property
        def elapsed(self):
            with self.cv:
                return self._elapsed
        @property
        def reserved(self):
            with self.cv:
                return self._reserved

###--------------
### 0 nc properties
###--------------

class _property_str(object):
    """
    MDSplus-independent class
    """
    def getdoc(self):return self.__doc__
    ro = False
    _cast = str
    def __get__(self, inst, cls):
        if inst is None: return self
        return self._cast(inst(self._cmd))
    def __set__(self, inst, value):
        if self.ro: raise AttributeError
        return inst(self._cmd,self._cast(value))
    def __init__(self, cmd, ro=False,doc=None):
        if doc is not None: self.__doc__ = doc
        self.ro = ro
        self._cmd = cmd

class _property_aggr(_property_str):
    ro = True

class _property_bool(_property_str):
    @staticmethod
    def _cast(ans): return int(ans)!=0
    def __set__(self, inst, value):
        if self.ro: raise AttributeError
        return inst(self._cmd,int(self._cast(value)))

class _property_int(_property_str):
    _cast = int

class _property_float(_property_str):
    _cast = float

class _property_list(_property_str):
    def __get__(self, inst, cls):
        if inst is None: return self
        return tuple(int(v) for v in inst(self._cmd).split(' ',1)[0].split(','))

class _property_list_f(_property_str):
    def __get__(self, inst, cls):
        if inst is None: return self
        return tuple(float(v) for v in inst(self._cmd).split(' ',1)[1].split(' '))

class _property_grp(object):
    """
    MDSplus-independent class
    """
    _parent = None
    def getdoc(self):return self.__doc__
    def __call__(self,cmd,*args):
        # allows for nextes structures, e.g. acq.SYS.CLK.COUNT
        return self._parent('%s:%s'%(self.__class__.__name__,str(cmd)),*args)
    def __str__(self):
        if isinstance(self._parent,_property_grp):
            return '%s:%s'%(str(self._parent),self.__class__.__name__)
        return self.__class__.__name__
    def __repr__(self):
        return '%s:%s'%(repr(self._parent),self.__class__.__name__)
    def __init__(self, parent, doc=None):
        if isinstance(parent,str):
            raise Exception("ERROR: used _property_grp as initializer: subclass instead")
        self._parent = parent
        if doc is not None: self.__doc__ = doc
        for k,v in self.__class__.__dict__.items():
            if isinstance(v,type) and issubclass(v,(_property_grp,)):
                self.__dict__[k] = v(self)
    def __getattribute__(self,name):
        v = super(_property_grp,self).__getattribute__(name)
        if name.startswith('_'): return v
        if isinstance(v,type):
            if issubclass(v,(_property_grp,)):
                return v(self)
            elif issubclass(v,(_property_str,)):
                return v(self).__get__(self,self.__class__)
        return v
    def __getattr__(self,name):
        if name.startswith('_'):
            return super(dtacq,self).__getattribute__(name)
        return self(name)
    def __setattr__(self,name,value):
        """
        Checks if it's any part of a super/class, and if it isn't, it assumes the netcat entry
        """
        try:
            if hasattr(self.__class__,name):
                super(_property_grp,self).__setattr__(name,value)
        except AttributeError:
            return self(name,value)

class _property_exe(_property_grp):
    _args = '1'
    _cmd = None
    def __call__(self,cmd=None,*args):
        if cmd is not None:
            return super(_property_exe,self).__call__(cmd,*args)
        self._parent(self.__class__.__name__ if self._cmd is None else self._cmd,self._args)

class _property_idx(_property_grp):
    """
    MDSplus-independent class
    """
    _format_idx = '%d'
    _cast = lambda s,x: x
    _format = '%s'
    _strip = ''
    _idxsep = ':'
    def get(self,idx):
        return '%s%s%s'%(self.__class__.__name__,self._idxsep,self._format_idx%idx)
    def set(self,idx,value):
        return '%s %s'%(self.get(idx),self._format%value)
    def __getitem__(self,idx):
        return self._cast(self._parent(self.get(idx)).strip(self._strip))
    def __setitem__(self,idx,value):
        return self._parent(self.set(idx,value))
    def setall(self,value):
        return [self.set(i+1,v) for i,v in enumerate(value)]

class _property_cnt(_property_grp):
    """
    MDSplus-independent class
    """
    class RESET(_property_exe): pass
    COUNT = _property_int('COUNT', 1)
    FREQ  = _property_float('FREQ',  1)
    ACTIVE= _property_float('ACTIVE',1)

class _property_state(object):
    def __get__(self, inst, cls):
        if inst is None: return self
        ans = inst(self._cmd)
        if not ans: return {'state':'CLEANUP'}
        try:   res = list(map(int,ans.split(' ')))+[0,0,0,0]
        except ValueError: return {'state':'CLEANUP'}
        stat=res[0] if res[0]>5 else STATE.get_name(res[0])
        return {'state':stat,'pre':res[1],'post':res[2],'elapsed':res[3],'reserved':tuple(res[4:])}
    def __init__(self, cmd, doc=None):
        if doc is not None: self.__doc__ = doc
        self._cmd = cmd


### 1 dtacq_knobs
class hwmon_knobs(object):
    in1  = _property_int('in1',1)
    in2  = _property_int('in2',1)
    in3  = _property_int('in3',1)
    in4  = _property_int('in4',1)
    temp = _property_int('temp',1)
    @property
    def help(self):
        return self('help').split('\n')
    @property
    def helpA(self):
        return dict(tuple(map(str.strip,a.split(' : '))) for a in self('helpA').split('\n'))

class dtacq_knobs(object):
    bufferlen    = _property_int('bufferlen',1)
    data32       = _property_bool('data32')
    MODEL        = _property_str('MODEL',1)
    NCHAN        = _property_int('NCHAN',1)
    SERIAL       = _property_str('SERIAL',1)
    @property
    def help(self):
        return self('help').split('\n')
    @property
    def helpA(self):
        return dict(tuple(map(str.strip,a.split(' :'))) for a in self('helpA').split('\n'))

class carrier_knobs(dtacq_knobs):
    acq480_force_training = _property_bool('acq480_force_training')
    aggregator= _property_aggr('aggregator')
    class fit_rtm_translen_to_buffer(_property_exe): pass
    """Gate Pulse Generator"""
    gpg_clk   = _property_list('gpg_clk',1)
    gpg_enable= _property_int ('gpg_enable')
    gpg_mode  = _property_int ('gpg_mode')
    gpg_sync  = _property_list('gpg_sync',1)
    gpg_trg   = _property_list('gpg_trg',1)
    live_mode = _property_int('live_mode',doc="Streaming: CSS Scope Mode {0:off, 1:free-run, 2:pre-post}")
    live_pre  = _property_int('live_pre',doc="Streaming: pre samples for pre-post mode")
    live_post = _property_int('live_post',doc="Streaming: post samples for pre-post mode")
    def play0(self,*args):
        """Initializing the distributor: feeds data from distributor to active sites"""
        return self('play0',args)
    class reboot(_property_exe):
        """reboots carrier with sync;sync;reboot"""
        _args = '3210'
    def run0(self,*args):
        """Initializing the aggregator: feeds data from active sites to aggregator"""
        return self('run0',args)
    def set_arm(self):  self('set_arm')
    def set_abort(self, keep_repeat=0):
        """Use keep_repeat 1 to only abort the arming on a single sequence"""
        if keep_repeat == 0: self.TRANSIENT_REPEAT=0
        self('set_abort')
    state            = _property_state('state')
    streamtonowhered = _property_str('streamtonowhered',doc='start|stop')
    class streamtonowhered_start(_property_exe):
        _cmd = 'streamtonowhered'
        _args= 'start'
    class streamtonowhered_stop(_property_exe):
        _cmd = 'streamtonowhered'
        _args= 'stop'
    transient_state  = _property_state('transient_state')
    def soft_trigger(self):   self('soft_trigger');return self
    shot      = _property_int('shot')
    def transient(self,pre=None,post=None,osam=None,soft_out=None,demux=None):
        cmd = 'transient'
        if not pre   is None: cmd += ' PRE=%d' %(pre,)
        if not post  is None: cmd += ' POST=%d'%(post,)
        if not osam  is None: cmd += ' OSAM=%d'%(osam,)
        if not soft_out is None: cmd += ' SOFT_TRIGGER=%d'%(1 if soft_out else 0,)
        if not demux is None: cmd += ' DEMUX=%d'%(1 if demux else 0,)
        ans = self(cmd)
        if cmd.endswith('transient'):
            glob = {}
            exec(ans.split('\n')[-1].replace(' ',';')) in {},glob
            return glob
    CONTINUOUS = _property_str('CONTINUOUS',doc="reliable way to start|stop stream")
    class CONTINUOUS_start(_property_exe):
        _cmd = 'CONTINUOUS'
        _args= 'start'
    class CONTINUOUS_stop(_property_exe):
        _cmd = 'CONTINUOUS'
        _args= 'stop'
    CONTINUOUS_STATE = _property_str('CONTINUOUS:STATE',1)
    CONTINUOUS_STATUS= _property_str('CONTINUOUS:STATUS',1)
    class GPG(_property_grp):
        class DBG(_property_grp):
            CTR    = _property_int('CTR',   1)
            DEF    = _property_int('DEF',   1)
            OSTATE = _property_int('OSTATE',1)
            PTR    = _property_int('PTR',   1)
            RSTATE = _property_int('RSTATE',1)
            STATE  = _property_int('STATE', 1)
            UNTIL  = _property_int('UNTIL', 1)
        ENABLE =  _property_int('ENABLE',doc="enable Gate Pulse Generator")
        MODE   =  _property_int('MODE',doc="set GPG mode One Shot | Loop | Loop/Wait")
    GPG_CLK       = _property_str('GPG_CLK',      doc="configure Gate Pulse Generator clock source")
    GPG_CLK_DX    = _property_str('GPG_CLK:DX',   doc='d0 through d7')
    GPG_CLK_SENSE = _property_str('GPG_CLK:SENSE',doc='1 for rising, 0 for falling')
    @property
    def GPG_CLK_ALL(self):  return self.gpg_clk
    @GPG_CLK_ALL.setter
    def GPG_CLK_ALL(self,value):
        value = tuple(str(e) for e in value[:3])
        #self('GPG_CLK %s\nGPG_CLK:DX %s\nGPG_CLK:SENSE %s'%value)
        self('gpg_clk %s,%s,%s'%value) # captized version is unreliable
    GPG_SYNC       = _property_str('GPG_SYNC',      doc="configure GPG sync with (sample) clock source")
    GPG_SYNC_DX    = _property_str('GPG_SYNC:DX',   doc='d0 through d7')
    GPG_SYNC_SENSE = _property_str('GPG_SYNC:SENSE',doc='1 for rising, 0 for falling')
    @property
    def GPG_SYNC_ALL(self):  return self.gpg_sync
    @GPG_SYNC_ALL.setter
    def GPG_SYNC_ALL(self,value):
        value = tuple(str(e) for e in value[:3])
        #self('GPG_SYNC %s\nGPG_SYNC:DX %s\nGPG_SYNC:SENSE %s'%value)
        self('gpg_sync %s,%s,%s'%value) # captized version is unreliable
    GPG_TRG       = _property_str('GPG_TRG',      doc="configure GPG start trigger source")
    GPG_TRG_DX    = _property_str('GPG_TRG:DX',   doc='d0 through d7')
    GPG_TRG_SENSE = _property_str('GPG_TRG:SENSE',doc='1 for rising, 0 for falling')
    @property
    def GPG_TRG_ALL(self):  return self.gpg_trg
    @GPG_TRG_ALL.setter
    def GPG_TRG_ALL(self,value):
        value = tuple(str(e) for e in value[:3])
        #self('GPG_TRG %s\nGPG_TRG:DX %s\nGPG_TRG:SENSE %s'%value)
        self('gpg_trg %s,%s,%s'%value) # captized version is unreliable
    class SIG(_property_grp):
        ZCLK_SRC  = _property_str('ZCLK_SRC', doc='INT33M, CLK.d0 - CLK.d7')
        class FP(_property_grp):
            CLKOUT= _property_str('CLKOUT')
            SYNC  = _property_str('SYNC')
            TRG   = _property_str('TRG')
        class SRC(_property_grp):
            class CLK (_property_idx): pass
            class SYNC(_property_idx): pass
            class TRG (_property_idx): pass
        class CLK(_property_grp): pass
        class CLK_EXT (_property_cnt): pass
        class CLK_MB  (_property_cnt):
            FIN = _property_int('FIN',doc='External input frequency')
            SET = _property_int('SET',doc='Set desired MB frequency')
            READY = _property_int('READY',1,doc='Clock generation ready')
        class CLK_S1  (_property_grp): # 1-6
            FREQ = _property_int('FREQ')
        class EVENT_SRC(_property_idx): pass
        class EVT_EXT (_property_cnt): pass
        class EVT_MB  (_property_cnt): pass
        class EVT_S1  (_property_cnt): pass# 1-6
        class SYN_EXT (_property_cnt): pass
        class SYN_MB  (_property_cnt): pass
        class SYN_S1  (_property_cnt): pass# 1-6
        class TRG_MB  (_property_cnt): pass
        class TRG_S1  (_property_cnt): pass# 1-6
    def STREAM_OPTS(self,raw=None,subset=None,nowhere=False): # package.w7x
        if nowhere: return self('STREAM_OPTS --null-copy')
        params = ['STREAM_OPTS']
        if raw is not None:    params.append(raw)
        if subset is not None: params.append('--subset=%s'%(self._tupletostr(subset),))
        if len(params)==1:     params.append('""')
        return self(' '.join(params))
    class SYS(_property_grp):
        class CLK(_property_grp):
            FPMUX = _property_str('FPMUX',doc="OFF, XCLK, FPCLK, ZCLK")
    class TRANSIENT(_property_exe):
        PRE          = _property_int('PRE',doc='Number of pre-trigger samples')
        POST         = _property_int('POST',doc='Number of post-trigger samples')
        OSAM         = _property_int('OSAM',doc='Subrate data monitoring')
        SOFT_TRIGGER = _property_int('SOFT_TRIGGER',doc='Initial soft_trigger() call? (0 or 1)')
        REPEAT       = _property_int('REPEAT',doc='Number of shots before set_abort is called')
        DELAYMS      = _property_int('DELAYMS',doc='Number of milliseconds to wait befor soft trigger')
        class SET_ARM(_property_exe): """put carrier in armed state; go to ARM"""
        class SET_ABORT(_property_exe): """aborts current capture; go to STOP"""
    def TRANSIENT_ALL(self,pre,post,osam,soft_out,repeat,demux):
        self._com('\n'.join([
            'transient DEMUX=%d'        % (1 if demux else 0),
            'TRANSIENT:PRE %d'          % pre,
            'TRANSIENT:POST %d'         % post,
            'TRANSIENT:OSAM %d'         % osam,
            'TRANSIENT:SOFT_TRIGGER %d' % (1 if soft_out else 0),
            'TRANSIENT:REPEAT %d'       % repeat,
            'TRANSIENT 1',
            ]))

class acq1001_knobs(carrier_knobs):
    pass

class acq2106_knobs(carrier_knobs):
    _bypass = '1-1_bypass'
    data_engine_2 = _property_aggr('data_engine_2',doc='aggregator for mgt482 line A')
    data_engine_3 = _property_aggr('data_engine_3',doc='aggregator for mgt482 line B')
    class load_si5326(_property_exe): cmd = 'load.si5326'
    run0_ready = _property_bool('run0_ready',1)
    set_si5326_bypass = _property_bool('set_si5326_bypass')
    class si5326_step_phase(_property_exe): pass
    si5326_step_state= _property_state('si5326_step_state')
    si5326bypass= _property_str('si5326bypass',1)
    si5326config= _property_str('si5326config',1)
    sites= _property_str('sites',1)
    class spadstart(_property_str): ro = True
    class ssb(_property_int): ro = True
    class SYS(carrier_knobs.SYS):
        class CLK(carrier_knobs.SYS.CLK):
            BYPASS       = _property_int('BYPASS')
            #C1B          = _property_str('C1B',1)
            #C2B          = _property_str('C2B',1)
            CONFIG       = _property_str('CONFIG',1)
            LOL          = _property_bool('LOL',1,doc='Jitter Cleaner - Loss of Lock')
            class OE_CLK1_ELF1(_property_exe):pass # 1-6
            OE_CLK1_ZYNQ = _property_int('OE_CLK1_ZYNQ')
            class Si5326(_property_grp):
                PLAN    = _property_str('PLAN',doc='{10M, 20M, 24M, 40M, 50M, 80M}')
                PLAN_EN = _property_int('PLAN_EN') # unused? EN for ENABLED?
            class Si570_OE(_property_exe):pass
    class TRANS_ACT(_property_grp):
        STATE_NOT_IDLE= _property_int('STATE_NOT_IDLE',ro=True)
        class FIND_EV(_property_grp):
            CUR = _property_int('CUR',ro=True)
            NBU = _property_int('NBU',ro=True)
            STA = _property_str('STA',ro=True)
        POST   = _property_int('POST',ro=True)
        PRE    = _property_str('PRE',ro=True)
        STATE  = _property_str('STATE',ro=True)
        TOTSAM = _property_int('TOTSAM',ro=True)

class site_knobs(dtacq_knobs):
    nbuffers     = _property_str('nbuffers',1)
    modalias     = _property_str('modalias',1)
    module_name  = _property_str('module_name',1)
    module_role  = _property_str('module_role',1)
    module_type  = _property_int('module_type',1)
    site         = _property_str('site',1)
    AGIX         = _property_int('AGIX')
    MANUFACTURER = _property_str('MANUFACTURER',1)
    MTYPE        = _property_int('MTYPE',1)
    PART_NUM     = _property_str('PART_NUM',1)

class module_knobs(site_knobs):
    simulate  = _property_bool('simulate')
    clkdiv    = _property_int('clkdiv')
    CLK       = _property_str('CLK',doc='1 for external, 0 for internal')
    CLK_DX    = _property_str('CLK:DX',doc='d0 through d7')
    CLK_SENSE = _property_str('CLK:SENSE',doc='1 for rising, 0 for falling')
    CLKDIV    = _property_int('CLKDIV')
    class SIG(_property_grp):
        class CLK_COUNT(_property_cnt): pass
        class sample_count(_property_cnt): pass
        class SAMPLE_COUNT(_property_cnt):
            RUNTIME = _property_str('RUNTIME')
    EVENT0       = _property_str('EVENT0',doc='enabled or disabled')
    EVENT0_DX    = _property_str('EVENT0:DX',doc='d0 through d7')
    EVENT0_SENSE = _property_str('EVENT0:SENSE',doc='1 for rising, 0 for falling')
    EVENT1       = _property_str('EVENT1',doc='enabled or disabled')
    EVENT1_DX    = _property_str('EVENT1:DX',doc='d0 through d7')
    EVENT1_SENSE = _property_str('EVENT1:SENSE',doc='1 for rising, 0 for falling')
    RGM          = _property_str('RGM', doc='0:OFF,2:RGM,3:RTM')
    RGM_DX       = _property_str('RGM:DX',doc='d0 through d7')
    RGM_SENSE    = _property_str('RGM:SENSE',doc='1 for rising, 0 for falling')
    SYNC         = _property_str('SYNC', doc='enabled or disabled')
    SYNC_DX      = _property_str('SYNC:DX',doc='d0 through d7')
    SYNC_SENSE   = _property_str('SYNC:SENSE',doc='1 for rising, 0 for falling')
    TRG          = _property_str('TRG', doc='enabled or disabled')
    TRG_DX       = _property_str('TRG:DX',doc='d0 through d7')
    TRG_SENSE    = _property_str('TRG:SENSE',doc='1 for rising, 0 for falling')
    @property
    def CLK_ALL(self):  return self.clk
    @CLK_ALL.setter
    def CLK_ALL(self,value):
        value = tuple(str(e) for e in value[:3])
        #self('CLK %s\nCLK:DX %s\nCLK:SENSE %s'%value)
        self('clk %s,%s,%s'%value) # captized version is unreliable
    @property
    def TRG_ALL(self):  return self.trg
    @TRG_ALL.setter
    def TRG_ALL(self,value):
        value = tuple(str(e) for e in value[:3])
        #self('TRG %s\nTRG:DX %s\nTRG:SENSE %s'%value)
        self('trg %s,%s,%s'%value) # captized version is unreliable
    @property
    def EVENT0_ALL(self):  return self.event0
    @EVENT0_ALL.setter
    def EVENT0_ALL(self,value):
        value = tuple(str(e) for e in value[:3])
        #self('EVENT0 %s\nEVENT0:DX %s\nEVENT0:SENSE %s'%value)
        self('event0 %s,%s,%s'%value) # captized version is unreliable
    @property
    def EVENT1_ALL(self):  return self.event1
    @EVENT1_ALL.setter
    def EVENT1_ALL(self,value):
        value = tuple(str(e) for e in value[:3])
        #self('EVENT1 %s\nEVENT1:DX %s\nEVENT1:SENSE %s'%value)
        self('event1 %s,%s,%s'%value) # captized version is unreliable
    @property
    def RGM_ALL(self):  return self.rgm
    @RGM_ALL.setter
    def RGM_ALL(self,value):
        value = tuple(str(e) for e in value[:3])
        #self('RGM %s\nRGM:DX %s\nRGM:SENSE %s'%value)
        self('rgm %s,%s,%s'%value) # captized version is unreliable
    RTM_TRANSLEN = _property_int('RTM_TRANSLEN',doc='samples per trigger in RTM; should fill N buffers')

class acq4xx_knobs(module_knobs):
    es_enable    = _property_int('es_enable',0,'data will include an event sample')
    class SIG(module_knobs.SIG):pass
    class AI(_property_grp):
        class CAL(_property_cnt):
            ESLO = _property_list_f('ESLO')
            EOFF = _property_list_f('EOFF')

class acq425_knobs(acq4xx_knobs):
    MAX_KHZ = _property_int('MAX_KHZ',1)

class acq480_knobs(acq4xx_knobs):
    acq480_loti  = _property_int('acq480_loti',1,doc='Jitter Cleaner - Loss of Time')
    train        = _property_int('train',1,doc='Jitter Cleaner - Loss of Time')
    class ACQ480(_property_grp):
        TRAIN = _property_str('TRAIN',1)
        class FIR(_property_idx):
            _format_idx = '%02d'
            DECIM = _property_int('DECIM')
        class FPGA(_property_grp):
            DECIM = _property_int('DECIM')
        class INVERT(_property_idx):
            _format_idx = '%02d'
        class GAIN(_property_idx):
            _format_idx = '%02d'
        class HPF(_property_idx):
            _format_idx = '%02d'
        class LFNS(_property_idx):
            _format_idx = '%02d'
        class T50R(_property_idx):
            _format_idx = '%02d'
        T50R_ALL = _property_int('T50R')
    JC_LOL = _property_int('JC_LOL',1,doc='Jitter Cleaner - Loss of Lock')
    JC_LOS = _property_int('JC_LOS',1,doc='Jitter Cleaner - Loss of Signal')
    class SIG(acq4xx_knobs.SIG):
        class CLK(_property_grp):
            TRAIN_BSY = _property_int('TRAIN_BSY',0,doc='Clock sync currently training')

class ao420_knobs(module_knobs):
    run = _property_bool('run',1)
    task_active = _property_bool('task_active',1)
    ACC = _property_str('ACC')
    class AO(_property_grp):
        class GAIN(_property_grp):
            class CH(_property_idx): pass
    class AWG(_property_grp):
        class D(_property_idx): pass
        class G(_property_idx): pass
    class D(_property_idx): _idxsep = ''
    class G(_property_idx): _idxsep = ''

###-----------------
### 2 dtacq nc classes
###-----------------

class dtacq(nc,dtacq_knobs):
    """
    MDSplus-independent
    """
    _excutables = []
    _transient = ['state','shot']
    _help = None
    _helpA = None
    cache = None
    _cache = {}
    @classmethod
    def add_cache(cls,host):
        cls._cache[host] = {}
    @classmethod
    def remove_cache(cls,host):
        return cls._cache.pop(host)
    def __init__(self,server,site):
        super(dtacq,self).__init__((server,_sys_port+site))
        for cls in self.__class__.mro():
            for k,v in cls.__dict__.items():
                if isinstance(v,type) and not k in self.__dict__:
                    if issubclass(v,(_property_grp,)):
                        self.__dict__[k] = v(self)
        self.cache = self._cache.get(server,None)
        if self.cache is not None:
            self.cache = self.cache.setdefault(str(site),{})
    @staticmethod
    def filter_result(cmd,res,val):
        cmd = cmd.strip()
        if cmd in dtacq._excutables or cmd in dtacq._transient or cmd.endswith(':RESET'):
            return cmd,None
        res = res.strip()
        if res.startswith(cmd):
            res = res[len(cmd)+1:]
        if len(res)==0:
            if len(val)==0:
                return cmd,None
            return cmd,val[0]
        return cmd,res
    def _com(self,cmd,ans=False,timeout=5):
        dbg = [None,None]
        super(dtacq,self)._com(cmd,ans,timeout,dbg)
        if dbg[0] is not None and self.cache is not None:
            rows = dbg[0].split('\n')
            rres = dbg[1].split('\n')
            sync = len(rows) == len(rres)
            for i in range(len(rows)):
                cmd = rows[i].strip().split(' ',2)
                res = rres[i] if sync else ''
                cmd,res = dtacq.filter_result(cmd[0],res,cmd[1:])
                if res is not None:
                    self.cache[cmd] = res
        if ans: return dbg[1]

    @staticmethod
    def _callerisinit(ignore):
        stack = inspect.stack()[2:]
        for call in stack:
            if call[3]==ignore:     continue
            if call[3]=='__init__': return True
            break
        return False
    def _getfromdict(self,name):
        for cls in self.__class__.mro():
            if cls is nc: raise AttributeError
            try: return cls.__dict__[name]
            except KeyError: continue
    def __getattribute__(self,name):
        v = nc.__getattribute__(self,name)
        if name.startswith('_'): return v
        if name in ('_server','_com','_getfromdict'): return v
        if isinstance(v,type):
            if issubclass(v,(_property_grp,)):
                return v(self)
            elif issubclass(v,(_property_str,)):
                return v(self).__get__(self,self.__class__)
        return v
    def __getattr__(self,name):
        if name.startswith('_'):
            return super(dtacq,self).__getattribute__(name)
        try:   return self._getfromdict(name)
        except AttributeError:
            return self(name)
    def __setattr__(self,name,value):
        """
        Checks if it's any part of a super/class, and if it isn't, it assumes the netcat entry
        """
        try:
            if hasattr(self.__class__,name):
                super(dtacq,self).__setattr__(name,value)
        except AttributeError:
            if not dtacq._callerisinit('__setattr__'):
                return self(name,value)
            return super(dtacq,self).__setattr__(name,value)

class carrier(dtacq,carrier_knobs):
    _log = None
    ai_sites = None
    ao_sites = None
    _excutables = dtacq._excutables + ['acqcmd','get.site','reboot','run0','play0','soft_transient','soft_trigger',
        'TRANSIENT:SET_ARM','TRANSIENT:SET_ABORT','set_arm','set_abort','SIG:SOFT_TRIGGER']
    def __init__(self,server): super(carrier,self).__init__(server,0)
    @property
    def log(self):
        if self._log is None:
            self._log = STATE.logger(self._server[0])
        return self._log
    def channel(self,i): return channel(i,self._server[0])
    def _init_carrier_(self,ai_sites=None,ao_sites=None):
        self.ai_sites = ai_sites
        self.ao_sites = ao_sites
    def wait(self,timeout,condition,breakcond):
        if not timeout is None: timeout = time.time()+timeout
        ok = [True] # python way of defining a pointer
        with self.log.cv:
            if condition(self,ok):
                while self.log.on:
                    if breakcond(self,ok): break
                    if timeout is not None and (time.time()-timeout>0):
                        ok[0] = False
                        break
                    self.log.cv.wait(1)
                else: raise Exception('logger terminated')
            if debug: dprint(self.state)
        return self.log.on and ok[0]

    def wait4state(self,state,timeout=None):
        if not state in STATE.names:
            raise Exception("No such state %s"%state)
        def condition(self,ok):
            if self.state['state'] == state: return False
            if state in self.log._state:
                self.log._state.remove(state)
            return True
        def breakcond(self,ok):
            return state in self.log._state
        return self.wait(timeout,condition,breakcond)

    def wait4arm(self,timeout=None):
        waitstates = (STATE.STOP,STATE.CLEANUP)
        def condition(self,ok):
            if not self.state['state'] in waitstates: return False
            if STATE.ARM in self.log._state:
                self.log._state.remove(STATE.ARM)
            self.TRANSIENT.SET_ARM()
            return True
        def breakcond(self,ok):
            if STATE.ARM in self.log._state or not self.state['state'] in waitstates: return True
            self.TRANSIENT.SET_ARM()
            return False
        return self.wait(timeout,condition,breakcond)

    def wait4post(self,post,timeout=None):
        waitstates = (STATE.ARM,STATE.PRE,STATE.POST)
        def condition(self,ok):
            if not self.state['state'] in waitstates or self.state['post']>=post: return False
            if STATE.STOP in self.log._state:
                self.log._state.remove(STATE.STOP)
            return True
        def breakcond(self,ok):
            state = self.state
            return (STATE.STOP in self.log._state) or state['state']==STATE.STOP or state['post']>=post
        return self.wait(timeout,condition,breakcond)

    def wait4abort(self,timeout=None):
        self.CONTINUOUS_stop()
        self.streamtonowhered_stop()
        self.TRANSIENT.SET_ABORT()
        def condition(self,ok):
            if self.state['state'] == STATE.STOP: return False
            if self.state['state'] == STATE.FIN2:
                time.sleep(1)
                if self.state['state'] == STATE.FIN2:
                    self.set_arm()
                    self.set_abort()
            self.log._state.clear()
            return True
        def breakcond(self,ok):
            if (STATE.STOP in self.log._state) or (self.state['state'] == STATE.STOP): return True
            self.TRANSIENT.SET_ABORT()
            return False
        return self.wait(timeout,condition,breakcond)

    def __call__(self,cmd,value=None,site=0):
        if len(cmd.strip())==0: return ""
        if site>0: cmd = 'set.site %d %s'%(site,cmd,)
        return super(carrier,self).__call__(cmd,value)

    def _init(self,ext,mb_fin,mb_set,pre,post,soft_out,demux=1,shot=1,sites=''):
        if not self.wait4abort(timeout=30): raise Exception('Could not abort.')
        if self.ai_sites is not None: self.run0(*self.ai_sites)
        if self.ao_sites is not None: self.play0(*self.ao_sites)
        if not shot is None: self.shot = shot
        self._setup_clock(ext,mb_fin,mb_set)
        #self.chainstart()
        self._setup_trigger(pre,post,soft_out,demux)
        #self.chainsend()
    def _setup_clock(self,ext,mb_fin,mb_set):
        if ext:
            self.SYS.CLK.FPMUX = 'FPCLK'
            if debug: dprint('Using external clock source')
        else:
            self.SIG.ZCLK_SRC = 0
            self.SYS.CLK.FPMUX = 'ZCLK'
            if debug: dprint('Using internal clock source')
        self.SIG.SRC.CLK[0] = 0
        self.SIG.SRC.CLK[1] = 0 #MCLK
        self.SIG.CLK_MB.FIN = mb_fin
        self.SIG.CLK_MB.SET = mb_set # = clk * clkdiv
    def _setup_trigger(self,pre,post,soft_out,demux):
        # setup Front Panel TRIG port
        self.SIG.FP.TRG = 'INPUT'
        # setup signal source for external trigger and software trigger
        self.SIG.SRC.TRG[0] = 0 # 'EXT'
        self.SIG.SRC.TRG[1] = 0 # 'STRIG'
        soft_out = 1 if pre>0 else soft_out
        self.live_mode = 2 if pre else 1
        self.live_pre  = pre
        self.live_post = post
        self.TRANSIENT_ALL(pre=pre,post=post,osam=1,repeat=0,soft_out=soft_out,demux=demux)
        if debug: dprint('PRE: %d, POST: %d'%(pre,post))

class acq1001(carrier,acq1001_knobs):
    _mclk_clk_min = 4000000

class acq2106(carrier,acq2106_knobs):
    def _setup_clock(self,ext,mb_fin,mb_set):
        super(acq2106,self)._setup_clock(ext,mb_fin,mb_set)
        if debug: dprint('%s: setting up clock %d'%(self._server[0],1))
        set_plan = mb_set in [10000000,20000000,24000000,40000000,50000000,80000000]
        if set_plan:
            self.SYS.CLK.BYPASS = 0
            self.SYS.CLK.Si5326.PLAN = '%02dM'%(mb_set//1000000,)
        else:
            set_bypass = mb_fin == mb_set
            is_bypass  = self.SYS.CLK.CONFIG == acq2106._bypass
            if set_bypass != is_bypass:
                self.SYS.CLK.BYPASS = int(set_bypass)
                t = 5
                while is_bypass == (self.SYS.CLK.CONFIG == acq2106._bypass):
                    t-=1
                    if t<0: break
                    time.sleep(1)
        self.SYS.CLK.OE_CLK1_ZYNQ = 1

class module(dtacq,module_knobs):
    _clkdiv_adc  = 1
    _clkdiv_fpga = 1
    is_master = False
    def __init__(self,server,site=1):
        super(module,self).__init__(server,site)
        self.is_master = site==1
    @property
    def data_scales(self):  return self.AI.CAL.ESLO[1:]
    @property
    def data_offsets(self): return self.AI.CAL.EOFF[1:]
    def _trig_mode(self,mode=None):
        if mode is None: return 0
        elif isinstance(mode,str):
            mode = mode.upper()
            if   mode == 'RGM': return 2
            elif mode == 'RTM': return 3
            else:               return 0
        return mode
    def _init(self,shot=None):
        if not shot is None:
            self.shot = shot
        self.data32 = 0

    def _init_master(self,pre,soft):
        self.SIG.sample_count.RESET()
        self.TRG_ALL    = (1,1 if pre|soft else 0,1)
        self.EVENT0_ALL = (1 if pre else 0,1 if soft else 0,1)
        self.CLK_ALL    = (1,1,1)

class acq425(module,acq425_knobs):
    class GAIN(_property_idx):
        _format_idx = '%02d'
        _cast = lambda s,x: int(x)
        _format = '%dV'
        ALL = _property_str('ALL')
    def gain(self,channel=0,*arg):
        if channel>0:
            return int(self('gain%d'%(channel,),*arg))
        else:
            return int(self('gain',*arg))
    def range(self,channel=0):
        channel = str(channel) if channel>0 else ''
        return 10./(1<<int(self('gain%s'%(channel,))))
    def _init_master(self,pre,soft,clkdiv,mode=None,translen=None):
        mode = self._trig_mode(mode)
        ese  = 1 if mode else 0
        self.chainstart()
        # use soft trigger to start stream for R?M: soft|ese
        super(acq425,self)._init_master(pre,soft|ese)
        if mode == 3 and not translen is None:
            self.rtm_translen = translen*self._clkdiv_fpga
        #self.EVENT1_ALL  = (ese,1 if soft else 0,ese) # marker is anyway set with f154
        self.RGM_ALL      = (mode,1 if soft else 0,1)
        self.es_enable    = ese
        self.chainsend()
        time.sleep(1)
        self.clkdiv = clkdiv
    def _init(self,gain=None,shot=None):
        self.chainstart()
        super(acq425,self)._init(shot)
        if not gain is None: self._com(self.GAIN.setall(  gain  ))
        self.chainsend()

class acq480(module,acq480_knobs):
    def get_skip(self):
        fpga = self._clkdiv_fpga
        if   fpga==10:
            delay=9
        elif fpga==4:
            delay=0
        else:
            delay=0
        return delay
    _FIR_DECIM = [1,2,2,4,4,4,4,2,4,8,1]
    def _max_clk_dram(self,num_modules): # DRAM: max_clk = 900M / Nmod / 8 / 2
        limit = [50000000,28000000,18000000,14000000,11000000,9000000][num_modules-1]
        return limit
    def max_clk(self,num_modules):
        limit = self._max_clk_dram(num_modules)
        adc_div,fpga_div = self._clkdiv_adc(self._firmode),self._clkdiv_fpga
        if  adc_div>1: limit = min(limit,80000000// adc_div)
        if fpga_div>1: limit = min(limit,25000000//fpga_div)
        return limit
    def _clkdiv_adc(self,fir): return self._FIR_DECIM[fir]
    __clkdiv_fpga = None
    @property
    def _clkdiv_fpga(self):
        if self.__clkdiv_fpga is None: self.__clkdiv_fpga = self.ACQ480.FPGA.DECIM
        return self.__clkdiv_fpga
    __firmode = None
    @property
    def _firmode(self):
        if self.__firmode is None: self.__firmode = self.ACQ480.FIR[1]
        return self.__firmode
    def _clkdiv(self,fir):
        return self._clkdiv_adc(fir)*self._clkdiv_fpga
    def _init(self,gain=None,invert=None,hpf=None,lfns=None,t50r=None,shot=None):
        self.chainstart()
        super(acq480,self)._init(shot)
        if not gain   is None: self._com(self.ACQ480.GAIN  .setall( gain   ))
        if not invert is None: self._com(self.ACQ480.INVERT.setall( invert ))
        if not hpf    is None: self._com(self.ACQ480.HPF   .setall( hpf    ))
        if not lfns   is None: self._com(self.ACQ480.LFNS  .setall( lfns   ))
        if not t50r   is None: self._com(self.ACQ480.T50R  .setall( t50r   ))
        self.chainsend()
    def _init_master(self,pre,soft,mode=None,translen=None,fir=0):
        mode = self._trig_mode(mode)
        ese  = 1 if mode else 0
        self.chainstart()
        # use soft trigger to start stream for R?M: soft|ese
        super(acq480,self)._init_master(pre,soft|ese)
        if mode == 3 and not translen is None:
            self.rtm_translen = translen*self._clkdiv_fpga
        #self.EVENT1_ALL  = (ese,1 if soft else 0,ese) # marker is anyway set with f154
        self.RGM_ALL      = (mode,1 if soft else 0,1)
        self.es_enable    = ese
        self.ACQ480.FIR[1] = int(fir==0)
        self.ACQ480.FIR[1] = fir
        self.chainsend()
        decim = 1<<int(fir==0)
        while self.ACQ480.FIR.DECIM == decim: time.sleep(.2)

class ao420(module,ao420_knobs):
    def sigCong(self,s1,s2,s3,s4):
        maxsize=max((s.size for s in (s1,s2,s3,s4)))
        # initial function times the maximum value (32767)
        w = [None]*4
        w[0] = (s1.flatten()*32767).astype(numpy.int16)
        w[1] = (s2.flatten()*32767).astype(numpy.int16)
        w[2] = (s3.flatten()*32767).astype(numpy.int16)
        w[3] = (s4.flatten()*32767).astype(numpy.int16)
        w = tuple(numpy.pad(v,(0,maxsize-v.size),'edge') for v in w)
        a = numpy.array(w) # columns for 4 channels
        b = a.tostring('F') # export Fortran style
        return b
    def set_gain_offset(self,ch,gain,offset):
        if gain+abs(offset)>100:
            gain   =   gain/2.
            offset = offset/2.
            self.AO.GAIN.CH[ch] = 1
        else:
            self.AO.GAIN.CH[ch] = 0
        self.set_gain(ch,gain)
        self.set_offset(ch,offset)
    def set_gain(self,ch,gain):
        gain = min(100,max(0,gain))
        self.G[ch] = int(round(gain*32767/100.))
    def set_offset(self,ch,offset):
        offset = min(100,max(-100,offset))
        self.D[ch] = int(round(offset*32767/100.))
    def loadSig(self,bitstring,rearm=False):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect((self._server[0],_ao_oneshot+int(bool(rearm))))
        sent,tosend = 0,len(bitstring)
        mv = memoryview(b(bitstring))
        try:
            sock.recv(1024)
            while sent<tosend:
                n = sock.send(mv[sent:])
                if n==0:
                    print("receiver did no accept any more bytes: still to send %d bytes"%(tosend,))
                    break
                sent += n
            sock.shutdown(socket.SHUT_WR)
            try:
                sock.settimeout(3+tosend//1000000)
                while True:
                    ans=sock.recv(1024)
                    if len(ans)==0:break
                    sock.settimeout(3)
            except Exception as e:
                print (e)
        finally:
            sock.close()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((self._server[0],_ao_oneshot_cs))
        try:
            sha1sum = sock.recv(40)
        finally:
            sock.close()
        print(sha1sum)
        '''
        if hashlib is not None:
            sha1sum = hashlib.sha1(bitstring).hexdigest()
            data = nc((self._server[0],_ao_oneshot_cs)).sock.recv(40)
            if data != sha1sum:
                raise Exception('Load Signal failed, checksum mismatch: %s != %s'%(data,sha1sum))
        '''
    def _arm(self,s1,s2,s3,s4,rearm=False):
        self.loadSig(self.sigCong(s1,s2,s3,s4),rearm)
    def _init(self,gain,offset,shot=None):
        self.chainstart()
        super(ao420,self)._init(shot)
        for i in range(4):
            self.set_gain_offset(i+1,gain[i],offset[i])
        self.chainsend()
    def _init_master(self,soft,clkdiv):
        self.chainstart()
        super(ao420,self)._init_master(0,soft)
        self.clkdiv = clkdiv
        self.EVENT1_ALL = (0,0,0)
        self.chainsend()

class acq1001s(dtacq):
    continuous_reader = _property_str('continuous_reader',1)
    diob_src = _property_str('diob_src',1)
    optimise_bufferlen = _property_str('optimise_bufferlen',1)
    driver_override  = _property_str('driver_override',1)

class mgt482(dtacq):
    _linemap = (13,12)
    _sites = set()
    _devid = 0
    def __init__(self,server='localhost',line=0):
        super(mgt482,self).__init__(server,self._linemap[line])
        self._line = line
        self._devid = line
    spad = _property_int('spad')
    @property
    def aggregator(self):
        sites = self('aggregator').split(' ')[1].split('=')[1]
        return [] if sites=='none' else [int(v) for v in sites.split(',')]
    @aggregator.setter
    def aggregator(self,sites):
        self('aggregator sites=%s'%(','.join([str(s) for s in sites])))
    def init(self,sites,devid=0):
        self.setup(sites,devid)
        self._init()
    def setup(self,sites,devid=0):
        self._sites = set() if sites is None else set(int(s) for s in sites)
        self._devid = int(devid)
    def _init(self):
        self.spad = 0
        self.aggregator = self._sites

class mgt_run_shot_logger(threading.Thread):
    """ used by mgtdram """
    _count = -1
    _pid   = None
    @property
    def error(self):
        with self._error_lock:
            return tuple(self._error)
    @property
    def pid(self):
        with self._busy_lock:
            return self._pid
    @property
    def count(self):
        with self._busy_lock:
            return self._count
    def __init__(self,host,autostart=True,debug=False,daemon=True):
        super(mgt_run_shot_logger,self).__init__(name='mgt_run_shot(%s)'%host)
        self.daemon = daemon
        self.mgt = line_logger((host,_mgt_log_port))
        self._busy_lock  = threading.Lock()
        self._error_lock = threading.Lock()
        self._error = []
        self._debug = True#bool(debug)
        if autostart: self.start()
    def debug(self,line):
        if self._debug:
            sys.stdout.write("%16.6f: ")
            sys.stdout.write(line)
            sys.stdout.flush()
    def run(self):
        re_busy  = re.compile('^BUSY pid ([0-9]+) SIG:SAMPLE_COUNT:COUNT ([0-9]+)')
        re_idle  = re.compile('^.* SIG:SAMPLE_COUNT:COUNT ([0-9]+)')
        re_error = re.compile('^ERROR: (.*)')
        for line in self.mgt.lines():
            if line is None or len(line)==0: continue
            line = s(line)
            hits = re_busy.findall(line)
            if len(hits)>0:
                pid,count = int(hits[0][0]),int(hits[0][1])
                if self._count<0 and count>0 or self._count==count: continue
                self.debug(line)
                with self._busy_lock:
                    self._count = count
                    self._pid   = pid
                continue
            hits = re_error.findall(line)
            if len(hits)>0:
                self.debug(line)
                with self._error_lock:
                    self._error.append(hits[0])
                continue
            hits = re_idle.findall(line)
            if len(hits)>0:
                count = int(hits[0])
                self.debug(line)
                with self._busy_lock:
                    self._count = count
                continue
            self.debug(line)
        if self._count==0: self._count=1
    def stop(self): self.mgt.stop()

class mgtdram(dtacq):
    class TRANS(nc):
        def __init__(self,server='localhost'):
            super(mgtdram.TRANS,self).__init__((server,_mgt_log_port))
    async = None
    def mgt_run_shot_log(self,num_blks,debug=False):
        self.mgt_run_shot(num_blks)
        return mgt_run_shot_logger(self._server[0],debug=debug)
    def __init__(self,server='localhost'):
        super(mgtdram,self).__init__(server,14)
        self.trans = self.TRANS(server)
    def mgt_offload(self,*blks):
        if   len(blks)==0: self('mgt_offload')
        elif len(blks)==1: self('mgt_offload %d'%(int(blks[0])))
        else:              self('mgt_offload %d-%d'%(int(blks[0]),int(blks[1])))
    def mgt_run_shot(self,num_blks):
        self('mgt_run_shot %d'%(int(num_blks),))
    def mgt_taskset(self,*args): self('mgt_taskset',*args)
    def mgt_abort(self): self.sock.send('mgt_abort\n')

### 3 _dtacq device classes
class _dtacq(object):
    _nc = None
    @property
    def nc(self):
        """
        Serves at the nc socket interface to the carrier/modules (lower-case classes)
        """
        if self._nc is None:
            self._nc = self._nc_class(self.setting_host)
        return self._nc
    @property
    def settings(self): return self.nc.settings
### STREAMING
class _streaming(object):
    active_ports = (0,)
    @property
    def id(self): "%s_%03d"%(self.setting_host,self.setting_shot)
    __streams = {}
    @property
    def _streams(self):
        return self._streaming__streams.get(self.id,None)
    @_streams.setter
    def _streams(self,value):
        if   isinstance(value,(set,)):
            self._streaming__streams[self.id] = value
        elif self.id in self._streaming__streams:
            self._streaming__streams.pop(self.id)
    class STREAM(threading.Thread):
        port      = 0
        devid     = 0
        triggered = False
        nSamples  = 0x10000
        def __init__(self,dev,port,share,name=None):
            if name is None:
                name = "%s(%s,%d)"%(self.__class__.__name__,dev,port)
            super(_streaming.STREAM,self).__init__(name=name)
            self._stop = threading.Event()
            self.port  = port
            self.dev   = dev
            self.share = share
        @property
        def on(self): return not self._stop.is_set()
        def stop(self): self._stop.set()
        def recv(self,sock,req_bytes,timeout=True):
            rem_bytes,ret = req_bytes,[]
            while self.on and rem_bytes>0:
                try:   buf = sock.recv(rem_bytes)
                except socket.timeout:
                    if timeout:  raise
                    if rem_bytes==req_bytes: continue
                    break
                blen = len(buf)
                if blen==0: break
                ret.append(buf)
                rem_bytes -= blen
            return req_bytes-rem_bytes,b''.join(ret)
        def run(self):
            NCHAN = self.dev.nc.NCHAN
            # bufferlen = self.dev.nc.bufferlen
            startchan,nchan = 1,NCHAN # TODO: implement custom subset
            buflen = nchan*self.nSamples*2 # should be multiple of bufferlen
            shape = (nchan,self.nSamples)
            # final setup
            self.dev.nc.OVERSAMPLING = 0 # other values would ev. skip samples
            subset = (startchan,nchan) if nchan<NCHAN else None
            self.dev.nc.STREAM_OPTS(subset=subset)
            sock = stream(self.dev._host).sock # starts stream
            try:
                read = 0
                sock.settimeout(1)
                # wait for trigger
                read,buf = self.recv(sock,buflen,False)
                if read==0: return
                self.triggered = True
                while read==buflen:
                    self.store(buf,shape,'<i2')
                    read,buf = self.recv(sock,buflen,True)
                else:# store rest
                    samples = read//nchan//2
                    if samples>0:
                        self.store(buf,(nchan,samples),'<i2')
            finally:
                sock.close()

    def arm_stream(self): pass
    def start_stream(self):
        self.nc.TRANSIENT() # TODO: necessary? take in TRANSIENT: settings
        return 0
    def stop_stream(self):
        self.nc.CONTINUOUS_stop()
    def deinit_stream(self): pass
    def streaming_arm(self):
        if not self._streams is None: raise Exception("Streams already initialized.")
        self.stop_stream()
        self.arm_stream()
        self.share = {'lock':threading.Lock()}
        streams = set([])
        for port in self.active_ports:
            streams.add(self.STREAM(self,port,self.share))
        for stream in streams:
            stream.start()
        self._streams = streams
        self.start_stream()
    def store_sites(self): pass
    def store_scale(self): pass
    def streaming_store(self):
        try: self.stop_stream()
        except: pass
        self.store_sites()
        if self._streams is None: raise Exception("INV_SETUP")
        streams = list(self._streams)
        triggered = len([None for stream in streams if stream.triggered])>0
        if triggered:
            self.store_scale()
        else:
            for stream in streams: stream.stop()
        for stream in streams: stream.join()
        self._streams = None
        self.deinit_stream()
        if not triggered: raise Exception("NOT_TRIGGERED")
    def streaming_deinit(self):
        try: self.stop_stream()
        except: pass
        if not self._streams is None:
            streams = list(self._streams)
            for stream in streams: stream.stop()
            for stream in streams: stream.join()
            self._streams = None
        self.deinit_stream()

class _mgt482(_streaming):
    _mgt = None
    @property
    def mgt(self):
        if self._mgt is None:
            self._mgt = (mgt482(self.setting_host,0),mgt482(self.setting_host,1))
        return self._mgt
    def init_mgt(self,A=None,B=None,a=0,b=1):
        self.mgt[0].setup(A,a)
        self.mgt[1].setup(B,b)
        if self.use_mgt:
            self.mgt[0]._init()
            self.mgt[1]._init()
    def get_port_name(self,port): return 'AB'[port]
    def get_sites(self,i): return self.mgt[i]._sites
    def get_devid(self,i): return self.mgt[i]._devid
    @property
    def active_ports(self): return tuple(i for i in range(2) if len(self.get_sites(i))>0)
    @property
    def use_mgt(self): return len(self.active_ports)>0
    def _blockgrp(self,i): return len(self.get_sites(i))
    @classmethod
    def get_mgt_sites(cls):
        ai = set()
        for l in cls._mgt.values():
            for s in l:
                ai.add(s)
        return tuple(ai)
    class STREAM(_streaming.STREAM):
        _folder = "/data"
        _blks_per_buf = 99
        dostore   = False
        post = -1 # for infinite
        trigger = 0
        def wait4ready(self):
            while not self._ready:
                 time.sleep(1)
        def __init__(self,dev,port,share):
            super(_mgt482.STREAM,self).__init__(dev,port,share)
            self.__init_meta__(dev,port,share)
        def __init_meta__(self,dev,port,share):
            self.devid = dev.get_devid(port)
            self.post = dev.setting_post
            self.blockgrp = dev._blockgrp(port)
            self.grp_per_buf = self._blks_per_buf//self.blockgrp
            self.chanlist = []
            num_channels = 0
            for s in dev.get_sites(port):
                off = dev._channel_offset[s-1]
                num = dev.getmodule(s)._num_channels
                self.chanlist.extend(range(off,off+num))
                num_channels += num
            self.size = (1<<22) * self.blockgrp     # _blockgrp blocks of 4MB
            self.shape = (num_channels,self.size//num_channels//2) # _ch_per_port channels of 16bit (2byte)
        def get_folder(self,buf):
            return "%s/%d/%06d"%(self._folder,self.devid,buf)
        def get_bufidx(self,idx):
            return idx//self.grp_per_buf+1,int(idx%self.grp_per_buf)*self.blockgrp
        def get_fullpath(self,idx):
            buf,idx = self.get_bufidx(idx)
            return '%s/%d.%02d'%(self.get_folder(buf),self.devid,idx)
        def get_block(self,block):
            if isinstance(block,int):
                block = self.get_fullpath(block)
            return numpy.memmap(block,dtype=numpy.int16,shape=self.shape,mode='r',order='F')
        @property
        def outdir(self): return "%s/%d"%(self._folder,self.devid)
        def run(self):
            import subprocess
            if not os.path.exists(self._folder):
                os.mkdir(self._folder)
            log = open("/tmp/mgt-stream-%d.log"%(self.devid,),'w')
            try:
                params = ['mgt-stream',str(self.devid),str(self.blockgrp)]
                self.stream = subprocess.Popen(params,stdout=log,stderr=subprocess.STDOUT)
            except:
                log.close()
                raise
            try:
                idx = 0
                fullpath = self.get_fullpath(idx)
                max_idx  = self.post//self.shape[1]
                while self.on:
                    if debug>1: dprint("waiting for %s"%fullpath)
                    if not os.path.exists(fullpath):
                        if self.stream.poll() is None:
                            time.sleep(1)
                            continue
                        else: break
                    size = os.path.getsize(fullpath)
                    if size<self.size:
                        if self.stream.poll() is None:
                            time.sleep(.1)
                            continue
                        else: break
                    if size>self.size:
                        raise Exception('file too big "%s" %dB > %dB'%(fullpath,size,self.size))
                    self.triggered = True
                    self.store(idx*self.shape[1],self.get_block(fullpath))
                    if idx%self.grp_per_buf == 0:
                        sys.stdout.write("%.3f: %s\n"%(time.time(),fullpath));sys.stdout.flush()
                    try: os.remove(fullpath)
                    except (SystemExit,KeyboardInterrupt): raise
                    except: print('Could not remove %s'%fullpath)
                    if self.post>=0 and idx>=max_idx: break
                    idx += 1
                    fullpath = self.get_fullpath(idx)
                if idx%self.grp_per_buf > 0:
                    sys.stdout.write("%.3f: %s\n"%(time.time(),fullpath));sys.stdout.flush()
            except Exception:
                import traceback
                traceback.print_exc()
            finally:
                if self.stream.poll() is None:
                    self.stream.terminate()
                    self.stream.wait()
        def store(self,i0,block):
            #import matplotlib.pyplot as pp
            dt = self.dev.get_dt()
            i1 = i0+block.shape[1]-1
            trigger = int(self.dev.setting_trigger)
            dim = numpy.array(range(i0,i1+1))*dt+trigger
            for i,idx in enumerate(self.chanlist):
                ch = idx+1
                raw = self.dev.getchannel(ch)
                if not raw.on: continue
                print(dim[0],dim[-1],block[i])
                #if i == 0:
                #    pp.plot(dim,block[i])
                #    pp.show()
    def store_sites(self):
        for site in self._active_mods:
            self.getmodule(site).store()
        self._master.store_master()
    def store_scale(self):
        ESLO,EOFF=self.data_scales,self.data_offsets
        for idx in range(self._num_channels):
            ch = idx+1
            node = self.getchannel(ch)
            if node.on:
                print("x * %g + %g"%(ESLO[idx],EOFF[idx]))
    def arm_stream(self):
        self.nc.STREAM_OPTS(nowhere=True)
        self.nc.OVERSAMPLING=0
        ERR = os.system('mgt-arm')
        if ERR !=0: print("ERROR %d during mgt-arm"%(ERR,))
    def deinit_stream(self):
        devs = [str(self.get_devid(port)) for port in range(2)]
        cmd = 'mgt-deinit %s'%(','.join(devs),)
        ERR = os.system(cmd)
        if ERR !=0: print("ERROR %d during %s"%(ERR,cmd))
    def start_stream(self):
        super(_mgt482,self).start_stream()
        self.nc.CONTINUOUS_start()
        t = 15
        while int(('0'+self.nc('state')).split(' ',1)[0])<1:
            t -= 1
            if t<=0: break
            time.sleep(1)

    def _arm_mgt(self):    self.streaming_arm()
    def _store_mgt(self):  self.streaming_store()
    def _deinit_mgt(self): self.streaming_deinit()

class _carrier(_dtacq):
    """
    Class that can set the various knobs (PVs) of the D-TACQ module. PVs are set from the user tree-knobs.
    """
    is_test = True
    setting_host = 'dtacq'
    setting_trigger = 0
    setting_trigger_edge = 'rising'
    setting_clock_src = None
    setting_clock = 1000000
    setting_shot = 0
    setting_pre = 0
    setting_post = 0
    ai_sites = None
    ao_sites = None
    def __init__(self,host='dtacq',**kw):
        self.setting_host = host
        for fun,args in kw.items():
            if not fun.startswith('setup_'): continue
            if not hasattr(self,fun): continue
            setup = getattr(self,fun)
            if not callable(setup): continue
            setup(*args)
    _nc_class = carrier
    @property
    def nc(self):
        """
        Serves at the nc socket interface to the carrier/modules (lower-case classes)
        """
        if self._nc is None:
            self._nc = self._nc_class(self.setting_host)
        return self._nc
    @property
    def simulate(self): return self._master.nc.simulate
    @simulate.setter
    def simulate(self,val): self._master.nc.simulate = val
    @property
    def _default_clock(self): self._master._default_clock
    @property
    def is_ext_clk(self): return self.setting_clock_src is not None
    @property
    def clock_ref(self): return self.setting_clock
    @classmethod
    def setup(cls,module,num_modules=1,mgt=None):
        cls.setup_class(cls,module,num_modules,mgt)
    @staticmethod
    def setup_class(cls,module,num_modules=1,mgt=None):
        cls.module_class = module
        cls.num_modules = num_modules
        if module._is_ai:
            def trigger_pre(self): return self.setting_pre
            cls.trigger_pre = property(trigger_pre)
            def trigger_post(self): return self.setting_post
            cls.trigger_post = property(trigger_post)
            cls.arm   = cls._arm_acq
            cls.store = cls._store_acq
            cls.deinit= cls._deinit_acq
        else: # is ao420
            cls.ao_sites = range(1,cls.num_modules+1)
            cls.arm = cls._arm_ao
        cls._num_channels = 0
        cls._channel_offset = []
        for m in range(1,cls.num_modules+1):
            cls._channel_offset.append(cls._num_channels)
            def getmodule(self): return self.getmodule(m)
            setattr(cls,'module%d'%(m), property(getmodule))
            cls._num_channels += module._num_channels
    @property
    def max_clk(self): return self._master.max_clk
    __active_mods = None
    @property
    def _active_mods(self):
        if self.__active_mods is None:
            self.__active_mods  = tuple(i for i in self.modules if self.getmodule(i).on)
        return self.__active_mods
    @property
    def modules(self): return range(1,self.num_modules+1)
    __optimal_sample_chunk = None
    @property
    def _optimal_sample_chunk(self):
        if self.__optimal_sample_chunk is None:
            self.__optimal_sample_chunk  = self.nc.bufferlen//self.nc.nchan//2
        return self.__optimal_sample_chunk
    @property
    def _num_active_mods(self): return len(self._active_mods)
    def _channel_port_offset(self,site):
        offset = 0
        for i in self.modules:
            if i == site: break
            offset += self.getmodule(i)._num_channels
        return offset
    def getmodule(self,site):
        return self.module_class(self,site=site)
    def getchannel(self,idx,*suffix):
        site = (idx-1)//self.module_class._num_channels+1
        ch   = (idx-1)% self.module_class._num_channels+1
        return self.getmodule(site).getchannel(ch,*suffix)
    @property
    def _master(self): #1st module should always be present
        return self.getmodule(1)
    @property
    def state(self): return self.nc.state['state']
    def _slice(self,ch): return slice(None,None,1)
    def soft_trigger(self):
        """ sends out a trigger on the carrier's internal trigger line (d1) """
        self.nc.soft_trigger()
    def reboot(self):
        self.nc.reboot()
    def init(self,ext_clk=None,clock=1000000,pre=0,post=1<<20,soft_out=False,di=1):
        dtacq.add_cache(self.setting_host)
        self.setting_clock = int(clock)
        self.setting_clock_src = ext_clk
        self.setting_pre  = int(pre)
        self.setting_post = int(post)
        self._master.setting_soft_out = bool(soft_out)
        self._init()
        self.commands = json.dumps(dtacq.remove_cache(self.setting_host))

    def _init(self):
        """ initialize all device settings """
        ext = self.is_ext_clk
        mb_fin = self.setting_clock_src if ext else _zclk_freq
        clock = self.setting_clock
        mb_set = self._master.getMB_SET(clock)
        soft_out = self._master.setting_soft_out
        post,pre = self.setting_post,self.setting_pre
        threads = [threading.Thread(target=self.nc._init, args=(ext,mb_fin,mb_set,pre,post,soft_out,self._demux,self.setting_shot))]
        for i in self._active_mods:
            threads.append(self.getmodule(i).init_thread())
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self._master.init_master(pre,self.is_test,int(mb_set/clock))
        if debug: dprint('Device is initialized with modules %s'%str(self._active_mods))
    def _arm_acq(self,timeout=50):
        """ arm the device for acq modules """
        timeout = int(timeout)
        return self.nc.wait4arm(timeout)
    def _arm_ao(self,data={},rearm=False):
        """ arm the device for ao modules """
        for i in self._active_mods:
            self.getmodule(i).arm(data.get(i,{}),rearm=rearm)
    def _store_acq(self,abort=False):
        if debug: dprint('store_bulk')
        for site in self._active_mods:
            self.getmodule(site).store()
        self._master.store_master()
        for i in range(5):
            state = self.state
            if not (state == STATE.ARM or state == STATE.PRE):
                break
            time.sleep(1)
        else:
            return False
        if abort:
            self.nc.wait4abort()
        else:
            self.nc.wait4post(self.setting_post)
            self.nc.wait4state(STATE.STOP)
        if self._demux:
            if self._master._es_enable:
                self._transfer_demuxed_es()
            else:
                self._transfer_demuxed()
        else:
            self._transfer_raw()
        return True
    @property
    def data_scales(self): return numpy.concatenate([self.getmodule(i).data_scales  for i in self.modules])
    @property
    def data_offsets(self): return numpy.concatenate([self.getmodule(i).data_offsets for i in self.modules])
    class _Downloader(threading.Thread):
        def __init__(self,dev,chanlist,lock,queue):
            super(_carrier._Downloader,self).__init__()
            self.nc    = dev.nc
            self.list  = chanlist
            self.lock  = lock
            self.queue = queue
        def run(self):
            while True:
                with self.lock:
                    if len(self.list)==0: break
                    ch = self.list.iterkeys().next()
                    slice,on = self.list.pop(ch)
                raw = None
                if on:
                    try:
                        raw = self.nc.channel(ch).raw(slice)
                    except (SystemExit,KeyboardInterrupt): raise
                    except:
                        import traceback
                        traceback.print_exc()
                self.queue.put((ch,raw,on))
    def _get_chanlist(self):
        """ returns a list of available channels with their corresponding module """
        nchan = self._num_channels
        chanlist = {}
        for ch in range(1,nchan+1):
            chanlist[ch] = (self._slice(ch),self.getchannel(ch).on)
        return (chanlist,Queue(nchan))
    def _start_threads(self,chanlist,queue):
        """ starts up to 8 threads for pulling the data """
        lock = threading.Lock()
        threads = []
        for t in range(2):
            threads.append(self._Downloader(self,chanlist,lock,queue))
        for t in threads: t.start()
        return threads

    def get_dt(self): return 1000000000/self.setting_clock
    def _get_dim_slice(self,i0,start,end,pre,mcdf=1):
        """ calculates the time-vector based on clk-tick t0, dt in ns, start and end """
        first= int(i0-pre)
        dt = self.get_dt()
        trg= self.setting_trigger
        def dmx(i):
            return int(i*dt+trg)
        def dim(first,last):
            for i in range(first,last+1):
                yield dmx(i)
        return slice(start,end),first,dim,dmx
    def _store_channels_from_queue(self,dims_slice,queue):
        """
        stores data in queue and time_vector to tree with linked segments
        blk:   list range of the data vector
        dim:   dimension to the data defined by blk
        queue: dict of ch:raw data
        """
        import matplotlib.pyplot as pp
        chunksize = 1<<18
        ESLO,EOFF=self.data_scales,self.data_offsets
        for i in range(queue.maxsize):
            ch,value,on = queue.get()
            if value is None or not on: continue
            node = self.getchannel(ch)
            scale = lambda x: x*ESLO[ch-1]+EOFF[ch-1]
            for slc,start,dimfun,dmx in dims_slice:
                val = value[slc]
                dlen = val.shape[0]
                for seg,is0 in enumerate(range(0,dlen,chunksize)):
                    is1 = min(is0+chunksize,dlen)-1
                    i0,i1 = i00+is0,i00+is1
                    dim,dm0,dm1 = dimfun(i0,i1),dmx(i0),dmx(i1)
                    if debug>1: dprint("segment (%7.1fms,%7.1fms)"%(dm0/1e6,dm1/1e6))
                    print((node.idx,scale(val[is0]),dm0,dm1,ESLO[ch-1],EOFF[ch-1],dim,val[is0:is1+1].shape))
                    if ch == 1:
                        pp.plot(list(dim),val[is0:is1+1])
                        pp.show()
    def _transfer_demuxed_es(self):
        """ grabs the triggered channels, opens a socket and reads out data """
        if debug: dprint('transfer_demuxed_es')
        chanlist,queue = self._get_chanlist()
        def findchaninlist(slc,skip=0):
            channels = range(1,len(chanlist)+1)[slc][skip:]
            for n in channels:
                if n in chanlist: return n
            return channels[0]
        ## 1&2 sample index, 5&6 clock count TODO: how to do clock count in 4CH mode of 480
        lo = findchaninlist(_es_marker.count_l)  #5
        hi = findchaninlist(_es_marker.count_h)  #6
        s0 = findchaninlist(_es_marker.static,0) #3
        s1 = findchaninlist(_es_marker.static,1) #7
        if s0 == s1: s0 = 4
        def get_and_queue_put(ch):
            slice,on = chanlist.pop(ch)
            raw = self.nc.channel(ch).raw(slice)
            queue.put((ch,raw,on))
            return raw
        loa = get_and_queue_put(lo)
        hia = get_and_queue_put(hi)
        s0a = get_and_queue_put(s0)
        s1a = get_and_queue_put(s1)
        threads = self._start_threads(chanlist,queue)
        mask = (s0a==_es_marker.int16.static)&(s1a==_es_marker.int16.static)
        index = numpy.nonzero(mask)[0].astype('int32').tolist()+[loa.shape[0]-1]
        loa = loa[mask].astype('uint16').astype('uint32')
        hia = hia[mask].astype('uint16').astype('uint32')
        fpga,skip= self._master._clkdiv_fpga,self._master._skip
        tt0 = (loa+(hia<<16))//fpga
        tt0 = (tt0-tt0[0]).tolist()
        pre = self.setting_pre
        # i0+skip to shift time vector as well, index[i]+1 to skip marker
        dims_slice = [self._get_dim_slice(i0,index[i]+1+skip,index[i+1],pre) for i,i0 in enumerate(tt0)]
        self._store_channels_from_queue(dims_slice,queue)
        for t in threads: t.join()
    def _transfer_demuxed(self):
        """ grabs the triggered channels, opens a socket and reads out data """
        if debug: dprint('transfer_demuxed')
        chanlist,queue = self._get_chanlist()
        threads = self._start_threads(chanlist,queue)
        pre = self.setting_pre
        dlen = pre+self.setting_post
        dims_slice = [self._get_dim_slice(0,self.get_dt(),0,dlen,pre)]
        self._store_channels_from_queue(dims_slice,queue)
        for t in threads: t.join()
    def _deinit_acq(self):
        """ abort and go to idle """
        self.nc.wait4abort(30)


class _acq1001(_carrier):
    """
    To be used for items specific to the ACQ2106 carrier
    """
    _nc_class = acq1001
    _demux = 1

class _acq2106(_carrier,_mgt482):
    """
    To be used for items specific to the ACQ2106 carrier
    """
    _nc_class = acq2106
    @property
    def _demux(self): return 0 if self.use_mgt else 1
    def _arm_acq(self,*a,**kw):
        if self.use_mgt:
            self._arm_mgt(*a,**kw)
        else:
            super(_acq2106,self)._arm_acq(*a,**kw)
    def _store_acq(self,*a,**kw):
        if self.use_mgt:
            self._store_mgt(*a,**kw)
        else:
            super(_acq2106,self)._store_acq(*a,**kw)
    def _deinit_acq(self,*a,**kw):
        if self.use_mgt:
            self._deinit_mgt(*a,**kw)
        else:
            super(_acq2106,self)._deinit_acq(*a,**kw)
    def calc_Mclk(self,clk,maxi,mini,decim):
        """
        Calculates the Mclk based off the user-specified clock, and the available filter decim values.
        To be used for future check/automatic Mclk calculation functionality
        """
        dec = 2**int(numpy.log2(maxi/clk))
        Mclk = clk*dec
        if (dec < min(decim) or dec > max(decim)) or (Mclk < mini or Mclk > maxi):
            raise ValueError('Impossible clock value, try another value in range [1.25, %d] MHz'%int(maxi/1e6))
        return int(Mclk),int(dec)

    def check(self):
        for mod in self._active_mods:
            try:
                if self.getmodule(mod).nc.ACQ480.FIR[1] != self.getmodule(mod+1).nc.ACQ480.FIR[1]:
                    print('INCORRECT DECIMATION VALUES')
            except (SystemExit,KeyboardInterrupt): raise
            except: pass

    def arm(self,timeout=50):
        try:   super(_acq2106,self).arm(timeout)
        except:
            if self.nc.SYS.CLK.LOL: sys.stderr.write('MCLK: Loss Of Lock!\n')
            raise

class _module(_dtacq):
    """
    MDSplus-dependent superclass covering Gen.4 D-tAcq module device types. PVs are set from the user tree-knobs.
    """
    _nc = None
    _nc_class = module
    _clkdiv_fpga = 1
    _skip = 0
    _es_enable = False
    _init_done = False
    setting_soft_out = False
    on = True
    @classmethod
    def setup(cls):
        cls.setup_class(cls)
    @staticmethod
    def setup_class(cls):
        for ch in range(1,cls._num_channels+1):
            class channelx(cls._channel_class):
                on = True
                idx = ch
            setattr(cls,"channel%02d"%ch,channelx)
    def __init__(self,parent,site):
        self.parent = parent
        self.site = site
        self._init_done = True
    def getchannel(self,ch,*suffix):
        chan = getattr(self,"channel%02d"%ch)
        if len(suffix)==0: return chan
        return getattr(chan,'_'.join(suffix))
    """ Most important stuff at the top """
    @property
    def max_clk(self): return self._max_clk
    @property
    def _default_clock(self): return self.max_clk
    @property
    def nc(self):
        """
        Interfaces directly through the DTACQ nc ports to send commands.
        """
        if self._nc is None:
            self._nc = self._nc_class(self._host,self.site)
        return self._nc
    @property
    def is_master(self): return self.site == 1
    def channel(self,ch,*args):
        """
        Helper to get arguments from individual channel subnodes (e.g. channel_c%02d_argument)
        """
        return getattr(getattr(self,'channel%02d'%ch),'_'.join((args)))
    @property
    def data_scales(self):  return self.nc.data_scales
    @property
    def data_offsets(self): return self.nc.data_offsets
    @property
    def _carrier(self): return self.parent # Node that points to host carrier nid
    @property
    def _trigger(self): return self._carrier._trigger
    __host=None
    @property
    def _host(self):
        if self.__host is None: self.__host = self._carrier.setting_host
        return self.__host
    @property
    def state(self): return self._carrier.state
    @property
    def setting_pre(self): return int(self._carrier.setting_pre)
    @property
    def setting_post(self):     return int(self._carrier._post)
    @property
    def max_clk_in(self): return self.getMB_SET(self.max_clk)
    """ Action methods """
    def init(self):
        self.nc._init(*self.init_args)
    def init_thread(self):
        return threading.Thread(target=self.nc._init,args=self.init_args)

class _acq425(_module):
    """
    D-tAcq ACQ425ELF 16 channel transient recorder
    http://www.d-tacq.com/modproducts.shtml
    """
    _is_ai = True
    _nc_class = acq425
    _num_channels = 16
    _max_clk = 2000000
    _default_clock = 1000000
    class _channel_class(object):
        gain = 1
    def setting_gain(self,i): return self.getchannel(i,'gain')
    def getMB_SET(self,clock): return 50000000
    """ Action methods """
    @property
    def init_args(self):
        return ([self.setting_gain(ch) for ch in range(1,self._num_channels+1)],self._carrier.setting_shot)
    def init_master(self,pre,soft,clkdiv):
        self.nc._init_master(pre,soft,clkdiv)
    def store(self):pass
    def store_master(self):pass
_acq425.setup()

class _acq480(_module):
    """
    D-tAcq ACQ480 8 channel transient recorder
    http://www.d-tacq.com/modproducts.shtml
    """
    _is_ai = True
    _nc_class = acq480
    _num_channels = 8
    class _channel_class:
        gain = 100
        invert = False
        hpf = 0
        lfns = 0
        t50r = False

    @property
    def max_clk(self):     return self.nc._max_clk_dram(self.parent.num_modules)
    @property
    def _es_enable(self):   return self.nc.es_enable
    @property
    def _clkdiv_adc(self):  return self.nc._clkdiv_adc(self.setting_fir)
    @property
    def _clkdiv_fpga(self): return self.nc._clkdiv_fpga
    @property
    def _soft_out(self):    return self.setting_soft_out or 0<self.nc._trig_mode(self.setting_trig_mode)
    @property
    def _skip(self):        return self.nc.get_skip()

    setting_trig_mode = 0
    setting_trig_mode_translen = 1048576
    setting_fir = 0

    def getMB_SET(self,clock):
        return self.nc._clkdiv(self.setting_fir)*clock
    @property
    def init_args(self):
        return (
            [self.getchannel(ch,'gain')   for ch in range(1,self._num_channels+1)],
            [self.getchannel(ch,'invert') for ch in range(1,self._num_channels+1)],
            [self.getchannel(ch,'hpf')    for ch in range(1,self._num_channels+1)],
            [self.getchannel(ch,'lfns')   for ch in range(1,self._num_channels+1)],
            [self.getchannel(ch,'t50r')   for ch in range(1,self._num_channels+1)],
            self.parent.setting_shot)
    def init_master(self,pre,soft,clkdiv):
        self.nc._init_master(pre,soft,self.setting_trig_mode,self.setting_trig_mode_translen,self.setting_fir)
        fir  = self.nc.ACQ480.FIR.DECIM
        fpga = self.nc.ACQ480.FPGA.DECIM
        self.clkdiv_fir  = fir
        self.clkdiv_fpga = fpga
        #check clock#
        clk = self._carrier.setting_clock
        if clk*fpga < 10000000:
            raise Exception('Bus clock must be at least 10MHz')
        clk_adc = clk*fpga*fir
        if clk_adc > 80000000:
            raise Exception('ADC clock cannot exceed 80MHz: is %g = %g * %g * %g'%(clk_adc,clk,fpga,fir))

    def store(self): pass
    def store_master(self): pass

    """Channel settings"""
    def setting_invert(self,ch): return int(self.getchannel(ch,'invert'))
    def setting_setInvert(self,ch):
        self.nc.ACQ480.INVERT[ch] = self.setting_invert(ch)
    def setting_gain(self,ch): return int(self.getchannel(ch,'gain'))
    def setting_setGain(self,ch):
        self.nc.ACQ480.GAIN[ch] = self.setting_gain(ch)
    def setting_hpf(self,ch): return int(self.getchannel(ch,'hpf'))
    def setting_setHPF(self,ch):
        self.nc.ACQ480.HPF[ch] = self.setting_hpf(ch)
    def setting_lfns(self,ch): return int(self.getchannel(ch,'lfns'))
    def _setLFNS(self,ch):
        self.nc.ACQ480.LFNS[ch] = self.setting_lfns(ch)
    def setting_t50r(self,ch): return int(self.getchannel(ch,'t50r'))
_acq480.setup()

class _ao420(_module):
    _is_ai = False
    _max_clk = 1000000
    _nc_class = ao420
    _num_channels = 4
    class _channel_class:
        value = None
        gain = 100
        offset = 0

    def getMB_SET(self,clock): return 50000000

    def _channel(self,i): return self.getchannel(i)
    def arm(self,data,rearm=False):
        #self.setting_rearm = rearm
        for i,d in data.items():
            self._channel(i).value = d
        self._arm()
    def _arm(self):
        args = [self._channel(i).value for i in range(1,self._num_channels+1)]
        args = [(numpy.array([0]) if a is None else a) for a in args]
        #kw = {'rearm':self.setting_rearm} # to unset rearm you need to reboot
        self.nc._arm(*args) # ,**kw
    @property
    def init_args(self):
        return (
            [self.getchannel(ch,'gain')   for ch in range(1,self._num_channels+1)],
            [self.getchannel(ch,'offset') for ch in range(1,self._num_channels+1)],
            self._carrier.setting_shot)
    def init_master(self,pre,soft,clkdiv):
        self.nc._init_master(soft,clkdiv)
_ao420.setup()


### 4 assemblies: carrier_module

class acq1001_acq425(_acq1001):pass
acq1001_acq425.setup(_acq425)

class acq1001_acq480(_acq1001):pass
acq1001_acq480.setup(_acq480)

class acq1001_ao420(_acq1001):pass
acq1001_ao420.setup(_ao420)

class acq2106_acq425x1(_acq2106):pass
acq2106_acq425x1.setup(_acq425,1)
class acq2106_acq425x2(_acq2106):pass
acq2106_acq425x2.setup(_acq425,2)
class acq2106_acq425x3(_acq2106):pass
acq2106_acq425x3.setup(_acq425,3)
class acq2106_acq425x4(_acq2106):pass
acq2106_acq425x4.setup(_acq425,4)
class acq2106_acq425x5(_acq2106):pass
acq2106_acq425x5.setup(_acq425,5)
class acq2106_acq425x6(_acq2106):pass
acq2106_acq425x6.setup(_acq425,6)

class acq2106_acq480x1(_acq2106):pass
acq2106_acq480x1.setup(_acq480,1)
class acq2106_acq480x2(_acq2106):pass
acq2106_acq480x2.setup(_acq480,2)
class acq2106_acq480x3(_acq2106):pass
acq2106_acq480x3.setup(_acq480,3)
class acq2106_acq480x4(_acq2106):pass
acq2106_acq480x4.setup(_acq480,4)
class acq2106_acq480x5(_acq2106):pass
acq2106_acq480x5.setup(_acq480,5)
class acq2106_acq480x6(_acq2106):pass
acq2106_acq480x6.setup(_acq480,6)


def test_without_mds():
    ai,ao = None,None
    try:
        post = (1<<15)*10
        sin = numpy.sin(numpy.linspace(0,numpy.pi*2,post))/5
        cos = numpy.sin(numpy.linspace(0,numpy.pi*2,post))/5
        #from LocalDevices.acq4xx import acq1001_ao420,acq2106_mgtx2_acq480x2
        ao=acq1001_ao420('192.168.44.254')
        #ai=acq2106_acq480x1('192.168.44.255')
        ai=acq2106_acq425x2('192.168.44.255')
        ai.init_mgt(A=[1])
        ao.init(post=post,clock=1000000)
        ai.init(pre=0,post=1000000,clock=1e6)
        #ai._master.nc.simulate = 0
        ai.arm()
        ao.arm({1:{1:sin,2:cos,3:-sin,4:-cos}})
        ai.soft_trigger()
        ao.soft_trigger()
        time.sleep(3)
        ai.store()
        ai.deinit()
    except:
        import traceback
        traceback.print_exc()
    return ai,ao

try: import MDSplus
except:
    ai,ao = test_without_mds()
else:
###-----------------
### MDSplus property
###-----------------
 class mdsrecord(object):
    """ A class for general interaction with MDSplus nodes
    obj._trigger = mdsrecord('trigger',float)
    obj._trigger = 5   <=>   obj.trigger.record = 5
    a = obj._trigger   <=>   a = float(obj.trigger.record.data())
    """
    def __get__(self,inst,cls):
        try:
            data = inst.__getattr__(self._name).record.data()
        except MDSplus.mdsExceptions.TreeNODATA:
            if len(self._default)>0:
                return self._default[0]
            raise
        if self._fun is None: return data
        return self._fun(data)
    def __set__(self,inst,value):
        inst.__getattr__(self._name).record=value
    def __init__(self,name,fun=None,*default):
        self._name = name
        self._fun  = fun
        self._default = default

###------------------------
### Private MDSplus Devices
###------------------------
 class _STREAMING(_streaming):
    class STREAM(_streaming.STREAM):
        def __init__(self,dev,port,share,name=None):
            _streaming.STREAM.__init__(self,dev,port,share,name)
            self.dev = self.dev.copy()
    def streaming_store(self):
        try: self.stop_stream()
        except: pass
        self.store_sites()
        if self._streams is None: raise MDSplus.DevINV_SETUP
        streams = list(self._streams)
        triggered = len([None for stream in streams if stream.triggered])>0
        if triggered:
            self.store_scale()
        else:
            for stream in streams: stream.stop()
        for stream in streams: stream.join()
        self._streams = None
        self.deinit_stream()
        if not triggered: raise MDSplus.DevNOT_TRIGGERED

 class _MDS_EXPRESSIONS(object):
    def get_dt(self,clk=None):
        if clk is None: clk = self.clock
        return MDSplus.DIVIDE(MDSplus.Int64(1e9),clk)
    def get_dim(self,i0=None,i1=None,trg=None,clk=None):
        if trg is None: trg = self.trigger
        dt = self.get_dt(clk)
        return MDSplus.Dimension(MDSplus.Window(i0,i1,trg),MDSplus.Range(None,None,dt))
    @staticmethod
    def update_dim(dim,i0,i1):
        dim[0][0],dim[0][1]=i0,i1
    def get_dmx(self,i0=None,trg=None,clk=None):
        if trg is None: trg = self.trigger
        dt = self.get_dt(clk)
        return MDSplus.ADD(MDSplus.MULTIPLY(i0,dt),trg)
    @staticmethod
    def update_dmx(dmx,i0):
        dm0[0][1] = i0
    @staticmethod
    def get_i1(i0,length): return i0+length-1
    def get_dim_set(self,i0=None,i1=None,trg=None,clk=None):
        return self.get_dim(i0,i1,trg,clk),self.get_dmx(i0,trg,clk),self.get_dmx(i1,trg,clk)
    @staticmethod
    def update_dim_set(dim,dm0,dm1,i0,i1):
        dim[0][0],dim[0][1]=i0,i1
        dm0[0][0],dm1[0][1]=i0,i1
    @staticmethod
    def get_scale(slope,offset):
        return MDSplus.ADD(MDSplus.MULTIPLY(MDSplus.dVALUE(),slope),offset)

 class _MGT482(_STREAMING,_MDS_EXPRESSIONS,_mgt482):
    parts = [
      {'path': '.MGT',             'type': 'structure', 'options': ('no_write_shot',)},
      {'path': '.MGT.A',           'type': 'structure', 'options': ('no_write_shot',)},
      {'path': '.MGT.A:SITES',     'type': 'numeric',   'options': ('no_write_shot',), 'help':'Sites streamed via lane A'},
      {'path': '.MGT.A:DEVICE_ID', 'type': 'numeric', 'valueExpr':'Int32(0)', 'options': ('no_write_shot','write_once'), 'help':"Host's device id for lane A"},
      {'path': '.MGT.B',           'type': 'structure', 'options': ('no_write_shot',)},
      {'path': '.MGT.B:SITES',     'type': 'numeric',   'options': ('no_write_shot',), 'help':'Sites streamed via lane B'},
      {'path': '.MGT.B:DEVICE_ID', 'type': 'numeric', 'valueExpr':'Int32(1)', 'options': ('no_write_shot','write_once'), 'help':"Host's device id for lane B"},
    ]
    _mgt_a_sites = mdsrecord('mgt_a_sites',tuple,tuple())
    _mgt_b_sites = mdsrecord('mgt_b_sites',tuple,tuple())
    _mgt_a_device_id = mdsrecord('mgt_a_device_id',int,0)
    _mgt_b_device_id = mdsrecord('mgt_b_device_id',int,1)
    def get_sites(self,i): return self._mgt_a_sites if i==0 else self._mgt_b_sites
    def get_devid(self,i): return self._mgt_a_device_id if i==0 else self._mgt_b_device_id
    class STREAM(_STREAMING.STREAM,_mgt482.STREAM):
        def __init__(self,dev,port,share):
            super(_MGT482.STREAM,self).__init__(dev,port,share)
            _mgt482.STREAM.__init_meta__(self,dev,port,share)
        def store(self,i0,block):
            i1 = self.dev.get_i1(i0,block.shape[1])
            dim,dm0,dm1 = self.dev.get_dim_set(i0,i1)
            for i,idx in enumerate(self.chanlist):
                ch = idx+1
                raw = self.dev.getchannel(ch)
                if not raw.on: continue
                raw.makeSegment(dm0,dm1,dim,block[i])
    def store_scale(self):
        ESLO,EOFF=self.data_scales,self.data_offsets
        for idx in range(self._num_channels):
            ch = idx+1
            node = self.getchannel(ch)
            if node.on:
                node.setSegmentScale(self.get_scale(ESLO[idx],EOFF[idx]))

 class _CARRIER(MDSplus.Device,_MDS_EXPRESSIONS,_carrier):
    """
    Class that can set the various knobs (PVs) of the D-TACQ module. PVs are set from the user tree-knobs.
    """
    parts = [
      {'path': ':ACTIONSERVER',                'type': 'TEXT',    'options':('no_write_shot','write_once')},
      {'path': ':ACTIONSERVER:INIT',           'type': 'ACTION',  'options':('no_write_shot','write_once'), 'valueExpr':'Action(node.DISPATCH,node.TASK)'},
      {'path': ':ACTIONSERVER:INIT:DISPATCH',  'type': 'DISPATCH','options':('no_write_shot','write_once'), 'valueExpr':'Dispatch(head.actionserver,"INIT",31)'},
      {'path': ':ACTIONSERVER:INIT:TASK',      'type': 'TASK',    'options':('no_write_shot','write_once'), 'valueExpr':'Method(None,"init",head)'},
      {'path': ':ACTIONSERVER:ARM',            'type': 'ACTION',  'options':('no_write_shot','write_once'), 'valueExpr':'Action(node.DISPATCH,node.TASK)'},
      {'path': ':ACTIONSERVER:ARM:DISPATCH',   'type': 'DISPATCH','options':('no_write_shot','write_once'), 'valueExpr':'Dispatch(head.actionserver,"INIT",head.actionserver_init)'},
      {'path': ':ACTIONSERVER:ARM:TASK',       'type': 'TASK',    'options':('no_write_shot','write_once'), 'valueExpr':'Method(None,"arm",head)'},
      {'path': ':ACTIONSERVER:SOFT_TRIGGER',          'type': 'ACTION',  'options':('no_write_shot','write_once','disabled'), 'valueExpr':'Action(node.DISPATCH,node.TASK)'},
      {'path': ':ACTIONSERVER:SOFT_TRIGGER:DISPATCH', 'type': 'DISPATCH','options':('no_write_shot','write_once'), 'valueExpr':'Dispatch(head.actionserver,"PULSE",1)'},
      {'path': ':ACTIONSERVER:SOFT_TRIGGER:TASK',     'type': 'TASK',    'options':('no_write_shot','write_once'), 'valueExpr':'Method(None,"soft_trigger",head)'},
      {'path': ':ACTIONSERVER:REBOOT',         'type': 'TASK',    'options':('write_once',), 'valueExpr':'Method(None,"reboot",head)'},
      {'path': ':COMMENT',        'type': 'text'},
      {'path': ':HOST',           'type': 'text',     'value': 'localhost',   'options': ('no_write_shot',)}, # hostname or ip address
      {'path': ':TRIGGER',        'type': 'numeric',  'valueExpr':'Int64(0)', 'options': ('no_write_shot',)},
      {'path': ':TRIGGER:EDGE',   'type': 'text',     'value': 'rising',      'options': ('no_write_shot',)},
      {'path': ':CLOCK_SRC',      'type': 'numeric',  'valueExpr':'head.clock_src_zclk','options': ('no_write_shot',), 'help':"reference to ZCLK or set FPCLK in Hz"},
      {'path': ':CLOCK_SRC:ZCLK', 'type': 'numeric',  'valueExpr':'Int32(33.333e6).setHelp("INT33M")','options': ('no_write_shot',), 'help':'INT33M'},
      {'path': ':CLOCK',          'type': 'numeric',  'valueExpr':'head._default_clock', 'options': ('no_write_shot',)},
      {'path': ':COMMANDS',       'type': 'text', 'options':('no_write_model','write_once')},
    ]
    @classmethod
    def setup(cls,module,num_modules=1,mgt=None):
        cls.setup_class(cls,module,num_modules,mgt)
    @staticmethod
    def setup_class(cls,module,num_modules=1,mgt=None):
        _carrier.setup_class(cls,module,num_modules,mgt)
        if module._is_ai:
            cls.parts = cls.parts + [
                {'path': ':ACTIONSERVER:STORE',          'type': 'ACTION',  'options':('no_write_shot','write_once'), 'valueExpr':'Action(node.DISPATCH,node.TASK)'},
                {'path': ':ACTIONSERVER:STORE:DISPATCH', 'type': 'DISPATCH','options':('no_write_shot','write_once'), 'valueExpr':'Dispatch(head.actionserver,"STORE",51)'},
                {'path': ':ACTIONSERVER:STORE:TASK',     'type': 'TASK',    'options':('no_write_shot','write_once'), 'valueExpr':'Method(None,"store",head)'},
                {'path': ':ACTIONSERVER:DEINIT',         'type': 'ACTION',  'options':('no_write_shot','write_once'), 'valueExpr':'Action(node.DISPATCH,node.TASK)'},
                {'path': ':ACTIONSERVER:DEINIT:DISPATCH','type': 'DISPATCH','options':('no_write_shot','write_once'), 'valueExpr':'Dispatch(head.actionserver,"DEINIT",31)'},
                {'path': ':ACTIONSERVER:DEINIT:TASK',    'type': 'TASK',    'options':('no_write_shot','write_once'), 'valueExpr':'Method(None,"deinit",head)'},
                {'path': ':TRIGGER:PRE',    'type': 'numeric',  'value': 0,             'options': ('no_write_shot',)},
                {'path': ':TRIGGER:POST',   'type': 'numeric',  'value': 100000,        'options': ('no_write_shot',)},
            ]
            cls.setting_pre  = mdsrecord('trigger_pre',int)
            cls.setting_post = mdsrecord('trigger_post',int)
        else: # is AO420
            cls.parts = list(_CARRIER.parts)
            cls.setting_pre  = 0
            cls.setting_post = 0
        for i in range(num_modules):
            prefix = ':MODULE%d'%(i+1)
            cls.parts.append({'path': prefix, 'type':'text', 'value':module.__name__[1:], 'options': ('write_once',)})
            module._addModuleKnobs(cls,prefix,i)
            if i==0: module._addMasterKnobs(cls,prefix)

    @property
    def is_test(self): return self.actionserver_soft_trigger.on
    @property
    def is_ext_clk(self):
        src = self.clock_src.record
        return not (isinstance(src,MDSplus.TreeNode) and src.nid==self.clock_src_zclk.nid)
    def getmodule(self,site):
        return self.module_class(self.part_dict["module%d"%site]+self.head.nid,self.tree,self,site=site)
    __host = None
    @property
    def setting_host(self):
        if self.__host is None:
            try:
                host = str(self.host.data())
            except (SystemExit,KeyboardInterrupt): raise
            except Exception as ex:
                raise MDSplus.DevNO_NAME_SPECIFIED(str(ex))
            if len(host) == 0:
                raise MDSplus.DevNO_NAME_SPECIFIED
            self.__host = host
        return self.__host
    @property
    def setting_shot(self): return self.tree.shot
    setting_clock_src = mdsrecord('clock_src',int)
    setting_clock     = mdsrecord('clock',int)
    setting_trigger   = mdsrecord('trigger',int)
    def soft_trigger(self):
        """
        ACTION METHOD: sends out a trigger on the carrier's internal trigger line (d1)
        """
        try:
            self.nc.soft_trigger()
        except socket.error as e:
            raise MDSplus.DevOFFLINE(str(e))

    def reboot(self):
        try:
            _carrier.reboot(self)
        except socket.error as e:
            raise MDSplus.DevOFFLINE(str(e))

    def init(self):
        """
        ACTION METHOD: initialize all device settings
        """
        dtacq.add_cache(self.setting_host)
        try:
            _carrier._init(self)
        except socket.error as e:
            raise MDSplus.DevOFFLINE(str(e))
        except (SystemExit,KeyboardInterrupt): raise
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise
        finally:
            self.commands = json.dumps(dtacq.remove_cache(self.setting_host))

    def _arm_acq(self,timeout=50):
        """
        ACTION METHOD: arm the device for acq modules
        """
        try:
            if not _carrier._arm_acq(self,timeout):
                raise MDSplus.MDSplusERROR('not armed after %d seconds'%timeout)
        except socket.error as e:
            raise MDSplus.DevOFFLINE(str(e))

    def _arm_ao(self):
        """
        ACTION METHOD: arm the device for ao modules
        """
        try: _carrier._arm_ao(self)
        except socket.error as e:
            raise MDSplus.DevOFFLINE(str(e))

    def _store_acq(self,abort=False):
        try:
            if not _carrier._store_acq(self,abort):
                raise MDSplus.DevNOT_TRIGGERED
        except socket.error as e:
            raise MDSplus.DevOFFLINE(str(e))
        except (SystemExit,KeyboardInterrupt): raise
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise

    def _get_dim_slice(self,i0,start,end,pre,mcdf=1):
        """ calculates the time-vector based on clk-tick t0, dt in ns, start and end """
        first= int(i0-pre)
        last = first + end-start-1
        dim,dm0,dm1 = self.get_dim_set(first,last)
        return slice(start,end),start,dim,dm0,dm1
    def _store_channels_from_queue(self,dims_slice,queue):
        """
        stores data in queue and time_vector to tree with linked segments
        blk:   list range of the data vector
        dim:   dimension to the data defined by blk
        queue: dict of ch:raw data
        """
        chunksize = 100000
        ESLO,EOFF=self.data_scales,self.data_offsets
        for i in range(queue.maxsize):
            ch,value,on = queue.get()
            if value is None or not on: continue
            node = self.getchannel(ch)
            node.setSegmentScale(self.get_scale(ESLO[ch-1],EOFF[ch-1]))
            for slc,start,dim,dm0,dm1 in dims_slice:
                val = value[slc]
                dlen = val.shape[0]
                for seg,is0 in enumerate(range(0,dlen,chunksize)):
                    is1 = min(is0+chunksize,dlen)-1
                    i0,i1 = start+is0,start+is1
                    self.dev.update_dim_set(dim,dm0,dm1,i0,i1)
                    if debug>1:  dprint("segment (%7.1fms,%7.1fms)"%(dm0/1e6,dm1/1e6))
                    node.makeSegment(dm0,dm1,dim,val[is0:is1+1])

    def _deinit_acq(self):
        """
        ACTION METHOD: abort and go to idle
        """
        try: _carrier._deinit_acq(self)
        except socket.error as e:
            raise MDSplus.DevOFFLINE(str(e))

 class _ACQ1001(_CARRIER,_acq1001): pass
 class _ACQ2106(_CARRIER,_MGT482,_acq2106):
    parts = _CARRIER.parts + _MGT482.parts
    def init(self):
        """
        ACTION METHOD: initialize all device settings
        """
        self.init_mgt(self._mgt_a_sites,self._mgt_b_sites,self._mgt_a_device_id,self._mgt_b_device_id)
        super(_ACQ2106,self).init()
    def _arm_acq(self,*a,**kw):
        if self.use_mgt:
            self._arm_mgt(*a,**kw)
        else:
            super(_ACQ2106,self)._arm_acq(*a,**kw)
    def _store_acq(self,*a,**kw):
        if self.use_mgt:
            self._store_mgt(*a,**kw)
        else:
            super(_ACQ2106,self)._store_acq(*a,**kw)
    def _deinit_acq(self,*a,**kw):
        if self.use_mgt:
            self._deinit_mgt(*a,**kw)
        else:
            super(_ACQ2106,self)._deinit_acq(*a,**kw)
 class _MODULE(MDSplus.TreeNode,_module):
    """
    MDSplus-dependent superclass covering Gen.4 D-tAcq module device types. PVs are set from the user tree-knobs.
    """
    def __init__(self,nid,*a,**kw):
        """ mimics _module.__init__ """
        if isinstance(nid,_MODULE): return
        self.site = kw.get('site',None)
	if self.site is None:
            raise Exception("No site specified for acq4xx._MODULE class")
        if isinstance(nid, _MODULE): return
        super(_MODULE,self).__init__(nid,*a,site=self.site)
        self._init_done = True

    @classmethod
    def _addMasterKnobs(cls,carrier,prefix):
        carrier.parts.append({'path': '%s:TRIG_MODE'         %(prefix,), 'type': 'text',    'value':'OFF','options': ('no_write_shot',), 'help':'*,"RTM","RTM"'})
        carrier.parts.append({'path': '%s:TRIG_MODE:TRANSLEN'%(prefix,), 'type': 'numeric', 'value':10000,'options': ('no_write_shot',), 'help':'Samples acquired per trigger for RTM'})
    @classmethod
    def _addModuleKnobs(cls,carrier,prefix,idx):
        carrier.parts.append({'path': '%s:CHECK'%(prefix,), 'type': 'TASK', 'options': ('write_once',), 'valueExpr':'Method(None,"check",head)'})

    def __getattr__(self,name):
        """ redirect Device.part_name to head """
        partname = "module%d_%s"%(self.site,name)
        if partname in self.head.part_dict:
            return self.__class__(self.head.part_dict[partname]+self.head.nid,self.tree,self.head,site=self.site)
        return self.__getattribute__(name)
    def __setattr__(self,name,value):
        """ redirect Device.part_name to head """
        if self._init_done:
            partname = "module%d_%s"%(self.site,name)
            if partname in self.head.part_dict:
                self.head.__setattr__(partname,value)
                return
        super(_MODULE,self).__setattr__(name,value)

    def getchannel(self,ch,*args):
        """ mimics _module.getchannel """
        return self.__getattr__('_'.join(['channel%02d'%(ch+self.head._channel_offset[self.site-1],)]+list(args)))
    def get_dim(self,ch): # unused TODO: use in store as it supports channels.range
        """
        Creates the time dimension array from clock, triggers, and sample counts
        """
        from MDSplus import MINUS,SUBTRACT,Window,Dimension
        pre  = self._carrier.trigger_pre
        post = self._carrier.trigger_post
        trig = self._carrier.trigger
        win  = Window(MINUS(pre),SUBTRACT(post,1),trig)
        rang = self.getchannel(ch,'range')
        dim  = Dimension(win,rang)
        return dim
    def check(self,*chs):
        """
        Can call from action node. Checks if all values are valid.
        """
        if len(chs)>0: chs = range(1,self._num_channels+1)
        if self.tree.shot!=-1:           raise MDSplus.TreeNOWRITESHOT # only check model trees
        if self.site==1 and not self.on: raise MDSplus.DevINV_SETUP    # module 1 is master module
        from MDSplus import Range
        pre,post = self._pre,self._post
        for ch in chs:
          if self.getchannel(ch).on:
            rang = self._range(ch)
            if not isinstance(rang,(Range,)) or rang.delta<1:
                                                 raise MDSplus.DevRANGE_MISMATCH
            if -pre>rang.begin:                  raise MDSplus.DevBAD_STARTIDX
            if post<rang.ending:                 raise MDSplus.DevBAD_ENDIDX
        return chs


 class _ACQ425(_MODULE,_acq425):
    @classmethod
    def _addMasterKnobs(cls,carrier,prefix):
        _MODULE._addMasterKnobs(carrier,prefix)
        carrier.parts.append({'path': '%s:CLKDIV'%(prefix,), 'type': 'numeric', 'options': ('no_write_model',)})
    @classmethod
    def _addModuleKnobs(cls,carrier,prefix,idx):
        _MODULE._addModuleKnobs(carrier,prefix,idx)
        for i in range(carrier._channel_offset[idx]+1,carrier._channel_offset[idx]+cls._num_channels+1):
            path = '%s:CHANNEL%02d'%(prefix,i)
            carrier.parts.append({'path': path, 'type': 'SIGNAL', 'options': ('no_write_model', 'write_once',)})
            carrier.parts.append({'path': '%s:RANGE' %(path,), 'type': 'AXIS',    'valueExpr':'Range(None,None,1)',       'options': ('no_write_shot')})
            carrier.parts.append({'path': '%s:GAIN'  %(path,), 'type': 'NUMERIC', 'value':10, 'options': ('no_write_shot',),  'help':'0..12 [dB]'})
            carrier.parts.append({'path': '%s:OFFSET'%(path,), 'type': 'NUMERIC', 'value':0., 'options': ('no_write_shot',), 'help':'0,1'})

    def setting_gain(self,i): return float(self.getchannel(i,'gain').record.data())

    """ Action methods """
    def check(self,*chs):
        chs = super(_ACQ425,self).check(*chs)
        for ch in chs:
          if self.getchannel(ch).on:
            try:    self._offset(ch)
            except (SystemExit,KeyboardInterrupt): raise
            except: raise MDSplus.DevBAD_OFFSET
            try:
                self._setGain(ch)
                if not self._gain(ch) == self.nc.range(ch): raise
            except (SystemExit,KeyboardInterrupt): raise
            except:
                print(ch,self._gain(ch),self.nc.range(ch))
                self.nc.GAIN[ch] = 10
                raise MDSplus.DevBAD_GAIN

 class _ACQ425(_ACQ425,_acq425): pass

 class _ACQ480(_MODULE,_acq480):
    @property
    def _clkdiv_fpga(self):
        try:   return int(self.clkdiv_fpga.record)
        except MDSplus.TreeNODATA:
            return self.nc._clkdiv_fpga
    @classmethod
    def _addMasterKnobs(cls,carrier,prefix):
        _MODULE._addMasterKnobs(carrier,prefix)
        carrier.parts.append({'path': '%s:CLKDIV'            %(prefix,), 'type': 'numeric', 'valueExpr':'MULTIPLY(node.FIR,node.FPGA)', 'options': ('write_once','no_write_shot')})
        carrier.parts.append({'path': '%s:CLKDIV:FIR'        %(prefix,), 'type': 'numeric', 'options': ('write_once','no_write_model')})
        carrier.parts.append({'path': '%s:CLKDIV:FPGA'       %(prefix,), 'type': 'numeric', 'options': ('write_once','no_write_model')})
        carrier.parts.append({'path': '%s:FIR'               %(prefix,), 'type': 'numeric', 'value':0,    'options': ('no_write_shot',), 'help':'DECIM=[1,2,2,4,4,4,4,2,4,8,1] for FIR=[0,1,2,3,4,5,6,7,8,9,10]'})

    @classmethod
    def _addModuleKnobs(cls,carrier,prefix,idx):
        for i in range(carrier._channel_offset[idx]+1,carrier._channel_offset[idx]+cls._num_channels+1):
            path = '%s:CHANNEL%02d'%(prefix,i)
            carrier.parts.append({'path': path, 'type': 'SIGNAL', 'options': ('no_write_model', 'write_once',)})
            carrier.parts.append({'path': '%s:INVERT' %(path,), 'type': 'numeric', 'value':False, 'options': ('no_write_shot',), 'help':'0,1'})
            carrier.parts.append({'path': '%s:RANGE'  %(path,), 'type': 'axis',    'valueExpr':'Range(None,None,1)', 'options': ('no_write_shot')})
            carrier.parts.append({'path': '%s:GAIN'   %(path,), 'type': 'numeric', 'value':0,     'options': ('no_write_shot',), 'help':'0..12 [dB]'})
            carrier.parts.append({'path': '%s:LFNS'   %(path,), 'type': 'numeric', 'value':False, 'options': ('no_write_shot',), 'help':'0,1'})
            carrier.parts.append({'path': '%s:HPF'    %(path,), 'type': 'numeric', 'value':False, 'options': ('no_write_shot',), 'help':'0,1'})
            carrier.parts.append({'path': '%s:T50R'   %(path,), 'type': 'numeric', 'value':False, 'options': ('no_write_shot',), 'help':'0,1'})

    @property
    def setting_trig_mode(self):
        try:   return self.trig_mode.record.data().tolist()
        except MDSplus.TreeNODATA: return 0
    setting_trig_mode_translen = mdsrecord('trig_mode_translen',int)
    setting_fir         = mdsrecord('fir',int)

    @property
    def init_args(self):
        return (
            [self.setting_gain(ch)   for ch in range(1,self._num_channels+1)],
            [self.setting_invert(ch) for ch in range(1,self._num_channels+1)],
            [self.setting_hpf(ch)    for ch in range(1,self._num_channels+1)],
            [self.setting_lfns(ch)   for ch in range(1,self._num_channels+1)],
            [self.setting_t50r(ch)   for ch in range(1,self._num_channels+1)],
            self.tree.shot)
    def init_master(self,pre,soft,clkdiv):
        self.nc._init_master(pre,soft,self.setting_trig_mode,self.setting_trig_mode_translen,self.setting_fir)
        fir  = self.nc.ACQ480.FIR.DECIM
        fpga = self.nc.ACQ480.FPGA.DECIM
        self.clkdiv_fir  = fir
        self.clkdiv_fpga = fpga
        #check clock#
        clk = self._carrier.setting_clock
        if clk*fpga < 10000000:
            print('Bus clock must be at least 10MHz')
            raise MDSplus.DevINV_SETUP
        if clk*fpga*fir > 80000000:
            print('ADC clock cannot exceed 80MHz')
            raise MDSplus.DevINV_SETUP

    """Channel settings"""
    def setting_invert(self,ch): return int(self.getchannel(ch,'invert').record.data())
    def setting_gain(self,ch): return int(self.getchannel(ch,'gain').record.data())
    def setting_hpf(self,ch): return int(self.getchannel(ch,'hpf').record.data())
    def setting_lfns(self,ch): return int(self.getchannel(ch,'lfns').record.data())
    def setting_t50r(self,ch): return int(self.getchannel(ch,'t50r').record.data())

 class _AO420(_MODULE,_ao420):
    """
    MDSplus-dependent superclass covering Gen.4 D-tAcq module device types. PVs are set from the user tree-knobs.
    """
    @classmethod
    def _addMasterKnobs(cls,carrier,prefix):
        _MODULE._addMasterKnobs(carrier,prefix)
        carrier.parts.append({'path': '%s:CLKDIV'%(prefix,), 'type': 'numeric', 'options': ('no_write_model',)})
    @classmethod
    def _addModuleKnobs(cls,carrier,prefix,idx):
        for i in range(carrier._channel_offset[idx]+1,carrier._channel_offset[idx]+cls._num_channels+1):
            path = '%s:CHANNEL%02d'%(prefix,i)
            carrier.parts.append({'path': path, 'type': 'SIGNAL',  'valueExpr':'SIN(MULTIPLY(Range(0,1,DIVIDE(1.,head.clock)),d2PI()))', 'options': ('no_write_shot',)})
            carrier.parts.append({'path': '%s:GAIN'   %(path,), 'type': 'numeric', 'value':100,     'options': ('no_write_shot',), 'help':'0..200%%'})
            carrier.parts.append({'path': '%s:OFFSET' %(path,), 'type': 'numeric', 'value':0,      'options': ('no_write_shot',),  'help':'-100..100%%'})
    def _channel(self,i): return self.getchannel(i).record
    def setting_gain(self,ch):   return float(self.getchannel(ch,'gain').record.data())
    def setting_offset(self,ch): return float(self.getchannel(ch,'offset').record.data())

 ###-----------------------
 ### Public MDSplus Devices
 ###-----------------------

 ### ACQ1001 carrier

 class ACQ1001_ACQ425(_ACQ1001):pass
 ACQ1001_ACQ425.setup(_ACQ425)
 class ACQ1001_ACQ480(_ACQ1001):pass
 ACQ1001_ACQ480.setup(_ACQ480)

 class ACQ1001_AO420(_ACQ1001):pass
 ACQ1001_AO420.setup(_AO420)

 ## set bank_mask A,AB,ABC (default all, i.e. ABCD) only for ACQ425 for now ##

 class _ACQ425_4CH(_ACQ425): _num_channels = 4
 class ACQ1001_ACQ425_4CH(_ACQ1001):pass
 ACQ1001_ACQ425_4CH.setup(_ACQ425_4CH)

 class _ACQ425_8CH(_ACQ425): _num_channels = 8
 class ACQ1001_ACQ425_8CH(_ACQ1001):pass
 ACQ1001_ACQ425_8CH.setup(_ACQ425_8CH)

 class _ACQ425_12CH(_ACQ425): _num_channels = 12
 class ACQ1001_ACQ425_12CH(_ACQ1001):pass
 ACQ1001_ACQ425_12CH.setup(_ACQ425_12CH)

 ## /mnt/fpga.d/ACQ1001_TOP_08_ff_64B-4CH.bit.gz
 # TODO: how to deal with es_enable CH 5&6 ?
 class _ACQ480_4CH(_ACQ480): _num_channels = 4
 class ACQ1001_ACQ480_4CH(_ACQ1001):pass
 ACQ1001_ACQ480_4CH.setup(_ACQ480_4CH)

 ### ACQ2106 carrier ###

 class ACQ2106_ACQ425x1(_ACQ2106):pass
 ACQ2106_ACQ425x1.setup(_ACQ425,1)
 class ACQ2106_ACQ425x2(_ACQ2106):pass
 ACQ2106_ACQ425x2.setup(_ACQ425,2)
 class ACQ2106_ACQ425x3(_ACQ2106):pass
 ACQ2106_ACQ425x3.setup(_ACQ425,3)
 class ACQ2106_ACQ425x4(_ACQ2106):pass
 ACQ2106_ACQ425x4.setup(_ACQ425,4)
 class ACQ2106_ACQ425x5(_ACQ2106):pass
 ACQ2106_ACQ425x5.setup(_ACQ425,5)
 class ACQ2106_ACQ425x6(_ACQ2106):pass
 ACQ2106_ACQ425x6.setup(_ACQ425,6)

 class ACQ2106_ACQ480x1(_ACQ2106):pass
 ACQ2106_ACQ480x1.setup(_ACQ480,1)
 class ACQ2106_ACQ480x2(_ACQ2106):pass
 ACQ2106_ACQ480x2.setup(_ACQ480,2)
 class ACQ2106_ACQ480x3(_ACQ2106):pass
 ACQ2106_ACQ480x3.setup(_ACQ480,3)
 class ACQ2106_ACQ480x4(_ACQ2106):_max_clk = 14000000
 ACQ2106_ACQ480x4.setup(_ACQ480,4)
 class ACQ2106_ACQ480x5(_ACQ2106):_max_clk = 11000000
 ACQ2106_ACQ480x5.setup(_ACQ480,5)
 class ACQ2106_ACQ480x6(_ACQ2106):_max_clk =  9000000
 ACQ2106_ACQ480x6.setup(_ACQ480,6)

 if with_mgtdram:
  class _MGTDRAM(object):
    @classmethod
    def get_mgt_sites(cls): return range(1,cls.num_modules+1)
    @property
    def id(self): "%s_%03d_%d"%(self.tree.name,self.tree.shot,self.nid)
    __stream = {}
    @property
    def _stream(self):
        return self._MGTDRAM__stream.get(self.id,None)
    @_stream.setter
    def _stream(self,value):
        if   isinstance(value,(_MGTDRAM.STREAM,)):
            self._MGTDRAM__stream[self.id] = value
        elif self.id in self._MGTDRAM__stream:
            self._MGTDRAM__stream.pop(self.id)
    class STREAM(threading.Thread):
        _folder = '/home/dt100/data'
        _blksize = (1<<22) # blocks of 4MB
        traceback = None
        exception = None
        post = 2147483647
        trigger = 0
        timeout = 120 # buffer timeout in sec
        def wait4armed(self):
            while self.state<1:
                if not self.isAlive():
                    return False
                time.sleep(1)
            return True
        @property
        def triggered(self):
            return self.state>1
        @property
        def transfering(self):
            return self.state>=3
        @property
        def state(self):
            with self._state_lock:
                return self._state
        def __init__(self,dev,blocks,autostart=True):
            super(_MGTDRAM.STREAM,self).__init__(name="MGTDRAM.STREAM(%s)"%id)
            self._stop = threading.Event()
            self.id  = dev.node_name.lower()
            self.ctrl= dev.nc
            self.mgt = mgtdram(dev._host)
            self._state_lock = threading.Lock()
            self._state = 0
            self._chans = dev._num_channels
            self._blkgrp = 12 if (self._chans%3)==0 else 16
            self._grpsize = self._blksize * self._blkgrp # blocks of 4MB
            self._grplen = self._grpsize//self._chans//2
            self._blklen = self._blksize//self._chans//2
            self.blocks = min(2048,-((-blocks)//self._blkgrp)*self._blkgrp)
            self.trigger = dev._trigger
            self.pre  = dev._pre
            self.post = dev._post
            self.samples = min(self.blocks*self._blklen,self.pre + self.post)
            self.dev  = dev.copy()
            self.fpga = dev._master._clkdiv_fpga
            self.skip = dev._master._skip
            self.transfer = self._transfer_es if dev._master._es_enable else self._transfer
            if not os.path.exists(self.folder):
                os.mkdir(self.folder)
                os.chmod(self.folder,0o777)
            else:
                for filename in os.listdir(self.folder):
                    fullpath = '%s/%s'%(self.folder,filename)
                    if os.path.isfile(fullpath):
                        try:    os.remove(fullpath)
                        except (SystemExit,KeyboardInterrupt): raise
                        except: print('ERROR: could not remove %s'%fullpath)
            self.file = sys.stdout
            if autostart:
                self.start()

        @property
        def folder(self):
            return "%s/%s"%(self._folder,self.id)
        def get_fullpath(self,idx):
            return '%s/%04d'%(self.folder,idx)
        def get_block(self,block):
            if isinstance(block,int):
                block = self.get_fullpath(block)
            size = os.path.getsize(block)
            length = size//self._chans//2
            return numpy.memmap(block,dtype=numpy.int16,shape=(self._chans,length),mode='r',order='F')
        def idx2ch(self,idx):
            return 1+idx
        def buffer(self):
            self.file.write('---MGT_OFFLOAD (%d blocks)---\n'%self.blocks)
            self.file.flush()
            if self.blocks<=0: return
            self.mgt.mgt_offload(0,self.blocks-1)
            ftp = self.mgt.trans.async(self.file)
            rem_samples = self.samples
            try:
                idx = 0
                while idx<self.blocks:
                    fullpath = self.get_fullpath(idx+self._blkgrp-1)
                    if debug>0: dprint('waiting for %s'%fullpath)
                    for i in range(self.timeout):
                        if os.path.exists(fullpath): break
                        if not ftp.isAlive():
                            if os.path.exists(fullpath): break
                            self.exception = MDSplus.DevBAD_POST_TRIG
                            return
                        time.sleep(1)
                    else:
                        self.traceback = 'FTP_TIMEOUT on file: %s'%fullpath
                        self.exception = MDSplus.DevIO_STUCK
                        return
                    while True:
                        size = os.path.getsize(fullpath)
                        if   size<self._grpsize:
                            if not ftp.isAlive(): break
                            time.sleep(.1)
                        elif size>self._grpsize:
                            self.traceback = 'FTP_FILE_SIZE "%s" %dB > %dB'%(fullpath,size,self._grpsize)
                            self.exception = MDSplus.DevCOMM_ERROR
                            return
                        else: break
                    block = self.get_block(fullpath)
                    if debug>0: dprint("buffer yield %s - %dB / %dB"%(fullpath,os.path.getsize(fullpath),self._grpsize))
                    yield block
                    try:    os.remove(fullpath)
                    except (SystemExit,KeyboardInterrupt): raise
                    except: print('Could not remove %s'%fullpath)
                    #if self.is_last_block(rem_samples,idx+self._blkgrp): return
                    idx += self._blkgrp
                    rem_samples -= block.shape[1]
            finally:
                ftp.join()

        def is_last_block(self,rem_samples,blocks_in):
            """ determine acquired number of samples and blocks """
            try:
                samples = min(self.shot_log.count//self.fpga,self.samples)
                if self.samples-rem_samples<samples: return False
                blocks  = min(-((-samples)//self._grplen)*self._blkgrp,self.blocks)
                if blocks_in<blocks:                 return False
                if debug>0: dprint("blocks: %d/%d, samples %d/%d"%(blocks,self.blocks,samples,self.samples))
            except:
                import traceback
                traceback.print_exc()
            return True

        def run(self):
            try:
                try:
                    self.mgt.mgt_abort()
                    self.file.write('---MGT_RUN_SHOT (%d blocks)---\n'%self.blocks)
                    self.shot_log = self.mgt.mgt_run_shot_log(self.blocks,debug=True)
                    # wait for first sample
                    while self.on:
                        if self.shot_log.count>=0:
                            break
                        time.sleep(1)
                    else: return # triggers mgt_abort in finally
                    if debug>0: dprint(" armed ")
                    with self._state_lock: self._state = 1
                    # wait for first sample
                    while self.on:
                        if self.shot_log.count>=1:
                            break
                        time.sleep(1)
                    else: return # triggers mgt_abort in finally
                    if debug>0: dprint(" triggered ")
                    with self._state_lock: self._state = 2
                except: # stop stream on exception
                    raise
                finally:
                    # wait for mgt_run_shot to finish
                    while self.shot_log.isAlive():
                        if not self.on:
                            self.mgt.mgt_abort()
                        self.shot_log.join(1)
                # transfer available samples
                if debug>0: dprint(" ready for transfer ")
                with self._state_lock: self._state = 3
                self.transfer(self.dev)
                # finished
                if debug>0: dprint(" transfered ")
                with self._state_lock: self._state = 4
            except Exception as e:
                import traceback
                self.exception = e
                self.traceback = traceback.format_exc()
                self.stop()

        def _transfer(self,dev):
            i0 = 0
            DT = MDSplus.DIVIDE(MDSplus.Int64(1e9),dev.clock)
            dim,dm0,dm1= self.dev.get_dim_set()
            for buf in self.buffer():
                i1 = self.dev.get_i1(i0,buf.shape[1])
                self.dev.update_dim_set(dim,dm0,dm1,i0,i1)
                for idx in range(self._chans):
                    ch = self.idx2ch(idx)
                    node = dev.getchannel(ch)
                    if node.on:
                        node.makeSegment(dm0,dm1,dim,buf[idx])
                i0 = i1+1

        def get_mask(self,buf):
            return (buf[_es_marker.static,...]==_es_marker.int16.static).all(0)

        def _transfer_es(self,dev):
            """
            ACTION METHOD: grabs the triggered channels from acq400_bigcat
            only works it bufferlen is set to default
            """
            if debug>0: dprint("STREAM._transfer_es")
            skip= self.skip
            ctx = [None,0,0] # offset,ttrg,tcur
            def get_chunks(buf):
                chunks,idx,skp = [],0,0
                # fixed in 613 ? - on range(3,n,4) is more robust
                mask = self.get_mask(buf)
                index= numpy.nonzero(mask)[0].astype('int32')
                lohi = buf[:,mask].astype('uint16').astype('int32')
                ## ch1&2 sample index, ch5&6 clock count
                tt0  = ((lohi[4]+(lohi[5]<<16))//self.fpga).tolist()
                for i,ctx[2] in enumerate(tt0):
                    if ctx[0] is None:
                        ctx[1] = ctx[2]
                        if debug>0: dprint("ttrg = %d"%ctx[1])
                    chunks.append((idx,index[i],ctx[0],ctx[2]-ctx[1],skp))
                    idx,ctx[0],skp = index[i]+1,ctx[2]-ctx[1],skip
                chunks.append((idx,buf.shape[1],ctx[0],ctx[2]-ctx[1],skp))
                if ctx[0] is not None:
                    ctx[0]+= buf.shape[1]-idx-skp
                return chunks
            d1 = None
            rem_samples = self.pre+self.post
            for block,buf in enumerate(self.buffer()):
                chunks = get_chunks(buf)
                if debug>0: dprint(block,chunks)
                for fm,ut,i0,t0,skip in chunks:
                    if i0 is None: continue
                    if debug>2: dprint(block,fm,ut,i0,t0,skip)
                    slc,i0,dim,dm0,dm1 = dev._get_dim_slice(i0,fm+skip,ut,self.pre)
                    val = buf[:,slc][:,:rem_samples]
                    rem_samples-=val.shape[1]
                    i1 = self.dev.get_i1(i0,val.shape[1])
                    self.dev.update_dim_set(dim,dm0,dm1,i0,i1)
                    if debug>1: dprint("segment (%7.1fms,%7.1fms) rem: %d"%(dm0/1e6,dm1/1e6,rem_samples))
                    for idx in range(self._chans):
                        ch = self.idx2ch(idx)
                        node = dev.getchannel(ch)
                        if node.on:
                            node.makeSegment(dm0,dm1,dim,val[idx])
                    if rem_samples<=0: return

        def stop(self): self._stop.set()

    def fits_in_ram(self):
        chans   = self._num_channels
        length  = self.STREAM._blksize//self._num_channels//2
        samples = self._post+self._pre
        blocks  = samples//length + (1 if (samples%length)>0 else 0)
        does = blocks<128 # have enought space for demux 128-1
        return does,blocks,length,chans
    def _arm_mgt(self,force=False):
        does,blocks,length,chans = self.fits_in_ram()
        if does: return self._arm_acq()
        if debug: dprint('_MGTDRAM._arm_mgt')
        if self._stream is None:
            self._stream = self.STREAM(self,blocks)
        if not self._stream.wait4armed():
            self._stream = None
            raise Exception('Stream terminated')

    def _store_mgt(self):
        does,blocks,length,chans = self.fits_in_ram()
        if does: return self._store_acq()
        if debug: dprint('_MGTDRAM._store_mgt')
        for site in self._active_mods:
            self.getmodule(site).store()
        self._master.store_master()
        ESLO,EOFF=self.data_scales,self.data_offsets
        for idx in range(chans):
            ch = idx+1
            node = self.getchannel(ch)
            if node.on:
                node.setSegmentScale(self.get_scale(ESLO[idx],EOFF[idx]))
        if self._stream is None:       raise MDSplus.DevINV_SETUP
        if self._stream.exception is not None:
            print(self._stream.traceback)
            raise self._stream.exception
        if not self._stream.triggered: raise MDSplus.DevNOT_TRIGGERED
  # _MGTDRAM

  class ACQ2106_MGTDRAM_ACQ425x1(ACQ2106_ACQ425x1,_MGTDRAM): pass
  ACQ2106_MGTDRAM_ACQ425x1.setup(_ACQ425,1,True)
  class ACQ2106_MGTDRAM_ACQ425x2(ACQ2106_ACQ425x2,_MGTDRAM): pass
  ACQ2106_MGTDRAM_ACQ425x2.setup(_ACQ425,2,True)
  class ACQ2106_MGTDRAM_ACQ425x3(ACQ2106_ACQ425x3,_MGTDRAM): pass
  ACQ2106_MGTDRAM_ACQ425x3.setup(_ACQ425,3,True)
  class ACQ2106_MGTDRAM_ACQ425x4(ACQ2106_ACQ425x4,_MGTDRAM): pass
  ACQ2106_MGTDRAM_ACQ425x4.setup(_ACQ425,4,True)
  class ACQ2106_MGTDRAM_ACQ425x5(ACQ2106_ACQ425x5,_MGTDRAM): pass
  ACQ2106_MGTDRAM_ACQ425x5.setup(_ACQ425,5,True)
  class ACQ2106_MGTDRAM_ACQ425x6(ACQ2106_ACQ425x6,_MGTDRAM): pass
  ACQ2106_MGTDRAM_ACQ425x6.setup(_ACQ425,6,True)

  class ACQ2106_MGTDRAM_ACQ480x1(ACQ2106_ACQ480x1,_MGTDRAM): pass
  ACQ2106_MGTDRAM_ACQ480x1.setup(_ACQ480,1,True)
  class ACQ2106_MGTDRAM_ACQ480x2(ACQ2106_ACQ480x2,_MGTDRAM): pass
  ACQ2106_MGTDRAM_ACQ480x2.setup(_ACQ480,2,True)
  class ACQ2106_MGTDRAM_ACQ480x3(ACQ2106_ACQ480x3,_MGTDRAM): pass
  ACQ2106_MGTDRAM_ACQ480x3.setup(_ACQ480,3,True)
  class ACQ2106_MGTDRAM_ACQ480x4(ACQ2106_ACQ480x4,_MGTDRAM): pass
  ACQ2106_MGTDRAM_ACQ480x4.setup(_ACQ480,4,True)
  class ACQ2106_MGTDRAM_ACQ480x5(ACQ2106_ACQ480x5,_MGTDRAM): pass
  ACQ2106_MGTDRAM_ACQ480x5.setup(_ACQ480,5,True)
  class ACQ2106_MGTDRAM_ACQ480x6(ACQ2106_ACQ480x6,_MGTDRAM): pass
  ACQ2106_MGTDRAM_ACQ480x6.setup(_ACQ480,6,True)

 ###-------------
 ### test drivers
 ###-------------

 from unittest import TestCase,TestSuite,TextTestRunner
 T=[time.time()]
 def out(msg,reset=False):
    if reset: T[0]=time.time() ; t=T[0]
    else:     t=T[0] ; T[0]=time.time()
    print('%7.3f: %s'%(T[0]-t,msg))
 class Tests(TestCase):
    simulate = False
    acq2106_425_host     = '192.168.44.255'
    acq2106_480_host     = '192.168.44.255' #'acq2106_065'
    acq2106_480_fpgadecim= 10
    acq1001_420_host     = '192.168.44.254' #'acq1001_291'
    acq1001_425_host     = '192.168.44.255'
    acq1001_480_host     = '192.168.44.255' #'acq1001_316'
    rp_host              = '10.44.2.100'#'RP-F0432C'
    shot = 1000
    @classmethod
    def getShotNumber(cls):
        return cls.shot
        import datetime
        d = datetime.datetime.utcnow()
        return d.month*100000+d.day*1000+d.hour*10

    @classmethod
    def setUpClass(cls):
        from LocalDevices import acq4xx as a#,w7x_timing
        import gc
        gc.collect(2)
        cls.shot = cls.getShotNumber()
        MDSplus.setenv('test_path','/tmp')
        with MDSplus.Tree('test',-1,'new') as t:
            #ACQ480=ACQ2106_ACQ480x4.Add(t,'ACQ480')
            A=a.ACQ2106_ACQ480x4.Add(t,'ACQ480x4')
            A.host      = cls.acq2106_480_host
            #A.clock_src = 10000000
            A.clock     =  2000000
            A.trigger_pre  = 0
            A.trigger_post = 100000
            A.module1_fir  = 3
            A.ACTIONSERVER.SOFT_TRIGGER.on = True
            A=a.ACQ2106_ACQ480x4.Add(t,'ACQ480x4_M2')
            A.mgt_a_sites = MDSplus.Int32([1,2])
            A.mgt_b_sites = MDSplus.Int32([3,4])
            A.host      = cls.acq2106_480_host
            #A.clock_src = 10000000
            A.clock     =  2000000
            A.trigger_pre  = 0
            A.trigger_post = 500000
            A.module1_fir  = 3
            A.ACTIONSERVER.SOFT_TRIGGER.on = True
            A=a.ACQ2106_ACQ425x2.Add(t,'ACQ425x2')
            A.host      = cls.acq2106_425_host
            #A.clock_src = 10000000
            A.clock     = 1000000
            A.trigger_pre  = 0
            A.trigger_post = 100000
            A.ACTIONSERVER.SOFT_TRIGGER.on = True
            A=a.ACQ2106_ACQ425x2.Add(t,'ACQ425x2_M2')
            A.mgt_a_sites = MDSplus.Int32([1,2])
            #A.mgt_b_sites = MDSplus.Int32([2])
            A.host      = cls.acq2106_425_host
            #A.clock_src = 10000000
            A.clock     = 1000000
            A.trigger_pre  = 0
            A.trigger_post = 500000
            A.ACTIONSERVER.SOFT_TRIGGER.on = True
            A=a.ACQ1001_ACQ425.Add(t,'ACQ425')
            A.host      = cls.acq1001_425_host
            #A.clock_src = 10000000
            A.clock     = 1000000
            A.trigger_pre  = 0
            A.trigger_post = 100000
            A.ACTIONSERVER.SOFT_TRIGGER.on = True
            A=a.ACQ1001_ACQ480.Add(t,'ACQ480')
            A.host      = cls.acq1001_480_host
            #A.clock_src = 10000000
            A.clock     = 2000000
            A.trigger_pre  = 0
            A.trigger_post = 100000
            A.ACTIONSERVER.SOFT_TRIGGER.on = True
            A=a.ACQ1001_AO420.Add(t,'AO420')
            A.host      = cls.acq1001_420_host
            #A.clock_src = 10000000
            A.clock     = 1000000
            a = numpy.array(range(100000))/50000.*numpy.pi
            A.getchannel(1).record=numpy.sin(a)
            A.getchannel(2).record=numpy.cos(a)
            A.getchannel(3).record=-numpy.sin(a)
            A.getchannel(4).record=-numpy.cos(a)
            A.ACTIONSERVER.SOFT_TRIGGER.on = True
            #R=w7x_timing.W7X_TIMING.Add(t,'R')
            #R.host           = cls.rp_host
            t.write()
        t.cleanDatafile()

    @classmethod
    def tearDownClass(cls): pass

    @staticmethod
    def makeshot(t,shot,dev):
        out('creating "%s" shot %d'%(t.tree,shot))
        MDSplus.Tree('test',-1,'readonly').createPulse(shot)
        t=MDSplus.Tree('test',shot)
        A=t.getNode(dev)
        A.simulate = Tests.simulate
        try:
            R = t.R
        except AttributeError:
            R=None
        A.debug=7
        out('setup trigger')
        if R is not None:
            R.disarm()
            R.init()
            R.arm()
        out('init A')
        A.init()
        out('arm A')
        A.arm()
        try:
            out('wait 2sec ')
            time.sleep(2)
            out('TRIGGER! ')
            if R is None:
                A.soft_trigger()
            else:
                R.trig();
            t=int(A.setting_post/A.setting_clock+1)*2
            out('wait %dsec'%t)
            time.sleep(t)
            if dev.startswith('ACQ'):
                out('store')
                A.store()
        finally:
            if dev.startswith('ACQ'):
                A.deinit()
        out('done')

    def test420Normal(self):
        out('start test420Normal',1)
        t=MDSplus.Tree('test')
        try: R = t.R
        except AttributeError: pass
        else: R.setup()
        self.makeshot(t,self.shot+8,'AO420')

    def test425Normal(self):
        out('start test425Normal',1)
        t=MDSplus.Tree('test')
        try: R = t.R
        except AttributeError: pass
        else: R.setup()
        self.makeshot(t,self.shot+5,'ACQ425')

    def test425X2Normal(self):
        out('start test425X2Normal',1)
        t=MDSplus.Tree('test')
        try: R = t.R
        except AttributeError: pass
        else: R.setup()
        self.makeshot(t,self.shot+6,'ACQ425X2')

    def test425X2Stream(self):
        out('start test425X2Stream',1)
        t=MDSplus.Tree('test')
        try: R = t.R
        except AttributeError: pass
        else: R.setup()
        self.makeshot(t,self.shot+7,'ACQ425X2_M2')

    def test480Normal(self):
        out('start test480Normal',1)
        t=MDSplus.Tree('test')
        try: R = t.R
        except AttributeError: pass
        else: R.setup()
        self.makeshot(t,self.shot+5,'ACQ480')

    def test480X4Normal(self):
        out('start test480X4Normal',1)
        t=MDSplus.Tree('test')
        try: R = t.R
        except AttributeError: pass
        else: R.setup(width=1000)
        t.ACQ480X4.module1_trig_mode='OFF';
        self.makeshot(t,self.shot+1,'ACQ480X4')

    def test480X4RGM(self):
        out('start test480X4RGM',1)
        t=MDSplus.Tree('test')
        t.R.setup(width=1000,gate2=range(3),timing=[i*(t.ACQ480X4.trigger_post>>4)*self.acq2106_480_fpgadecim for i in [0,1,2,4,5,8,9,13,14,19,20,100]])
        t.ACQ480X4.module1_trig_mode='RGM';
        self.makeshot(t,self.shot+2,'ACQ480X4')

    def test480X4RTM(self):
        out('start test480X4RTM',1)
        t=MDSplus.Tree('test')
        try: R = t.R
        except AttributeError: pass
        else: R.setup(width=100,period=100000*self.acq2106_480_fpgadecim,burst=30)
        t.ACQ480X4.module1_trig_mode='RTM'
        t.ACQ480X4.module1_trig_mode_translen=t.ACQ480X4.trigger_post>>3
        self.makeshot(t,self.shot+3,'ACQ480X4')

    def test480X4Stream(self):
        out('start test480X4MGT',1)
        t=MDSplus.Tree('test')
        #t.ACQ2106_064.trigger_post=12500000
        try: R = t.R
        except AttributeError: pass
        else: R.setup(width=100)
        t.ACQ2106_064.module1_trig_mode='OFF';
        self.makeshot(t,self.shot+1,'ACQ480X4_M2')

    def runTest(self):
        for test in self.getTests():
            self.__getattribute__(test)()

    @staticmethod
    def get480Tests():
        return ['test480Normal','test480X4Normal','test480X4RGM','test480X4RTM']

    @staticmethod
    def get425Tests():
        return ['test425Normal','test425X6Normal','test425X6Stream']

    @staticmethod
    def get420Tests():
        return ['test420Normal']


 def suite(tests):
    return TestSuite(map(Tests,tests))

 def run480():
    TextTestRunner(verbosity=2).run(suite(Tests.get480Tests()))

 def run425():
    TextTestRunner(verbosity=2).run(suite(Tests.get425Tests()))

 def run420():
    TextTestRunner(verbosity=2).run(suite(Tests.get420Tests()))

 def runTests(tests):
    TextTestRunner(verbosity=2).run(suite(tests))

 def runmgtdram(blocks=10,uut='localhost'):
    blocks = int(blocks)
    m=mgtdram(uut)
    print("INIT  PHASE RUN")
    m._init(blocks,log=sys.stdout)
    print("INIT  PHASE DONE")
    print("STORE PHASE RUN")
    m._store(blocks,chans=32)
    print("STORE PHASE DONE")

 if __name__=='__main__':
    import sys
    if len(sys.argv)<=1:
        print('%s test'%sys.argv[0])
        print('%s test420'%sys.argv[0])
        print('%s test425'%sys.argv[0])
        print('%s test480'%sys.argv[0])
        print('%s testmgtdram <blocks> [uut]'%sys.argv[0])
    else:
        MDSplus.setenv('test_path','/tmp')
        print(sys.argv[1:])
        if sys.argv[1]=='test':
            if len(sys.argv)>2:
                runTests(sys.argv[2:])
            else:
                shot = 1
                try:    shot>0 # analysis:ignore
                except: shot = Tests.getShotNumber()
                from matplotlib.pyplot import plot # analysis:ignore

                #expt,dev=('qmb','ACQ1001_292') # ACQ1001_ACQ480
                #expt,dev=('qxt1','ACQ2106_070') # ACQ2106_ACQ425x6
                expt,dev=('qoc','ACQ2106_065') # ACQ2106_ACQ480x4
                #expt,dev=('qmr1','ACQ2106_068') # ACQ2106_ACQ480x4
                #for expt,dev in [('qmb','ACQ1001_072'),('qxt1','ACQ2106_070'),('qoc','ACQ2106_064')]:
                try:
                    def force(node,val):
                        node.no_write_shot = False
                        node.write_once = False
                        node.record = val
                    print(dev)
                    MDSplus.Tree(expt).createPulse(shot)
                    t=MDSplus.Tree(expt,shot)
                    A=t.HARDWARE.getNode(dev)
                    if dev.startswith('ACQ2106'):
                        force(A.MODULE1.TRIG_MODE, 'TRANSIENT')
                    if A.MODULE1.record == '_ACQ480':
                        force(A.CLOCK,20000000)
                    R = t.HARDWARE.RPTRIG.com
                    R.disarm()
                    R.gate([])
                    R.gate2([])
                    R.invert([])
                    print(R.makeSequence(0))
                    R.arm()
                    print('RP ready')
                    force(A.TRIGGER.POST,int(1e7))
                    A.init()
                    print('ACQ initialized')
                    A.arm()
                    print('ACQ armed, wait 2 sec')
                    try:
                        time.sleep(2)
                        R.trig()
                        print('RP fired, wait 5 sec')
                        time.sleep(5)
                        print('ACQ storing')
                        A.store()
                    finally:
                        A.deinit()
                        print('M1C1: ssegse= %d'%A.getchannel(1).getNumSegments())
                except:
                     import traceback
                     traceback.print_exc()
        elif sys.argv[1]=='test480':
            run480()
        elif sys.argv[1]=='test425':
            run425()
        elif sys.argv[1]=='test420':
            run420()
        elif sys.argv[1]=='testmgtdram':
            runmgtdram(*sys.argv[2:])
    if 0:
        Tests.simulate = True
        t=Tests()
        t.setUpClass()
        t.test425X2Normal()
        t.test425X2Stream()
        #t.test480X4Stream()
        #t.test480Normal()
        import matplotlib.pyplot as pp
        t = MDSplus.Tree('test', 1007)
        rec = t.ACQ425X2_M2.getchannel(1).record
        pp.plot(rec.dim_of()[:10000],rec.data()[:10000])
        pp.show()
