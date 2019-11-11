#
# Copyright (c) 2018, Massachusetts Institute of Technology All rights reserved.
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

import sys,socket,threading,numpy

if sys.version_info < (3,):
    def _s(b): return str(b)
    def _b(s): return bytes(s)
else:
    def _s(b): return b if isinstance(b,str)   else b.decode('ASCII')
    def _b(s): return s if isinstance(s,bytes) else s.encode('ASCII')


###----------------
### nc base classes
###----------------
class staticmethodX(object):
    def __get__(self, inst, cls):
        if inst is None:
            return self.method
        return self.method.__get__(inst)
    def __init__(self, method):
        self.method = method
class nc(object):
    """
    Core n-etwork c-onnection to the DTACQ appliance. All roads lead here (Rome of the DTACQ world).
    This class provides the methods for sending and receiving information/data through a network socket
    All communication with the D-TACQ devices will require this communication layer
    """
    _log_txt = []
    _log_fid = []
    def log(self,fid,txt):
        self._log_txt.append(txt)
        self._log_fid.append(fid)
        if fid==0: sys.stdout.write('\033[32;1m')
        else:      sys.stdout.write('\033[35;1m')
        sys.stdout.write(txt)
        sys.stdout.write('\033[m')
    @staticmethodX
    def recv(sock,toread):
        if isinstance(sock,(nc,)):
            sock = sock.sock
        buf = bytearray(toread)
        view = memoryview(buf)
        try:
            while toread>0:
                nbytes = sock.recv_into(view, toread)
                if nbytes==0: break #EOF
                view = view[nbytes:]
                toread -= nbytes
        except socket.timeout:
            if len(buf) == toread:
                raise
        if toread>0:
            return buf[:-toread]
        return buf
    @staticmethodX
    def send(sock,msg):
        if isinstance(sock,(nc,)):
            sock = sock.sock
        view = memoryview(_b(msg))
        tosend = len(view)
        while tosend>0:
            nbytes = sock.send(view)
            if nbytes==0: continue
            view = view[nbytes:]
            tosend -= nbytes
    @staticmethodX
    def recvline(sock,n=1,toread=0xffff,stop=b'\n',timeout=None,retry=False):
        if isinstance(sock,(nc,)):
            sock = sock.sock
        buf = bytearray(toread)
        view = memoryview(buf)
        if timeout is not None:
            oto = sock.gettimeout()
            if timeout<0:
                retry = True
                sock.settimeout(-timeout)
            else:
                sock.settimeout(timeout)
        try:
            for i in range(n):
                while toread>0:
                    try:
                        nbytes = sock.recv_into(view, 1)
                    except socket.timeout:
                        if retry: continue
                        else:     raise
                    if view[0] in stop: break
                    if nbytes==0: break #EOF
                    view = view[nbytes:] # slicing views is cheap
                    toread -= nbytes
                if nbytes==0: break #EOF
                view = view[nbytes:] # slicing views is cheap
                toread -= nbytes
        finally:
            if timeout is not None:
                sock.settimeout(oto)
        if toread>0:
            return _s(buf[:-toread])
        return _s(buf)
    def __init__(self,server):
        """
        Here server is a tuple of host & port. For example: ('acq196_388',53504)
        """
        self._server = server
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
    welcomelines = 0
    initcmd = None
    _sock = None
    @property
    def sock(self):
        """
        Creates a socket object, and returns it
        TODO: thread safe dialog
        """

        if self._sock is not None:
            return self._sock
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock = sock
        sock.settimeout(5)
        sock.connect(self._server)
        self.log(1,''.join([nc.recvline(sock) for i in range(self.welcomelines)]))
        if not self.initcmd is None:
            self.log(0,self.initcmd[0])
            nc.send(sock,self.initcmd[0])
            self.log(1,''.join([nc.recvline(sock) for i in range(self.initcmd[1])]))
        return sock
    @staticmethodX
    def close(self):
        if self._sock is not None:
            self._sock.close()
            self._sock = None
    def __del__(self,*a):
        self.close()

class dt100(nc):
    __super = nc
    welcomelines = 1
    def __init__(self,ip):
        super(dt100,self).__init__((ip,53504))
    _lock = threading.Lock()
    def cmd(self,cmd,recvlines=None):
        cmd = cmd+'\n'
        if recvlines is None:
            recvlines = cmd.count('\n')
        with self._lock:
            try:
                self.send(cmd)
                self.log(0,cmd)
                ans = self.recvline(recvlines)
                self.log(1,ans)
                return ans
            except:
                self.close()
                raise
    def get_boards(self):
        self.cmd('dt100 getBoards')
    @staticmethodX
    def close(self):
        if self._sock is not None:
            try: self._sock.send('\nbye\n')
            except: pass
        self.__super.close(self)

