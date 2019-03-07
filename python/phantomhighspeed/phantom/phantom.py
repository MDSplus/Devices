# !! currently the phantom libraries are unstable in their  Win64 version
# make sure you use win 32bit python

import ctypes as _c,numpy as _n
import time as _time
class RECT(_c.Structure):
     _fields_ = [
        ('left',   _c.c_uint32),
        ('top',    _c.c_uint32),
        ('right',  _c.c_uint32),
        ('bottom', _c.c_uint32),
    ]
class TIME64(_c.Structure):
     _fields_ = [
        ('fractions',  _c.c_uint32),
        ('seconds',    _c.c_uint32),
    ]
class PCINESTATUS(_c.Structure):
    _fields_ = [
        ('Stored',    _c.c_uint32),
        ('Active',    _c.c_uint32),
        ('Triggered', _c.c_uint32),
    ]
class ACQUIPARAMS(_c.Structure):
    _fields_ = [
        ('ImWidth',      _c.c_uint32),
        ('ImHeight',     _c.c_uint32),
        ('FrameRateInt', _c.c_uint32),
        ('Exposure',     _c.c_uint32),
        ('EDRExposure',  _c.c_uint32),
        ('ImDelay',      _c.c_uint32),
        ('PTFrames',     _c.c_uint32),
        ('ImCount',      _c.c_uint32),
        ('SyncImaging',  _c.c_uint32),
        ('AutoExposure', _c.c_uint32),
        ('AutoExpLevel', _c.c_uint32),
        ('AutoExpSpeed', _c.c_uint32),
        ('AutoExpRect',  RECT),
        ('Recorded',     _c.c_uint32),
        ('TriggerTime',  TIME64),
        ('RecordedCount',_c.c_uint32),
        ('FirstIm',      _c.c_uint32),
        ('FRPSteps',     _c.c_uint32),
        ('FRPImgNr',     _c.c_uint32*16),
        ('FRPRate',      _c.c_uint32*16),
        ('FRPExp',       _c.c_uint32*16),
        ('Decimation',   _c.c_uint32),
        ('BitDepth',     _c.c_uint32),
        ('CamGainRed',   _c.c_uint32),
        ('CamGainGreen', _c.c_uint32),
        ('CamGainBlue',  _c.c_uint32),
        ('CamGain',      _c.c_uint32),
        ('ShutterOff',   _c.c_uint32),
        ('CFA',          _c.c_uint32),
        ('CineName',     _c.c_char*256),
        ('Description',  _c.c_char*4096),
        ('FRPShape',     _c.c_uint32*16),
        ('dFrameRate',   _c.c_double),
       ]
class IMRANGE(_c.Structure):
    _fields_ = [
        ('First', _c.c_int32),
        ('Cnt',   _c.c_uint32),
    ]
class IH(_c.Structure):
    _fields_ = [
        ('biSize',          _c.c_uint32),
        ('biWidth',         _c.c_int32 ),
        ('biHeight',        _c.c_int32 ),
        ('biPlanes',        _c.c_int16 ),
        ('biBitCount',      _c.c_int16 ),
        ('biCompression',   _c.c_uint16),
        ('biSizeImage',     _c.c_uint16),
        ('biXPelsPerMeter', _c.c_int32 ),
        ('biYPelsPerMeter', _c.c_int32 ),
        ('biClrUsed',       _c.c_uint16),
        ('biClrImportant',  _c.c_uint16),
        ('BlackLevel',      _c.c_int32),
        ('WhiteLevel',      _c.c_int32),
    ]
class IP(object):
    def __init__(self,ip):
        if isinstance(ip,(str,)):
            self.__dict__['str'] = ip
        else:
            self.__dict__['int'] = ip
    @property
    def int(self):
        if 'int' in self.__dict__: return self.__dict__['int']
        ip = _n.array([int(i) for i in self.str.split('.')],_n.uint8)
        ip.dtype = _n.uint32
        self.__dict__['int'] = ip[0].newbyteorder('S')
        return self.__dict__['int']
    @property
    def str(self):
        if 'str' in self.__dict__: return self.__dict__['str']
        ip = _n.array([self.int],_n.uint32)
        ip.dtype = _n.uint8
        return "%d.%d.%d.%d"%(ip[3],ip[2],ip[1],ip[0])
