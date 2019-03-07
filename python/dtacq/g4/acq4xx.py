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
# - server side demuxing for normal oeration not reliable, why?
# - find a way to detemine when the device is armed in mgt(dram)
# - properly check if the clock is in range
#  + ACQ480: maxADC=80MHz, maxBUS=50MHz, minBUS=10MHz, maxFPGA_FIR=25MHz
#
debug = 0
#import pdb
import os,time,sys,io,MDSplus,threading,re,numpy,socket,inspect
if sys.version_info<(3,):
    from Queue import Queue
else:
    from queue import Queue
    xrange = range
_state_port    = 2235
_bigcat_port   = 4242
_aggr_port     = 4210
_sys_port      = 4220
_data_port     = 53000
_mgt_log_port  = 53990
_ao_oneshot    = 54201
_ao_oneshot_re = 54202
class _es_marker:
    """hexdump
    0000000 llll hhhh f156 aa55 LLLL HHHH f156 aa55
    0000010 0000 0000 f15f aa55 LLLL HHHH f15f aa55
    *
    0000040
    -----------------------------------------------
    w00     llll   current memory_row_index (low word)
    w01     hhhh   current memory_row_index (high word)
    w02,06  f156   marker for master module
    w03:04: aa55   static marker
    w04:08: LLLL   current sample_clock_count (low word)
    w05:08: HHHH   current sample_clock_count (high word)
    w10:04: f15f   marker for slave module
    """
    index_l= slice( 0,   1,1)
    index_h= slice( 1,   2,1)
    master = slice( 2,   8,4)
    static = slice( 3,   8,4) # 8 should be None but modules are not always aligned
    count_l= slice( 4,None,8)
    count_h= slice( 5,None,8)
    slave  = slice(10,None,4)
    class uint16:
        master = 0xf156
        static = 0xaa55
        slave  = 0xf15f
    class int16:
        master = 0xf156-(1<<16)
        static = 0xaa55-(1<<16)
        slave  = 0xf15f-(1<<16)

def s(b): return b if isinstance(s,str)   else b.decode('ASCII')
def b(s): return s if isinstance(s,bytes) else bytes(s,'ASCII')

###----------------
### nc base classes
###----------------

class nc(object):
    """
    Core n-etwork c-onnection to the DTACQ appliance. All roads lead here (Rome of the DTACQ world).
    This class provides the methods for sending and receiving information/data through a network socket
    All communication with the D-TACQ devices will require this communication layer
    """
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
        self._chain = None
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
    def read(self,format='int16'):
        """
        Reads out channel data (from the buffer array) in chunks, then returns a single array of data.
        """
        ans = [buf for buf in self.chunks()]
        return numpy.frombuffer(b''.join(ans),format)

    def stop(self): self._stop.set()

    def lines(self,timeout=60):
        """
        Reads out channel data (from the buffer array) in chunks, then returns a single array of data.
        """
        sock= self.sock
        sock.settimeout(timeout)
        try:
            line = ''
            while not self._stop.is_set():
                buf = sock.recv(1)
                if len(buf)==0: break
                line += buf
                if buf=='\n':
                    yield line
                    line = ''
        finally:
            sock.close()

    def chunks(self,nbytes=4096,timeout=10):
        """
        Reads out channel data (from the buffer array) in chunks, then returns a single array of data.
        """
        sock= self.sock
        sock.settimeout(timeout)
        try:
            while not self._stop.is_set():
                buf = sock.recv(nbytes)
                if len(buf)==0: break
                yield buf
        finally:
            sock.close()

    def buffer(self,nbytes=4194304,format='int16'):
        """
        Reads out channel data (from the buffer array) in chunks, then returns a single array of data.
        """
        sock= self.sock
        try:
            while not self._stop.is_set():
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

    def _com(self,cmd,ans=False,timeout=5):
        if isinstance(cmd,(list,tuple)):
            cmd = '\n'.join(cmd)
        if not (self._chain is None or ans):
            self._chain.append(cmd)
            return
        def __com(cmd):
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                sock.connect(self._server)
                if debug>=3: print(cmd)
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
        if ans: return __com(cmd)
        __com(cmd)

    def _exe(self,cmd,value=None):
        """
        Print the command and return object assignment
        """
        res = self(cmd,value)
        if len(res)>0: print(res)
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
            if res.startswith('ERROR:'):
                raise Exception(res)
            if res.startswith(cmd):
                res = res[len(cmd)+1:]
            return res.strip()
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
    def data(self,eslo=1,eoff=0,rang=None):
        return self.raw(rang)*eslo+eoff
    def dump(self,out=sys.stdout):
        for buf in self.lines(60):
            if out is not None:
                out.write(s(buf))
                if isinstance(out,file):
                    out.flush()
    def async(self,dump=None):
        if dump is True:
            args = [io.BytesIO()]
        else:
            args = [dump]
        thread = threading.Thread(target=self.dump,args=args,name='%s.async'%repr(self))
        if dump:
                thread.out = args[0]
        thread.start()
        return thread

class channel(nc):
    """
    MDSplus-independent way of opening a data channel to stream out data from the carrier.
    Call it independently as: ch = channel([num],host)
    """
    def __str__(self):
        return "Channel(%s,%d)"%self._server
    def __init__(self,ch,server='localhost'):
        super(channel,self).__init__((server,_data_port+ch))

class bigcat(nc):
    """
    MDSplus-independent class
    ACQ400 FPGA class purposed for fetching data from participating modules
    """
    def __init__(self,server='localhost'):
        super(bigcat,self).__init__((server,_bigcat_port))

class logger(threading.Thread):
    """
    This is a background subprocess (thread). Listens for the status updates provided by the log port: _state_port (via the carrier)
    """
    _state_str = ['STOP','ARM','PRE','POST','FIN1','FIN2']
    loggers = {}
    _com = None
    _re_state = re.compile("([0-9]+) ([0-9]+) ([0-9]+) ([0-9]+) ([0-9]+)")
    def __new__(cls, host='localhost',*arg,**kwarg):
        if host in logger.loggers:
            return logger.loggers[host]
        return super(logger,cls).__new__(cls)
    def __init__(self, host='localhost',debug=0):
        if host in self.loggers: return
        self._stop = threading.Event()
        self.loggers[host] = self
        super(logger,self).__init__(name=host)
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
                    if self.debug>1: print(msg)
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
                    if self.debug==1: print(match.group(0))
                    statid = int(match.group(1))
                    stat=statid if statid>5 else logger._state_str[statid]
                    self._state.add(stat)
                    self._pre     = int(match.group(2))
                    self._post    = int(match.group(3))
                    self._elapsed = int(match.group(4))
                    self._reserved= int(match.group(5))
                    self.cv.notify_all()
        finally:
            del(self.loggers[self.name])
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
        if not state in logger._state_str:
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
### nc properties
###--------------

class _property_str(object):
    """
    MDSplus-independent class
    """
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
    def __call__(self,cmd,*args):
        # allows for nextes structures, e.g. acq.SYS.CLK.COUNT
        return self._parent('%s:%s'%(self.__class__.__name__,str(cmd)),*args)
    def __str__(self):
        if isinstance(self._parent,_property_grp):
            return '%s:%s'%(str(self._parent),self.__class__.__name__)
        return self.__class__.__name__
    def __repr__(self):
        return '%s:%s'%(repr(self._parent),self.__class__.__name__)
    def __init__(self, parent,doc=None):
        self._parent = parent
        if doc is not None: self.__doc__ = doc
        for k,v in self.__class__.__dict__.items():
            if isinstance(v,type) and issubclass(v,(_property_grp,)):
                self.__dict__[k] = v(self)

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
        return '%s%s%s'%(str(self),self._idxsep,self._format_idx%idx)
    def set(self,idx,value):
        return '%s %s'%(self.get(idx),self._format%value)
    def __getitem__(self,idx):
        return self._cast(self._parent('%s%s%s'%(self.__class__.__name__,self._idxsep,self._format_idx%idx)).strip(self._strip))
    def __setitem__(self,idx,value):
        return self._parent('%s%s%s %s'%(self.__class__.__name__,self._idxsep,self._format_idx%idx,self._format%value))
    def setall(self,value):
        return [self.set(i+1,v) for i,v in enumerate(value)]


class _property_cnt(_property_grp):
    """
    MDSplus-independent class
    """
    def reset(self):  self.RESET=1;self.RESET=0;
    RESET = _property_str('RESET')
    COUNT = _property_int('COUNT', 1)
    FREQ  = _property_int('FREQ',  1)
    ACTIVE= _property_float('ACTIVE',1)

###-----------------
### dtacq nc classes
###-----------------

class dtacq(nc):  # HINT: dtacq
    """
    MDSplus-independent
    """
    _excutables = ['acqcmd','get.site','reboot','run0','soft_transient','soft_trigger','streamtonowhered']
    _help = None
    _help2 = None
    def __init__(self,server,site):
        super(dtacq,self).__init__((server,_sys_port+site))
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
        v = super(dtacq,self).__getattribute__(name)
        if name.startswith('__') and name.endswith('__'): return v
        if name in ('_server','_com','_getfromdict'): return v
        if isinstance(v,type):
            if issubclass(v,(_property_grp,)):
                return v(self)
            elif issubclass(v,(_property_str,)):
                return v(self).__get__(self,self.__class__)
        return v
    def __getattr__(self,name):
        try:   return self._getfromdict(name)
        except AttributeError:
            return self(name)
    def __setattr__(self,name,value):
        """
        Checks if it's any part of a super/class, and if it isn't, it assumes the netcat entry
        """
        try:
            super(dtacq,self).__getattribute__(name)
            super(dtacq,self).__setattr__(name,value)
        except AttributeError:
            if not dtacq._callerisinit('__setattr__'):
                return self(name,value)
            return super(dtacq,self).__setattr__(name,value)
    @property
    def settings2(self):
        h2 = self.help2.items()
        h2.sort()
        settings = {}
        for k,v in h2:
            if k!='help' and k!="help2" and v[0].startswith('r'):
                res = self(k)
                try:     settings[k] = int(res)
                except ValueError:
                 try:    settings[k] = map(int,res.split(' ',1)[0].split(','))
                 except ValueError: settings[k] = res
        return settings
    @property
    def settings(self):
        h = self.help
        h.sort()
        settings = {}
        for k in h:
            if k!='help' and k!="help2" and k!=k.upper() and not k.startswith('set') and k not in self._excutables:
                res = self(k)
                try:     settings[k] = int(res)
                except ValueError:
                 try:    settings[k] = map(int,res.split(' ',1)[0].split(','))
                 except ValueError: settings[k] = res
        return settings
    @property
    def help(self):
        if self._help is None:
            self._help = self('help').split('\n')
        return self._help
    @property
    def help2(self):
        if self._help2 is None:
            res = self('help2').split('\n')
            ans = {}
            for i in range(0,len(res),2):
                name_mod = tuple(map(str.strip,res[i].split(' : ')))
                ans[name_mod[0]] = (name_mod[1],res[i+1].strip())
            self._help2 = ans
        return self._help2
    site    = _property_int('site')

class carrier(dtacq):
    """
    MDSplus-independent class purposed to provide controls for carrier-wide knobs
    Interface layer to the DTACQ MDSplus device knobs.
    """
    def mgt(self,i):     return mgt(i,self._server[0])
    def channel(self,i): return channel(i,self._server[0])
    def __init__(self,server='localhost'):
        super(carrier,self).__init__(server,0)
        for k,v in self.__class__.__dict__.items():
            if isinstance(v,type):
                if issubclass(v,(_property_grp,)):
                    self.__dict__[k] = v(self)
        self.log = logger(server)
