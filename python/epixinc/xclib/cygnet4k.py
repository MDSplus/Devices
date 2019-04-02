#!/usr/bin/python
__version__=(2018,8,31,12)
from threading import Thread,Event
from ctypes import CDLL, byref, c_ushort, c_uint32, c_int, c_char_p, c_void_p, c_long, c_double, create_string_buffer
from time import sleep, time
from sys import exc_info, version_info,platform
import signal,numpy
from platform import uname
if version_info[0]<3:
    from Queue import Queue
else:
    from queue import Queue
def error(msg):
    from sys import stderr
    stderr.write('ERROR: %s\n'%msg)

class CygnetExc(Exception):pass
class CygnetExcConnect(CygnetExc):
    message = 'Could not open camera. No camera connected?.'
class CygnetExcValue(CygnetExc):
    message = 'Value invalid or out of range'
class CygnetExcComm(CygnetExc):
    message = 'Communication Error'

class CygnetExcExtSerTimeout(CygnetExcComm):
    message = 'Partial command packet received, camera timed out waiting for end of packet. Command not processed.'
class CygnetExcExtCkSumErr(CygnetExcComm):
    message = 'Check sum transmitted by host did not match that calculated for the packet. Command not processed.'
class CygnetExcExtI2CErr(CygnetExcComm):
    message = 'An I2C command has been received from the Host but failed internally in the camera.'
class CygnetExcExtUnknownCmd(CygnetExcComm):
    message = 'Data was detected on serial line, command not recognized.'
class CygnetExcExtDoneLow(CygnetExcComm):
    message = 'Host Command to access the camera EPROM successfully received by camera but not processed as EPROM is busy. i.e. FPGA trying to boot.'


class __register(property):
    @property
    def __doc__(self): return '%s=0x%04x[%d], %s'%(self.name,self.addr,self.len,self.doc)
    def __init__(self, addr, len, name, doc):
        self.addr = addr
        self.len  = len
        self.name = name
        self.doc  = doc
class _register_m(__register):
    ext = False
    def __init__(self, addr, len, name, r, w, doc):
        super(_register_m,self).__init__(addr,len,name,doc)
        self.r,self.w = r,w
    def __get__(self, inst, cls):
        if inst is None: return self
        if self.r is None:
            return super(_register_m,self).__get__(inst, cls)
        return self.r(inst.get_value(self.addr,self.len,self.ext))
    def __set__(self, inst, value):
        if self.w is None:
            super(_register_m,self).__set__(inst,value)
        inst.set_value(self.addr|0x80 if self.ext else self.addr,self.len,self.w(value),self.ext)
class _register_e(_register_m): ext = True
class _register_c(__register):
    def __init__(self, addr, len, name, conv, doc):
        super(_register_c,self).__init__(addr,len,name,doc)
        self.conv = conv
    def __get__(self, inst, cls):
        if inst is None: return self
        return self.conv(inst.get_cvalue(self.addr,self.len))