_NULL = _c.c_void_p(0)
_PHCONHEADERVERSION = _c.c_uint32(770)

class PhantomExc(Exception): pass
class PhantomExcConnect(PhantomExc): pass
class PhantomExcTimeout(PhantomExc): pass
class PhantomExcNotTriggered(PhantomExc): pass

class phantom(object):
    debug = False
    _phcon = None
    @staticmethod
    def find_cameras(source_addr=""):
        import socket
        import time
        server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        server.settimeout(1)
        server.bind((source_addr, 0))
        server.sendto(b"phantom?", ('<broadcast>', 7380))
        ans = {}
        while True:
            try:   type,addr = server.recvfrom(256)
            except:break
            else:  ans[addr[0]] = type
        return ans

    @classmethod
    def phcon(cls):
        if cls._phcon is None:
            cls._phcon = _c.CDLL("PhCon.dll")
            DO_IGNORECAMERAS = 1
            cls._phcon.PhSetDllsOption(0) # ensure this setting
            cls._phcon.PhLVRegisterClientEx(_NULL, _NULL, _PHCONHEADERVERSION)
        return cls._phcon
    @classmethod
    def unregister(cls):
        if cls._phcon is None: return
        #cls._phcon.PhLVUnregisterClient()
        handle = cls._phcon._handle
        cls._phcon = None
        _c.windll.kernel32.FreeLibrary(handle)
    @classmethod
    def add_ip(cls,ip):
        if cls.debug: print("adding ip %s"%ip)
        cls._check(cls.phcon().PhAddVisibleIp(_c.c_uint32(IP(ip).int)))
    @classmethod
    def _PhMakeAllIpVisible(cls):
        cls._check(cls.phcon().PhMakeAllIpVisible())
    @classmethod
    def getVisibleIp(cls):
        cnt = _c.c_uint32(cls.getCameraCount())
        pips= (_c.c_uint32*cnt.value)()
        cls._check(cls.phcon().PhGetVisibleIp(_c.byref(cnt),pips))
        return [IP(ip).str for ip in pips]
    @classmethod
    def getIgnoredIp(cls):
        cnt = _c.c_uint32(cls.getCameraCount())
        pips= (_c.c_uint32*cnt.value)()
        cls._check(cls.phcon().PhGetIgnoredIp(_c.byref(cnt),pips))
        return [IP(ip).str for ip in pips]
    @classmethod
    def _PhGetErrorMessage(cls,errno):
        msg = (_c.c_char*256)()
        cls.phcon().PhGetErrorMessage(_c.c_int32(errno),msg)
        return msg.value
    @classmethod
    def _check(cls,errno):
        if errno<0:
            raise PhantomExc("%d: %s"%(errno,cls._PhGetErrorMessage(errno),))
        elif cls.debug and errno>0:
            print("%d: %s"%(errno,cls._PhGetErrorMessage(errno),))
    sdlo_phantom = 100
    sdlo_phcon   = 101
    sdlo_phint   = 102
    sdlo_phfile  = 103
    sdlo_phsig   = 104
    sdlo_phsigv  = 105
    sdlo_toram   = 106
    @classmethod
    def _PhSetDllsLogOption(cls,module,level):
        cls._check(cls.phcon().PhSetDllsLogOption(_c.c_uint32(module),_c.c_uint32(level)))
    @classmethod
    def setConLog(cls,level=0): # 0:off, -1:full
        cls._PhSetDllsLogOption(cls.sdlo_phcon,level)
    @classmethod
    def setIntLog(cls,level=0): # 0:off, -1:full
        cls._PhSetDllsLogOption(cls.sdlo_phint,level)
    @classmethod
    def setFileLog(cls,level=0): # 0:off, -1:full
        cls._PhSetDllsLogOption(cls.sdlo_phfile,level)
    @classmethod
    def setSigLog(cls,level=0): # 0:off, -1:full
        cls._PhSetDllsLogOption(cls.sdlo_phsig,level)
    @classmethod
    def setSigVLog(cls,level=0): # 0:off, -1:full
        cls._PhSetDllsLogOption(cls.sdlo_phsigv,level)
    @classmethod
    def setLogToRam(cls,state=True): # state ? to_ram : to_disk
        cls._PhSetDllsLogOption(cls.sdlo_toram,1 if state else 0)
    @classmethod
    def getCameraCount(cls):
        camcount = _c.c_int32(-1)
        cls._check(cls.phcon().PhGetCameraCount(_c.byref(camcount)))
        return camcount.value
    @classmethod
    def addSimulatedCamera(cls,camver=122,camid=11):
        cls._check(cls.phcon().PhAddSimulatedCamera(_c.c_int32(camver),_c.c_int32(camid)))
    def __init__(self,ip=None):
        if ip is None:
            self.phcon()
            if self.getCameraCount()==0:
                print("No Camera found: Adding Simulated Camera.")
                self.addSimulatedCamera()
            self._cn = _c.c_int32(0)
        else:
            self.phcon() # disable discovery if we have an ip
            self.add_ip(ip)
            self._PhMakeAllIpVisible()
            _time.sleep(10)
            ips = self.getVisibleIp()
            if ip in ips:
                self._cn = _c.c_int32(ips.index(ip))
            else:
                print('ip invisible')
                self._cn = _c.c_int32(len(ips))
            if self.is_offline:
                raise PhantomExcConnect("Camera @ '%s' unreachable!"%(ip,))
        if self.debug: print("using %s"%(self,))
    def __str__(self):  return "PHANTOM(%s,%d)"%self.camera_id
    def __repr__(self): return self.__str__()
    def blackReferenceCI(self,callback=_NULL):
        self._check(self.phcon().PhBlackReferenceCI(self._cn,callback))
    def _PhGet(self,reg,ans_p): self.check(self._phcon.PhGet(self._cn,_c.c_int32(reg),ans_p))
    @property
    def is_offline(self): return self._phcon.PhOffline(self._cn)>0
    @property
    def ip_address(self):
        ans = (_c.c_char*16)()
        self.phcon().PhGet(1070,ans)
        return ans.value
    def _PhGetPartitionCount(self):
        partCount = _c.c_uint32(-1)
        self._check(self._phcon.PhGetPartitions(self._cn, _c.byref(partCount), _NULL))
        return partCount.value
    def _PhSetPartitions(self,parts=[1]):
        arr_p = _n.array(parts,_n.int32).ctypes.data_as(_c.POINTER(_c.c_int32))
        self._check(self._phcon.PhSetPartitions(self._cn,_c.c_uint32(len(parts)),arr_p))
    def _PhRecordCine(self):
        self._check(self.phcon().PhRecordCine(self._cn))
    def _PhSendSoftwareTrigger(self):
        self._check(self._phcon.PhSendSoftwareTrigger(self._cn))
    @property
    def camera_id(self):
        serial = _c.c_int32(-1)
        name = (_c.c_char*260)()
        self._check(self._phcon.PhGetCameraID(self._cn,_c.byref(serial),name))
        return name.value,serial.value
    @property
    def is_simulated(self): return self.camera_id[0].startswith('Sim_')
    def getCineParams(self,cine=1):
        aqParams = ACQUIPARAMS()
        self._check(self._phcon.PhGetCineParams(self._cn, _c.c_int32(cine), _c.byref(aqParams), _NULL))
        return aqParams
    def setCineParams(self,aParams,cinenr=1):
        if self._PhGetPartitionCount()==1:
            self._check(self._phcon.PhSetSingleCineParams(self._cn, _c.byref(aParams)))
        else:
            self._check(self._phcon.PhSetCineParams(self._cn, _c.c_int32(cinenr),  _c.byref(aParams)))
    def _PhMaxCineCnt(self):
        return self._phcon.PhMaxCineCnt(self._cn)
    def _PhGetCineStatus(self):
        cs = (PCINESTATUS*self._PhMaxCineCnt())()
        self._check(self._phcon.PhGetCineStatus(self._cn,cs))
        return cs
    def newCineFromCamera(self,cinenr=1):
        pcihandle = _c.POINTER(_c.c_int32)()
        phantom._check(cine.phfile().PhNewCineFromCamera(self._cn,_c.c_int32(cinenr),_c.byref(pcihandle)))
        return cine(pcihandle)

    def init(self,nframes=1000,framerate=1000,exposure=50,width=128,height=128):
        """ init(nframes=1000,framerate=1000,exposure=50,width=128,height=128) """
        cp = self.getCineParams()
        cp.PTFrames,cp.dFrameRate,cp.Exposure = nframes,framerate,exposure
        cp.ImWidth,cp.ImHeight                = width,height
        self.setCineParams(cp)
        self.blackReferenceCI()
        _time.sleep(.3)
    def arm(self):
        self._PhSetPartitions()
        self._PhRecordCine()
        self.wait_active()
    def soft_trigger(self):
        self._PhSendSoftwareTrigger()
        self.wait_triggered()
    @property
    def is_active(self):    return self._PhGetCineStatus()[1].Active>0
    @property
    def is_triggered(self): return self._PhGetCineStatus()[1].Triggered>0
    @property
    def is_stored(self):    return self._PhGetCineStatus()[1].Stored>0
    def wait_active(self,timeout=3):
        to = _time.time()+timeout
        while not self.is_active:
            if _time.time()>to:
                raise PhantomExcTimeout("timeout: not active")
            _time.sleep(.1)
    def wait_triggered(self,timeout=10):
        to = _time.time()+timeout
        while not self.is_triggered:
            if _time.time()>to:
                raise PhantomExcNotTriggered("timeout: not triggered")
            _time.sleep(.1)
    def wait_stored(self,timeout=10):
        to = _time.time()+timeout
        while not self.is_stored:
            if _time.time()>to:
                raise PhantomExcTimeout("timeout: not stored")
            _time.sleep(.1)
    def read_images(self,first=0,cnt=1000,maxchunk=100,debug=False):
        if debug: print("downloading %d frames."%cnt)
        ih = IH()
        with self.newCineFromCamera() as c:
            c.setUseCase(c.uc_save)
            first = max(c.getFirstImageNo(),first)
            bufsz = c.getMaxImgSize()
            if c.getIs16bppCine()>0:
                dtype,bpp = _n.uint16,2
            else:
                dtype,bpp = _n.uint8 ,1
            w,h = c.getImWidth(),c.getImHeight()
            buf = (_c.c_char*(bufsz*maxchunk))()
            end = first+cnt
            while cnt>0:
                chunk = min(cnt,maxchunk)
                c.getCineImage(end-cnt,chunk,buf,bufsz*chunk,ih)
                if ih.biBitCount%3 == 0:
                    yield _n.frombuffer(buf[:chunk*w*h*bpp*3],dtype).reshape((chunk,3,h,w))
                else:
                    yield _n.frombuffer(buf[:chunk*w*h*bpp],dtype).reshape((chunk,h,w))
                cnt -= chunk
                if debug: print("remaining frames: %6d"%cnt)