#    def __del__(self):
#        self.log.stop()

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
            if debug: print(self.log._state,"no timeout" if timeout is None else time.time()-timeout,self.state,self.log.on,ok[0])
        return self.log.on and ok[0]

    def wait4state(self,state,timeout=None):
        if not state in logger._state_str:
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
        waitstates = ('STOP','CLEANUP')
        def condition(self,ok):
            if not self.state['state'] in waitstates: return False
            if 'ARM' in self.log._state:
                self.log._state.remove('ARM')
            return True
        def breakcond(self,ok):
            if 'ARM' in self.log._state or not self.state['state'] in waitstates: return True
            self.TRANSIENT.SET_ARM = 1
            return False
        return self.wait(timeout,condition,breakcond)

    def wait4post(self,post,timeout=None):
        waitstates = ('ARM','PRE','POST')
        def condition(self,ok):
            if not self.state['state'] in waitstates or self.state['post']>=post: return False
            if 'STOP' in self.log._state:
                self.log._state.remove('STOP')
            return True
        def breakcond(self,ok):
            state = self.state
            return ('STOP' in self.log._state) or state['state']=='STOP' or state['post']>=post
        return self.wait(timeout,condition,breakcond)

    def wait4abort(self,timeout=None):
        self.streamtonowhered = 'stop'
        def condition(self,ok):
            if self.state['state'] == 'STOP': return False
            self.log._state.clear()
            self.TRANSIENT.SET_ARM = 1
            self.set_arm()
            self.TRANSIENT.SET_ABORT = 1
            self.set_abort()
            return True
        def breakcond(self,ok):
            if ('STOP' in self.log._state) or (self.state['state'] == 'STOP'): return True
            self.TRANSIENT.SET_ABORT = 1
            return False
        return self.wait(timeout,condition,breakcond)

    def __call__(self,cmd,value=None,site=0):
        if len(cmd.strip())==0: return ""
        if site>0: cmd = 'set.site %d %s'%(site,cmd,)
        return super(carrier,self).__call__(cmd,value)

    def _state(self,cmd):
        ans = self(cmd)
        if not ans: return {'state':'CLEANUP'}
        try:    res = map(int,ans.split(' '))
        except ValueError: return {'state':'CLEANUP'}
        stat=res[0] if res[0]>5 else logger._state_str[res[0]]
        return {'state':stat,'pre':res[1],'post':res[2],'elapsed':res[3],'reserved':tuple(res[4:])}
    def run0(self,*args):
        """
        Initializing the aggregator: feeds active sites to aggregator
        """
        if len(args)==0: return self('run0')
        return self( 'run0\nrun0 %s'%(','.join(map(str,args)),))

    def reboot(self):
        """reboots carrier ala sync;sync;reboot (3210 is required as argument)"""
        self('reboot 3210')
    live_mode        = _property_int('live_mode',doc="Streaming: CSS Scope Mode {0:off, 1:free-run, 2:pre-post}")
    live_pre         = _property_int('live_pre',doc="Streaming: pre samples for pre-post mode")
    live_post        = _property_int('live_post',doc="Streaming: post samples for pre-post mode")
    @property
    def state(self):           return self._state('state')
    model   = _property_str('model',ro=True)
    @property
    def transient_state(self): return self._state('transient_state')
    def acq480_force_training(self,_set=True): self('acq480_force_training',1 if _set else 0);return self
    def soft_trigger(self):   self('soft_trigger');return self
    def set_arm(self):        self('set_arm');return self
    def set_abort(self, keep_repeat=0):
        """Use keep_repeat 1 to only abort the arming on a single sequence"""
        if keep_repeat == 0: self.TRANSIENT.REPEAT=0
        self('set_abort');return self
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
    def fit_rtm_translen_to_buffer(self): self('fit_rtm_translen_to_buffer');return self
    aggregator= _property_str('aggregator',ro=True)
    streamtonowhered = _property_str('streamtonowhered',doc='start|stop')
    bufferlen = _property_int('bufferlen',1,'kernel buffer length')
    MODEL     = _property_int('MODEL',ro=True)
    NCHAN     = _property_int('NCHAN',ro=True)
    shot      = _property_int('shot')
    """Gate Pulse Generator"""
    gpg_clk   = _property_list('gpg_clk')
    gpg_enable= _property_int ('gpg_enable')
    gpg_mode  = _property_int ('gpg_mode')
    gpg_sync  = _property_list('gpg_sync')
    gpg_trg   = _property_list('gpg_trg')
    class SIG(_property_grp):
        ZCLK_SRC= _property_str('ZCLK_SRC', doc='INT33M, CLK.d0 - CLK.d7')
        class FP(_property_grp):
            CLKOUT= _property_str('CLKOUT')
            SYNC  = _property_str('SYNC')
            TRG   = _property_str('TRG')
        class SRC(_property_grp):
            class CLK (_property_idx): pass
            class SYNC(_property_idx): pass
            class TRG (_property_idx): pass
        class CLK_EXT (_property_cnt): pass
        class CLK_MB  (_property_cnt):
            FIN = _property_int('FIN',doc='External input frequency')
            SET = _property_int('SET',doc='Set desired MB frequency')
        class CLK_S1  (_property_grp):
            FREQ = _property_int('FREQ')
        class CLK_S2  (_property_grp):
            FREQ = _property_int('FREQ')
        class CLK_S3  (_property_grp):
            FREQ = _property_int('FREQ')
        class CLK_S4  (_property_grp):
            FREQ = _property_int('FREQ')
        class CLK_S5  (_property_grp):
            FREQ = _property_int('FREQ')
        class CLK_S6  (_property_grp):
            FREQ = _property_int('FREQ')
        class EVT_EXT (_property_cnt): pass
        class EVT_MB  (_property_cnt): pass
        class EVT_S1  (_property_cnt): pass
        class EVT_S2  (_property_cnt): pass
        class SYN_EXT (_property_cnt): pass
        class SYN_MB  (_property_cnt): pass
        class SYN_S1  (_property_cnt): pass
        class SYN_S2  (_property_cnt): pass
        class TRG_MB  (_property_cnt): pass
        class TRG_S1  (_property_cnt): pass
    class SYS(_property_grp):
        class CLK(_property_grp):
            FPMUX = _property_str('FPMUX',doc="OFF, XCLK, FPCLK, ZCLK")

    class TRANSIENT(_property_grp):
        PRE          = _property_int('PRE')
        POST         = _property_int('POST')
        OSAM         = _property_int('OSAM',doc='Subrate data monitoring')
        SOFT_TRIGGER = _property_int('SOFT_TRIGGER',doc='Initial soft_trigger() call? (0 or 1)')
        REPEAT       = _property_int('REPEAT',doc='Number of shots before set_abort is called')
        REPEAT       = _property_int('REPEAT',doc='Number of shots before set_abort is called')
        DELAYMS      = _property_int('DELAYMS',doc='Number of milliseconds to wait befor soft trigger')
        SET_ARM      = _property_str('SET_ARM',doc='put carrier in armed state; go to ARM')
        SET_ABORT    = _property_str('SET_ABORT',doc='aborts current capture; go to STOP')
    def TRANSIENT_ALL(self,pre=50000,post=50000,osam=1,soft_out=1,repeat=0,demux=None):
        self._com('\n'.join([
            'TRANSIENT:PRE %d'          % pre,
            'TRANSIENT:POST %d'         % post,
            'TRANSIENT:OSAM %d'         % osam,
            'TRANSIENT:SOFT_TRIGGER %d' % (1 if soft_out else 0),
            'TRANSIENT:REPEAT %d'       % repeat
            ]))
        self.transient(pre=pre,post=post,osam=osam,soft_out=soft_out,demux=demux)

    def _init(self,ext,mb_fin,mb_set,pre,post,soft_out,demux=None,shot=1):
        if not self.wait4abort(timeout=30): raise Exception('Could not abort.')
        if not shot is None: self.shot = shot
        self._setup_clock(ext,mb_fin,mb_set)
        #self.chainstart()
        self._setup_trigger(pre,post,soft_out,demux)
        #self.chainsend()

    def _setup_clock(self,ext,mb_fin,mb_set):
        if ext:
            self.SYS.CLK.FPMUX = 'FPCLK'
            if debug: print('Using external clock source')
        else:
            self.SIG.ZCLK_SRC = 0
            self.SYS.CLK.FPMUX = 'ZCLK'
            if debug: print('Using internal clock source')
        self.SIG.SRC.CLK[0] = 0
        self.SIG.SRC.CLK[1] = 0 #MCLK
        self.SIG.CLK_MB.FIN = mb_fin
        self.SIG.CLK_MB.SET = mb_set # = clk * clkdiv

    def _setup_trigger(self,pre,post,soft_out,demux=None):
        # setup Front Panel TRIG port
        self.SIG.FP.TRG = 'INPUT'
        # setup signal source for external trigger and software trigger
        self.SIG.SRC.TRG[0] = 0 # 'EXT'
        self.SIG.SRC.TRG[1] = 0 # 'STRIG'
        soft_out = 1 if pre>0 else soft_out
        self.live_mode = 2 if pre else 1
        self.live_pre  = pre
        self.live_post = post
        self.TRANSIENT_ALL(pre=pre,post=post,osam=1,soft_out=soft_out,demux=demux)
        if debug: print('PRE: %d, POST: %d'%(pre,post))

class acq1001(carrier):
    """
    MDSplus-independent knobs specific to the 2106.
    """
    _mclk_clk_min = 4000000

class acq2106(carrier):
    """
    MDSplus-independent knobs specific to the 2106.
    """
    CONTINUOUS       = _property_str('CONTINUOUS',ro=True)
    CONTINUOUS_STATUS= _property_str('CONTINUOUS:STATUS',ro=True)
    class SYS(carrier.SYS):
        class CLK(carrier.SYS.CLK):
            BYPASS       = _property_int('BYPASS')
            CONFIG       = _property_str('CONFIG')
            LOL          = _property_int('LOL',1,doc='Jitter Cleaner - Loss of Lock')
            #CB1          = _property_int('CB1')
            #CB2          = _property_int('CB2')
            OE_CLK1_ZYNQ = _property_int('OE_CLK1_ZYNQ')
            class Si5326(_property_grp):
                INTCLK_SET = _property_str('INTCLK_SET')
            DIST_CLK_SRC = _property_str('DIST_CLK_SRC',doc='0:HDMI, 1:Si5326')
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

    def _setup_clock(self,ext,mb_fin,mb_set):
        iterations = 10
        while True:
            if debug: print('%s: setting up clock %d'%(self._server[0],11-iterations))
            set_bypass = mb_fin == mb_set
            is_bypass  = self.SYS.CLK.CONFIG == '1-1_bypass'
            if set_bypass != is_bypass:
                self.SYS.CLK.BYPASS       = int(set_bypass)
                time.sleep(5)
            #self.chainstart()
            self.SYS.CLK.OE_CLK1_ZYNQ = 1
            self.SYS.CLK.DIST_CLK_SRC = 1
            super(acq2106,self)._setup_clock(ext,mb_fin,mb_set)
            #self.chainsend()
            if  self.SYS.CLK.CONFIG[0] == '-' or iterations<=0: break
            iterations -= 1