class dt100_master(dt100):
    initcmd = ('dt100 open master 1\n',1)
class dt100_shell(dt100):
    __super = dt100
    initcmd = ('dt100 open shell\n',1)
    _lock = threading.Lock()
    def cmd(self,*args,**kw):
        cmd = ' '.join(map(str,args)) + '\n'
        ans = []
        with self._lock:
            try:
                self.send(cmd)
                self.log(0,cmd)
                while True:
                    line = self.recvline(**kw)
                    if len(line)==0: break
                    if line.startswith('EOF '): break
                    ans.append(str(line))
            except Exception as e:
                self.close()
                raise e
        ans = ''.join(ans)
        self.log(1,ans)
        return ans
    def close(self):
        if self._sock is not None:
            try: self._sock.send('\nexit\n')
            except: pass
        self.__super.close(self)

class dt100_sys(dt100):
    __super = nc
    def __init__(self,ip,filepath):
        super(dt100_sys,self).__init__(ip)
        self._lock = threading.Lock()
        self.initcmd = ('dt100 open sys %s\n'%(filepath,),0)
        self.filepath = filepath
    def cmd(self,*args):
        cmd = ' '.join(map(str,args)) + '\n'
        ans = []
        with self._lock:
            try:
                self.send(cmd)
                self.log(0,cmd)
                while True:
                    line = self.recvline()
                    if len(line)==0: break
                    if line.startswith('EOF'): break
                    ans.append(str(line))
            except Exception as e:
                self.close()
                raise e
        ans = ''.join(ans)
        self.log(1,ans)
        return ans
    def close(self):
        self.__super.close(self)

class dt100_channel(dt100):
    def __init__(self,ip,ch,brd=1):
        super(dt100_channel,self).__init__(ip)
        self._lock = threading.Lock()
        chs = '%02d'%ch if ch>0 else 'XX'
        self.initcmd = ('dt100 open data2 /dev/acq32/acq32.%d.%s\n'%(brd,chs),0)
        self.brd = brd
        self.ch = ch
    def read(self, nsamples=1, start=0, stride=1, chunk=1024): # nsamples <= 131072
        with self._lock:
            try:
                cmd = "dt100 read %d %d %d\n" % (start, start+nsamples, stride)
                self.send(cmd)
                self.log(0,cmd)
                total = self.recv(4)
                if len(total)!=4: raise Exception('Channel did not send any data!')
                total = int(numpy.frombuffer(total,'>i4')[0])
                self.log(2,"<%d bytes>"%total)
                while total>chunk:
                    arr = numpy.frombuffer(self.recv(chunk),'>i2')
                    if len(arr) == 0: break
                    total -= chunk
                    yield arr
                arr = numpy.frombuffer(self.recv(total),'>i2')
                yield arr
            except:
                self.close()
                raise

class dt100_stream(dt100):
    _marker = -21931
    def read_raw(self, np=1, chunk=1024, ready=False):
        with self._lock:
            try:
                cmd = "dt100 stream 1 0 %d\n"%(np,)
                self.send(cmd)
                self.log(0,cmd)
                if ready: yield
                while True:
                    try:
                        arr = numpy.frombuffer(self.recv(chunk),'<i2')
                    except socket.timeout:
                        continue
                    if len(arr) == 0:
                        print("stream closed")
                        self.close()
                    yield arr
            finally:
                self.close()
    def read(self, nch=2, schunk=1024, ready=False):
        """ strips tag and sorts channels """
        np = nch//2
        if nch < 2: raise Exception("stream: nch must be at least 2")
        if np*2 != nch: raise Exception("stream: nch must be mutiple of 2")
        data_per_time = nch+1
        bchunk = schunk*data_per_time*2
        g = self.read_raw(np,bchunk,ready)
        if ready: yield next(g)
        try:
            while True:
                yield next(g).reshape((schunk,data_per_time))[:,1:]
        except ValueError:
            pass # acq stopped sending