class cine(object):
    _phfile = None
    uc_view = 1
    uc_save = 2
    @classmethod
    def phfile(cls):
        if cine._phfile is None:
            cine._phfile = _c.CDLL("PhFile.dll")
        return cine._phfile
    def __init__(self,pcihandle):
        self.pcihandle = pcihandle
    def __enter__(self): return self
    def __exit__(self,*a):
        self._PhDestroyCine()
    def _PhGetCineInfo(self,info):
        par = _c.c_int32(-1)
        phantom._check(self._phfile.PhGetCineInfo(self.pcihandle, _c.c_int32(info), _c.byref(par)))
        return int(par.value)
    def getIs16bppCine(self):
        GCI_IS16BPPCINE = 13
        return self._PhGetCineInfo(GCI_IS16BPPCINE)
    def getImWidth(self):
        GCI_IMWIDTH = 24
        return self._PhGetCineInfo(GCI_IMWIDTH)
    def getImHeight(self):
        GCI_IMHEIGHT = 25
        return self._PhGetCineInfo(GCI_IMHEIGHT)
    def getPostTriggerFrames(self):
        GCI_POSTTRIGGER = 28
        return self._PhGetCineInfo(GCI_POSTTRIGGER)
    def getImageCount(self):
        GCI_IMAGECOUNT = 29
        return self._PhGetCineInfo(GCI_IMAGECOUNT)
    def getFirstImageNo(self):
        GCI_FIRSTIMAGENO = 38
        return self._PhGetCineInfo(GCI_FIRSTIMAGENO)
    def getMaxImgSize(self):
        GCI_MAXIMGSIZE = 400
        return self._PhGetCineInfo(GCI_MAXIMGSIZE)
    def setUseCase(self,save=True):
        val = 2 if save else 1 # save2 or view1
        phantom._check(self._phfile.PhSetUseCase(self.pcihandle,_c.c_int32(val)))
    def getCineImage(self,fst,cnt,buf,bufsz,ih):
        imrang = IMRANGE()
        imrang.First,imrang.Cnt = fst,cnt
        phantom._check(self._phfile.PhGetCineImage(self.pcihandle,_c.byref(imrang),buf,_c.c_uint32(bufsz),_c.byref(ih)))
    def _PhDestroyCine(self):
        phantom._check(self._phfile.PhDestroyCine(self.pcihandle))