class module(dtacq):
    _clkdiv_adc  = 1
    _clkdiv_fpga = 1
    is_master = False
    def __init__(self,server,site=1):
        super(module,self).__init__(server,site)
        self.is_master = site==1
    data32  = _property_int('data32')
    active_chan = _property_int('active_chan',1)
    clkdiv      = _property_int('clkdiv')
    CLKDIV      = _property_int('CLKDIV')
    clk         = _property_list('clk')
    sync        = _property_list('sync')
    trg         = _property_list('trg')
    sysclkhz    = _property_int('sysclkhz',1)
    model       = _property_str('model',ro=True)
    MODEL       = _property_int('MODEL',ro=True)
    NCHAN       = _property_int('NCHAN',ro=True)
    nchan       = _property_int('nchan',ro=True)
    shot        = _property_int('shot')
    class SIG(_property_grp):
        class CLK_COUNT(_property_cnt): pass
        class sample_count(_property_cnt): pass
        class SAMPLE_COUNT(_property_cnt):
            RUNTIME = _property_str('RUNTIME')
    class AI(_property_grp):
        class CAL(_property_cnt):
            ESLO = _property_list_f('ESLO')
            EOFF = _property_list_f('EOFF')
    CLK          = _property_str('CLK',doc='1 for external, 0 for internal')
    CLK_DX       = _property_str('CLK:DX',doc='d0 through d7')
    CLK_SENSE    = _property_str('CLK:SENSE',doc='1 for rising, 0 for falling')
    @property
    def CLK_ALL(self):  return self.clk
    @CLK_ALL.setter
    def CLK_ALL(self,value):
        self.CLK,self.CLK_DX,self.CLK_SENSE = tuple(str(e) for e in value[:3])
    TRG          = _property_str('TRG', doc='enabled or disabled')
    TRG_DX       = _property_str('TRG:DX',doc='d0 through d7')
    TRG_SENSE    = _property_str('TRG:SENSE',doc='1 for rising, 0 for falling')
    @property
    def TRG_ALL(self):  return self.trg
    @TRG_ALL.setter
    def TRG_ALL(self,value):
        self.TRG,self.TRG_DX,self.TRG_SENSE = tuple(str(e) for e in value[:3])
    EVENT0       = _property_str('EVENT0',doc='enabled or disabled')
    EVENT0_DX    = _property_str('EVENT0:DX',doc='d0 through d7')
    EVENT0_SENSE = _property_str('EVENT0:SENSE',doc='1 for rising, 0 for falling')
    @property
    def EVENT0_ALL(self):  return self.event0
    @EVENT0_ALL.setter
    def EVENT0_ALL(self,value):
        self.EVENT0,self.EVENT0_DX,self.EVENT0_SENSE = tuple(str(e) for e in value[:3])
    EVENT1       = _property_str('EVENT1',doc='enabled or disabled')
    EVENT1_DX    = _property_str('EVENT1:DX',doc='d0 through d7')
    EVENT1_SENSE = _property_str('EVENT1:SENSE',doc='1 for rising, 0 for falling')
    @property
    def EVENT1_ALL(self):  return self.event1
    @EVENT1_ALL.setter
    def EVENT1_ALL(self,value):
        self.EVENT1,self.EVENT1_DX,self.EVENT1_SENSE = tuple(str(e) for e in value[:3])
    @property
    def data_scales(self):  return self.AI.CAL.ESLO[1:]
    @property
    def data_offsets(self): return self.AI.CAL.EOFF[1:]

    def _init(self,shot=None):
        if not shot is None:
            self.shot = shot
        self.data32 = 0

    def _init_master(self,pre,soft):
        self.SIG.sample_count.RESET=1
        self.TRG_ALL    = (1,1 if pre|soft else 0,1)
        self.EVENT0_ALL = (1 if pre else 0,soft,1)
        self.CLK_ALL    = (1,1,1)

class acq425(module):
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
    MAX_KHZ = _property_int('MAX_KHZ',ro=True)

    def _init_master(self,pre,soft,clkdiv):
        #self.chainstart()
        super(acq425,self)._init_master(pre,soft)
        self.EVENT1_ALL  = (0,0,0)
        #self.chainsend()
        time.sleep(1)
        self.CLKDIV = clkdiv

    def _init(self,gain=None,shot=None):
        self.chainstart()
        super(acq425,self)._init(shot)
        if not gain is None: self._com(self.GAIN.setall(  gain  ))
        self.chainsend()


class acq480(module):
    """
    MDSplus-independent set of controlable knobs specific to the ACQ480 module.
    """
    def get_skip(self):
        fpga = self._clkdiv_fpga
        if   fpga==10:
            delay=9
        elif fpga==4:
            delay=0
        else:
            delay=0
        return delay
    class ACQ480(_property_grp):
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
    RGM          = _property_str('RGM', doc='0:OFF,2:RGM,3:RTM')
    RGM_DX       = _property_str('RGM:DX',doc='d0 through d7')
    RGM_SENSE    = _property_str('RGM:SENSE',doc='1 for rising, 0 for falling')
    @property
    def RGM_ALL(self):  return self.rgm
    @RGM_ALL.setter
    def RGM_ALL(self,value):
        value = tuple(str(e) for e in value[:3])
        self('RGM %s\nRGM:DX %s\nRGM:SENSE %s'%value)
    RTM_TRANSLEN = _property_int('RTM_TRANSLEN',doc='samples per trigger in RTM; should fill N buffers')
    class SIG(module.SIG):
        class CLK(_property_grp):
            TRAIN_BSY = _property_int('TRAIN_BSY',0,doc='Clock sync currently training')

    es_enable    = _property_int('es_enable',0,'data will include an event sample')
    JC_LOL       = _property_int('JC_LOL',1,doc='Jitter Cleaner - Loss of Lock')
    JC_LOS       = _property_int('JC_LOS',1,doc='Jitter Cleaner - Loss of Signal')
    acq480_loti  = _property_int('acq480_loti',1,doc='Jitter Cleaner - Loss of Time')
    train        = _property_int('train',1,doc='Jitter Cleaner - Loss of Time')
    #_num_channels = 8
    _FIR_DECIM = [1,2,2,4,4,4,4,2,4,8,1]
    def _max_clk_dram(self,num_modules): # DRAM: _max_clk = 900M / Nmod / 8 / 2
        limit = [50000000,28000000,18000000,14000000,11000000,9000000][num_modules-1]
        return limit
    def _max_clk(self,num_modules):
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
    def _trig_mode(self,mode=None):
        if mode is None: return 0
        elif isinstance(mode,str):
            mode = mode.upper()
            if   mode == 'RGM': return 2
            elif mode == 'RTM': return 3
            else:               return 0

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
        super(acq480,self)._init_master(pre,soft)
        if mode == 3 and not translen is None:
            self.rtm_translen = translen*self._clkdiv_fpga
        self.EVENT1_ALL   = (ese,soft,ese)
        self.RGM_ALL      = (mode,soft,1)
        self.es_enable    = ese
        self.ACQ480.FIR[1] = int(fir==0)
        self.ACQ480.FIR[1] = fir
        self.chainsend()