class statemon(nc):
    __super = nc
    welcomelines = 1
    ST_STOP        = 0
    ST_ARM         = 1
    ST_RUN         = 2
    ST_POSTPROCESS = 4
    ST_CAPDONE     = 5
    last_time = [0,0,0,0,0,0]
    last_state = {}
    def __init__(self,ip,verbose=False):
        super(statemon,self).__init__((ip,53536 if verbose else 53535))
        self.sock.settimeout(60)
        self._stop  = threading.Event()
        self._daemon = None
        self.verbose = verbose
    def __iter__(self):
        while True: yield self.__next__()
    def __next__(self):
        while not self._stop.is_set():
            try:
                line = self.recvline().strip()
                if len(line)==0: raise StopIteration
            except socket.timeout:continue
            else: break
        if self.verbose:
            parts = line.split(':',1)
            if len(parts)>1:
                state = parts[0].strip().split(' ')
                time = float(state[0])
                parts = parts[1].split(' ')
                if len(state)>1:
                    state,label,shot = state[1:]
                    state,shot = int(state),int(shot.split('=',1)[1])
                    self.last_time[state] = time
                    self.last_state.update({'time':time, 'state':state, 'label':label, 'shot':shot})
                else:
                    self.last_state['time'] = time
                    self.last_state['shot'] = int(parts[4].split('=',1)[1])
                self.last_state['samples'] = int(parts[0].split('=',1)[1])
                self.last_state['pre']     = int(parts[1].split('=',1)[1])
                self.last_state['post']    = int(parts[2].split('=',1)[1])
                self.last_state['elapsed'] = int(parts[3].split('=',1)[1])
                return self.last_state
        time,state,label = line.split(' ',2)
        time,state = float(time),int(state)
        self.last_time[state] = time
        self.last_state.update({'time':time, 'state':state, 'label':label})
        if state == self.ST_ARM:
             self.last_state['samples'] = 0
             self.last_state['pre']     = 0
             self.last_state['post']    = 0
             self.last_state['elapsed'] = 0
        return self.last_state
    def start(self):
        def watch(mon):
            try:
                for s in mon: pass
            except: pass
        self._daemon = threading.Thread(target=watch,args=(self,))
        self._daemon.daemon = True
        self._daemon.start()
    def stop(self):
        self._stop.set()
    def __del__(self,*a,**kw):
        self.stop()