class cygnet4k(object):
    TRIG_EXT_RISING  = 0b11001000
    TRIG_EXT_FALLING = 0b01001000
    TRIG_INTEGRATE   = 0b00001100
    TRIG_INT         = 0b00001110
    debug  = 8
    _lib   = []
    um     = 1
    aoi_rect = [0,0,2048,2048]
    @classmethod
    def lib(cls):
        if len(cls._lib)==0:
            cls._lib.append(cygnet4k._xclib())
        return cls._lib[0]
    class _xclib(CDLL):
        @staticmethod
        def unitmap(unit): return 1<<(unit-1)
        DRIVERPARMS = '-XU 1 -DM %d'  # allow other applications to share use of imaging boards previously opened for use by the first application
        def __init__(self):
            if platform.startswith('win'):
                 form = "%s.dll"
            else:form = "lib%s.so"
            nameparts = ['xclib',uname()[4]]
            for i in range(2):
                try:
                    name = form%('_'.join(nameparts[:i]))
                    super(cygnet4k._xclib,self).__init__(name)
                except OSError:
                    if i==0: err = 'xclib: %s'%(exc_info()[1],)
                    else:
                        print(err);raise
                else: break
            self.pxd_mesgErrorCode.restype = c_char_p

        def print_error_msg(self,status):
            error(self.pxd_mesgErrorCode(status))
            self.pxd_mesgFault(0xFF)

        def close(self):
            self._chk(self.pxd_PIXCIclose(),msg="close")

        def connect(self,um,formatfile="",format="DEFAULT"):
            driverparams = self.DRIVERPARMS % um
            self._chk(self.pxd_PIXCIopen(c_char_p(driverparams), c_char_p(format), c_char_p(formatfile)),CygnetExcConnect,"open")

        def _chk(self,status,exc=CygnetExc,msg=None):
            if status>=0: return status
            self.print_error_msg(status)
            raise exc if msg is None else exc(msg)

        def go_live(self,um):
            self._chk(self.pxd_goLivePair(um, c_long(1), c_long(2)))
        def gone_live(self,um):
            return self.pxd_goneLive(um,0)
        def go_unlive(self,um):
            self._chk(self.pxd_goUnLive(um))

        @classmethod
        def _chk_ser(cls,ack):
            if isinstance(ack,bytes): ack = ord(ack[0])
            if ack==0x50: return
            if ack==0x51: raise CygnetExcExtSerTimeout
            if ack==0x52: raise CygnetExcExtCkSumErr
            if ack==0x53: raise CygnetExcExtI2CErr
            if ack==0x54: raise CygnetExcExtUnknownCmd
            if ack==0x55: raise CygnetExcExtDoneLow
            else:         raise CygnetExcComm(ack)
        def init_serial(self,um):
            try:
                self._chk(self.pxd_serialConfigure(um, 0, c_double(115200.), 8, 0, 1, 0, 0, 0),CygnetExcComm,"init_serial")
            except:
                error("ERROR CONFIGURING SERIAL CAMERALINK PORT")
                raise CygnetExcComm
        def chk_sum(self,msg):
            check = 0
            for c in msg: check ^= ord(c)
            return check
        def send_msg(self,um,msg):
            msg += '\x50';chk = self.chk_sum(msg);msg += chr(chk)
            if cygnet4k.debug&2: print('serial write: %s'%(' '.join(['0x%02x'%ord(c) for c in msg]),))
            self._chk(self.pxd_serialWrite(um, 0, c_char_p(msg), len(msg)),CygnetExcComm,"send_msg")
            return chk
        def flush_serial(self,um):
            buf = create_string_buffer(1)
            while self.pxd_serialRead(um, 0, buf, 1)>0: pass
        def recv_msg(self,um,expected,ack=True,chk=None):
            ackchk = (1 if ack else 0)+(0 if chk is None else 1)
            bytes_to_read = expected + ackchk  # ETX and optional check sum
            buf = create_string_buffer(bytes_to_read)
            timeout = time()+.5;out=b''
            wait = 0.01
            while timeout>time():
                read = self._chk(self.pxd_serialRead(um, 0, buf, bytes_to_read),CygnetExcComm,"recv_msg")
                if read == 0:
                    sleep(wait)
                    wait+=0.01
                    continue
                out+= buf.raw[:read]
                bytes_to_read-= read
                if bytes_to_read<=0:
                    if chk is not None:
                        rchk = ord(out[-1])
                        if rchk != chk:
                            print("CHK MISMATCH: 0x%02x => 0x%02x"%(chk,rchk))
                    if ack: self._chk_ser(out[expected])
                    break
            else:
                if cygnet4k.debug&2: print('serial read: %s'%(' '.join(['0x%02x'%ord(c) for c in out[:expected+ackchk-bytes_to_read]]),))
                raise CygnetExcComm("timeout with %d remaining bytes ack,chk = %s"%(bytes_to_read,(ack,chk)))
            if cygnet4k.debug&2: print('serial read: %s'%(' '.join(['0x%02x'%ord(c) for c in out[:expected+ackchk]]),))
            return out[:expected]

        def get_image_res(self,um): return self.pxd_imageXdims(um),self.pxd_imageYdims(um)
        @property
        def sys_tick_units(self):
            ticku = (c_uint32*2)()
            self._chk(self.pxd_infoSysTicksUnits(ticku),CygnetExcComm,"sys_tick_units")
            return (1E-6 * ticku[0]) / ticku[1]
        def check_capture(self,um,buf=None,last=None):
            nbuf = self.pxd_capturedBuffer(um)
            if nbuf==buf: last,buf,False
            curr = self.pxd_buffersFieldCount(um,nbuf)
            if last is None or (curr-last)>0:
                return curr,nbuf,True
            return last,buf,False
        def fetch_frame(self, um, roi):
            tick_slope = self.sys_tick_units
            tick_off   = None
            if cygnet4k.debug:
                print("number of boards:   %d"   % self.pxd_infoUnits())
                print("buffer memory size: %.1f MB" % (self.pxd_infoMemsize(um)/1048576.))
                print("frame buffers:      %d"   % self.pxd_imageZdims(um))
                print("image resolution:   %d x %d" % tuple(roi[2:]))
                print("max. image res.:    %d x %d" % self.get_image_res(um))
                print("colors:             %d"   % self.pxd_imageCdims(um))
                print("bits per pixel:     %d"   % self.pxd_imageBdims(um))
                print("msec per tick:      %.1f" % (tick_slope * 1E3))
            dbuf = create_string_buffer(roi[2]*roi[3]*2)
            curr,fbuf,new = self.check_capture(um)
            if cygnet4k.debug&8:
                tstart = time()
                to = 0
            while True:
                curr,fbuf,new = self.check_capture(um,fbuf,curr)
                if not new:
                    yield None
                    if cygnet4k.debug&8:
                        to += 1
                    continue
                ticks = self.pxd_buffersSysTicks(um, fbuf)
                if tick_off is None:
                    tick_off = ticks;
                dim  = (ticks - tick_off) * tick_slope
                pixels = self._chk(self.pxd_readushort(um, fbuf, roi[0], roi[1], roi[0]+roi[2], roi[1]+roi[3], dbuf, len(dbuf)/2, c_char_p("Grey")), CygnetExcComm, "readushort")
                data = numpy.frombuffer(dbuf,numpy.uint16).reshape(roi[2:]).copy()
                if cygnet4k.debug&8:
                    print("FRAME %5d READ FROM %d AT TIME %.3f in %f %d" % (curr,fbuf,dim,time()-tstart,to))
                    tstart = time()
                    to = 0
                yield dim,data

    _init_serial_done = False
    def serial_io(self, msg, bytes_to_read=0):
        self.connect()
        if isinstance(msg,int): msg = chr(msg)
        if not self._init_serial_done:
            self.lib().init_serial(self.um)
            self._init_serial_done = True
            sleep(0.02)
        if not bytes_to_read is None:
            self.lib().flush_serial(self.um)
        chk = self.lib().send_msg(self.um,msg)
        if bytes_to_read is None: return # reset micro
        return self.lib().recv_msg(self.um,bytes_to_read,self._serial_ack,chk if self._serial_chk else None)

    @property
    def system_state(self):
        """get system state byte"""
        byte = ord(self.serial_io(0x49,1))
        self._serial_ack,self._serial_chk = bool(byte & 1<<4),bool(byte & 1<<6)
        return byte
    def get_system_state(self):
        """get system state as dict"""
        byte = self.system_state
        return {
        'chksum':  bool(byte & 1<<6),
        'ack':     bool(byte & 1<<4),
        'FPGAboot':bool(byte & 1<<2),
        'FPGArun': bool(byte & 1<<1),
        'FPGAcom': bool(byte & 1<<0)}
    _serial_ack = _serial_chk = False
    @system_state.setter
    def system_state(self,byte):
        old = self._serial_ack,self._serial_chk
        self._serial_ack,self._serial_chk = bool(byte & 1<<4),bool(byte & 1<<6)
        try:    self.serial_io(b'\x4F%c'%byte)
        except: self._serial_ack,self._serial_chk = old
    def set_system_state(self,chksum,ack,FPGAhold,FPGAcom):
        """
        set_system_state(chksum,ack,FPGAhold,FPGAcomms)
        chksum   Bit 6 = 1 to enable check sum mode
        ack      Bit 4 = 1 to enable command ack
        FPGAhold Bit 1 = 0 to Hold FPGA in RESET; do not boot
        FPGAcom  Bit 0 = 1 to enable comms to FPGA EPROM
        """
        byte = 0
        if chksum:   byte |= 1<<6
        if ack:      byte |= 1<<4
        if FPGAhold: byte |= 1<<1
        if FPGAcom:  byte |= 1<<0
        self.system_state = byte

    def reset(self):
        """Will trap Micro causing watchdog and reset of firmware."""
        # The camera will give no response to this command
        self.serial_io('\x55\x99\x66\x11',None)
        while True:
            try:
                self.system_state = 0x11
                if self.system_state == 0x11: break
            except CygnetExc: sleep(.2)
        while True:
            self.system_state = 0x12
            sleep(.2)
            if self.system_state == 0x16:
                 break
    def set_byte(self,addr,byte):
        if self.debug&4: print("set: 0x%02x:= 0x%02x"%(addr,byte))
        self.serial_io(b'\x53\xE0\x02%c%c'%(addr,byte))

    def set_value(self, addr, len, value, use_ext_reg=False):
        if self.debug&4: print(("set: 0x%%02x:= 0x%%0%dx"%(len*2,))%(addr,value))
        s,d = (0,8) if use_ext_reg else (len*8-8,-8)
        for i in range(len):
            byte = value>>s & 0xFF
            if use_ext_reg: # write to extended register
                self.set_byte(0xF3,addr+i)
                self.set_byte(0xF4,byte)
            else:
                self.set_byte(addr+i,byte)
            s += d

    def get_byte(self,addr):
        self.serial_io(b'\x53\xE0\x01%c'%addr)
        byte = ord(self.serial_io(b'\x53\xE1\x01', 1))
        if self.debug&4: print("get: 0x%02x = 0x%02x"%(addr,byte))
        return byte

    def get_value(self, addr, len=1, use_ext_reg=False):
        value = 0
        _addr = addr+len-1 if use_ext_reg else addr
        for i in range(len):
            if use_ext_reg:
                self.set_value(_addr,1,0x00,True)
                byte = self.get_byte(0x73)
            else:
                byte = self.get_byte(_addr)
            value = value<<8 | byte
            _addr += -1 if use_ext_reg else 1
        if self.debug&4: print(("get: 0x%%02x = 0x%%0%dx"%(len*2,))%(addr,value))
        return value

    def get_cvalue(self,addr,len):
        addrc = tuple((addr>>i)&0xff for i in range(17,-1,-8))
        lenc  = len+(addr&1)
        self.system_state |= 1
        try:
            self.serial_io(b'\x53\xAE\x05\x01%c%c%c\x00'%addrc)
            return self.serial_io(b'\x53\xAF%c'%lenc,lenc)[addr&1:]
        finally:
            self.system_state &= -2

    def set_trig_mode(self, raising, ext, abort, cont, fixed, snap):
        """setTrigModeP(raising,ext,abort,cont,fixed,snap)"""
        byte = 0
        if raising: byte |= 1<<7
        if ext:     byte |= 1<<6
        if abort:   byte |= 1<<3
        if cont:    byte |= 1<<2
        if fixed:   byte |= 1<<1
        if snap:    byte |= 1<<0
        self.trig_mode = byte
    def get_trig_mode(self):
        """get trigger mode as dict"""
        byte = self.trig_mode
        return {
        'raising': bool(byte & 1<<7),
        'ext':     bool(byte & 1<<6),
        'abort':   bool(byte & 1<<3),
        'cont':    bool(byte & 1<<2),
        'fixed':   bool(byte & 1<<1),
        'snap':    bool(byte & 1<<0)}
    @property
    def micro_Version(self):
        return tuple(map(ord,self.serial_io(b'\x56',2)[0:2]))

    fpga_ctrl_reg = _register_m(0x00,1,'fpga_ctrl_reg',int,int,"Bit 0 = 1 if TEC is enabled")
    pcb_temp      = _register_m(0x70,2,'pcb_temp[oC]',lambda x: (x&0xFFF if x&0x800 else x&0xFFF-0x1000)/16.,None,"16-bit value; temp * 16")
    trig_mode     = _register_m(0xD4,1,'trig_mode',int,int,"""raising Bit 7 = 1 to enable rising edge, = 0 falling edge Ext trigger (Default=1)
ext     Bit 6 = 1 to enable External trigger (Default=0)
abort   Bit 3 = 1 to Abort current exposure, self-clearing bit (Default=0)
cont    Bit 2 = 1 to start continuous seq'., 0 to stop (Default=1)
fixed   Bit 1 = 1 to enable Fixed frame rate, 0 for continuous ITR (Default=0)
snap    Bit 0 = 1 for snapshot, self-clearing bit (Default=0)""")
    digital_gain  = _register_m(0xD5,2,'digital_gain',lambda x: x/512.,lambda x: int(x*512),"16-bit value; gain * 512")
    roi_x_size    = _register_m(0xD7,2,'roi_x_size',  lambda x: x&0xFFF,lambda x: min(x,0xFFF),"ROI X size as 12-bit value")
    roi_x_offset  = _register_m(0xD9,2,'roi_x_offset',lambda x: x&0xFFF,lambda x: min(x,0xFFF),"ROI X offset as 12-bit value")
    binning       = _register_m(0xDB,1,'binning', lambda x: 1<<(x&7),lambda x: 0x11*(x>>1),"1x1,2x2,4x4 = 0x00,0x11,0x22")
    frame_rate    = _register_m(0xDD,4,'frame_rate[Hz]',lambda x: 6E7/x,lambda x: int(6E7/x),"32-bit value; 1 count = 1*60 MHz period = 16.66ns")
    exposure      = _register_m(0xED,5,'exposure[ms]',lambda x: x/6e4,lambda x: int(x*6e4),"40-bit value; 1 count = 1*60 MHz period = 16.66ns")
    fpga_major    = _register_m(0x7E,1,'fpga_major',int,None,"fpga major version")
    fpga_minor    = _register_m(0x7F,1,'fpga_minor',int,None,"fpga minor version")
    roi_y_size    = _register_e(0x01,2,'roi_y_size',  lambda x: x&0xFFF,lambda x: min(x,0xFFF),"ROI Y size as 12-bit value")
    roi_y_offset  = _register_e(0x03,2,'roi_y_offset',lambda x: x&0xFFF,lambda x: min(x,0xFFF),"ROI Y offset as 12-bit value")
    cmos_temp_raw = _register_e(0x7E,2,'cmos_temp',int,None,"16-bit value")
    serial        = _register_c(0x04,2,'serial',lambda x: tuple(ord(i) for i in x),"serial number")
    build_date    = _register_c(0x06,3,'build_data',lambda x: tuple(ord(i) for i in x),"build date (DD,MM,YY)")
    build_code    = _register_c(0x09,5,'build_code',str,"build code")
    adc_cal       = _register_c(0x0E,4,'adc_cal',lambda x: (ord(x[0])|ord(x[1])<<8,ord(x[2])|ord(x[3])<<8),"CMOS temp callibration for [0,40] oC")
    _adc_cal = None
    @property
    def cmos_temp(self):
        raw = self.cmos_temp_raw
        try:
            if self._adc_cal is None: self._adc_cal = self.adc_cal
            return (40./(self._adc_cal[1]-self._adc_cal[0]))*(raw-self._adc_cal[0])
        except: return raw
    @property
    def roi_rect(self):
        return [self.roi_x_offset,self.roi_y_offset,self.roi_x_size,self.roi_y_size]
    @roi_rect.setter # does not work properly
    def roi_rect(self, rect):
        self.roi_x_size,  self.roi_y_size   = rect[2:]
        self.roi_x_offset,self.roi_y_offset = rect[:2]
        self.abort()
    def __init__(self,dev_id=1):
        if dev_id<=0: raise Exception('Wrong value for DEVICE_ID, must be a positive integer.')
        self.dev_id = dev_id
    _dev_open= 0
    @property
    def dev_open(self): return (self._dev_open & self.um)>0
    @dev_open.setter
    def dev_open(self,val):
        if val: cygnet4k._dev_open |= self.um
        else:   cygnet4k._dev_open &= 0xffffffff-self.um

    def connect(self,config_file=""):
        if len(config_file)>0: self.close()  # as config file might have changed we re-open
        if not self.dev_open:
            self.lib().connect(self.um,config_file)  # use config file if defined else ""
            self.dev_open = True
            self._serial_ack = self._serial_chk = False
            self.system_state
    def close(self):
        if self.dev_open:
            try:   self.lib().close()
            except CygnetExc: pass
            self.dev_open = False
    def snapshot(self): self.trig_mode |= 1<<0
    def abort(self):    self.trig_mode |= 1<<3

    def init(self,exposure=None,frame_rate=None,trig_mode=None,config_file="",aoi_rect=None,binning=None):
        self.connect(config_file)  # use config file if defined else ""
        if aoi_rect:   self.aoi_rect   = aoi_rect
        if exposure:   self.exposure   = exposure
        if frame_rate: self.frame_rate = frame_rate
        if trig_mode:  self.trig_mode  = trig_mode
        if binning:    self.binning    = binning
        if cygnet4k.debug:
            print('binning:    %dx%d' % tuple([self.binning]*2))
            print('AOI rect:   %s'    % self.aoi_rect)
            print('ROI rect:   %s'    % self.roi_rect)
            print('exposure:   %g ms' % self.exposure)
            print('int. clock: %g Hz' % self.frame_rate)
            print('trig_mode:  %s'    % bin(self.trig_mode))
    """ STORE """
    class _stream_feeder(Thread):
        def __init__(self, device, consumer, nframes=-1, aoi=None):
            Thread.__init__ (self,name="stream_feeder")
            self.daemon   = True
            self.device   = device
            self.consumer = consumer
            self.nframes  = nframes
            self._stop    = Event()
            self.ready    = Event()
            self.cframes  = 0
            self.aoi      = aoi

        @property
        def is_triggered(self): return self.cframes>0
        def stop(self): self._stop.set()
        def run(self):
            try:
                if self.nframes == 0: return
                bin = self.device.binning
                aoi = [d//bin for d in self.device.aoi_rect] if self.aoi is None else self.aoi
                for next in self.device.lib().fetch_frame(self.device.um,aoi):
                    self.ready.set()
                    if self._stop.is_set(): return
                    if next is None:
                        sleep(.01)
                        continue
                    self.consumer.put(next,False)
                    self.cframes += 1
                    if (self.nframes>0 and self.cframes >= self.nframes): return
            finally:
                self.consumer.start()
                self.consumer.put(None)

    class _stream_consumer(Thread):
        """a thread class that will stream frames to MDSplus tree"""
        def __init__ (self, nframes, storemethod, *storeargs, **storekwargs):
            Thread.__init__ (self,name="stream_consumer")
            self.daemon      = True
            self.nframes     = nframes
            self.storemethod = storemethod
            self.storeargs   = storeargs
            self.storekwargs = storekwargs
            self.queue = Queue(-1 if nframes<0 else nframes+1)
            self._stop = Event()
        def stop(self): self._stop.set()
        def run(self):
            tstart = time()
            cframes = 0
            while (self.nframes<0 or cframes<self.nframes):  # run until None is send
                if self._stop.is_set(): break
                frameset = self.queue.get()
                if frameset is None: break
                self.storemethod(frameset[0],frameset[1], *self.storeargs, **self.storekwargs)
                cframes += 1
            print("STORE FINISHED AFTER %.1f sec"%(time()-tstart))
        def put(self,*a,**k): self.queue.put(*a,**k)
        def get(self,*a,**k): self.queue.get(*a,**k)

    _streams  = {}
    def get_stream(self,id):
        if self.um in self._streams:
            return self._streams[self.um][id]
    def set_stream(self,id,val):
        if not self.um in self._streams:
            self._streams[self.um] = [None,None]
        self._streams[self.um][id] = val
    @property
    def stream_feeder(self):return self.get_stream(0)
    @stream_feeder.setter
    def stream_feeder(self,val):self.set_stream(0,val)
    @property
    def stream_consumer(self):return self.get_stream(1)
    @stream_consumer.setter
    def stream_consumer(self,val):self.set_stream(1,val)
    def get_temps(self):
        try:   cmos = self.cmos_temp
        except:cmos = None
        try:   pcb  = self.pcb_temp
        except:pcb  = None
        return cmos,pcb
    def start_capture_stream(self, nframes, aoi, storemethod, *storeargs, **storekwargs):
        self.connect() # connect if not yet connected
        if self.lib().gone_live(self.um):
            self.stop_capture_stream(-1)
        cmos,pcb = self.get_temps()
        self.lib().go_live(self.dev_id)
        self.stream_consumer = self._stream_consumer(nframes, storemethod, *storeargs, **storekwargs)
        self.stream_feeder   = self._stream_feeder(self, self.stream_consumer, nframes, aoi)
        timeout = time()+3
        while not self.lib().gone_live(self.um):
            if timeout>time(): raise CygnetExc("timeout on going live")
            sleep(.1)
        self.stream_feeder.start()
        signal.signal(signal.SIGINT,lambda *a: self.stop_capture_stream(0))
        if cygnet4k.debug: print("Video capture started.")
        if self.stream_feeder.is_alive():
            self.stream_feeder.ready.wait(1)
        return cmos,pcb
    def stop_capture_stream(self,timeout=1):
        if self.stream_feeder is not None:
            if timeout>0 and not self.stream_feeder.nframes<0:
                timeout+=time()
                while self.stream_feeder.is_alive():
                    if time()>timeout: break
                    self.stream_feeder.join(.1)
        self.connect()
        self.lib().go_unlive(self.um)
        if self.stream_feeder is not None:
            if timeout<0: self.stream_consumer.stop()
            self.stream_feeder.stop()
            self.stream_feeder.join()
            self.stream_feeder = None
            if cygnet4k.debug: print("Video capture stopped.")
            signal.signal(signal.SIGINT, signal.SIG_DFL)
            cmos,pcb = (None,None) if timeout<0 else self.get_temps()
            self.stream_consumer.join()
            self.stream_consumer = None
        elif self.stream_consumer is not None:
            if timeout<0: self.stream_consumer.stop()
            else:         self.stream_consumer.put(None)
            cmos,pcb = (None,None) if timeout<0 else self.get_temps()
            self.stream_consumer.join()
            self.stream_consumer = None
        return cmos,pcb

try:
 import MDSplus
except: pass
else:
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

 class CYGNET4K(MDSplus.Device):
    """Cygnet 4K sCMOS Camera"""
    parts=[
      {'path':':ACTIONSERVER',       'type':'text', 'options':('no_write_shot','write_once')},
      {'path':':ACTIONSERVER:INIT',  'type':'action','valueExpr':"Action(Dispatch(head.actionserver,'INIT',20,None),Method(None,'init',head))",'options':('no_write_shot','write_once')},
      {'path':':ACTIONSERVER:START', 'type':'action','valueExpr':"Action(Dispatch(head.actionserver,'INIT',50,None),Method(None,'start',head))",'options':('no_write_shot','write_once')},
      {'path':':ACTIONSERVER:STOP',  'type':'action','valueExpr':"Action(Dispatch(head.actionserver,'STORE',50,None),Method(None,'stop',head,1))",'options':('no_write_shot','write_once')},
      {'path':':ACTIONSERVER:DEINIT','type':'action','valueExpr':"Action(Dispatch(head.actionserver,'DEINIT',50,None),Method(None,'deinit',head))",'options':('no_write_shot','write_once')},
      {'path':':COMMENT',      'type':'text'},
      {'path':':CONF_FILE',    'type':'text',                                                 'options':('no_write_shot',)},
      {'path':':DEVICE_ID',    'type':'numeric', 'valueExpr':"Int32(1)",                      'options':('no_write_shot',)},
      {'path':':NUM_FRAMES',   'type':'numeric', 'valueExpr':"Int32(100)",                    'options':('no_write_shot',)},
      {'path':':BINNING',      'type':'text',    'value':'1x1',                               'options':('no_write_shot',)},
      {'path':':ROI_RECT',     'type':'numeric', 'valueExpr':'Int32([0,0,2048,2048])',        'options':('no_write_shot',)},
      {'path':':EXPOSURE',     'type':'numeric', 'valueExpr':"Float32(4).setUnits('ms')",     'options':('no_write_shot',)}, # msec
      {'path':':FRAME_RATE',   'type':'numeric', 'valueExpr':"Float32(27.333).setUnits('Hz')",'options':('no_write_shot',)}, # Hz
      {'path':':TRIGGER_TIME', 'type':'numeric', 'valueExpr':"Float32(0).setUnits('s')",      'options':('no_write_shot',)},
      {'path':':TRIG_MODE',    'type':'numeric', 'valueExpr':'node.INT',                      'options':('no_write_shot',)},
      {'path':':TRIG_MODE:EXT_RISING',  'type':'numeric', 'value':cygnet4k.TRIG_EXT_RISING,   'options':('no_write_shot',)},
      {'path':':TRIG_MODE:EXT_FALLING', 'type':'numeric', 'value':cygnet4k.TRIG_EXT_FALLING,  'options':('no_write_shot',)},
      {'path':':TRIG_MODE:INT',         'type':'numeric', 'value':cygnet4k.TRIG_INT,          'options':('no_write_shot',)},
      {'path':':TEMP_CMOS',             'type':'numeric','options':('no_write_model','write_once')},
      {'path':':TEMP_PCB',              'type':'numeric','options':('no_write_model','write_once')},
      {'path':':FRAMES',                'type':'signal', 'options':('no_write_model','write_once')},
      {'path':':FRAMES:MAX',            'type':'signal', 'options':('no_write_model','write_once')},
    ]
    _conf_file  = mdsrecord('conf_file',str)
    _dev_id     = mdsrecord('device_id',int)
    _trigger    = mdsrecord('trigger_time',float)
    _num_frames = mdsrecord('num_frames',int)
    _roi_rect   = mdsrecord('roi_rect', lambda x: [int(i) for i in x])
    _frame_rate = mdsrecord('frame_rate',int)
    _exposure   = mdsrecord('exposure', float)
    _trig_mode  = mdsrecord('trig_mode',int)
    _binning    = mdsrecord('binning',lambda x: int(x[0]))

    _cygnet4k = None
    @property
    def cygnet4k(self):
        if self._cygnet4k is None:
            self._cygnet4k = cygnet4k(self._dev_id)
        return self._cygnet4k
    def init(self):
        try:
            self.deinit()
            # self.cygnet4k.reset()
            self.cygnet4k.init(
                self._exposure,
                self._frame_rate,
                self._trig_mode,
                self._conf_file,
                self._roi_rect,
                self._binning,
            )
        except CygnetExcConnect: raise MDSplus.DevOFFLINE
        except CygnetExcValue:   raise MDSplus.DevINV_SETUP
        except CygnetExcComm:    raise MDSplus.DevIO_STUCK
    @staticmethod
    def _stream(dim,data,node,nodemax):
         nodemax.makeSegment(dim,dim,MDSplus.Float32([dim]),MDSplus.Uint16([numpy.max(data)]))
         if MDSplus.Device.debug: print('storeFrame: %s, %s, %s'%(node.minpath,dim,data.shape))
         dims = MDSplus.Float32([dim]).setUnits('s')
         data = MDSplus.Uint16([data])
         node.makeSegment(dim,dim,dims,data)
    def start(self):
        def validate(node,value):
            node.write_once = node.no_write_shot = False
            try:    node.record = node.record.setValidation(value)
            finally:node.write_once = node.no_write_shot = True
        def store_temp(node,new):
            if   isinstance(new,(float,)): node.record = MDSplus.Float64([new])
            elif isinstance(new,(int,  )): node.record = MDSplus.Uint32 ([new])
        try:
            validate(self.frame_rate,MDSplus.Float32(self.cygnet4k.frame_rate))
            validate(self.exposure,  MDSplus.Float32(self.cygnet4k.exposure))
            validate(self.trig_mode, MDSplus.Uint8(self.cygnet4k.trig_mode))
            validate(self.binning,   MDSplus.Int8(self.cygnet4k.binning))
            validate(self.roi_rect,  MDSplus.Int16(self.cygnet4k.roi_rect))
            aoi = self._roi_rect
            cmos,pcb = self.cygnet4k.start_capture_stream(self._num_frames,aoi,self._stream,self.frames,self.frames_max)
            store_temp(self.temp_cmos, cmos)
            store_temp(self.temp_pcb , pcb )
        except CygnetExcConnect: raise MDSplus.DevOFFLINE
        except CygnetExcValue:   raise MDSplus.DevINV_SETUP
        except CygnetExcComm:    raise MDSplus.DevIO_STUCK

    def stop(self,timeout=1):
        if self.cygnet4k.stream_consumer is None: return
        if isinstance(timeout,MDSplus.Data): timeout = timeout.data().tolist()
        def update(node,new):
            if   isinstance(new,(float,)): new = MDSplus.Float32(new)
            elif isinstance(new,(int,  )): new = MDSplus.Uint16(new)
            else: return
            rec = node.getRecord(None)
            if rec is None: rec = MDSplus.Array([new,new])
            elif len(rec)!=1: return
            else: rec = MDSplus.Array([rec[0],new])
            node.write_once = node.no_write_shot = False
            try:    node.record = rec
            finally:node.write_once = node.no_write_shot = True
        try:
            cmos,pcb = self.cygnet4k.stop_capture_stream(timeout)
            if self.frames_max.getNumSegments()>0:
                triggered = True
                rec = self.frames_max.getRecord(None)
                if rec is not None:
                    self.frames_max.write_once = self.frames_max.no_write_shot = False
                    try:    self.frames_max.record = rec
                    finally:self.frames_max.write_once = self.frames_max.no_write_shot = True
            else: triggered = False
            if timeout<0: return
            update(self.temp_cmos,cmos)
            update(self.temp_pcb, pcb )
        except CygnetExcConnect: raise MDSplus.DevOFFLINE
        except CygnetExcValue:   raise MDSplus.DevINV_SETUP
        except CygnetExcComm:    raise MDSplus.DevIO_STUCK
        if not triggered: raise MDSplus.DevNOT_TRIGGERED
    def deinit(self): self.stop(-1)

 def testmds(expt='test',shot=1):
    import gc;gc.collect()
    MDSplus.setenv('test_path','/tmp')
    from LocalDevices.cygnet4k import CYGNET4K
    with MDSplus.Tree(expt,shot,'NEW') as t:
        dev = CYGNET4K.Add(t,"CYGNET4K")
        t.write()
        dev.conf_file.no_write_shot = False
        dev.conf_file = "/etc/xcap_cygnet4k.fmt"
        dev.roi_rect.no_write_shot = False
        dev.roi_rect = MDSplus.Int32([500,500,1000,1000])
    old = MDSplus.Device.debug
    MDSplus.Device.debug = 0 #max(1,old)
    t.open()
    try:
        dev.init()
        sleep(1)
        dev.start()
        sleep(1)
        dev.stop()
    finally:
        dev.deinit()
        print(dev.frames_max.getRecord(None))
        t.close()
        MDSplus.Device.debug = old

def test():
   c = cygnet4k(1)
   c.init(39,25,c.TRIG_INT,"/etc/xcap_cygnet4k.fmt",[500,500,1000,1000],2)
   def store(dim,data):
       print("STORED: %7.3fs %s; %4d <= p <= %4d; %d"%(dim,data.shape,numpy.min(data),numpy.max(data),numpy.sum(data==0)))
   c.start_capture_stream(10,store)
   try:
       sleep(3)
   finally:
       c.stop_capture_stream()

if __name__=='__main__':
    testmds()