class ao420(module):
    class G(_property_idx):
        _cast = int
        _idxsep=''
    class D(_property_idx):
        _cast = int
        _idxsep=''
    class AO(_property_grp):
        class GAIN(_property_grp):
            class CH(_property_idx):
                _strip='x'
                _cast = int
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
        self.G[ch] = round(gain*32767/100.)
    def set_offset(self,ch,offset):
        offset = min(100,max(-100,offset))
        self.D[ch] = round(offset*32767/100.)

    def loadSig(self,bitstring):
        """
        Port 54201: Oneshot
        Port 54202: Oneshot + rearm
        """
        data = nc((self._server[0],_ao_oneshot))
        data._com(bitstring,timeout=3+len(bitstring)//1000000)

    def _arm(self,s1,s2,s3,s4):
        self.loadSig(self.sigCong(s1,s2,s3,s4))
    def _init(self,gain,offset,shot=None):
        self.chainstart()
        super(ao420,self)._init(shot)
        for i in range(4):
            self.set_gain_offset(i+1,gain[i],offset[i])
        self.chainsend()
    def _init_master(self,soft,clkdiv):
        self.chainstart()
        super(ao420,self)._init_master(0,soft)
        self.CLKDIV = clkdiv
        self.EVENT1_ALL  = (0,0,0)
        self.chainsend()

class mgt(dtacq):
    def __init__(self,port=0,server='localhost'):
        super(mgt,self).__init__(server,port+12)
        self.port = port
    spad = _property_int('spad')
    @property
    def aggregator(self):
        sites = self('aggregator').split(' ')[1].split('=')[1]
        return [] if sites=='none' else [int(v) for v in sites.split(',')]
    @aggregator.setter
    def aggregator(self,sites):
        self('aggregator sites=%s'%(','.join([str(s) for s in sites])))
    def init(self,sites):
        self.spad = 0
        self.aggregator = sites

class mgt_run_shot_logger(threading.Thread):
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
        self.mgt = nc((host,_mgt_log_port))
        self._busy_lock  = threading.Lock()
        self._error_lock = threading.Lock()
        self._error = []
        self._debug = True#bool(debug)
        if autostart: self.start()
    def debug(self,line):
        if self._debug:
            sys.stdout.write(line)
            sys.stdout.flush()
    def run(self):
        re_busy  = re.compile('^BUSY pid ([0-9]+) SIG:SAMPLE_COUNT:COUNT ([0-9]+)')
        re_idle  = re.compile('^.* SIG:SAMPLE_COUNT:COUNT ([0-9]+)')
        re_error = re.compile('^ERROR: (.*)')
        for line in self.mgt.chunks():
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
        data = inst.__getattr__(self._name).record.data()
        if self._fun is None: return data
        return self._fun(data)
    def __set__(self,inst,value):
        inst.__getattr__(self._name).record=value
    def __init__(self,name,fun=None):
        self._name = name
        self._fun  = fun

###------------------------
### Private MDSplus Devices
###------------------------

class _DTACQ(MDSplus.Device):
    """
    MDSplus-dependent superclass covering D-tAcq device types.
    Interface layer between tree and DAQ appliance.
    """
    _nc = None
    @property
    def settings(self): return self.nc.settings
    def settings_write(self,filepath):
        with open(filepath,'w') as f:
            items = self.settings.items();items.sort()
            for kv in items:
                f.write("%-21s = %s\n"%kv)
    def settings_print(self):
        items = self.settings.items();items.sort()
        for kv in items:
            print("%s: %s"%kv)

class _CARRIER(_DTACQ):  # HINT: _CARRIER
    """
    Class that can set the various knobs (PVs) of the D-TACQ module. PVs are set from the user tree-knobs.
    """
    _nc_class = carrier
    _demux = None
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
      {'path': ':CLOCK',          'type': 'numeric',  'valueExpr':'head._max_clk', 'options': ('no_write_shot',)},
    ]

    @classmethod
    def _setParts(cls,module,num_modules=1,mgt=None):
        if not module is _AO420:
            cls.parts = _CARRIER.parts + [
                {'path': ':ACTIONSERVER:STORE',          'type': 'ACTION',  'options':('no_write_shot','write_once'), 'valueExpr':'Action(node.DISPATCH,node.TASK)'},
                {'path': ':ACTIONSERVER:STORE:DISPATCH', 'type': 'DISPATCH','options':('no_write_shot','write_once'), 'valueExpr':'Dispatch(head.actionserver,"STORE",51)'},
                {'path': ':ACTIONSERVER:STORE:TASK',     'type': 'TASK',    'options':('no_write_shot','write_once'), 'valueExpr':'Method(None,"store",head)'},
                {'path': ':ACTIONSERVER:DEINIT',         'type': 'ACTION',  'options':('no_write_shot','write_once'), 'valueExpr':'Action(node.DISPATCH,node.TASK)'},
                {'path': ':ACTIONSERVER:DEINIT:DISPATCH','type': 'DISPATCH','options':('no_write_shot','write_once'), 'valueExpr':'Dispatch(head.actionserver,"DEINIT",31)'},
                {'path': ':ACTIONSERVER:DEINIT:TASK',    'type': 'TASK',    'options':('no_write_shot','write_once'), 'valueExpr':'Method(None,"deinit",head)'},
                {'path': ':TRIGGER:PRE',    'type': 'numeric',  'value': 0,             'options': ('no_write_shot',)},
                {'path': ':TRIGGER:POST',   'type': 'numeric',  'value': 100000,        'options': ('no_write_shot',)},
            ]
            if mgt is None:
                cls.arm   = cls._arm_acq
                cls.store = cls._store_acq
                cls.deinit= cls._deinit_acq
            else:
                cls.arm   = cls._arm_mgt
                cls.store = cls._store_mgt
                cls.deinit= cls._deinit_mgt
                cls._mgt = mgt
            cls._pre  = mdsrecord('trigger_pre',int)
            cls._post = mdsrecord('trigger_post',int)
        else:
            cls.parts = list(_CARRIER.parts)
            cls.arm = cls._arm_ao
            cls._pre  = 0
            cls._post = 0
        cls.module_class = module
        cls.num_modules = num_modules
        cls._num_channels = 0
        cls._channel_offset = []
        for i in range(num_modules):
            cls._channel_offset.append(cls._num_channels)
            prefix = ':MODULE%d'%(i+1)
            cls.parts.append({'path': prefix, 'type':'text', 'value':module.__name__, 'options': ('write_once',)})
            module._addModuleKnobs(cls,prefix)
            cls._num_channels += module._num_channels
            if i==0: module._addMasterKnobs(cls,prefix)
    @property
    def nc(self):
        """
        Serves at the nc socket interface to the carrier/modules (lower-case classes)
        """
        if self._nc is None:
            self._nc = self._nc_class(self._host)
        return self._nc

    @property
    def _max_clk(self): return self._master._max_clk

    __active_mods = None
    @property
    def _active_mods(self):
        if self.__active_mods is None:
            self.__active_mods  = tuple(i for i in self._modules if self.module(i).on)
        return self.__active_mods

    @property
    def _modules(self): return range(1,self.num_modules+1)

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
        for i in self._modules:
            if i == site: break
            offset += self.module(i)._num_channels
        return offset

    def channel(self,idx,*suffix):
        site = (idx-1)//self.module_class._num_channels+1
        return self.__getattr__('_'.join(["module%d_channel%02d"%(site,idx)]+list(suffix)))
    def _range(self,i): return self.channel(i,'range').record.deref
    def module(self,site):
        return self.module_class(self.part_dict["module%d"%site]+self.head.nid,self.tree,self,site=site)
    @property
    def _master(self): #1st module should always be present
        return self.module(1)
    __host = None
    @property
    def _host(self):
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
    _clock_src    = mdsrecord('clock_src',int)
    _clock        = mdsrecord('clock',int)
    _trigger      = mdsrecord('trigger',int)

    @property
    def state(self): return self.nc.state['state']

    @property
    def is_test(self): return self.actionserver_soft_trigger.on

    def _raw(self,mod,ch):
        com = channel(self._channel_port_offset(mod.site)+ch,self._host)
        return com.raw(mod._range(ch).slice)
    def _value(self,mod,ch):
        return mod._value(ch,self.nc.data32)
    def _dimension(self,mod,ch):
        from MDSplus import SUBTRACT,DIVIDE,UNARY_MINUS,Window,Range,SUBSCRIPT,Dimension
        win  = Window(UNARY_MINUS(self.trigger_pre),SUBTRACT(self.trigger_post,1),self.trigger)
        rang = Range(None,None,DIVIDE(1.,self.clock))
        return SUBSCRIPT(Dimension(win,rang),mod.channel(ch,'range')).setUnits('s')

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
            self.nc.reboot()
        except socket.error as e:
            raise MDSplus.DevOFFLINE(str(e))

    def init(self):
        """
        ACTION METHOD: initialize all device settings
        """
        src = self.clock_src.record
        ext = not (isinstance(src,MDSplus.TreeNode) and src.nid==self.clock_src_zclk.nid)
        mb_fin,clock = self._clock_src,self._clock
        mb_set = self._master.getMB_SET(clock)
        soft_out = self._master._soft_out
        post,pre = self._post,self._pre
        try:
            threads = [threading.Thread(target=self.nc._init, args=(ext,mb_fin,mb_set,pre,post,soft_out,self._demux,self.tree.shot))]
            for i in self._active_mods:
                threads.append(self.module(i).init_thread())
            for thread in threads: thread.start()
            for thread in threads: thread.join()
            self._master.init_master(pre,self.is_test,int(mb_set/clock))
            if debug: print('Device is initialized with modules %s'%str(self._active_mods))
        except socket.error as e:
            raise MDSplus.DevOFFLINE(str(e))
        except (SystemExit,KeyboardInterrupt): raise
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise

    def _arm_acq(self,timeout=50):
        """
        ACTION METHOD: arm the device for acq modules
        """
        timeout = int(timeout)
        try:
            if not self.nc.wait4arm(timeout):
                raise MDSplus.MDSplusERROR('not armed after %d seconds'%timeout)
        except socket.error as e:
            raise MDSplus.DevOFFLINE(str(e))

    def _arm_ao(self):
        """
        ACTION METHOD: arm the device for ao modules
        """
        try:
            for i in self._active_mods:
                self.module(i).arm()
        except socket.error as e:
            raise MDSplus.DevOFFLINE(str(e))

    def _store_acq(self,abort=False):
        if debug: print('store_bulk')
        for site in self._active_mods:
            self.module(site).store()
        self._master.store_master()
        try:
            for i in range(5):
                state = self.state
                if not (state == 'ARM' or state == 'PRE'):
                    break
                time.sleep(1)
            else:
                raise MDSplus.DevNOT_TRIGGERED
            if abort: self.nc.wait4abort()
            else:
                self.nc.wait4post(self._post)
                self.nc.wait4state('STOP')
            if self._demux is None or self._demux:
                if self._master._es_enable:
                    self._transfer_demuxed_es()
                else:
                    self._transfer_demuxed()
            else:
                self._transfer_raw()
        except socket.error as e:
            raise MDSplus.DevOFFLINE(str(e))
        except (SystemExit,KeyboardInterrupt): raise
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise

    @property
    def ESLO(self): return numpy.concatenate([self.module(i).data_scales  for i in self._modules])
    @property
    def EOFF(self): return numpy.concatenate([self.module(i).data_offsets for i in self._modules])
    class _Downloader(threading.Thread):
        def __init__(self,dev,chanlist,lock,queue):
            super(_ACQ2106._Downloader,self).__init__()
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
            chanlist[ch] = (self._range(ch).slice,self.channel(ch).on)
        return (chanlist,Queue(nchan))
    def _start_threads(self,chanlist,queue):
        """ starts up to 8 threads for pulling the data """
        lock = threading.Lock()
        threads = []
        for t in range(2):
            threads.append(self._Downloader(self,chanlist,lock,queue))
        for t in threads: t.start()
        return threads
    def _get_dim_slice(self,i0,DT,start,end,pre,mcdf=1):
        """ calculates the time-vector based on clk-tick t0, dt in ns, start and end """
        first= int(i0-pre)
        last = first + end-start-1
        dim  = MDSplus.Dimension(MDSplus.Window(first,last,self.trigger),MDSplus.Range(None,None,DT))
        dt   = int(DT)
        return dim,slice(start,end),first,self._trigger,dt
    def _store_channels_from_queue(self,dims_slice,queue):
        """
        stores data in queue and time_vector to tree with linked segments
        blk:   list range of the data vector
        dim:   dimension to the data defined by blk
        queue: dict of ch:raw data
        """
        chunksize = 100000
        ESLO,EOFF=self.ESLO,self.EOFF
        for i in range(queue.maxsize):
            ch,value,on = queue.get()
            if value is None or not on: continue
            node = self.channel(ch)
            node.setSegmentScale(MDSplus.ADD(MDSplus.MULTIPLY(MDSplus.dVALUE(),ESLO[ch-1]),EOFF[ch-1]))
            for dim,slc,i00,t0,dt in dims_slice:
                val = value[slc]
                dlen = val.shape[0]
                for seg,is0 in enumerate(range(0,dlen,chunksize)):
                    is1 = min(is0+chunksize,dlen)-1
                    i0,i1 = i00+is0,i00+is1
                    dim[0][0],dim[0][1]=i0,i1
                    d0=MDSplus.Int64(t0+i0*dt)
                    d1=MDSplus.Int64(t0+i1*dt)
                    if debug>1:  print("segment (%7.1fms,%7.1fms)"%(d0/1e6,d1/1e6))
                    node.makeSegment(d0,d1,dim,val[is0:is1+1])

    def _get_dt(self): return MDSplus.DIVIDE(MDSplus.Int64(1e9),self.clock)

    def _transfer_demuxed_es(self):
        """
        ACTION METHOD: grabs the triggered channels, opens a socket and reads out data to the respective signal node
        """
        if debug: print('transfer_demuxed_es')
        self.tree.usePrivateCtx(1)
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
        pre = self._pre
        dt = self._get_dt()
        # i0+skip to shift time vector as well, index[i]+1 to skip marker
        dims_slice = [self._get_dim_slice(i0,dt,index[i]+1+skip,index[i+1],pre) for i,i0 in enumerate(tt0)]
        self._store_channels_from_queue(dims_slice,queue)
        for t in threads: t.join()

    def _transfer_demuxed(self):
        """
        ACTION METHOD: grabs the triggered channels, opens a socket and reads out data to the respective signal node
        """
        if debug: print('transfer_demuxed')
        chanlist,queue = self._get_chanlist()
        threads = self._start_threads(chanlist,queue)
        pre = self._pre
        dlen = pre+self._post
        dims_slice = [self._get_dim_slice(0,self._get_dt(),0,dlen,pre)]
        self._store_channels_from_queue(dims_slice,queue)
        for t in threads: t.join()

    def _deinit_acq(self):
        """
        ACTION METHOD: abort and go to idle
        """
        try:
            self.nc.wait4abort(30)
        except socket.error as e:
            raise MDSplus.DevOFFLINE(str(e))

class _ACQ1001(_CARRIER):
    """
    To be used for items specific to the ACQ2106 carrier
    """
    _nc_class = acq1001

class _ACQ1002(_CARRIER):
    pass
class _ACQ2006(_CARRIER):
    pass

class _ACQ2106(_CARRIER):
    """
    To be used for items specific to the ACQ2106 carrier
    """
    _nc_class = acq2106
    _demux    = 1 # TODO: figure out why memory demuxing does not work consistently
    _mgt      = None
    def init(self):
        super(_ACQ2106,self).init()
        if self._mgt is None: return
        if self._mgt is True: return
        for port,sites in self._mgt.items():
            self.mgt(port).init(sites)
    def _dimension(self,mod,ch):
        from MDSplus import SUBTRACT,DIVIDE,UNARY_MINUS,FLOAT,Window,Range,SUBSCRIPT,Dimension
        win  = Window(UNARY_MINUS(self.trigger_pre),SUBTRACT(self.trigger_post,1),self.trigger)
        rang = Range(None,None,DIVIDE(FLOAT(self._master.clkdiv),self.clock))
        return SUBSCRIPT(Dimension(win,rang),mod.channel(ch,'range')).setUnits('s')

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
                if self.module(mod).nc.ACQ480.FIR[1] != self.module(mod+1).nc.ACQ480.FIR[1]:
                    print('INCORRECT DECIMATION VALUES')
            except (SystemExit,KeyboardInterrupt): raise
            except: pass

    def arm(self,timeout=50):
        try:   super(_ACQ2106,self).arm(timeout)
        except MDSplus.DevOFFLINE: raise
        except MDSplus.MDSplusERROR: # timed out
            if self.nc.SYS.CLK.LOL: sys.stderr.write('MCLK: Loss Of Lock!\n')
            raise