class _acq1xx(object):
    """ Subclasses must define:
        nmodules
        nchannels
        channels_per_module = nchannels // nmodules
        channelmap
    """
    class ROLE:
        SOLO   = 'SOLO'
        MASTER = 'MASTER'
        SLAVE  = 'SLAVE'
    class STATE:
        STOP        = 'ST_STOP'
        ARM         = 'ST_ARM'
        RUN         = 'ST_RUN'
        POSTPROCESS = 'ST_POSTPROCESS'
        CAPDONE     = 'ST_CAPDONE'

    class MODE:
        GATED_TRANSIENT     = 'GATED_TRANSIENT'     # 0
        SOFT_TRANSIENT      = 'SOFT_TRANSIENT'      # 2
        SOFT_CONTINUOUS     = 'SOFT_CONTINUOUS'     # 3
        TRIGGERED_CONTINUOUS= 'TRIGGERED_CONTINUOUS'# 4
    class ROUTE:
        class D:
            CLK  = 0
            CLK1 = 1
            CLK2 = 2
            TRG  = 3
            TRG1 = 4
            TRG2 = 5
        MEZZ = 'mezz' # Front panel input LEMO - DI0:CLK, DI3:TRG
        LEMO = MEZZ
        FPGA = 'fpga' # Local DIO output - Useful for driving other cards
        LOCAL= FPGA
        SELF = FPGA
        RIO  = 'rio'  # Local Rear IO inputs - Depends on RTM
        PXI  = 'pxi'  # Backplane PXI signaling - Slave from other cards
        EXPORT = PXI
        IMPORT = PXI
    class DIO:
        CLK      = 'DI0'
        TRG      = 'DI3'
        CLK1_OUT = 'DO1'
        CLK1_IN  = 'DI1'
    def __init__(self,ip):
        self.ip = ip
    _dt100_shell = None
    @property
    def dt100_shell(self):
        if self._dt100_shell is None:
            self._dt100_shell = dt100_shell(self.ip)
        return self._dt100_shell
    def shell(self,*args,**kw):
        return self.dt100_shell.cmd(*args,**kw)
    def acqcmd(self,*args,**kw):
        return self.shell('acqcmd',*args,**kw)
    def wait_while(self,cond,cmd):
        self.acqcmd('--while',cond,cmd,retry=True)
    def wait_until(self,cond,cmd):
        self.acqcmd('--until',cond,cmd,retry=True)
    def wait_arm(self):
        self.wait_while(self.STATE.STOP,'getState')
    def wait_stop(self):
        self.wait_until(self.STATE.STOP,'getState')
    _statemon = None
    @property
    def statemon(self):
        if self._statemon is None:
            self._statemon = statemon(self.ip,True)
        return self._statemon
    _dt100_master = None
    @property
    def dt100_master(self):
        if self._dt100_master is None:
            self._dt100_master = dt100_master(self.ip)
        return self._dt100_master
    def master(self,cmd):
        return self.dt100_master.cmd(cmd)
    def channel(self,ch,brd):
        return dt100_channel(self.ip,ch,brd)
    def dt100_stream(self):
        return dt100_stream(self.ip)
    def stream(self,nch=32,chunk=1024,ready=False):
        s = self.dt100_stream()
        try:
            gen = s.read(nch,chunk,ready)
            if ready: yield next(gen)
            for c in gen:
                yield c
        finally:
            s.close()
    @classmethod
    def sort(cls,d):
        idx = numpy.argsort(cls.channel_map[:d.shape[1]])
        return d[:,idx]
    def read_chan(self,idx,nsamples):
        return self.channel(idx).read(nsamples)
    def set_dio(self,code):
        """ code = '[-01]{6}'
            0: low, 1,H:High -:state is not to be changed
        """
        self.acqcmd('--','setDIO',code)
    def get_dio(self):
        return self.acqcmd('getDIO').split('=',2)[1].strip()
    def set_route(self,d,sin,*sout):
        """ set.route <d> in <sin> out <sout0> <sout1> ...
            set_route('d0','mezz','fpga','pxi')
        """
        if isinstance(d,int): d= 'd%d'%(d,)
        self.shell('set.route',d,'in',sin,'out',*sout)
    def get_route(self,d):
        return self.shell('get.route',d).strip()
    def get_vin(self,*chs):
        if   len(chs)==0:
            ans = self.shell('get.vin')
        elif isinstance(chs[0],slice):
            ans = self.shell('get.vin','%d:%d'%(chs[0].start+1,chs[0].stop))
        else:
            ans = self.shell('get.vin',*chs)
        vins = numpy.array([float(v) for v in ans.strip().split(',')],'float32')
        return vins.reshape((vins.size//2,2))
    def set_role(self,role=None,clkkhz=''):
        if role is None: role = self.ROLE.MASTER
        self.shell("set.%s.role"%(self.__class__.__name__,),role,clkkhz)
    def set_trig(self,di=None,rising=True):
        """ set.trig <di> <rising/falling> """
        if di is None:
            args = ('none',)
        else:
            if isinstance(di,int):
                di = 'DI%d'%(di,)
            args = (di,'rising' if rising else 'falling')
        self.shell("set.trig",*args)
    def set_ext_clk(self,di=None,rising=True):
        """ set.ext_clk <di> <rising/falling> """
        if di is None:
            args = ('none',)
        else:
            if isinstance(di,int):
                di = 'DI%d'%(di,)
            args = (di,'rising' if rising else 'falling')
        self.shell('set.ext_clk',*args)
    def set_simulate(self,val=True):
        self.shell('set.simulate',1 if val else 0)
    def soft_trigger(self):
        self.shell('stimulate.trigger')
    def set_channel_mask(self,mask=0b111):
        self.shell('set.channelMask',mask)
    def set_channel_block_mask(self,active):
        self.shell('set.channelBlockMask',active)
    def get_channel_block_mask(self):
        return self.shell('get.channelBlockMask').strip()
    def set_mode(self,mode,pre=0,post=0):
        if mode == self.MODE.TRIGGERED_CONTINUOUS:
            self.set_mode_triggered_continuous(pre,post)
        else:
            if mode == self.MODE.SOFT_TRANSIENT:
                arg = post
            else:
                arg = pre
            self.acqcmd('setMode',mode,arg)
    def set_mode_triggered_continuous(self,pre=0,post=0):
        self.acqcmd('setModeTriggeredContinuous',pre,post)
    def get_num_channels(self):
        return int(self.shell('get.numChannels'))
    def set_num_channels(self,maxchan=0):
        raise Exception('set_num_channels: not implemented in subclass of _axq1xx')
    def set_internal_clock(self,freq_hz):
        self.acqcmd('setInternalClock',freq_hz)
    def set_external_clock_f(self,fin_khz=None,fout_khz=None,dix=0,div=0):
        """ setExternalClock --fin FIN_KHZ --fout FOUT_KHZ DIx [DIV]
        FIN_KHZ  : External Clock frequency (integer kHz) [default: 1000]
        FOUT_KHZ : Required Sample Clock freq (integer kHz) [default:1000]
        DIx      : DIx {0..5} line where clock appears eg DI0 (LEMO).
        DIV      : optional pre-scale for external clock (less useful)
        """
        if isinstance(dix,int): dix = 'DI%d'%(dix,)
        args = ['--'] # allow --fin and --fout to be passed down to setExternalClock
        if not fin_khz  is None: args.extend(['--fin', fin_khz ])
        if not fout_khz is None: args.extend(['--fout',fout_khz])
        args.append(dix)
        if div>1: args.append(div)
        self.acqcmd('setExternalClock',*args)
    def set_pre_post_mode(self,pre=1024,post=1024,trg_src=3,rising=True):
        if trg_src is None: trigger = 'none'
        else: trigger = "%s %s"%(trg_src,"rising" if rising else "falling")
        self.shell("set.pre_post_mode",int(pre),int(post),trigger)
    def set_dtacq(self,cmd,*args):
        self.shell("set.dtacq",cmd,*args)
    def get_state(self):
        return self.shell('get.State').split(':',2)[1].strip()
    @property
    def stateid(self):
        return int(self.get_state().split(' ',1)[0])
    @property
    def state(self):
        return self.get_state().split('_',2)[1]
    def abort(self):
        self.acqcmd("setAbort")
    def init(self,*a,**kw):
        raise Exception("init: not implemented in subclass of _acq1xx")
    def arm(self):
        self.acqcmd("setArm")
    def setup_trigger(self,ext_trg,edge):
        self.set_trig(self.DIO.TRG,edge)
        self.set_route(self.ROUTE.D.TRG,self.ROUTE.LEMO,self.ROUTE.SELF,self.ROUTE.EXPORT)
        # self.set_route(self.ROUTE.D.TRG,self.ROUTE.LOCAL,self.ROUTE.EXPORT)
    def setup_clock(self,ext_clk,freq,role,ext_freq=1000000):
        self.set_role(role,freq//1000)
        if role == self.ROLE.SLAVE: return
        if ext_clk:
            self.set_route(self.ROUTE.D.CLK,self.ROUTE.LEMO,self.ROUTE.SELF,self.ROUTE.EXPORT)
            self.set_external_clock(ext_freq,freq,self.DIO.CLK)
        else:
            self.set_ext_clk()
            self.set_internal_clock(freq)
            if role == self.ROLE.SOLO:
                self.set_route(self.ROUTE.D.CLK,self.ROUTE.LOCAL,self.ROUTE.EXPORT)

class acq196(_acq1xx):
    """ max streaming rates at num_channels
            ~25kHz @ 96ch
            ~40kHz @ 64ch
            ~70kHz @ 32ch
    """
    nchannels = 96
    nmodules  = 3
    channels_per_module = nchannels // nmodules
    def channel_map(nmodules):
        cm = [1]
        for i in (2,8,16,4,1):
            cm.extend([c+i for c in cm])
        for i in range(1,nmodules):
            i *= 32
            cm.extend([c+i for c in cm])
        return cm
    channel_map = channel_map(nmodules)
    def set_num_channels(self,maxchan=0):
        if maxchan<=0: maxchan=self.nchannels
        n32 = ((maxchan-1)//self.channels_per_module+1)
        self.set_channel_block_mask(n32*'1')
    def init(self,freq=25000,pre=10000,post=200000,ext_clk=False,ext_trg=False,edge=1,nch=32,mode=None):
        if mode is None: mode = self.MODE.TRIGGERED_CONTINUOUS
        self.abort()
        self.setup_clock(ext_clk,freq,self.ROLE.MASTER)
        self.setup_trigger(ext_trg,edge)
        self.set_num_channels(nch)
        self.set_mode(mode,pre,post)
    def test(self,nch=96,chunk=1024,once=True): # HINT: TEST
        """ nch must be multiple of 2 """
        read = 0
        channels = self.channel_map[:nch]
        if isinstance(channels,list):
            channels.sort()
        print("streaming channels: %s"%(channels,))
        from time import time
        stream = self.stream(nch,chunk,ready=not once)
        if once:
            import matplotlib.pyplot as pp
        else:
            next(stream)
            t0    = time()
        for d in stream:
            read += d.shape[0]
            a = self.sort(d)
            if once:
                print(read)
                pp.plot(a)
                pp.show()
                if read>0: return a
            else:
                print(read,read/float(time()-t0))

class acq132(_acq1xx):
    """ max streaming rates at num_channels
            ~ 80kHz @ 32ch
            ~140kHz @ 16ch
            ~200kHz @  8ch
            ~140kHz @  4ch
        min freq: 62500Hz
    """
    nmodules  = 8
    nchannels = 32
    channels_per_module = nchannels // nmodules
    channel_map = range(1,33)
    min_sclk = 4000000
    max_nacc = 64
    min_clk  = min_sclk//max_nacc
    def set_dtacq_rgm(self,on=True):
        self.set_dtacq('RepeatingGateMode',1 if on else 0)
    def set_dtacq_dual_rate(self,on=True,*params):
        self.set_dtacq('DualRate',1 if on else 0,*params)
    def set_gate_src(self,di=None,high=True):
        if di is None:
            args = ['none']
        else:
            if isinstance(di,int):
                di = 'DI%d'%(di,)
            args = [di,'high' if high else 'low']
        self.shell("set.gate_src",*args)
    def set_all_accumulate(self,nacc,shift):
        self.shell('set.all.acq132.accumulate',nacc,shift)
    def set_all_decimate(self,nacc,shift):
        self.shell('set.all.acq132.decimate',nacc,shift)
    def setup_trigger(self,ext_clk,freq,role,gate=None):
        if gate is None:
            self.set_dtacq_rgm(False)
            self.set_gate_src()
            super(acq132,self).setup_trigger(self,ext_clk,freq,role)
        else:
            self.set_dtacq_rgm(False)
            self.set_trig()
    def setup_clock(self,ext_clk,freq,role):
        if freq<self.min_clk: raise Exception('setup_clock: selected sampling rate too low; freq < %d Hz'%(self.min_clk,))
        nacc = 1
        shift = -2
        while freq<self.min_sclk:
            freq*=2
            nacc*=2
            shift+=1
        super(acq132,self).setup_clock(ext_clk,freq,role)
        self.set_all_accumulate(nacc,shift if shift>0 else 0)
    def set_num_channels(self,maxchan=0):
        if maxchan<=0: maxchan=self.nchannels
        mods = ((maxchan-1)//self.channels_per_module+1)
        if   mods<=2: mask = '10001000'
        elif mods<=4: mask = '11001100'
        else:         mask = '11111111'
        self.set_channel_block_mask(mask)
    def init(self,freq=200000,pre=10000,post=200000,ext_clk=False,ext_trg=False,edge=1,nch=32,mode=None):
        if mode is None: mode = self.MODE.TRIGGERED_CONTINUOUS
        self.abort()
        self.setup_clock(ext_clk,freq,self.ROLE.MASTER)
        self.setup_trigger(ext_trg,edge,self.ROLE.MASTER,False)
        self.set_num_channels(nch)
        self.set_mode(mode,pre,post)
    def test(self,nch=32,chunk=1024,once=True): # HINT: TEST
        """ nch must be multiple of 2 """
        read = 0
        channels = self.channel_map[:nch]
        if isinstance(channels,list):
            channels.sort()
        print("streaming channels: %s"%(channels,))
        from time import time
        stream = self.stream(nch,chunk,ready=not once)
        if once:
            import matplotlib.pyplot as pp
        else:
            next(stream)
            t0    = time()
        for d in stream:
            read += d.shape[0]
            a = self.sort(d)
            if once:
                print(read)
                pp.plot(a)
                pp.show()
                if read>0: return a
            else:
                print(read,read/float(time()-t0))


if __name__ == '__main__':
    d=acq132('192.168.0.100')
    d.statemon.start()
    f=dt100_sys(d.ip,'/tmp/test')
    channels = 8
    d.set_simulate()
    d.init(100000,nch=channels)
    d.arm()
    #d.wait_arm()
    print(d.statemon.last_time)
    try:
        d.soft_trigger()
        a=d.test(nch=channels,chunk=100,once=1)
    finally:
        d.abort()
        print(d.statemon.last_time)