try:
 import MDSplus
except:
    pass
else:
 class mdsrecord(object):
    """ A class for general interaction with MDSplus nodes
    obj._trigger = mdsrecord('trigger',float)
    obj._trigger = 5   <=>   obj.trigger.record = 5
    a = obj._trigger   <=>   a = float(obj.trigger.record.data())
    """
    def __get__(self,inst,cls):
        data = inst.__getattr__(self._name).getRecord(None)
        if data is None: return None
        data = data.data()
        if self._fun is None or data is None: return data
        return self._fun(data)
    def __set__(self,inst,value):
        inst.__getattr__(self._name).record=value
    def __init__(self,name,fun=None):
        self._name = name
        self._fun  = fun
 class PHANTOM(MDSplus.Device):
    parts=[# Prepare init action collection structure
           {'path': ':ACTIONSERVER',      'type': 'TEXT',     'options':('no_write_shot','write_once')},

           # Init-phase action: configure Phantom camera
           {'path': ':ACTIONSERVER:INIT',          'type': 'ACTION',   'options':('no_write_shot','write_once'),   'valueExpr':'Action(node.DISPATCH,node.TASK)'},
           {'path': ':ACTIONSERVER:INIT:DISPATCH', 'type': 'DISPATCH', 'options':('no_write_shot','write_once'),   'valueExpr':'Dispatch(head.ACTIONSERVER,"INIT",20)'},
           {'path': ':ACTIONSERVER:INIT:TASK',     'type': 'TASK',     'options':('no_write_shot','write_once'),   'valueExpr':'Method(None,"init",head)'},

           {'path': ':ACTIONSERVER:ARM',          'type': 'ACTION',   'options':('no_write_shot','write_once'),   'valueExpr':'Action(node.DISPATCH,node.TASK)'},
           {'path': ':ACTIONSERVER:ARM:DISPATCH', 'type': 'DISPATCH', 'options':('no_write_shot','write_once'),   'valueExpr':'Dispatch(head.ACTIONSERVER,"INIT",50)'},
           {'path': ':ACTIONSERVER:ARM:TASK',     'type': 'TASK',     'options':('no_write_shot','write_once'),   'valueExpr':'Method(None,"arm",head)'},

           {'path': ':ACTIONSERVER:SOFT_TRIGGER',          'type': 'ACTION',   'options':('no_write_shot','write_once','disabled'),   'valueExpr':'Action(node.DISPATCH,node.TASK)'},
           {'path': ':ACTIONSERVER:SOFT_TRIGGER:DISPATCH', 'type': 'DISPATCH', 'options':('no_write_shot','write_once'),   'valueExpr':'Dispatch(head.ACTIONSERVER,"PULSE",1)'},
           {'path': ':ACTIONSERVER:SOFT_TRIGGER:TASK',     'type': 'TASK',     'options':('no_write_shot','write_once'),   'valueExpr':'Method(None,"soft_trigger",head)'},

           # Store-phase action: save video to local tree
           {'path': ':ACTIONSERVER:STORE',          'type': 'ACTION',   'options':('no_write_shot','write_once'),   'valueExpr':'Action(node.DISPATCH,node.TASK)'},
           {'path': ':ACTIONSERVER:STORE:DISPATCH', 'type': 'DISPATCH', 'options':('no_write_shot','write_once'),   'valueExpr':'Dispatch(head.ACTIONSERVER,"STORE",10)'},
           {'path': ':ACTIONSERVER:STORE:TASK',     'type': 'TASK',     'options':('no_write_shot','write_once'),   'valueExpr':'Method(None,"store",head,100)'},

           # Create rest of nodes
           {'path': ':FRAMES',         'type': 'SIGNAL',                                             'options':('no_write_model','write_once')},
           {'path': ':FRAMES:MAX',     'type': 'SIGNAL',                                             'options':('no_write_model','write_once')},
           {'path': ':IP_ADDRESS',     'type': 'TEXT',                                               'options':('no_write_shot', )},
           {'path': ':TRIGGER',        'type': 'NUMERIC', 'valueExpr':'Float64(0).setUnits("s")',    'options':('no_write_shot', )},
           {'path': ':RESOLUTION',     'type': 'NUMERIC', 'valueExpr':'Uint32Array([256,128])',      'options':('no_write_shot', ), 'help':'frame dimension in [W,H]'},
           {'path': ':NUM_FRAMES',     'type': 'NUMERIC', 'value':1000,                              'options':('no_write_shot', )},
           {'path': ':FRAME_RATE',     'type': 'NUMERIC', 'valueExpr':'Int32(10000).setUnits("Hz")', 'options':('no_write_shot',)},
           {'path': ':EXPOSURE',       'type': 'NUMERIC', 'valueExpr':'Int32(100).setUnits("us")',   'options':('no_write_shot',),  'help':'Exposure time in us'},
    ]

    _ip         = mdsrecord('ip_address',str)
    _trigger    = mdsrecord('trigger',float)
    _num_frames = mdsrecord('num_frames',int)
    _resolution = mdsrecord('resolution', lambda x: [int(i) for i in x])
    _frame_rate = mdsrecord('frame_rate',int)
    _exposure   = mdsrecord('exposure', lambda x: int(x*1000))

    _phantom = None
    @property
    def phantom(self):
        if self._phantom is None:
            self.__class__._phantom = phantom(self._ip)
        return self._phantom
    def init(self):
        if self.debug: print("started init")
        w,h = self._resolution
        try: self.phantom.init(self._num_frames,self._frame_rate,self._exposure,w,h)
        except PhantomExcConnect:     raise MDSplus.DevOFFLINE
        except PhantomExc:            raise MDSplus.DevINV_SETUP
        if self.phantom.is_simulated: raise MDSplus.DevCAMERA_NOT_FOUND
    def arm(self):
        if self.debug: print("started arm")
        try: self.phantom.arm()
        except PhantomExcConnect:     raise MDSplus.DevOFFLINE
        except PhantomExcTimeout:     raise MDSplus.DevERROR_DOING_INIT
        except PhantomExc:            raise MDSplus.DevINV_SETUP
        if self.phantom.is_simulated: raise MDSplus.DevCAMERA_NOT_FOUND
    def soft_trigger(self):
        if self.debug: print("started soft_trigger")
        try: self.phantom.soft_trigger()
        except PhantomExcConnect:     raise MDSplus.DevOFFLINE
        except PhantomExc:            raise MDSplus.DevTRIGGER_FAILED
        if self.phantom.is_simulated: raise MDSplus.DevCAMERA_NOT_FOUND
    def store(self,chunk=100):
       if self.debug: print("started store")
       try:
        chunk = int(chunk);
        if chunk <= 0: chunk = 1
        if not self.phantom.is_triggered:raise MDSplus.DevNOT_TRIGGERED
        self.phantom.wait_stored()
        ap = self.phantom.getCineParams()
        def replace_set_with_is(node,value):
            node.no_write_shot = False
            node.no_write_model = True
            node.record = value
            node.write_once = True
        replace_set_with_is(self.frame_rate, MDSplus.Float64(float(ap.dFrameRate)).setUnits('Hz'))
        replace_set_with_is(self.exposure,MDSplus.Float64(int(ap.Exposure)/1000.).setUnits('us'))
        t = _time.time()
        trigger = self._trigger
        rate    = float(ap.dFrameRate)
        try:    import Queue as queue
        except: import queue
        Q = queue.Queue(30)
        def run():
            cur_frame = 0
            maxarray = None
            while cur_frame < self._num_frames:
                try: frames = Q.get(True,1)
                except queue.Empty: continue
                if frames is None: break
                for ic in range(frames.shape[0]):
                    time = trigger + cur_frame / rate
                    limit = MDSplus.Float32(time)
                    dim   = MDSplus.Float32Array([time])
                    data = frames[ic:ic+1]
                    self.frames.makeSegment(limit,limit,dim,data)
                    if maxarray is None:
                        maxarray = _n.zeros((self._num_frames,),dtype=data.dtype)
                    maxarray[cur_frame] = data.max()
                    cur_frame += 1
            win = MDSplus.Window(0,self._num_frames-1,self.trigger)
            rng = MDSplus.Range(None,None,MDSplus.Float64(1./self._frame_rate))
            dim = MDSplus.Dimension(win,rng)
            self.frames_max = MDSplus.Signal(maxarray, None, dim)
        import threading
        thread = threading.Thread(target=run)
        thread.start()
        try:
            for imgs in self.phantom.read_images(0,self._num_frames,chunk,debug=self.debug):
                while thread.is_alive():
                    try:   Q.put(imgs,True,1)
                    except queue.Full: continue
                    else:  break
                else: break
        finally:
            Q.put(None) # indicate last frame to end thread
        thread.join()
        if self.debug: print("transferred in %.2f"%(_time.time()-t,))
       except PhantomExcConnect:     raise MDSplus.DevOFFLINE
       except PhantomExcTimeout:     raise MDSplus.DevTRIGGERED_NOT_STORED
       except PhantomExc:            raise MDSplus.DevCOMM_ERROR
       if self.phantom.is_simulated: raise MDSplus.DevCAMERA_NOT_FOUND
    def deinit(self):
        try: self.phantom.unregister()
        except PhantomExcConnect: raise MDSplus.DevOFFLINE
        except PhantomExc:        raise MDSplus.DevException
        finally: self.__class__._phantom = None
 def testmds(expt='test',shot=1):
    import gc;gc.collect()
    MDSplus.setenv('test_path','C:\\temp')
    from LocalDevices.phantom import PHANTOM
    with MDSplus.Tree(expt,shot,'NEW') as t:
        dev = PHANTOM.Add(t,"PHANTOM")
        t.write()
    old = MDSplus.Device.debug
    MDSplus.Device.debug = max(1,old)
    t.open()
    try:
        dev.init()
        dev.arm()
        dev.soft_trigger()
        dev.store()
    finally:
        dev.deinit()
        t.close()
        MDSplus.Device.debug = old


def test(nframes=1000,filepath="Z:\\tmp\dump"):
    import threading
    try:    import Queue as queue
    except: import queue
    chunksize = 100
    Q = queue.Queue(3)
    def run():
        with open(filepath,"wb") as f:
            while True:
                try: frames = Q.get(True,1)
                except queue.Empty: continue
                if frames is None: break
                f.write(frames.tobytes())
    phantom.debug = True
    p = phantom("10.44.2.118")
    p.init(nframes=nframes,framerate=10000,exposure=90000,width=256,height=128)
    p.arm()
    p.soft_trigger()
    p.wait_stored()
    t = _time.time()
    thread = threading.Thread(target=run)
    thread.start()
    try:
        for imgs in p.read_images(0,nframes,chunksize,debug=1):
            while thread.is_alive():
                try:   Q.put(imgs,True,1)
                except queue.Full: continue
                else:  break
            else: break
    finally:
        Q.put(None)
    thread.join()
    print("transferred in %.2f"%(_time.time()-t,))
if __name__=="__main__":
    pass