class _MODULE(MDSplus.TreeNode):  # HINT: _MODULE
    """
    MDSplus-dependent superclass covering Gen.4 D-tAcq module device types. PVs are set from the user tree-knobs.
    """
    _nc = None
    _nc_class = module
    _clkdiv_fpga = 1
    _skip = 0
    _es_enable = False
    _init_done = False
    _soft_out = False
    @classmethod
    def _addMasterKnobs(cls,carrier,prefix): pass
    @classmethod
    def _addModuleKnobs(cls,carrier,prefix):
        carrier.parts.append({'path': '%s:CHECK'%(prefix,), 'type': 'TASK', 'options': ('write_once',), 'valueExpr':'Method(None,"check",head)'})

    def __getattr__(self,name):
        partname = "module%d_%s"%(self.site,name)
        if partname in self.head.part_dict:
            return self.__class__(self.head.part_dict[partname]+self.head.nid,self.tree,self.head,site=self.site)
        return self.__getattribute__(name)

    def __setattr__(self,name,value):
        if self._init_done:
            partname = "module%d_%s"%(self.site,name)
            if partname in self.head.part_dict:
                self.head.__setattr__(partname,value)
                return
        super(_MODULE,self).__setattr__(name,value)

    def __init__(self,nid,*a,**kw):
        if isinstance(nid, _MODULE): return
        self.site = kw.pop('site')
        super(_MODULE,self).__init__(nid,*a,**kw)
        self._init_done = True

    """ Most important stuff at the top """
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
        return self.__getattr__('_'.join(['channel%02d'%(ch+self.head._channel_offset[self.site-1],)]+list(args)))
    def _idx(self,ch):
        """
        Creates the time dimension array from clock, triggers, and sample counts
        """
        from MDSplus import MINUS,SUBTRACT,Window,Dimension
        pre  = self._carrier.trigger_pre
        post = self._carrier.trigger_post
        trig = self._carrier.trigger
        win  = Window(MINUS(pre),SUBTRACT(post,1),trig)
        rang = self.channel(ch,'range')
        dim  = Dimension(win,rang)
        return dim
    """ Everything pertaining to referencing nodes and their values """
    @property
    def data_scales(self):  return self.nc.data_scales
    @property
    def data_offsets(self): return self.nc.data_offsets

    def _value(self,ch,data32=False):
        from MDSplus import ADD,MULTIPLY,dVALUE
        return ADD(MULTIPLY(dVALUE(),self.data_scales[ch-1]),self.data_offsets[ch-1])
    def _raw(self,ch):
        return self._carrier._raw(self,ch)
    def _dimension(self,ch):
        return self._carrier._dimension(self,ch)
    @property
    def _carrier(self): return self.parent # Node that points to host carrier nid
    @property
    def _trigger(self): return self._carrier._trigger
    __host=None
    @property
    def _host(self):
        if self.__host is None: self.__host = self._carrier._host
        return self.__host
    @property
    def state(self): return self._carrier.state
    @property
    def _pre(self): return int(self._carrier._pre)
    @property
    def _post(self):   return int(self._carrier._post)
    def _offset(self,i): return float(self.channel(i,'offset').record.data())
    def _range(self,i): return self.channel(i,'range').record.deref
    @property
    def _max_clk_in(self): return self.getMB_SET(self._max_clk)
    """ Action methods """
    def init(self):
        self.nc._init(*self.init_args)
    def init_thread(self):
        return threading.Thread(target=self.nc._init,args=self.init_args)

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
          if self.channel(ch).on:
            rang = self._range(ch)
            if not isinstance(rang,(Range,)) or rang.delta<1:
                                                 raise MDSplus.DevRANGE_MISMATCH
            if -pre>rang.begin:                  raise MDSplus.DevBAD_STARTIDX
            if post<rang.ending:                 raise MDSplus.DevBAD_ENDIDX
        return chs

class _ACQ425(_MODULE):
    """
    D-tAcq ACQ425ELF 16 channel transient recorder
    http://www.d-tacq.com/modproducts.shtml
    """
    _nc_class = acq425
    _num_channels = 16
    @classmethod
    def _addMasterKnobs(cls,carrier,prefix):
        _MODULE._addMasterKnobs(carrier,prefix)
        carrier.parts.append({'path': '%s:CLKDIV'%(prefix,), 'type': 'numeric', 'options': ('no_write_model',)})
    @classmethod
    def _addModuleKnobs(cls,carrier,prefix):
        _MODULE._addModuleKnobs(carrier,prefix)
        for i in range(carrier._num_channels+1,carrier._num_channels+cls._num_channels+1):
            path = '%s:CHANNEL%02d'%(prefix,i)
            carrier.parts.append({'path': path, 'type': 'SIGNAL', 'options': ('no_write_model', 'write_once',)})
            carrier.parts.append({'path': '%s:RANGE' %(path,), 'type': 'AXIS',    'valueExpr':'Range(None,None,1)',       'options': ('no_write_shot')})
            carrier.parts.append({'path': '%s:GAIN'  %(path,), 'type': 'NUMERIC', 'value':10, 'options': ('no_write_shot',),  'help':'0..12 [dB]'})
            carrier.parts.append({'path': '%s:OFFSET'%(path,), 'type': 'NUMERIC', 'value':0., 'options': ('no_write_shot',), 'help':'0,1'})

    def _gain(self,i): return float(self.channel(i,'gain').record.data())

    def getMB_SET(self,clock): return 50000000
    """ Action methods """
    def check(self,*chs):
        chs = super(_ACQ425,self).check(*chs)
        for ch in chs:
          if self.channel(ch).on:
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
    @property
    def init_args(self):
        return (
            [self._gain(ch) for ch in range(1,self._num_channels+1)],
            self.tree.shot)
    def init_master(self,pre,soft,clkdiv):
        self.nc._init_master(pre,soft,clkdiv)
    def store(self):pass
    def store_master(self):pass

class _ACQ425_1000(_ACQ425):
    _max_clk = 1000000
class _ACQ425_2000(_ACQ425):
    _max_clk = 2000000

class _ACQ480(_MODULE):
    """
    D-tAcq ACQ480 8 channel transient recorder
    http://www.d-tacq.com/modproducts.shtml
    """
    _nc_class = acq480
    _num_channels = 8
    @property
    def _max_clk(self):     return self.nc._max_clk_dram(self.parent.num_modules)
    @property
    def _es_enable(self):   return self.nc.es_enable
    @property
    def _clkdiv_adc(self):  return self.nc._clkdiv_adc(self._fir)
    @property
    def _clkdiv_fpga(self):
        try:   return int(self.clkdiv_fpga.record)
        except MDSplus.TreeNODATA:
            return self.nc._clkdiv_fpga
    @property
    def _soft_out(self):    return 0<self.nc._trig_mode(self._trig_mode)
    @property
    def _skip(self):        return self.nc.get_skip()
    @classmethod
    def _addMasterKnobs(cls,carrier,prefix):
        carrier.parts.append({'path': '%s:CLKDIV'            %(prefix,), 'type': 'numeric', 'valueExpr':'MULTIPLY(node.FIR,node.FPGA)', 'options': ('write_once','no_write_shot')})
        carrier.parts.append({'path': '%s:CLKDIV:FIR'        %(prefix,), 'type': 'numeric', 'options': ('write_once','no_write_model')})
        carrier.parts.append({'path': '%s:CLKDIV:FPGA'       %(prefix,), 'type': 'numeric', 'options': ('write_once','no_write_model')})
        carrier.parts.append({'path': '%s:FIR'               %(prefix,), 'type': 'numeric', 'value':0,    'options': ('no_write_shot',), 'help':'DECIM=[1,2,2,4,4,4,4,2,4,8,1] for FIR=[0,1,2,3,4,5,6,7,8,9,10]'})
        carrier.parts.append({'path': '%s:TRIG_MODE'         %(prefix,), 'type': 'text',    'value':'OFF','options': ('no_write_shot',), 'help':'*,"RTM","RTM"'})
        carrier.parts.append({'path': '%s:TRIG_MODE:TRANSLEN'%(prefix,), 'type': 'numeric', 'value':10000,'options': ('no_write_shot',), 'help':'Samples acquired per trigger for RTM'})

    @classmethod
    def _addModuleKnobs(cls,carrier,prefix):
        for i in range(carrier._num_channels+1,carrier._num_channels+cls._num_channels+1):
            path = '%s:CHANNEL%02d'%(prefix,i)
            carrier.parts.append({'path': path, 'type': 'SIGNAL', 'options': ('no_write_model', 'write_once',)})
            carrier.parts.append({'path': '%s:INVERT' %(path,), 'type': 'numeric', 'value':False, 'options': ('no_write_shot',), 'help':'0,1'})
            carrier.parts.append({'path': '%s:RANGE'  %(path,), 'type': 'axis',    'valueExpr':'Range(None,None,1)', 'options': ('no_write_shot')})
            carrier.parts.append({'path': '%s:GAIN'   %(path,), 'type': 'numeric', 'value':0,     'options': ('no_write_shot',), 'help':'0..12 [dB]'})
            carrier.parts.append({'path': '%s:LFNS'   %(path,), 'type': 'numeric', 'value':False, 'options': ('no_write_shot',), 'help':'0,1'})
            carrier.parts.append({'path': '%s:HPF'    %(path,), 'type': 'numeric', 'value':False, 'options': ('no_write_shot',), 'help':'0,1'})
            carrier.parts.append({'path': '%s:T50R'   %(path,), 'type': 'numeric', 'value':False, 'options': ('no_write_shot',), 'help':'0,1'})

    @property
    def _trig_mode(self):
        try:   return self.trig_mode.data().tolist()
        except MDSplus.TreeNODATA: return 0
    _trig_mode_translen = mdsrecord('trig_mode_translen',int)
    _fir         = mdsrecord('fir',int)

    def getMB_SET(self,clock):
        return self.nc._clkdiv(self._fir)*clock
    @property
    def init_args(self):
        return (
            [self._gain(ch)   for ch in range(1,self._num_channels+1)],
            [self._invert(ch) for ch in range(1,self._num_channels+1)],
            [self._hpf(ch)    for ch in range(1,self._num_channels+1)],
            [self._lfns(ch)   for ch in range(1,self._num_channels+1)],
            [self._t50r(ch)   for ch in range(1,self._num_channels+1)],
            self.tree.shot)
    def init_master(self,pre,soft,clkdiv):
        self.nc._init_master(pre,soft,self._trig_mode,self._trig_mode_translen,self._fir)
        fir  = self.nc.ACQ480.FIR.DECIM
        fpga = self.nc.ACQ480.FPGA.DECIM
        self.clkdiv_fir  = fir
        self.clkdiv_fpga = fpga
        #check clock#
        clk = self._carrier._clock
        if clk*fpga < 10000000:
            print('Bus clock must be at least 10MHz')
            raise MDSplus.DevINV_SETUP
        if clk*fpga*fir > 80000000:
            print('ADC clock cannot exceed 80MHz')
            raise MDSplus.DevINV_SETUP


    def store(self): pass
    def store_master(self): pass

    """Channel settings"""
    def _invert(self,ch): return int(self.channel(ch,'invert').record.data())
    def _setInvert(self,ch):
        self.nc.ACQ480.INVERT[ch] = self._invert(ch)
    def _gain(self,ch): return int(self.channel(ch,'gain').record.data())
    def _setGain(self,ch):
        self.nc.ACQ480.GAIN[ch] = self._gain(ch)
    def _hpf(self,ch): return int(self.channel(ch,'hpf').record.data())
    def _setHPF(self,ch):
        self.nc.ACQ480.HPF[ch] = self._hpf(ch)
    def _lfns(self,ch): return int(self.channel(ch,'lfns').record.data())
    def _setLFNS(self,ch):
        self.nc.ACQ480.LFNS[ch] = self._lfns(ch)
    def _t50r(self,ch): return int(self.channel(ch,'t50r').record.data())

class _AO420(_MODULE):  # HINT: _AO420
    """
    MDSplus-dependent superclass covering Gen.4 D-tAcq module device types. PVs are set from the user tree-knobs.
    """
    _nc_class = ao420
    _num_channels = 4
    _max_clk = 1000000
    @classmethod
    def _addMasterKnobs(cls,carrier,prefix):
        _MODULE._addMasterKnobs(carrier,prefix)
        carrier.parts.append({'path': '%s:CLKDIV'%(prefix,), 'type': 'numeric', 'options': ('no_write_model',)})
    @classmethod
    def _addModuleKnobs(cls,carrier,prefix):
        for i in range(carrier._num_channels+1,carrier._num_channels+cls._num_channels+1):
            path = '%s:CHANNEL%02d'%(prefix,i)
            carrier.parts.append({'path': path, 'type': 'SIGNAL',  'valueExpr':'SIN(MULTIPLY(Range(0,1,DIVIDE(1.,head.clock)),d2PI()))', 'options': ('no_write_shot',)})
            carrier.parts.append({'path': '%s:GAIN'   %(path,), 'type': 'numeric', 'value':100,     'options': ('no_write_shot',), 'help':'0..200%%'})
            carrier.parts.append({'path': '%s:OFFSET' %(path,), 'type': 'numeric', 'value':0,      'options': ('no_write_shot',),  'help':'-100..100%%'})

    """ Everything pertaining to referencing nodes and their values """

    def getMB_SET(self,clock): return 50000000

    def _channel(self,i): return self.channel(i).record.data()
    def _gain(self,ch):   return int(self.channel(ch,'gain').record.data())
    def _offset(self,ch): return int(self.channel(ch,'offset').record.data())

    def arm(self):
        self.nc._arm(self._channel(1),self._channel(2),self._channel(3),self._channel(4))
    @property
    def init_args(self):
        return (
            [self._gain(ch)   for ch in range(1,self._num_channels+1)],
            [self._offset(ch) for ch in range(1,self._num_channels+1)],
            self.tree.shot)
    def init_master(self,pre,soft,clkdiv):
        self.nc._init_master(soft,clkdiv)

class _MGT(object):
    _nports = 1
    _blockgrp = 1
    @property
    def id(self): "%s_%03d_%d"%(self.tree.name,self.tree.shot,self.nid)
    __streams = {}
    @property
    def _streams(self):
        return self._MGT__streams.get(self.id,None)
    @_streams.setter
    def _streams(self,value):
        if   isinstance(value,(set,)):
            self._MGT__streams[self.id] = value
        elif self.id in self._MGT__streams:
            self._MGT__streams.pop(self.id)
    class STREAM(threading.Thread):
        _folder = "/data"
        _blks_per_buf = 99
        triggered = False
        dostore   = False
        post = 2147483647
        trigger = 0
        def wait4ready(self):
            while not self._ready:
                 time.sleep(1)
        def __init__(self,port,dev):
            super(_MGT.STREAM,self).__init__(name="MGT.STREAM(%d)"%port)
            self._stop = threading.Event()
            self.port = port
            self.tree = dev.tree
            self.path = dev.path
            self.post    = dev._post
            self.trigger = dev._trigger
            self._blockgrp = dev._blockgrp
            self._ch_per_port = dev._num_channels//dev._nports
            self._size = (1<<22) * dev._blockgrp     # _blockgrp blocks of 4MB
            self._shape = (self._ch_per_port,self._size//self._ch_per_port//2) # _ch_per_port channels of 16bit (2byte)
        def get_folder(self,buf):
            return "%s/%d/%06d"%(self._folder,self.port,buf)
        def get_bufidx(self,idx):
            grp_per_buf = self._blks_per_buf/self._blockgrp
            return idx//grp_per_buf+1,int(idx%grp_per_buf)*self._blockgrp
        def get_fullpath(self,idx):
            buf,idx = self.get_bufidx(idx)
            return '%s/%d.%02d'%(self.get_folder(buf),self.port,idx)
        def get_block(self,block):
            if isinstance(block,int):
                block = self.get_fullpath(block)
            return numpy.memmap(block,dtype=numpy.int16,shape=self._shape,mode='r',order='F')
        @property
        def outdir(self): return "%s/%d"%(self._folder,self.port)
        def idx2ch(self,idx):
            return 1+idx+self._ch_per_port*self.port
        def run(self):
            import subprocess
            if not os.path.exists(self._folder):
                os.mkdir(self._folder)
            log = open("/tmp/mgt_stream_%d.log"%(self.port,),'w')
            try:
                params = ['mgt-stream',str(self.port),str(self._blockgrp)]
                self.stream = subprocess.Popen(params,stdout=log,stderr=subprocess.STDOUT)
            except:
                log.close()
                raise
            try:
                MDSplus.Tree.usePrivateCtx(True)
                dev = MDSplus.Tree(self.tree.tree,self.tree.shot).getNode(self.path)
                idx = 0
                fullpath = self.get_fullpath(idx)
                max_idx  = self.post/self._shape[1]
                while not self._stop.is_set():
                    #if self.triggered and not self.dostore:
                    #    time.sleep(1)
                    #    continue
                    if not os.path.exists(fullpath):
                        if self.stream.poll() is None:
                            time.sleep(1)
                            continue
                        else: break
                    size = os.path.getsize(fullpath)
                    if size<self._size:
                        if self.stream.poll() is None:
                            time.sleep(.1)
                            continue
                        else: break
                    if size>self._size:
                        raise Exception('file too big "%s" %dB > %dB'%(fullpath,size,self._size))
                    self.triggered = True
                    self.store(dev,idx*self._shape[1],self.get_block(fullpath))
                    print(fullpath)
                    try: os.remove(fullpath)
                    except (SystemExit,KeyboardInterrupt): raise
                    except: print('Could not remove %s'%fullpath)
                    if idx>=max_idx: break
                    idx += 1
                    fullpath = self.get_fullpath(idx)
            except Exception:
                import traceback
                traceback.print_exc()
            finally:
                if self.stream.poll() is None:
                    self.stream.terminate()
                    self.stream.wait()

        def store(self,dev,i0,block):
            dt = MDSplus.DIVIDE(MDSplus.Int64(1e9),dev.clock)
            i1 = i0+block.shape[1]-1
            dim = MDSplus.Dimension(MDSplus.Window(i0,i1,dev.trigger),MDSplus.Range(None,None,dt))
            d0=MDSplus.Int64(i0*dt+self.trigger)
            d1=MDSplus.Int64(i1*dt+self.trigger)
            for i in range(self._ch_per_port):
                ch = self.idx2ch(i)
                raw = dev.channel(ch)
                if not raw.on: continue
                raw.makeSegment(d0,d1,dim,block[i])
        def stop(self): self._stop.set()
    def mgt(self,i):  return mgt(i,self._host)

    def _arm_mgt(self):
        if not self._streams is None: raise Exception("Streams already initialized.")
        os.system('mgt-arm')
        streams = set([])
        for port in range(self._nports):
            streams.add(self.STREAM(port,self))
        for stream in streams:
            stream.start()
        self._streams = streams
        self.nc.transient(0,100000) # is this necessary?
        self.nc.streamtonowhered = 'start'
        time.sleep(5)
    def _store_mgt(self):
        if self._streams is None: raise MDSplus.DevINV_SETUP
        for site in self._active_mods: self.module(site).store()
        self._master.store_master()
        self.nc.streamtonowhered = 'stop'
        streams = list(self._streams)
        triggered = len([True for stream in streams if stream.triggered])>0
        if triggered:
            ESLO,EOFF=self.ESLO,self.EOFF
            for idx in range(self._num_channels):
                ch = idx+1
                node = self.channel(ch)
                if node.on:
                    node.setSegmentScale(MDSplus.ADD(MDSplus.MULTIPLY(MDSplus.dVALUE(),ESLO[idx]),EOFF[idx]))
            #for stream in streams: stream.dostore = True
        else:
            for stream in streams: stream.stop()
        for stream in streams: stream.join()
        self._streams = None
        os.system('mgt-deinit')
        if not triggered: raise MDSplus.DevNOT_TRIGGERED
    def _deinit_mgt(self):
        self.nc.streamtonowhered = 'stop'
        if not self._streams is None:
            streams = list(self._streams)
            for stream in streams: stream.stop()
            for stream in streams: stream.join()
            self._streams = None
        os.system('mgt-deinit')
class _MGTx2(_MGT): _nports = 2

class _MGTDRAM(object):
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
            self._blklen = self._blksize/self._chans/2
            self.blocks = min(2048,-((-blocks)//self._blkgrp)*self._blkgrp)
            self.trigger = dev._trigger
            self.pre  = dev._pre
            self.post = dev._post
            self.samples = min(self.blocks*self._blklen,self.pre + self.post)
            self.tree = dev.tree
            self.path = dev.path
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
                    if debug>0: print('waiting for %s'%fullpath)
                    for i in range(180): # TODO: is this too high?
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
                    if debug>0: print("buffer yield %s - %dB / %dB"%(fullpath,os.path.getsize(fullpath),self._grpsize))
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
                if debug>0: print("blocks: %d/%d, samples %d/%d"%(blocks,self.blocks,samples,self.samples))
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
                    while not self._stop.is_set():
                        if self.shot_log.count>=0:
                            break
                        time.sleep(1)
                    else: return # triggers mgt_abort in finally
                    if debug>0: print(" armed ")
                    with self._state_lock: self._state = 1
                    # wait for first sample
                    while not self._stop.is_set():
                        if self.shot_log.count>=1:
                            break
                        time.sleep(1)
                    else: return # triggers mgt_abort in finally
                    if debug>0: print(" triggered ")
                    with self._state_lock: self._state = 2
                except: # stop stream on exception
                    raise
                finally:
                    # wait for mgt_run_shot to finish
                    while self.shot_log.isAlive():
                        if self._stop.is_set():
                            self.mgt.mgt_abort()
                        self.shot_log.join(1)
                # transfer available samples
                if debug>0: print(" ready for transfer ")
                with self._state_lock: self._state = 3
                MDSplus.Tree.usePrivateCtx(True)
                dev = MDSplus.Tree(self.tree.tree,self.tree.shot).getNode(self.path)
                self.transfer(dev)
                # finished
                if debug>0: print(" transfered ")
                with self._state_lock: self._state = 4
            except Exception as e:
                import traceback
                self.exception = e
                self.traceback = traceback.format_exc()
                self.stop()

        def _transfer(self,dev):
            i0 = 0
            dt = MDSplus.DIVIDE(MDSplus.Int64(1e9),dev.clock)
            for buf in self.buffer():
                i1 = i0+buf.shape[1]-1
                dim = MDSplus.Dimension(MDSplus.Window(i0,i1,dev.trigger),MDSplus.Range(None,None,dt))
                d0 = MDSplus.Int64(i0*dt+self.trigger)
                d1 = MDSplus.Int64(i1*dt+self.trigger)
                for idx in range(self._chans):
                    ch = self.idx2ch(idx)
                    node = dev.channel(ch)
                    if node.on:
                        node.makeSegment(d0,d1,dim,buf[idx])
                i0 = i1+1

        def get_mask(self,buf):
            return (buf[_es_marker.static,...]==_es_marker.int16.static).all(0)

        def _transfer_es(self,dev):
            """
            ACTION METHOD: grabs the triggered channels from acq400_bigcat
            only works it bufferlen is set to default
            """
            if debug>0: print("STREAM._transfer_es")
            skip= self.skip
            DT  = MDSplus.DIVIDE(MDSplus.Int64(1e9),dev.clock)
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
                        if debug>0: print("ttrg = %d"%ctx[1])
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
                if debug>0: print(block,chunks)
                for fm,ut,i0,t0,skip in chunks:
                    if i0 is None: continue
                    if debug>2: print(block,fm,ut,i0,t0,skip)
                    dim,slc,i0,t0,dt = dev._get_dim_slice(i0,DT,fm+skip,ut,self.pre)
                    val = buf[:,slc][:,:rem_samples]
                    rem_samples-=val.shape[1]
                    i1 = i0+val.shape[1]-1
                    dim[0][0],dim[0][1]=i0,i1
                    d0=MDSplus.Int64(t0+i0*dt)
                    d1=MDSplus.Int64(t0+i1*dt)
                    if debug>1:  print("segment (%7.1fms,%7.1fms) rem: %d"%(d0/1e6,d1/1e6,rem_samples))
                    for idx in range(self._chans):
                        ch = self.idx2ch(idx)
                        node = dev.channel(ch)
                        if node.on:
                            node.makeSegment(d0,d1,dim,val[idx])
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
        if debug: print('_MGTDRAM._arm_mgt')
        if self._stream is None:
            self._stream = self.STREAM(self,blocks)
        if not self._stream.wait4armed():
            self._stream = None
            raise Exception('Stream terminated')
        # TODO: find a way to detemine when the device is ready
    def _store_mgt(self):
        does,blocks,length,chans = self.fits_in_ram()
        if does: return self._store_acq()
        if debug: print('_MGTDRAM._store_mgt')
        for site in self._active_mods:
            self.module(site).store()
        self._master.store_master()
        ESLO,EOFF=self.ESLO,self.EOFF
        for idx in range(chans):
            ch = idx+1
            node = self.channel(ch)
            if node.on:
                node.setSegmentScale(MDSplus.ADD(MDSplus.MULTIPLY(MDSplus.dVALUE(),ESLO[idx]),EOFF[idx]))
        if self._stream is None:       raise MDSplus.DevINV_SETUP
        if self._stream.exception is not None:
            print(self._stream.traceback)
            raise self._stream.exception
        if not self._stream.triggered: raise MDSplus.DevNOT_TRIGGERED

    def _deinit_mgt(self):
        does,blocks,length,chans = self.fits_in_ram()
        if does: return self._deinit_acq()
        if debug: print('_MGTDRAM._deinit_mgt')
        if isinstance(self._stream,(threading.Thread,)):
            try:
                while self._stream.isAlive():
                    if not self._stream.triggered:
                        self._stream.stop()
                    self._stream.join(1)
                if self._stream.exception is not None:
                    print(self._stream.traceback)
                    raise self._stream.exception
            finally:
                self._stream = None
        else:
            self.nc.streamtonowhered = 'stop'
            mgtdram(self._host).mgt_abort()

###-----------------------
### Public MDSplus Devices
###-----------------------

### ACQ1001 carrier

class ACQ1001_ACQ425_1000(_ACQ1001):pass
ACQ1001_ACQ425_1000._setParts(_ACQ425_1000)
class ACQ1001_ACQ425_2000(_ACQ1001):pass
ACQ1001_ACQ425_2000._setParts(_ACQ425_2000)
class ACQ1001_ACQ480(_ACQ1001):pass
ACQ1001_ACQ480._setParts(_ACQ480)

class ACQ1001_AO420(_ACQ1001):pass
ACQ1001_AO420._setParts(_AO420)

## set bank_mask A,AB,ABC (default all, i.e. ABCD) only for ACQ425 for now ##

class _ACQ425_1000_4CH(_ACQ425_1000): _num_channels = 4
class ACQ1001_ACQ425_1000_4CH(_ACQ1001):pass
ACQ1001_ACQ425_1000_4CH._setParts(_ACQ425_1000_4CH)

class _ACQ425_1000_8CH(_ACQ425_1000): _num_channels = 8
class ACQ1001_ACQ425_1000_8CH(_ACQ1001):pass
ACQ1001_ACQ425_1000_8CH._setParts(_ACQ425_1000_8CH)

class _ACQ425_1000_12CH(_ACQ425_1000): _num_channels = 12
class ACQ1001_ACQ425_1000_12CH(_ACQ1001):pass
ACQ1001_ACQ425_1000_12CH._setParts(_ACQ425_1000_12CH)

class _ACQ425_2000_4CH(_ACQ425_2000): _num_channels = 4
class ACQ1001_ACQ425_2000_4CH(_ACQ1001):pass
ACQ1001_ACQ425_2000_4CH._setParts(_ACQ425_2000_4CH)

class _ACQ425_2000_8CH(_ACQ425_2000): _num_channels = 8
class ACQ1001_ACQ425_2000_8CH(_ACQ1001):pass
ACQ1001_ACQ425_2000_8CH._setParts(_ACQ425_2000_8CH)

class _ACQ425_2000_12CH(_ACQ425_2000): _num_channels = 12
class ACQ1001_ACQ425_2000_12CH(_ACQ1001):pass
ACQ1001_ACQ425_2000_12CH._setParts(_ACQ425_2000_12CH)

## /mnt/fpga.d/ACQ1001_TOP_08_ff_64B-4CH.bit.gz
# TODO: how to deal with es_enable CH 5&6 ?
_num_channels = 8
class _ACQ480_4CH(_ACQ480): _num_channels = 4
class ACQ1001_ACQ480_4CH(_ACQ1001):pass
ACQ1001_ACQ480_4CH._setParts(_ACQ480_4CH)

### ACQ2106 carrier ###

class ACQ2106_ACQ425_1000x1(_ACQ2106):pass
ACQ2106_ACQ425_1000x1._setParts(_ACQ425_1000,1)
class ACQ2106_ACQ425_1000x2(_ACQ2106):pass
ACQ2106_ACQ425_1000x2._setParts(_ACQ425_1000,2)
class ACQ2106_ACQ425_1000x3(_ACQ2106):pass
ACQ2106_ACQ425_1000x3._setParts(_ACQ425_1000,3)
class ACQ2106_ACQ425_1000x4(_ACQ2106):pass
ACQ2106_ACQ425_1000x4._setParts(_ACQ425_1000,4)
class ACQ2106_ACQ425_1000x5(_ACQ2106):pass
ACQ2106_ACQ425_1000x5._setParts(_ACQ425_1000,5)
class ACQ2106_ACQ425_1000x6(_ACQ2106):pass
ACQ2106_ACQ425_1000x6._setParts(_ACQ425_1000,6)

class ACQ2106_ACQ425_2000x1(_ACQ2106):pass
ACQ2106_ACQ425_2000x1._setParts(_ACQ425_2000,1)
class ACQ2106_ACQ425_2000x2(_ACQ2106):pass
ACQ2106_ACQ425_2000x2._setParts(_ACQ425_2000,2)
class ACQ2106_ACQ425_2000x3(_ACQ2106):pass
ACQ2106_ACQ425_2000x3._setParts(_ACQ425_2000,3)
class ACQ2106_ACQ425_2000x4(_ACQ2106):pass
ACQ2106_ACQ425_2000x4._setParts(_ACQ425_2000,4)
class ACQ2106_ACQ425_2000x5(_ACQ2106):pass
ACQ2106_ACQ425_2000x5._setParts(_ACQ425_2000,5)
class ACQ2106_ACQ425_2000x6(_ACQ2106):pass
ACQ2106_ACQ425_2000x6._setParts(_ACQ425_2000,6)

class ACQ2106_ACQ480x1(_ACQ2106):pass
ACQ2106_ACQ480x1._setParts(_ACQ480,1)
class ACQ2106_ACQ480x2(_ACQ2106):pass
ACQ2106_ACQ480x2._setParts(_ACQ480,2)
class ACQ2106_ACQ480x3(_ACQ2106):pass
ACQ2106_ACQ480x3._setParts(_ACQ480,3)
class ACQ2106_ACQ480x4(_ACQ2106):_max_clk = 14000000
ACQ2106_ACQ480x4._setParts(_ACQ480,4)
class ACQ2106_ACQ480x5(_ACQ2106):_max_clk = 11000000
ACQ2106_ACQ480x5._setParts(_ACQ480,5)
class ACQ2106_ACQ480x6(_ACQ2106):_max_clk =  9000000
ACQ2106_ACQ480x6._setParts(_ACQ480,6)

class ACQ2106_MGT_ACQ425_1000x1(ACQ2106_ACQ425_1000x1,_MGT): _blockgrp = 1
ACQ2106_MGT_ACQ425_1000x1._setParts(_ACQ425_1000,1,mgt={0:[1]})
class ACQ2106_MGT_ACQ425_1000x2(ACQ2106_ACQ425_1000x2,_MGT): _blockgrp = 2
ACQ2106_MGT_ACQ425_1000x2._setParts(_ACQ425_1000,2,mgt={0:[1,2]})
class ACQ2106_MGT_ACQ425_1000x3(ACQ2106_ACQ425_1000x3,_MGT): _blockgrp = 3
ACQ2106_MGT_ACQ425_1000x3._setParts(_ACQ425_1000,3,mgt={0:[1,2,3]})
class ACQ2106_MGT_ACQ425_1000x4(ACQ2106_ACQ425_1000x4,_MGT): _blockgrp = 4
ACQ2106_MGT_ACQ425_1000x4._setParts(_ACQ425_1000,4,mgt={0:[1,2,3,4]})
class ACQ2106_MGT_ACQ425_1000x5(ACQ2106_ACQ425_1000x5,_MGT): _blockgrp = 5
ACQ2106_MGT_ACQ425_1000x5._setParts(_ACQ425_1000,5,mgt={0:[1,2,3,4,5]})
class ACQ2106_MGT_ACQ425_1000x6(ACQ2106_ACQ425_1000x6,_MGT): _blockgrp = 6
ACQ2106_MGT_ACQ425_1000x6._setParts(_ACQ425_1000,6,mgt={0:[1,2,3,4,5,6]})

class ACQ2106_MGT_ACQ425_2000x1(ACQ2106_ACQ425_2000x1,_MGT): _blockgrp = 1
ACQ2106_MGT_ACQ425_2000x1._setParts(_ACQ425_2000,1,mgt={0:[1]})
class ACQ2106_MGT_ACQ425_2000x2(ACQ2106_ACQ425_2000x2,_MGT): _blockgrp = 2
ACQ2106_MGT_ACQ425_2000x2._setParts(_ACQ425_2000,2,mgt={0:[1,2]})
class ACQ2106_MGT_ACQ425_2000x3(ACQ2106_ACQ425_2000x3,_MGT): _blockgrp = 3
ACQ2106_MGT_ACQ425_2000x3._setParts(_ACQ425_2000,3,mgt={0:[1,2,3]})
class ACQ2106_MGT_ACQ425_2000x4(ACQ2106_ACQ425_2000x4,_MGT): _blockgrp = 4
ACQ2106_MGT_ACQ425_2000x4._setParts(_ACQ425_2000,4,mgt={0:[1,2,3,4]})
class ACQ2106_MGT_ACQ425_2000x5(ACQ2106_ACQ425_2000x5,_MGT): _blockgrp = 5
ACQ2106_MGT_ACQ425_2000x5._setParts(_ACQ425_2000,5,mgt={0:[1,2,3,4,5]})
class ACQ2106_MGT_ACQ425_2000x6(ACQ2106_ACQ425_2000x6,_MGT): _blockgrp = 6
ACQ2106_MGT_ACQ425_2000x6._setParts(_ACQ425_2000,6,mgt={0:[1,2,3,4,5,6]})

class ACQ2106_MGT_ACQ480x1(ACQ2106_ACQ480x1,_MGT): _blockgrp = 1
ACQ2106_MGT_ACQ480x1._setParts(_ACQ480,1,mgt={0:[1]})
class ACQ2106_MGT_ACQ480x2(ACQ2106_ACQ480x2,_MGT): _blockgrp = 2
ACQ2106_MGT_ACQ480x2._setParts(_ACQ480,2,mgt={0:[1,2]})
class ACQ2106_MGT_ACQ480x3(ACQ2106_ACQ480x3,_MGT): _blockgrp = 3
ACQ2106_MGT_ACQ480x3._setParts(_ACQ480,3,mgt={0:[1,2,3]})
class ACQ2106_MGT_ACQ480x4(ACQ2106_ACQ480x4,_MGT): _blockgrp = 4
ACQ2106_MGT_ACQ480x4._setParts(_ACQ480,4,mgt={0:[1,2,3,4]})
class ACQ2106_MGT_ACQ480x5(ACQ2106_ACQ480x5,_MGT): _blockgrp = 5
ACQ2106_MGT_ACQ480x5._setParts(_ACQ480,5,mgt={0:[1,2,3,4,5]})
class ACQ2106_MGT_ACQ480x6(ACQ2106_ACQ480x6,_MGT): _blockgrp = 6
ACQ2106_MGT_ACQ480x6._setParts(_ACQ480,6,mgt={0:[1,2,3,4,5,6]})

class ACQ2106_MGTx2_ACQ425_1000x2(ACQ2106_ACQ425_1000x2,_MGTx2): _blockgrp = 1
ACQ2106_MGTx2_ACQ425_1000x2._setParts(_ACQ425_1000,2,mgt={1:[1],0:[2]})
class ACQ2106_MGTx2_ACQ425_1000x4(ACQ2106_ACQ425_1000x4,_MGTx2): _blockgrp = 2
ACQ2106_MGTx2_ACQ425_1000x4._setParts(_ACQ425_1000,4,mgt={1:[1,2],0:[3,4]})
class ACQ2106_MGTx2_ACQ425_1000x6(ACQ2106_ACQ425_1000x6,_MGTx2): _blockgrp = 3
ACQ2106_MGTx2_ACQ425_1000x6._setParts(_ACQ425_1000,6,mgt={1:[1,2,3],0:[4,5,6]})

class ACQ2106_MGTx2_ACQ425_2000x2(ACQ2106_ACQ425_2000x2,_MGTx2): _blockgrp = 1
ACQ2106_MGTx2_ACQ425_2000x2._setParts(_ACQ425_2000,2,mgt={1:[1],0:[2]})
class ACQ2106_MGTx2_ACQ425_2000x4(ACQ2106_ACQ425_2000x4,_MGTx2): _blockgrp = 2
ACQ2106_MGTx2_ACQ425_2000x4._setParts(_ACQ425_2000,4,mgt={1:[1,2],0:[3,4]})
class ACQ2106_MGTx2_ACQ425_2000x6(ACQ2106_ACQ425_2000x6,_MGTx2): _blockgrp = 3
ACQ2106_MGTx2_ACQ425_2000x6._setParts(_ACQ425_2000,6,mgt={1:[1,2,3],0:[4,5,6]})

class ACQ2106_MGTx2_ACQ480x2(ACQ2106_ACQ480x2,_MGTx2): _blockgrp = 1
ACQ2106_MGTx2_ACQ480x2._setParts(_ACQ480,2,mgt={1:[1],0:[2]})
class ACQ2106_MGTx2_ACQ480x4(ACQ2106_ACQ480x4,_MGTx2): _blockgrp = 2
ACQ2106_MGTx2_ACQ480x4._setParts(_ACQ480,4,mgt={1:[1,2],0:[3,4]})
class ACQ2106_MGTx2_ACQ480x6(ACQ2106_ACQ480x6,_MGTx2): _blockgrp = 3
ACQ2106_MGTx2_ACQ480x6._setParts(_ACQ480,6,mgt={1:[1,2,3],0:[4,5,6]})

class ACQ2106_MGTDRAM_ACQ425_1000x1(ACQ2106_ACQ425_1000x1,_MGTDRAM): pass
ACQ2106_MGTDRAM_ACQ425_1000x1._setParts(_ACQ425_1000,1,True)
class ACQ2106_MGTDRAM_ACQ425_1000x2(ACQ2106_ACQ425_1000x2,_MGTDRAM): pass
ACQ2106_MGTDRAM_ACQ425_1000x2._setParts(_ACQ425_1000,2,True)
class ACQ2106_MGTDRAM_ACQ425_1000x3(ACQ2106_ACQ425_1000x3,_MGTDRAM): pass
ACQ2106_MGTDRAM_ACQ425_1000x3._setParts(_ACQ425_1000,3,True)
class ACQ2106_MGTDRAM_ACQ425_1000x4(ACQ2106_ACQ425_1000x4,_MGTDRAM): pass
ACQ2106_MGTDRAM_ACQ425_1000x4._setParts(_ACQ425_1000,4,True)
class ACQ2106_MGTDRAM_ACQ425_1000x5(ACQ2106_ACQ425_1000x5,_MGTDRAM): pass
ACQ2106_MGTDRAM_ACQ425_1000x5._setParts(_ACQ425_1000,5,True)
class ACQ2106_MGTDRAM_ACQ425_1000x6(ACQ2106_ACQ425_1000x6,_MGTDRAM): pass
ACQ2106_MGTDRAM_ACQ425_1000x6._setParts(_ACQ425_1000,6,True)

class ACQ2106_MGTDRAM_ACQ425_2000x1(ACQ2106_ACQ425_2000x1,_MGTDRAM): pass
ACQ2106_MGTDRAM_ACQ425_2000x1._setParts(_ACQ425_2000,1,True)
class ACQ2106_MGTDRAM_ACQ425_2000x2(ACQ2106_ACQ425_2000x2,_MGTDRAM): pass
ACQ2106_MGTDRAM_ACQ425_2000x2._setParts(_ACQ425_2000,2,True)
class ACQ2106_MGTDRAM_ACQ425_2000x3(ACQ2106_ACQ425_2000x3,_MGTDRAM): pass
ACQ2106_MGTDRAM_ACQ425_2000x3._setParts(_ACQ425_2000,3,True)
class ACQ2106_MGTDRAM_ACQ425_2000x4(ACQ2106_ACQ425_2000x4,_MGTDRAM): pass
ACQ2106_MGTDRAM_ACQ425_2000x4._setParts(_ACQ425_2000,4,True)
class ACQ2106_MGTDRAM_ACQ425_2000x5(ACQ2106_ACQ425_2000x5,_MGTDRAM): pass
ACQ2106_MGTDRAM_ACQ425_2000x5._setParts(_ACQ425_2000,5,True)
class ACQ2106_MGTDRAM_ACQ425_2000x6(ACQ2106_ACQ425_2000x6,_MGTDRAM): pass
ACQ2106_MGTDRAM_ACQ425_2000x6._setParts(_ACQ425_2000,6,True)

class ACQ2106_MGTDRAM_ACQ480x1(ACQ2106_ACQ480x1,_MGTDRAM): pass
ACQ2106_MGTDRAM_ACQ480x1._setParts(_ACQ480,1,True)
class ACQ2106_MGTDRAM_ACQ480x2(ACQ2106_ACQ480x2,_MGTDRAM): pass
ACQ2106_MGTDRAM_ACQ480x2._setParts(_ACQ480,2,True)
class ACQ2106_MGTDRAM_ACQ480x3(ACQ2106_ACQ480x3,_MGTDRAM): pass
ACQ2106_MGTDRAM_ACQ480x3._setParts(_ACQ480,3,True)
class ACQ2106_MGTDRAM_ACQ480x4(ACQ2106_ACQ480x4,_MGTDRAM): pass
ACQ2106_MGTDRAM_ACQ480x4._setParts(_ACQ480,4,True)
class ACQ2106_MGTDRAM_ACQ480x5(ACQ2106_ACQ480x5,_MGTDRAM): pass
ACQ2106_MGTDRAM_ACQ480x5._setParts(_ACQ480,5,True)
class ACQ2106_MGTDRAM_ACQ480x6(ACQ2106_ACQ480x6,_MGTDRAM): pass
ACQ2106_MGTDRAM_ACQ480x6._setParts(_ACQ480,6,True)


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
    acq2106_425_host     = 'acq2106_070'
    acq2106_480_host     = 'acq2106_065'
    acq2106_480_fpgadecim= 10
    acq1001_420_host     = 'acq1001_291'
    acq1001_425_host     = 'acq1001_072'
    acq1001_480_host     = '192.168.44.211' #'acq1001_316'
    rp_host              = '10.44.2.100'#'RP-F0432C'
    shot = 1000
    @staticmethod
    def getShotNumber():
        import datetime
        d = datetime.datetime.utcnow()
        return d.month*100000+d.day*1000+d.hour*10

    @classmethod
    def setUpClass(cls):
        from LocalDevices import acq4xx as a,w7x_timing
        import gc
        gc.collect(2)
        cls.shot = cls.getShotNumber()
        with MDSplus.Tree('test',-1,'new') as t:
            #ACQ480=ACQ2106_ACQ480x4.Add(t,'ACQ480')
            A=a.ACQ2106_ACQ480x4.Add(t,'ACQ480x4')
            A.host      = cls.acq2106_480_host
            A.clock_src = 10000000
            A.clock     =  2000000
            A.trigger_pre  = 0
            A.trigger_post = 100000
            A.module1_fir  = 3
            A=a.ACQ2106_MGTDRAM_ACQ480x4.Add(t,'ACQ2106_064')
            A.host      = cls.acq2106_480_host
            A.clock_src = 10000000
            A.clock     =  2000000
            A.trigger_pre  = 0
            A.trigger_post = 10000000
            A.module1_fir  = 3
            A=a.ACQ2106_ACQ425_2000x6.Add(t,'ACQ425x6')
            A.host      = cls.acq2106_425_host
            A.clock_src = 10000000
            A.clock     = 2000000
            A.trigger_pre  = 0
            A.trigger_post = 100000
            A=a.ACQ2106_MGTx2_ACQ425_2000x6.Add(t,'ACQ425x6_M2')
            A.host      = cls.acq2106_425_host
            A.clock_src = 10000000
            A.clock     = 2000000
            A.trigger_pre  = 0
            A.trigger_post = 100000
            A=a.ACQ1001_ACQ425_1000.Add(t,'ACQ425')
            A.host      = cls.acq1001_425_host
            A.clock_src = 10000000
            A.clock     = 2000000
            A.trigger_pre  = 0
            A.trigger_post = 100000
            A=a.ACQ1001_ACQ480.Add(t,'ACQ480')
            A.host      = cls.acq1001_480_host
            #A.clock_src = 10000000
            A.clock     = 2000000
            A.trigger_pre  = 0
            A.trigger_post = 100000
            A=a.ACQ1001_AO420.Add(t,'AO420')
            A.host      = cls.acq1001_420_host
            #A.clock_src = 10000000
            A.clock     = 1000000
            a = numpy.array(range(100000))/50000.*numpy.pi
            A.channel(1).record=numpy.sin(a)
            A.channel(2).record=numpy.cos(a)
            A.channel(3).record=-numpy.sin(a)
            A.channel(4).record=-numpy.cos(a)
            R=w7x_timing.W7X_TIMING.Add(t,'R')
            R.host           = cls.rp_host
            t.write()

    @classmethod
    def tearDownClass(cls): pass

    @staticmethod
    def makeshot(t,shot,dev):
        out('creating "%s" shot %d'%(t.tree,shot))
        MDSplus.Tree('test',-1,'readonly').createPulse(shot)
        t=MDSplus.Tree('test',shot)
        A,R=t.getNode(dev),t.R
        A.debug=7
        out('setup trigger')
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
            R.trig();t=int(A._post/A._clock+1)*2
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
        t.R.setup()
        self.makeshot(t,self.shot+8,'AO420')

    def test425Normal(self):
        out('start test425Normal',1)
        t=MDSplus.Tree('test')
        t.R.setup()
        self.makeshot(t,self.shot+5,'ACQ425')

    def test425X6Normal(self):
        out('start test425X6Normal',1)
        t=MDSplus.Tree('test')
        t.R.setup()
        self.makeshot(t,self.shot+6,'ACQ425X6')

    def test425X6Stream(self):
        out('start test425X6Stream',1)
        t=MDSplus.Tree('test')
        t.R.setup()
        self.makeshot(t,self.shot+7,'ACQ425X6_M2')

    def test480Normal(self):
        out('start test480Normal',1)
        t=MDSplus.Tree('test')
        t.R.setup()
        self.makeshot(t,self.shot+5,'ACQ480')

    def test480X4Normal(self):
        out('start test480X4Normal',1)
        t=MDSplus.Tree('test')
        t.R.setup(width=1000)
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
        t.R.setup(width=100,period=100000*self.acq2106_480_fpgadecim,burst=30)
        t.ACQ480X4.module1_trig_mode='RTM'
        t.ACQ480X4.module1_trig_mode_translen=t.ACQ480X4.trigger_post>>3
        self.makeshot(t,self.shot+3,'ACQ480X4')

    def test480X4MGTDRAM(self):
        out('start test480X4MGTDRAM',1)
        t=MDSplus.Tree('test')
        t.ACQ2106_064.trigger_post=12500000
        t.R.setup(width=100)
        t.ACQ480X4.module1_trig_mode='OFF';
        self.makeshot(t,self.shot+1,'ACQ2106_064')

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
        print(sys.argv[1:])
        if sys.argv[1]=='test':
            if len(sys.argv)>2:
                runTests(sys.argv[2:])
            else:
                shot = 1
                try:    shot>0 # analysis:ignore
                except: shot = Tests.getShotNumber()
                from matplotlib.pyplot import plot # analysis:ignore

                #expt,dev=('qmb','ACQ1001_292') # ACQ1001_ACQ480_1000
                #expt,dev=('qxt1','ACQ2106_070') # ACQ2106_ACQ425_2000x6
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
                        print('M1C1: ssegse= %d'%A.channel(1).getNumSegments())
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
