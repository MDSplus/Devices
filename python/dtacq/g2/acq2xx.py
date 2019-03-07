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

import numpy
import array
import ftplib
import tempfile
import socket
import json
import MDSplus
import re
import pexpect
import os
import time
#import pdb

debug = 0

if os.getenv("LOGCMD", "NO") == "YES":
    logcmd = 1
else:
    logcmd = 0

def lprint(s):
    if logcmd:
        print(s)

def dprint(s):
    if debug:
        print(s)

class Connection:
    def __init__(self, _p):
        self.p = _p

class DT100 :
    """
    Connects to remote dt100 server, holds open connections and handles transactions
    """
    def logtx(self, s):
        global logcmd
        if logcmd > 0:
            print("%s => \"%s\"" % (self.host, s))

    def logrx(self, s):
        global logcmd
        if logcmd > 0:
            print("%s <= \"%s\"" % (self.host, s))

    def _connect(self):
        hp = self.host.split(":")
        if len(hp)==2:
            # it's a tunnel ...
            target = hp[0] + ' ' + hp[1]
        else:
            target = self.host + ' ' + '53504'

        return Connection(pexpect.spawn('nc ' + target))

    def connectMaster(self):
        dprint("connectMaster( " + self.host + " )")
        self.acq = self._connect()
        self.acq.p.expect('MasterInterpreter')
        self.acq.p.sendline('dt100 open master 1')
        i = self.acq.p.expect("DT100:\r", timeout=60);
        if i==0:
            dprint("OK")
        else:
            print("Timeout")

    def connectShell(self):
        dprint("connectShell( " + self.host + " )")
        self.sh = self._connect()
        self.sh.p.expect('MasterInterpreter')
        self.sh.p.sendline('dt100 open shell 1')
        i = self.sh.p.expect("DT100:\r", timeout=60);
        if i==0:
            dprint("OK")
        else:
            print("Timeout")

    def connectStatemon(self):
        hp = self.host.split(":")
        if len(hp)==2:
            # it's a tunnel ...
            port = int(hp[1]) + 1
            target = hp[0] + ' ' + str(port)
        else:
            target = self.host + ' ' + '53535'

        dprint("connectStatemon(" + target)

        self.statemon = pexpect.spawn('nc ' + target)
        self.statemon.first_time = 1
        self.statemon.arm_time = self.statemon.stop_time = 0
        #self.statemon = pexpect.spawn('nc ' + self.host + ' ' + '53535')

    def connectChannel(self, channel):
        channel_dev = "/dev/acq32/acq32.1.%02d" % channel
        dprint("connectChannel( " + self.host + " " + channel_dev + " )")
        ch = self._connect()
        ch.p.expect('MasterInterpreter')
        dprint("sendline dt100 open data1 " + channel_dev)
        ch.p.sendline('dt100 open data1 ' + channel_dev)
        dprint("expect:");
        i = ch.p.expect("DT100:\r", timeout=60);
        if i==0:
            dprint("OK")
        else:
            print("Timeout")
        return ch

    def acqcmd(self, command):
        tx = "acqcmd " + command
        self.logtx(tx)
        self.acq.p.sendline(tx)
        self.acq.m = re.compile('ACQ32:(.*)\r')
        i = self.acq.p.expect(self.acq.m, timeout=60);
        if i==0:
            self.logrx(self.acq.p.match.group(0))
            return self.acq.p.match.group(1)
        else:
            print("Timeout")
            return 0

    def acq2sh(self, command):
        self.logtx(command)
        self.sh.p.sendline(command)
        self.sh.m = re.compile('(.*)\r\nEOF(.*)\r\n')
        i = self.sh.p.expect(self.sh.m, timeout=60);
        if i==0:
            dprint("OK")
            return self.sh.p.match.group(1)
        else:
            print("Timeout")
            return 0

    def waitState(self, state):
        regstr = '([0-9\.]*) [0-9] ST_(.*)\r\n'
        dprint ("waitState %s" % regstr)
        wantex = re.compile(regstr)

        while self.statemon.expect([wantex, pexpect.TIMEOUT], timeout=60) == 0:
            dprint(self.statemon.after)
            if self.statemon.match.group(2) == "ARM":
                self.statemon.arm_time = (float)(self.statemon.match.group(1))
                self.statemon.stop_time = 0
            elif self.statemon.match.group(2) == "STOP":
                self.statemon.stop_time = (float)(self.statemon.match.group(1))
            if self.statemon.match.group(2) == state:
                if state == "STOP" and self.statemon.first_time == 1:
                    dprint("pass first time")
                    pass
                else:
                    break
            self.statemon.first_time = 0

#                print self.statemon.match.group(0)
#        print "match %s" % (self.statemon.match.group(1))

        active_time = 0

        if self.statemon.arm_time != 0 and self.statemon.stop_time != 0:
            active_time = self.statemon.stop_time - self.statemon.arm_time
            self.statemon.arm_time = self.statemon.stop_time = 0
            dprint("Active time: %f" % active_time)

        return [self.statemon.match.group(2), active_time]

    def readChannel(self, channel, nsamples, start=0, stride=1, format='h'):
        ch = self.connectChannel(channel)
        read_spec = "dt100 read %d %d %d" % (start, start+nsamples, stride)
        self.logtx("sendline:" + read_spec)
        ch.p.sendline(read_spec)
        read_rep = re.compile('DT100:([0-9]*) bytes\r\n')
        rc = ch.p.expect(read_rep, timeout=60)
        if rc == 0:
            nbytes = int(ch.p.match.group(1))
            data = array.array(format)
            data.fromstring(ch.p.read(nbytes))
            dprint(data)
            return data
        else:
            dprint("ERROR")
            return "ERROR"

    def __init__(self, _host):
        'create a transport host is a DNS name, or \'.D\' in A.B.C.D where $SUBNET=A.B.C'
        dprint("Dt100__init__ host:" + _host)
        if _host.startswith('.'):
            self.host = str(os.getenv("SUBNET")) + _host
        else:
            self.host = _host

        if os.getenv("CONNECT", "YES") == "YES":
            self.connectMaster()
            self.connectShell()
            self.connectStatemon()

## ACQ200 constants
IN32 = '-' * 32
Z32  = '0' * 32
IN6  = '-' * 6
Z6   = '0' * 6

GNSR = re.compile('getNumSamples=([0-9]*) pre=([0-9]*) post=([0-9]*) elapsed=([0-9]*)')

GNS_TOTAL   = 0
GNS_PRE     = 1
GNS_POST    = 2
GNS_ELAPSED = 3
## end ACQ200 constants

class ACQ200:
    """
    Models an ACQ200 class intelligent digitizer
    """
    def set_dio32(self, value = IN32):
        return self.uut.acq2sh("set.dio32 " + value)

    def set_dio32_bit(self, bit) :
        bits = Z32[:bit] + "1" + Z32[bit+1:]
        self.set_dio32(bits)
        return bits

    def get_dio32(self):
        return self.uut.acq2sh("get.dio32")

    def set_dio6(self, value = IN6):
        return self.uut.acqcmd("setDIO " + value)

    def set_dio6_bit(self, bit, value = 0) :
        self.uut.acq2sh("set.dtacq dio_bit %d %s" % (bit, value))

    def get_dio6(self):
        return self.uut.acqcmd("getDIO")

    def set_route(self, dx, route = "in fpga"):
        return self.uut.acq2sh("set.route "+dx+" "+route)

    def clear_routes(self):
        for dx in ['d0', 'd1', 'd2', 'd3', 'd4', 'd5' ] :
            self.uut.acq2sh("set.route " + dx + " in fpga")

    def get_state(self):
        return self.uut.acqcmd("getState")

    def get_numSamples(self):
        reply = self.uut.acqcmd("getNumSamples")
        amatch = GNSR.match(reply)
        return amatch.groups()

    def set_arm(self):
        return self.uut.acqcmd("setArm")

    def set_abort(self):
        return self.uut.acqcmd("setAbort")

    def get_host(self):
        return self.uut.host

    def setChannelCount(self, nchan):
        self.uut.acqcmd("setChannelMask " + '1' * nchan)

    def setPrePostMode(self, pre=100000, post=100000, trig_src='DI3', trig_edge='rising'):
        self.uut.acq2sh("set.pre_post_mode %d %d %s %s" % (pre, post, trig_src, trig_edge,))

    def softTrigger(self):
        return self.uut.acq2sh("set.dtacq dio_bit 3 P")

    def waitState(self, state):
        return self.uut.waitState(state)

    def __init__(self, uut):
        self.uut = uut

class ACQ(MDSplus.Device):
    """
    Abstract class to subclass the 2G d-tacq acqxxx device types.  Contains
    members and methods that all of the 2G acqxxx  devices share:

    members:
      parts - the shared parts.  This should have the channels and the actions appended to it
      actions - the actions.  This gets appended after the channels

    methods:
      debugging() - is debugging enabled.  Controlled by environment variable DEBUG_DEVICES

    """

    acq_parts=[
        {'path': ':ACTIONSERVER',                       'type': 'TEXT',    'options':('no_write_shot','write_once')},
        {'path': ':ACTIONSERVER:INIT',                  'type': 'ACTION',  'options':('no_write_shot','write_once'), 'valueExpr':'Action(node.DISPATCH,node.TASK)'},
        {'path': ':ACTIONSERVER:INIT:DISPATCH',         'type': 'DISPATCH','options':('no_write_shot','write_once'), 'valueExpr':'Dispatch(head.actionserver,"INIT",31)'},
        {'path': ':ACTIONSERVER:INIT:TASK',             'type': 'TASK',    'options':('no_write_shot','write_once'), 'valueExpr':'Method(None,"init",head)'},
        {'path': ':ACTIONSERVER:ARM',                   'type': 'ACTION',  'options':('no_write_shot','write_once','disabled'), 'valueExpr':'Action(node.DISPATCH,node.TASK)'},
        {'path': ':ACTIONSERVER:ARM:DISPATCH',          'type': 'DISPATCH','options':('no_write_shot','write_once'), 'valueExpr':'Dispatch(head.actionserver,"INIT",51)'},
        {'path': ':ACTIONSERVER:ARM:TASK',              'type': 'TASK',    'options':('no_write_shot','write_once'), 'valueExpr':'Method(None,"arm",head)'},
        {'path': ':ACTIONSERVER:SOFT_TRIGGER',          'type': 'ACTION',  'options':('no_write_shot','write_once','disabled'), 'valueExpr':'Action(node.DISPATCH,node.TASK)'},
        {'path': ':ACTIONSERVER:SOFT_TRIGGER:DISPATCH', 'type': 'DISPATCH','options':('no_write_shot','write_once'), 'valueExpr':'Dispatch(head.actionserver,"PULSE",1)'},
        {'path': ':ACTIONSERVER:SOFT_TRIGGER:TASK',     'type': 'TASK',    'options':('no_write_shot','write_once'), 'valueExpr':'Method(None,"softTrigger",head)'},
        {'path': ':ACTIONSERVER:STORE',                 'type': 'ACTION',  'options':('no_write_shot','write_once'), 'valueExpr':'Action(node.DISPATCH,node.TASK)'},
        {'path': ':ACTIONSERVER:STORE:DISPATCH',        'type': 'DISPATCH','options':('no_write_shot','write_once'), 'valueExpr':'Dispatch(head.actionserver,"DEINIT",1)'},
        {'path': ':ACTIONSERVER:STORE:TASK',            'type': 'TASK',    'options':('no_write_shot','write_once'), 'valueExpr':'Method(None,"store",head)'},
        {'path': ':ACTIONSERVER:DISARM',                'type': 'TASK',    'options':('write_once',),                'valueExpr':'Method(None,"disarm",head)'},
        {'path': ':ACTIONSERVER:REBOOT',                'type': 'TASK',    'options':('write_once',),                'valueExpr':'Method(None,"reboot",head)'},

        {'path':':MASTER',            'type':'text',    'options':('no_write_shot',),  'valueExpr':'head'},
        {'path':':HOST',              'type':'text',    'options':('no_write_shot',),  'value':'192.168.0.254'},
        {'path':':COMMENT',           'type':'text'},
        {'path':'.STATUS',            'type':'structure'},
        {'path':'.STATUS:REPLIES',    'type':'any',     'options':('write_once','no_write_model',)},
        {'path':'.STATUS:COMMANDS',   'type':'text',    'options':('no_write_shot',),  'value':MDSplus.makeArray(['cat /proc/cmdline', 'get.d-tacq.release'])},

        {'path':':CLOCK',             'type':'numeric', 'options':('no_write_shot',),  'value':1000000},
        {'path':':CLOCK:SOURCE',      'type':'text',    'options':('no_write_shot',),  'value':'internal'}, # old: 'head.int_clock'
        {'path':':CLOCK:SOURCE:FIN',  'type':'numeric', 'options':('no_write_shot',),  'value':0},

        {'path':':TRIGGER',           'type':'numeric', 'options':('no_write_shot',)},
        {'path':':TRIGGER:SOURCE',    'type':'text',    'options':('no_write_shot',),  'value':'external'},
        {'path':':TRIGGER:EDGE',      'type':'text',    'options':('no_write_shot',),  'value':'rising'},
        {'path':':TRIGGER:POST',      'type':'numeric', 'options':('no_write_shot',),  'value':128},
        {'path':':TRIGGER:PRE',       'type':'numeric', 'options':('no_write_shot',),  'value':0},
        {'path':':TRIGGER:MODE',      'type':'text',    'options':('no_write_shot',),  'value':'TRANSIENT'}, # 'help':'TRANSIENT, RGM'
        ]

    debug=None
    data_socket = -1

    wires = ['fpga','mezz','rio','pxi','lemo','none','fpga pxi',' ']
    max_tries = 120

    def debugging(self):
        import os
        if self.debug == None:
            self.debug=os.getenv("DEBUG_DEVICES")
        return(self.debug)

    def getInteger(self, node, cls):
        try:
            ans = int(node.record)
        except Exception as e:
            print(("ACQ error reading %s erro is\n%s" %(node, e,)))
            raise cls()
        return ans

    def getPreTrig(self) :
        parts = self.settings['getNumSamples'].split('=')
        pre_trig = int(parts[2].split(' ')[0])
        return pre_trig

    def getPostTrig(self) :
        parts = self.settings['getNumSamples'].split('=')
        post_trig = int(parts[3].split(' ')[0])
        return post_trig

    def getBoardIp(self):
        from MDSplus.mdsExceptions import DevNO_NAME_SPECIFIED
        try:
            boardip=str(self.host.record)
        except Exception as e:
            raise DevNO_NAME_SPECIFIED(str(e))
        if len(boardip) == 0 :
            raise DevNO_NAME_SPECIFIED()
        return boardip

    def dataSocketDone(self):
        self.data_socket.send("done\n");
        self.data_socket.shutdown(socket.SHUT_RDWR)
        self.data_socket.close()
        self.data_socket=-1

    def connectAndFlushData(self):
        import select
        import time
        if self.data_socket == -1 :
            self.data_socket = socket.socket()
            self.data_socket.connect((self.getBoardIp(), 54547))
        rr, rw, ie = select.select([self.data_socket], [], [], 0)
        if len(rr) > 0 :
            if self.debugging():
                print("flushing old data from socket")
            self.data_socket.recv(99999, socket.MSG_DONTWAIT)
#            self.data_socket.close()
#            self.data_socket = -1
            time.sleep(.05)
            self.connectAndFlushData()

    def readRawData(self, chan, pre, start, end, inc, retrying) :
        from MDSplus.mdsExceptions import DevERROR_READING_CHANNEL
        if self.debugging():
            print(("starting readRawData(chan=%d, pre=%d. start=%d, end=%d, inc=%d)" %(chan,pre, start, end, inc,)))
        try:
            self.connectAndFlushData()
            self.data_socket.settimeout(10.)
#            self.data_socket.send("/dev/acq200/data/%02d %d\n" % (chan,end,))
            self.data_socket.send("/dev/acq200/data/%02d\n" % (chan,))
            f=self.data_socket.makefile("r",32768)
            bytes_to_read = 2*(end+pre+1)
            buf = f.read(bytes_to_read)
            binValues = array.array('h')
            binValues.fromstring(buf)
            ans = numpy.ndarray(buffer=binValues,
                                dtype=numpy.int16,
                                offset=(pre+start)*2,
                                strides=(inc*2),
                                shape=((end-start+1)/inc))

        except socket.timeout as e:
            if not retrying :
                print("Timeout - closing socket and retrying")
                self.data_socket.shutdown(socket.SHUT_RDWR)
                self.data_socket.close()
                self.data_socket=-1
                return self.readRawData(chan, pre, start, end, inc, True)
            else:
                 raise
        except Exception as e:
            print(("ACQ error reading channel %d\n, %s" % (chan, e,)))
            raise DevERROR_READING_CHANNEL(str(e))
        if self.debugging():
            print(("Read Raw data pre=%d start=%d end = %d inc=%d returning len = %d" % (pre, start, end, inc, len(ans),)))
        return ans

    def loadSettings(self):
        from MDSplus.mdsExceptions import DevCANNOT_LOAD_SETTINGS
        tries = 0
        self.settings = None
        last_error = None
        while self.settings == None and tries < 10 :
            try:
                tries = tries + 1
                self.settings = self.readSettings()
#                complete = 1
            except Exception as e:
                last_error=e
                if self.debugging():
                    print(("Error loading settings%s" % str(e)))
        if self.settings == None :
            print(("after %d tries could not load settings" % (tries,)))
            raise DevCANNOT_LOAD_SETTINGS(str(last_error))

    def checkTreeAndShot(self, arg1='checks', arg2='checks'):
        from MDSplus.mdsExceptions import DevWRONG_TREE
        from MDSplus.mdsExceptions import DevWRONG_SHOT
        from MDSplus.mdsExceptions import DevWRONG_PATH

        if arg1 == "checks" or arg2 == "checks":
            path = self.local_path
            tree = self.local_tree
            shot = self.tree.shot
            if self.debugging() :
                print("json is loaded")
            if tree != self.settings['tree'] :
                print(("ACQ Device open tree is %s board armed with tree %s" % (tree, self.settings["tree"],)))
                raise DevWRONG_TREE()
            if path != self.settings['path'] :
                print(("ACQ device tree path %s, board armed with path %s" % (path, self.settings["path"],)))
                raise DevWRONG_PATH()
            if shot != int(self.settings['shot']) :
                print(("ACQ open shot is %d, board armed with shot %d" % (shot, int(self.settings["shot"]),)))
                raise DevWRONG_SHOT()

    def storeStatusCommands(self):
        status = []
        cmds = self.status_commands.record
        for cmd in cmds:
            cmd = cmd.strip()
            if self.debugging():
                print(("about to append answer for /%s/\n   which is /%s/" % (cmd,str(self.settings[cmd],))))
            status.append(self.settings[cmd])
            if self.debugging():
                print(("%s returned %s\n" % (cmd, self.settings[cmd],)))
        if self.debugging():
            print("about to write board_status signal")
        self.status_replies.record = status #MDSplus.Signal(cmds, None, status)

    def checkTrigger(self, arg1, arg2):
        from time import sleep
        from MDSplus.mdsExceptions import DevNOT_TRIGGERED
        state = self.getBoardState()
        if state == "ACQ32:0 ST_STOP" or (state == "ACQ32:4 ST_POSTPROCESS" and (arg1 == "auto" or arg2 == "auto")):
            return
        if arg1 != "auto" and arg2 != "auto" :
            tries = 0
            while state == "ACQ32:4 ST_POSTPROCESS" and tries < 120:
                tries +=1
                sleep(1)
                state=self.getBoardState()
            if state != "ACQ32:0 ST_STOP" :
                raise DevNOT_TRIGGERED()

    def triggered(self):
        import time
        complete = 0
        tries = 0
        while not complete and tries < 120 :
            state = self.getBoardState()
            if self.debugging():
                print(("get state returned %s" % (state,)))
            if state == "ACQ32:4 ST_POSTPROCESS" :
                tries +=1
                time.sleep(1)
            else:
                complete=1
        state = self.getBoardState()
        if self.debugging():
            print(("get state after loop returned %s" % (state,)))
        if state != "ACQ32:0 ST_STOP" :
            print(("ACQ196 device not triggered /%s/"% (self.getBoardState(),)))
            return 0
        return 1

    def getBoardState(self):
        from MDSplus.mdsExceptions import DevCANNOT_GET_BOARD_STATE
        boardip = self.getBoardIp()
        last_error = None
        for t in range(10):
            try:
                UUT = ACQ200(DT100(boardip))
            except Exception as e:
                print(("could not connect to the board %s"% (boardip,)))
                last_error=e
            try:
                if not UUT == None:
                    a = UUT.uut.acqcmd('getState')
                    return "ACQ32:%s"%a
            except Exception as e:
                print(("could not send getState to the board try %d"%t))
                last_error = e
        if not last_error == None:
            raise DevCANNOT_GET_BOARD_STATE(str(last_error))
        else:
            return 'unknown'

#    def getBoardState(self):
#        """Get the current state"""
#        import socket,time
#       for tries in range(5):
#            s=socket.socket()
#           s.settimeout(5.)
#            state="Unknown"
#            try:
#                s.connect((self.getBoardIp(),54545))
#                state=s.recv(100)[0:-1]
#               if self.debugging():
#                   print "getBoardState  returning /%s/\n" % (state,)
#                s.close()
#                return state
#            except socket.error, e:
#               print "Error getting board state - offline: %s" % (str(e),)
#               state = "off-line"
#                s.close()
#               return state
#            except Exception,e:
#                print "Error getting board state: %s" % (str(e),)
#               state = "off-line"
#                s.close()
#            time.sleep(3)
#
#
# Let this function raise an error that will be
# Thrown all the way out of the device method
#
    def getMyIp(self):
        import socket
        from MDSplus.mdsExceptions import DevOFFLINE
        try:
            s=socket.socket()
            s.connect((self.getBoardIp(),54545))
            hostip = s.getsockname()[0]
            state=s.recv(100)[0:-1]
            if self.debugging():
                print(("getMyIp  read /%s/\n" % (state,)))
            s.close()
        except Exception as e:
            raise DevOFFLINE(str(e))
        return hostip

    def getMaster(self):
        """
        Grabs status of device in relationship to other boards in the CPCI carrier

        1. If MASTER node is empty, then the device is alone int he carrier,
           and no external clock/trigger pass-through is required.
        2. If MASTER node points to self, then the device is master to another
           device, and must pass on the external clock/trigger.
        3. If MASTER node points to another device, then the device is slave
           to that device.
        """
        try:
            Mdev = self.master.record
        except:
            Mdev = None
        if not Mdev:
            master    = True
            clock_out = False
            if self.debugging():
                print("Board is alone in carrier")
        elif Mdev == self.head:
            master    = True
            clock_out = True
            if self.debugging():
                print("Board is master to another slave device")
        else:
            master    = False
            clock_out = False
            if self.debugging():
                print("Board is slave to %s"%Mdev)
        return master,clock_out

    def addGenericJSON(self, fd):
        if self.debugging():
            print("starting addGenericJson")
        fd.write(r"""
begin_json() {   echo "{"; }
end_json() {   echo "\"done\" : \"done\"  }"; }
add_term() {   echo " \"$1\" : \"$2\", "; }
add_acqcmd() { add_term "$1" "`acqcmd $1`"; }
add_cmd() { add_term "$1" "`$1`"; }
settingsf=/tmp/settings.json
begin_json > $settingsf
add_term tree $tree >> $settingsf
add_term shot $shot >> $settingsf
add_term path $path >> $settingsf
""")
        cmds = self.status_commands.record
        for cmd in cmds:
            cmd = cmd.strip()
            if self.debugging():
                print(("adding cmd '%s' >> $settingsf/ to the file."%(cmd,)))
            fd.write("add_cmd '%s' >> $settingsf\n"%(cmd,))
        fd.write(r"""
cat - > /etc/postshot.d/postshot.sh <<EOF
begin_json() {   echo "{"; }
end_json() {   echo "\"done\" : \"done\"  }"; }
add_term() {   echo " \"\$1\" : \"\$2\", "; }
add_acqcmd() { add_term "\$1" "\`acqcmd \$1\`"; }
add_cmd() { add_term "\$1" "\`\$1\`"; }
settingsf=/tmp/settings.json
add_acqcmd getNumSamples >> $settingsf
add_acqcmd getChannelMask >> $settingsf
add_acqcmd getInternalClock >> $settingsf
add_cmd date >> $settingsf
add_cmd hostname >> $settingsf
add_cmd 'sysmon -T 0' >> $settingsf
add_cmd 'sysmon -T 1' >> $settingsf
add_cmd get.channelMask >> $settingsf
add_cmd get.channel_mask >> $settingsf
add_cmd get.d-tacq.release >> $settingsf
add_cmd get.event0 >> $settingsf
add_cmd get.event1 >> $settingsf
add_cmd get.extClk  >> $settingsf
add_cmd get.ext_clk >> $settingsf
add_cmd get.int_clk_src >> $settingsf
add_cmd get.modelspec >> $settingsf
add_cmd get.numChannels >> $settingsf
add_cmd get.pulse_number >> $settingsf
add_cmd get.trig >> $settingsf
add_cmd get.ob_clock >> $settingsf
""")

    def finishJSON(self, fd, auto_store):
        if self.debugging():
            print("starting finishJSON")
        fd.write("end_json >> $settingsf\n")

        if auto_store != None :
            if self.debugging():
                fd.write("mdsValue 'setenv(\"\"DEBUG_DEVICES=yes\"\")'\n")
            fd.write("mdsConnect %s\n" %self.getMyIp())
            fd.write("mdsOpen %s %d\n" %(self.local_tree, self.tree.shot,))
            fd.write("mdsValue 'tcl(\"\"do /meth %s autostore\"\", _out),_out'\n" %( self.local_path, ))
            if self.debugging():
                fd.write("mdsValue 'write(*,_out)'\n")
            fd.write("mdsClose\n")
            fd.write("mdsDisconnect\n")

        fd.write("EOF\n")
        fd.write("chmod a+x /etc/postshot.d/postshot.sh\n")
        fd.flush()
        fd.seek(0,0)
        self.auto_store = auto_store

    def bufferChannel(self,chanNode,chan,chanMask,preTrig,postTrig):
        """
        First part of the legacy storeChannel method
        Only reads channel data into memory
        """
        if (chan<4) or (chanNode.on and chanMask[chan:chan+1] == '1') :  # TODO: only always include 0,1,2,3 if RGM
            try:
                start = max(int(self.__getattr__('channels_input_%2.2d_startidx'%(chan+1,))),-preTrig)
            except:
                start = -preTrig
            try:
                end = min(int(self.__getattr__('channels_input_%2.2d_endidx'%(chan+1,))),postTrig-1)
            except:
                end = postTrig-1
            try:
                inc = max(int(self.__getattr__('channels_input_%2.2d_inc'%(chan+1,))),1)
            except:
                inc = 1
            if self.debugging():
                print(("about to readRawData(chan=%d, preTrig=%d, start=%d, end=%d, inc=%d)" % (chan+1, preTrig, start, end, inc)))
            buf = self.readRawData(chan+1, preTrig, start, end, inc, False)
            if self.debugging():
                print(("readRawData returned %s\nChannel %s is buffered" % (type(buf),chan+1,)))
            return buf

    def storeBuffer(self,chanNode,chan,chanMask,buf,dims_slice=None):
        """
        Works in conjunction to the bufferChannel method
        It is the remainder of the legacy storeChannel method
        Stores channels as segmented data
        """
        if chanNode.on and chanMask[chan:chan+1] == '1' :
            if self.debugging():
                print(("Storing channel %d as segmented data" % (chan+1,)))

            chunksize = 100000
            node = self.__getattr__('channels_input_%2.2d'%(chan+1,))

            for dim,slc,t0,dt in dims_slice:
                val = buf[slc]
                dlen = val.shape[0]
                node.setSegmentScale(MDSplus.ADD(node.VMIN,MDSplus.MULTIPLY(MDSplus.SUBTRACT(node.VMAX,node.VMIN),MDSplus.DIVIDE(MDSplus.ADD(MDSplus.dVALUE(),32768.),65535.))))
                for seg,i0 in enumerate(range(0,dlen,chunksize)):
                    i1 = min(i0+chunksize,dlen)-1
                    dim[0][0],dim[0][1]=i0,i1
                    d0=MDSplus.Int64(t0+i0*dt)
                    d1=MDSplus.Int64(t0+i1*dt)
                    node.makeSegment(d0,d1,dim,MDSplus.Int16Array(val[i0:i1+1]))

            chanNode.write_once = True
            if self.debugging():
                print('Data successfully stored to node\n')

    def startInitializationFile(self,fd):
        if self.debugging():
            print("starting initialization")
        host = self.getMyIp()
        fd.write("acqcmd setAbort\n")
        fd.write("host=%s\n"%(host,))
        fd.write("tree=%s\n"%(self.local_tree,))
        fd.write("shot=%s\n"%(self.tree.shot,))
        fd.write("path='%s'\n"%(self.local_path,))

    def setClockRouting(self,fd,clk_src,master,clock_out):
        """
        Route the six internal DIO lines (d0-5). Supports master/slave setup
        internally within the carrier.

        Clock routing:
            - If board is master, it first step is to route the external clock
            to the PXI backplane via DO2. Second step is to route the external
            clock to the FPGA directly via D0 (in typical fashion).
            - If board is slave, simply route the clock from PXI backplane to
            the FPGA via D0.
        """
        try:
            if clk_src == 'external':
                if clock_out:
                    fd.write("acqcmd setExternalClock DI0 DO2\n")
                    fd.write("set.route d2 in fpga out pxi\n")
                    fd.write("acqcmd - setDIO --1-----\n")
                    if self.debugging():
                        print("External clock output on line: D2")
                fd.write("set.route d0 in lemo out fpga pxi\n")
                if self.debugging():
                    print("External clock in - line: D0 | in: lemo | out: fpga pxi")
            elif clk_src == 'internal':
                if not master:
                    fd.write("set.route d0 in pxi out fpga\n")
                    if self.debugging():
                        print("Using derived backplane clock - line: D2 | in: pxi | out: fpga")
                else: # device is master
                    if self.debugging():
                        print("No routing necessary for internal clock. If errors, reboot device.")
        except Exception as e:
            raise MDSplus.DevBAD_CLOCK_SRC(str(e))

    def setTrigRouting(self,fd,trig_src,master,clock_drm=None):
        """
        Route the six internal DIO lines (d0-5). Supports master/slave setup
        internally within the carrier.

        Trigger routing:
            - If board is master, route external trigger to PXI backplane via D3.
            - If board is slave, route external trigger from PXI backplane via D3.
            - If clock_drm is enabled, set trigger gate src to D3
        """
        try:
            if trig_src == 'external':
                fd.write("set.route d3 in lemo out fpga pxi\n")
                if self.debugging():
                    print("External trigger - line: DI3 | wire: lemo | bus: fpga pxi")
                    print("set.route d3 in lemo out fpga pxi")
            elif trig_src == 'internal':
                if not master:
                    fd.write("set.route d3 in pxi out fpga\n")
                    if clock_drm:
                        fd.write("set.gate_src DI3 high\n")
                    if self.debugging():
                        print("Using trigger over pxi - line: DI3 | wire: pxi | bus: fpga")
                else: # device is master
                    if clock_drm:
                        fd.write("set.route d3 in pxi out fpga\n")
                        fd.write("set.gate_src DI3 high\n")
                    if self.debugging():
                        print("If errors, reboot device to use internal trigger")
        except Exception as e:
            raise MDSplus.DevBAD_TRIG_SRC(str(e))

    def readSettings(self):
        settingsfd = tempfile.TemporaryFile()
        ftp = ftplib.FTP(self.getBoardIp())
        ftp.login('dt100', 'dt100')
        ftp.retrlines("RETR /tmp/settings.json", lambda s, w=settingsfd.write: w(s+"\n"))
        settingsfd.seek(0,0)
        try :
            if self.debugging():
                print("got the settings")
            settings = json.load(settingsfd)
        finally:
            settingsfd.close()
        settingsfd.close()
        if self.debugging():
            print("The settings are loaded")
        return settings

#
# Do not return status let caller catch (or not) exceptions
#
    def doInit(self,fd):
        """Tell the board to arm"""
        import socket
        from MDSplus.mdsExceptions import DevERROR_DOING_INIT

        if self.debugging():
            print("starting doInit")
        status=1
        try:
            ftp = ftplib.FTP(self.getBoardIp())
            ftp.login('dt100','dt100')
            ftp.storlines("STOR /tmp/initialize",fd)
        except Exception as e:
            print(("Error sending arm commands via ftp to %s\n%s" % (self.getBoardIp(), e,)))
            raise DevERROR_DOING_INIT(str(e))
        s=socket.socket()
        try:
            s.settimeout(10.)
            s.connect((self.getBoardIp(),54546))
            s.send("initialize")
        except Exception as e:
            status=0
            s.close()
            print(("Error sending doInit: %s" % (str(e),)))
            raise DevERROR_DOING_INIT(str(e))
        finally:
            s.close()
        if self.debugging():
            print("finishing doInit")
        return status

    def storeClock(self):
        clock_src=self.clock_src.record.getOriginalPartName().getString()[1:]
        if self.debugging():
            print(("clock_src = %s" % (clock_src,)))
        try:
            clock_div = int(self.clock_div)
        except:
            clock_div = 1
        if self.debugging():
           print(("clock div is %d" % (clock_div,)))

        if clock_src == 'INT_CLOCK' :
            intClock = float(self.settings['getInternalClock'].split()[1])
            delta=1.0/float(intClock)
            self.clock.record = MDSplus.Range(None, None, delta)
        else:
            if self.debugging():
                print("it is external clock")
            if clock_div == 1 :
                self.clock.record = self.clock_src
            else:
                if self.debugging():
                    print(("external clock with divider %d  clock source is %s" % ( clock_div, clock_src,)))
                clk = self.clock_src
                try :
                    while type(clk) != MDSplus.compound.Range :
                        clk = clk.record
                    if self.debugging():
                        print("I found the Range record - now writing the clock with the divide")
                    self.clock.record = MDSplus.Range(clk.getBegin(), clk.getEnding(), clk.getDelta()*clock_div)
                except:
                    print("could not find Range record for clock to construct divided clock storing it as undivided")
                    self.clock.record  = clock_src
                if self.debugging():
                    print("divided clock stored")

    def waitftp(self) :
        import time
        from MDSplus.mdsExceptions import DevOFFLINE
        from MDSplus.mdsExceptions import DevNOT_TRIGGERED
        from MDSplus.mdsExceptions import DevIO_STUCK
        from MDSplus.mdsExceptions import DevTRIGGERED_NOT_STORED
        from MDSplus.mdsExceptions import DevUNKOWN_STATE

        """Wait for board to finish digitizing and storing the data"""
        state = self.getBoardState()
        tries = 0
        while (state == "ACQ32:4 ST_POSTPROCESS") and tries < self.max_tries :
            tries = tries + 1
            state = self.getBoardState()
            time.sleep(2)

        if state == 'off-line' :
            raise DevOFFLINE()
        if state == "ACQ32:1 ST_ARM" or state == "ACQ32:2 ST_RUN" :
            raise DevNOT_TRIGGERED()
        if state == "ACQ32:4 ST_POSTPROCESS" :
            raise DevIO_STUCK()
        if state == "ACQ32:0 ST_STOP" or state == "Ready":
            for chan in range(int(self.active_chan.record), 0, -1):
                chanNode = self.__getattr__('input_%2.2d' % (chan,))
                if chanNode.on :
                    max_chan = chanNode
                    break

            if max_chan.rlength > 0:
                return 1
            else:
                print('max_chan = %s'%max_chan) # temporary
                print('max_chan.rlength = %s'%max_chan.rlength) # temporary
                print("Triggered, but data not stored !")
                raise DevTRIGGERED_NOT_STORED()
        else:
            print(("ACQxxx UNKNOWN BOARD state /%s/" % (state,)))
            raise DevUNKOWN_STATE()

    def waitAcq(self) :
        from time import sleep
        from MDSplus.mdsExceptions import DevNOT_TRIGGERED,DevBAD_POST_TRIG,DevIO_STUCK,DevUNKOWN_STATE

        """Wait for board to finish digitizing the data"""
        state = self.getBoardState()
        tries = 0
        timeout = 60
        while ((state == "ACQ32:2 ST_RUN") or (state == "ACQ32:4 ST_POSTPROCESS")) and tries < timeout :
            state = self.getBoardState()
            tries = tries + 1
            sleep(1)

        if state == "unknown" :
            raise DevUNKOWN_STATE()
        if state == "ACQ32:1 ST_ARM" :
            raise DevNOT_TRIGGERED()
        if state == "ACQ32:2 ST_RUN" :
            raise DevBAD_POST_TRIG()
        if state == "ACQ32:4 ST_POSTPROCESS" :
            raise DevIO_STUCK()
        if state == "ACQ32:0 ST_STOP" or state == "Ready":
            return 1
        else:
            print(("ACQxxx UNKNOWN BOARD state /%s/" % (state,)))
            raise DevUNKOWN_STATE()

    def softTrigger(self):
        from MDSplus.mdsExceptions import DevTRIGGER_FAILED

        if self.debugging():
            print("starting trigger")
        try:
            boardip  = self.getBoardIp()
            trig_src = 3
            if self.debugging() :
                print("executing soft trigger on board %s, trig_src is D%s."% (boardip, trig_src,))

            UUT = ACQ200(DT100(boardip))
            route = UUT.uut.acq2sh('get.route D%s'%(trig_src,))

            d1 = UUT.uut.acq2sh('set.route d%s in fpga out'%(trig_src,))
            d2 = UUT.uut.acq2sh('set.dtacq dio_bit %s P'%(trig_src,))
            d3 = UUT.uut.acq2sh('set.route %s' %(route,))
            d4 = UUT.uut.acq2sh('set.dtacq dio_bit %s -'%(trig_src,))

            if self.debugging():
                print(("got back: %s" % (route,)))
                print(("     and: %s" % (d1,)))
                print(("     and: %s" % (d2,)))
                print(("     and: %s" % (d3,)))
                print(("     and: %s" % (d4,)))
        except Exception as e:
            print("Error doing Trigger method")
            raise DevTRIGGER_FAILED(str(e))

    def acqcmd(self, arg):
        from MDSplus.mdsExceptions import DevACQCMD_FAILED

        boardip = self.getBoardIp()

        try:
            UUT = ACQ200(DT100(boardip))
            a = UUT.uut.acqcmd(str(arg))
        except Exception as e:
            print(("could not send %s to the board" %(str(arg),)))
            raise DevACQCMD_FAILED(str(e))
        print(("%s  %s -> %s"%(boardip, arg, a,)))
        return 1

    def acq2sh(self, arg):
        from MDSplus.mdsExceptions import DevACQ2SH_FAILED
        boardip = self.getBoardIp()
        try:
            UUT = ACQ200(DT100(boardip))
            a = UUT.uut.acq2sh(str(arg))
        except Exception as e:
            print(("could not connect to the board %s"% (boardip,)))
            raise DevACQ2SH_FAILED(str(e))
        if self.debugging():
            print(("%s  %s -> %s"%(boardip, arg, a,)))
        return a

    def getnumsamples(self):
        self.acqcmd('getNumSamples')
        return 1

    def getstate(self):
        self.acqcmd('getState')
        return 1

    def autostore(self):
        self.store("auto")
        return 1

    def arm(self):
        """
        Arms the device with current settings
        """
        boardip = self.getBoardIp()
        UUT = ACQ200(DT100(boardip))
        UUT.uut.acqcmd('setArm')

    def disarm(self):
        """
        Disarms the device
        """
        boardip = self.getBoardIp()
        UUT = ACQ200(DT100(boardip))
        UUT.uut.acqcmd('setAbort')

    def reboot(self):
        """
        Reboots the device
        """
        try:    self.acq2sh('sync;sync;reboot')
        except: pass

    def _get_decim(self,clk,fin):
        """
        Calculates accumulation decimation and bit-shift factors based off
        desired clock frequecy and external clock.
        """
        if self.debugging():
            print('Getting clk decimation and bit shift values')
        minClk  = 4e6; extClk = fin; df = 1e3
        mClk    = numpy.arange(minClk,extClk+df,df)
        dec     = 2**numpy.log2(mClk/clk)
        decVals = []
        for i in range(len(dec)):
            if numpy.log2(dec[i])%1 == 0: decVals.append(int(dec[i]))
        decim = max(decVals)
        if decim == 32: decim = decVals[-2]
        shift = int(numpy.log2(decim))-2 # to adjust for 14 bit in a 16 bit register
        return decim,shift

    def _get_dim_slice(self,i0,mClk,dt,trigNode,start,end,pre):
        """
        Calculates the time-vector based on clk-tick t0, dt [ns], start and
        end. If dt results in an integer value in nanosecond, store as int64,
        else store as float. This only affects the dimension slice expression.
        """
        dt_mClk = int(1e9/mClk) # [ns]
        toff= i0*dt_mClk
        if dt % 1 == 0:
            dim = MDSplus.Dimension(MDSplus.Window(-pre,end-start-1-pre,MDSplus.ADD(trigNode,MDSplus.Int64(toff))),MDSplus.Range(None,None,MDSplus.Int64(dt)))
        else:
            dim = MDSplus.Dimension(MDSplus.Window(-pre,end-start-1-pre,MDSplus.ADD(trigNode,MDSplus.Float64(toff))),MDSplus.Range(None,None,MDSplus.Float64(dt)))
        t0  = trigNode + toff
        return dim,slice(start,end),t0,dt

    def _event_analysis(self,raw,mClk,clock_dt,trigNode,pre):
        """
        Calculates the time stamps for each RGM window
        """
        if self.debugging():
            print('Analyzing the RGM windows using channels 1-4')
        _int16_marker = -21931

        m1a = raw[2]
        m2a = raw[3]
        hia = raw[0]
        loa = raw[1]
        mask  = (m1a==_int16_marker)
        mask2 = (m2a==_int16_marker)

        if not (mask == mask2).all():
            print('##### Gate masks do not match #####')
            if self.debugging:
                print(m1a[mask2], m2a[mask])

        if not mask.any():
            print('##### NO GATE MARKERS FOUND #####')

        hi = hia[mask].astype('uint16')
        lo = loa[mask].astype('uint16')

        idx = numpy.concatenate((numpy.array(xrange(1,loa.shape[0]+1))[mask],numpy.array(loa.shape)),0)
        tt0 = numpy.array(lo,'uint32') + (numpy.array(hi,'uint32')<<16) # or hi*65536 -> a 16-bit shift
        tt0 = tt0-tt0[0]
        if self.debugging():
            print('Acquisition window idices (tt0) = %s'%tt0)

        dims_slice = [self._get_dim_slice(t0,mClk,clock_dt,trigNode,idx[i],idx[i+1]-1,pre) for i,t0 in enumerate(tt0)]

        return dims_slice

class ACQ132(ACQ):
    """
    D-Tacq ACQ132 - 32 channel transient recorder - 14-bit - up to 8MSPS

    Device support for d-tacq acq132 @ http://www.d-tacq.com/acq132cpci.shtml
    """
    max_chan   = 32
    chanBlocks = max_chan/16
    daq_mem    = 512
    parts      = list(ACQ.acq_parts)

    acq132_parts=[
        {'path':':CHANNELS',                      'type':'numeric', 'options':('no_write_shot',), 'value':32},
        {'path':':CLOCK.ACCUMULATION',            'type':'structure'},
        {'path':':CLOCK.ACCUMULATION:MCLK',       'type':'numeric', 'options':('write_once','no_write_model',)},
        {'path':':CLOCK.ACCUMULATION:DECIMATION', 'type':'numeric', 'options':('write_once','no_write_model',)},
        {'path':':CLOCK.ACCUMULATION:SHIFT',      'type':'numeric', 'options':('write_once','no_write_model',)},
        {'path':':CLOCK:DRM',                     'type':'numeric', 'options':('no_write_shot',), 'value':0},
        {'path':':CLOCK.DRM:DECIMATION',          'type':'numeric', 'options':('write_once','no_write_model',)},
        {'path':':CLOCK.DRM:SHIFT',               'type':'numeric', 'options':('write_once','no_write_model',)},
        ]

    for i in range(32):
        acq132_parts.append({'path':':CHANNELS:INPUT_%2.2d'%(i+1,),         'type':'signal',  'options':('no_write_model','write_once',)})
        acq132_parts.append({'path':':CHANNELS:INPUT_%2.2d:VMIN'%(i+1,),    'type':'numeric', 'options':('no_write_model','write_once',)})
        acq132_parts.append({'path':':CHANNELS:INPUT_%2.2d:VMAX'%(i+1,),    'type':'numeric', 'options':('no_write_model','write_once',)})
        acq132_parts.append({'path':':CHANNELS:INPUT_%2.2d:STARTIDX'%(i+1,),'type':'NUMERIC', 'options':('no_write_shot',)})
        acq132_parts.append({'path':':CHANNELS:INPUT_%2.2d:ENDIDX'%(i+1,),  'type':'NUMERIC', 'options':('no_write_shot',)})
        acq132_parts.append({'path':':CHANNELS:INPUT_%2.2d:INC'%(i+1,),     'type':'NUMERIC', 'options':('no_write_shot',)})
    del i

    parts.extend(acq132_parts)

    def initftp(self, auto_store=None):
        """
        Set initialization parameters
        Send parameters to device
        Arm hardware
        """
        start=time.time()
        if self.debugging():
            print("starting init");
        path = self.local_path
        tree = self.local_tree
        shot = self.tree.shot
        if self.debugging():
            print(('ACQ132 initftp path = %s tree = %s shot = %d' % (path, tree, shot)))

        # Grab basic values from the tree
        master,clock_out = self.getMaster()

        active_chan = self.getInteger(self.channels,MDSplus.DevBAD_ACTIVE_CHAN)
        if active_chan not in (8,16,32) :
            raise MDSplus.DevBAD_ACTIVE_CHAN()
        if self.debugging():
            print("Number of active channels: %s"%active_chan)

        try:
            trig_src = self.trigger_source.record
        except Exception as e:
            raise MDSplus.DevBAD_TRIG_SRC(str(e))
        try:
            trig_edge = self.trigger_edge.record
        except Exception as e:
            raise MDSplus.DevBAD_PARAMETER(str(e))
        if self.debugging():
            print("Trigger source: %s %s"%(trig_src,trig_edge,))

        try:
            clock_src = self.clock_source.record
        except Exception as e:
            raise MDSplus.DevBAD_CLOCK_SRC(str(e))
        if self.debugging():
            print("Clock source: %s"%clock_src)
        try:
            clock_drm = self.clock_drm.record
            if not clock_drm == 0:
                if self.debugging(): print('Enabling DualRateMode')
        except Exception as e:
            raise MDSplus.DevBAD_PARAMETER(str(e))

        # Setting pre and post to a multiple of 1024 guarantees that you'll
        # get that exact number of samples, rather than the nearest acceptable
        # number that the devices chooses.
        pre_trig = int((self.getInteger(self.trigger_pre,MDSplus.DevBAD_PRE_TRIG)-1)/1024+1)*1024
        if self.debugging():
            print("Pre trigger samples: %s"%pre_trig)

        post_trig = int((self.getInteger(self.trigger_post,MDSplus.DevBAD_POST_TRIG)-1)/1024+1)*1024
        if self.debugging():
            print("Post trigger samples: %s"%post_trig)

        clock_freq = self.getInteger(self.clock,MDSplus.DevBAD_CLOCK_FREQ)
        if self.debugging():
            print("Clock frequency: %s"%clock_freq)

        if self.debugging():
            print("have the settings")

        # Now create the "initialize" ftp command file
        fd = tempfile.TemporaryFile()

        # Basic initial settings
        self.startInitializationFile(fd)

        # Route the internal DI lines
        self.setClockRouting(fd,clock_src,master,clock_out)
        self.setTrigRouting(fd,trig_src,master,clock_drm)

        # Set the number of active channels
        activeBlock = active_chan/self.chanBlocks
        chan_mask = ('1'*activeBlock + '0'*(16-activeBlock))*self.chanBlocks
        fd.write("acqcmd setChannelMask %s\n"% (chan_mask,))

        # Set the clock frequencies
        if (clock_src == 'external') or (clock_src == 'internal' and not master):
            # Get external clock frequency
            clock_fin = self.getInteger(self.clock_source_fin,MDSplus.DevBAD_CLOCK_FREQ)
            if self.debugging():
                print("External clock freq: %s"%clock_fin)
            # Calculate accumulation values to achieve desired clock frequency
            decim,shift = self._get_decim(clock_freq,clock_fin)
            mClkset = decim*int(clock_freq)
            # Check mClk setpoint error
            ob_clk  = self.acq2sh('ob_calc_527 %s /dev/dtacq/ob_clock --verbose 1'%(mClkset/1000,)).split(' ')
            mClk = int(ob_clk[1])*1000
            if self.debugging():
                print("mClk setpoint: %s | mClk actual: %s"%(mClkset,mClk,))
            self.clock_accumulation_mclk.record       = MDSplus.Int32(mClk)
            self.clock_accumulation_decimation.record = MDSplus.Int32(decim)
            self.clock_accumulation_shift.record      = MDSplus.Int32(shift)
            # Adjust recorded CLOCK if the value isn't possible
            if mClkset != mClk:
                clock_freq = mClk/decim
                self.clock.no_write_shot = False
                self.clock.record = clock_freq
                self.clock.no_write_shot = True
                if self.debugging():
                    print("Invalid mClk setpoint, altering CLOCK: %s"%clock_freq)
            if self.debugging():
                print(('Freq = '+str(int(clock_freq))+' | mClk = '+str(mClk)+' | dec = '+str(decim)+' | shift = '+str(shift)))
            # Send commands to set up device properly
            fd.write("acqcmd -- setExternalClock --fin %d --fout %d DI0\n" % (clock_fin/1000, mClk/1000,))
            fd.write("set.all.acq132.accumulate %d %d\n"%(decim, shift))

        else: # clock is internal - device is master
            if self.debugging():
                print("Internal clock")
            fd.write("acqcmd setInternalClock %d\n" % clock_freq)

        # Set the trigger mode - currently TRANSIENT and RGM are supported
        trig_mode = self.trigger_mode.record
        if self.debugging(): print('Trigger mode: %s'%trig_mode)
        if trig_mode == 'RGM':
            fd.write("set.pre_post_mode %d %d DI3 %s\n"%(pre_trig,post_trig,trig_edge,))
            fd.write("set.dtacq RepeatingGateMode 2\n")
            fd.write("set.dtacq DualRate 0\n")
            fd.write("set.gate_src DI3 high\n")
        else: # trig_mode == 'TRANSIENT':
            if clock_drm:
                drm_dec = int(mClk/(clock_freq/clock_drm))
                drm_shift = int(numpy.log2(drm_dec))-2 # to adjust for 14 bit in a 16 bit register
                self.clock_drm_decimation.record = MDSplus.Int32(drm_dec)
                self.clock_drm_shift.record = MDSplus.Int32(drm_shift)
                if self.debugging():
                    print("DRM decimation factor used = %i"%drm_dec)
                    print("DRM low clock = %i"%(int(mClk/drm_dec)))
                fd.write("set.pre_post_mode %d %d DI3 %s\n"%(pre_trig,post_trig,trig_edge,))
                fd.write("set.dtacq RepeatingGateMode 0\n")
                fd.write("set.dtacq DualRate 1 %s %s\n"%(drm_dec,drm_shift))
                fd.write("set.gate_src DI3 high\n")
                fd.write("set.event event1 DI3 rising\n")
                fd.write("set.sys /sys/module/acq132/parameters/rgm_with_es 1\n")
            else:
                fd.write("set.dtacq RepeatingGateMode 0\n")
                fd.write("set.dtacq DualRate 0\n")
                fd.write("set.event event1 none\n")
                fd.write("set.pre_post_mode %d %d DI3 %s\n"%(pre_trig,post_trig,trig_edge,))

        # Generic JSON adds general information to the [initialization] ftp file
        self.addGenericJSON(fd)

        # grab the AI calibrations
        fd.write("add_cmd 'get.vin 1:32'>> $settingsf\n")
        self.finishJSON(fd, auto_store)

        print(("Time to make init file = %g" % (time.time()-start)))
        start = time.time()

        # Send the file - begin INIT procedure
        self.doInit(fd)
        fd.close()

        print(("Time for board to init = %g" % (time.time()-start)))

    def init(self, auto_store=None):
        self.initftp(auto_store)

    def store(self, arg1='checks', arg2='noauto'):
        if self.debugging():
            print("Begining store")

        # Wait for ACQ to finish acquiring/postprocessing
        self.waitAcq()

        self.checkTrigger(arg1, arg2)
        self.loadSettings()
        self.checkTreeAndShot(arg1, arg2)
        self.storeStatusCommands()

        preTrig = self.getPreTrig()
        postTrig = self.getPostTrig()
        if self.debugging():
            print(("got preTrig %d and postTrig %d" % (preTrig, postTrig,)))

        vins   = self.settings['get.vin 1:32']
        vinArr = eval('MDSplus.makeArray([%s])' % (vins,))
        for i in range(32):
            self.__setattr__('channels_input_%2.2d_vmin'%(i+1,),MDSplus.Float32(vinArr[2*i]))
            self.__setattr__('channels_input_%2.2d_vmax'%(i+1,),MDSplus.Float32(vinArr[2*i+1]))
        if self.debugging():
            print("Got the calibration vins")#: %s"%(str(vins,)))

        chanMask = self.settings['getChannelMask'].split('=')[-1]
        if self.debugging():
            print(("Active channel mask: %s" % (chanMask,)))

        # Grab some settings from the tree
        clock_src  = self.clock_source.record
        trig_mode  = self.trigger_mode.record
        clock_freq = self.clock.record # [Hz]
        clock_dt   = 1e9/clock_freq # [ns]
        if clock_src == 'external':
            mClk   = self.clock_accumulation_mclk.record # [Hz]
        else:
            mClk   = clock_freq
        trigNode   = self.trigger
        drm        = self.clock_drm.record
        if drm:
            drm_dec    = self.clock_drm_decimation.record


        # Beginning store phase
        last_error=None
        """ The following is for segmented storage mode """
        import Queue
        queue = Queue.Queue(); raw = list()
        if self.debugging():
            print('Buffering channels 1-4')

        # Buffer the first 4 channels
        for rchan in range(4):
            try:
                chanNode = self.__getattr__('channels_input_%2.2d' % (rchan+1,))
                buf = self.bufferChannel(chanNode,rchan,chanMask,preTrig,postTrig)
                raw.append(buf)
                queue.put(chanNode)
            except Exception as e:
                print(("Error buffering channels 1-4: ch %d\n%s" % (rchan+1, e,)))
                last_error = e

        # Event analysis (e.g. for RGM windows)
        if trig_mode == 'RGM':
            if self.debugging():
                print('RGM event analysis')
            dims_slice = self._event_analysis(raw,mClk,clock_dt,trigNode,preTrig)

        else: # trigger mode is TRANSIENT
            if self.debugging():
                print('Transient event analysis')
            dims_slice = [self._get_dim_slice(0,mClk,clock_dt,trigNode,0,len(raw[0]),preTrig)]
        if self.debugging():
            print('Dimension slice = %s\n'%(dims_slice,))

        # Store all channels (only buffer 5-32)
        for chan in range(32):
            try:
                if chan in range(4):
                    chanNode = queue.get()
                    self.storeBuffer(chanNode,chan,chanMask,raw[chan],dims_slice)
                else:
                    chanNode = self.__getattr__('channels_input_%2.2d' % (chan+1,))
                    if chanNode.on and chanMask[chan:chan+1] == '1' :
                        if self.debugging():
                            print('Channel %s is ENABLED' % (chan+1,))
                        buf = self.bufferChannel(chanNode,chan,chanMask,preTrig,postTrig)
                        self.storeBuffer(chanNode,chan,chanMask,buf,dims_slice)
                    else:
                        if self.debugging():
                            print('Channel %s is DISABLED' % (chan+1,))
            except Exception as e:
                print(("Error storing channel %d\n%s" % (chan+1, e,)))
                last_error = e

        # Close socket connection
        self.dataSocketDone()
        if last_error:
            raise last_error

class ACQ196(ACQ):
    """
    D-Tacq ACQ196 - 96 channel transient recorder - 16-bit @ 500kSPS

    device support for d-tacq acq196 http://www.d-tacq.com/acq196cpci.shtml
    """
    max_chan   = 96
    daq_mem    = 512
    parts      = list(ACQ.acq_parts)

    acq196_parts=[
        {'path':':CHANNELS',      'type':'numeric', 'options':('no_write_shot',), 'value':96},
        {'path':':CLOCK:DIVIDER', 'type':'numeric', 'options':('write_once','no_write_model',)},
        ]

    for i in range(96):
        acq196_parts.append({'path':':CHANNELS:INPUT_%2.2d'%(i+1,),         'type':'signal' , 'options':('no_write_model','write_once',)})
        acq196_parts.append({'path':':CHANNELS:INPUT_%2.2d:VMIN'%(i+1,),    'type':'numeric', 'options':('no_write_model','write_once',)})
        acq196_parts.append({'path':':CHANNELS:INPUT_%2.2d:VMAX'%(i+1,),    'type':'numeric', 'options':('no_write_model','write_once',)})
        acq196_parts.append({'path':':CHANNELS:INPUT_%2.2d:STARTIDX'%(i+1,),'type':'NUMERIC', 'options':('no_write_shot',)})
        acq196_parts.append({'path':':CHANNELS:INPUT_%2.2d:ENDIDX'%(i+1,),  'type':'NUMERIC', 'options':('no_write_shot',)})
        acq196_parts.append({'path':':CHANNELS:INPUT_%2.2d:INC'%(i+1,),     'type':'NUMERIC', 'options':('no_write_shot',)})
    del i

    parts.extend(acq196_parts)

    def initftp(self, auto_store=None):
        """
        Initialize the device
        Send parameters
        Arm hardware
        """
        start=time.time()
        if self.debugging():
            print("starting init\n");
        path = self.local_path
        tree = self.local_tree
        shot = self.tree.shot
        if self.debugging():
            print('ACQ196 initftp path = %s tree = %s shot = %d\n' % (path, tree, shot))

        # Grab basic values from the tree
        master,clock_out = self.getMaster()

        active_chan = self.getInteger(self.channels,MDSplus.DevBAD_ACTIVE_CHAN)
        if active_chan not in (32,64,96) :
            raise MDSplus.DevBAD_ACTIVE_CHAN()
        if self.debugging():
            print("Number of active channels: %s"%active_chan)

        try:
            trig_src = self.trigger_source.record
        except Exception as e:
            raise MDSplus.DevBAD_TRIG_SRC(str(e))
        try:
            trig_edge = self.trigger_edge.record
        except Exception as e:
            raise MDSplus.DevBAD_PARAMETER(str(e))
        if self.debugging():
            print("Trigger source: %s %s"%(trig_src,trig_edge,))

        try:
            clock_src = self.clock_source.record
        except Exception as e:
            raise MDSplus.DevBAD_CLOCK_SRC(str(e))
        if self.debugging():
            print("Clock source: %s"%clock_src)

        # Setting pre and post to a multiple of 1024 guarantees that you'll
        # get that exact number of samples, rather than the nearest acceptable
        # number that the devices chooses.
        pre_trig = int((self.getInteger(self.trigger_pre,MDSplus.DevBAD_PRE_TRIG)-1)/1024+1)*1024
        if self.debugging():
            print("Pre trigger samples: %s"%pre_trig)

        post_trig = int((self.getInteger(self.trigger_post,MDSplus.DevBAD_POST_TRIG)-1)/1024+1)*1024
        if self.debugging():
            print("Post trigger samples: %s"%post_trig)

        clock_freq = self.getInteger(self.clock,MDSplus.DevBAD_CLOCK_FREQ)
        if self.debugging():
            print("Clock frequency: %s"%clock_freq)

        if self.debugging():
            print("have the settings\n")

        # Now create the "initialize" ftp command file
        fd = tempfile.NamedTemporaryFile(mode='w+b', bufsize=-1, suffix='.tmp', prefix='tmp', dir='/tmp', delete= not self.debugging())
        if self.debugging():
            print('opened temporary file %s\n'% fd.name)

        # Basic initial settings
        self.startInitializationFile(fd)

        # Set the number of active channels
        fd.write("acqcmd  setChannelMask " + '1' * active_chan+"\n")

        # Route clock DI lines
        self.setClockRouting(fd,clock_src,master,clock_out)

        # Set the clock frequencies
        if (clock_src == 'external') or (clock_src == 'internal' and not master):
            # Get external clock frequency
            clock_fin = self.getInteger(self.clock_source_fin,MDSplus.DevBAD_CLOCK_FREQ)
            if self.debugging():
                print("External clock freq: %s"%clock_fin)
            # Send commands to set up device properly
            clkDiv = int(clock_fin/clock_freq)
            self.clock_divider.record = clkDiv
            fd.write("acqcmd setInternalClock 0\n")
            fd.write("acqcmd setExternalClock DI0 %d\n" % clkDiv)
        else: # clock is internal - device is master
            if self.debugging():
                print("Internal clock")
            fd.write("acqcmd setInternalClock %d\n" % clock_freq)

        # set the channel mask 2 [more] times - ???
#        fd.write("acqcmd  setChannelMask " + '1' * active_chan+"\n")
#        fd.write("acqcmd  setChannelMask " + '1' * active_chan+"\n")

        # Route trigger DI lines
        self.setTrigRouting(fd,trig_src,master)

        # Set the trigger mode - currently TRANSIENT and RGM are supported
        trig_mode = self.trigger_mode.record
        if self.debugging(): print('Trigger mode: %s'%trig_mode)
        if trig_mode == 'RGM':
            fd.write("set.pre_post_mode %d %d DI3 %s\n"%(pre_trig,post_trig,trig_edge,))
            fd.write("set.dtacq RepeatingGateMode 2\n")
            fd.write("set.gate_src DI3 high\n")
        else: # trig_mode == 'TRANSIENT':
            fd.write("set.dtacq RepeatingGateMode 0\n")
            fd.write("set.pre_post_mode %d %d DI3 %s\n"%(pre_trig,post_trig,trig_edge,))

        #  set the [pre_post] trigger mode last
#        fd.write("set.pre_post_mode %d %d DI3 %s\n"%(pre_trig,post_trig,trig_edge,))

        # Generic JSON adds general information to the [initialization] ftp file
        self.addGenericJSON(fd)

        # grab the AI calibrations
        fd.write("add_cmd 'get.vin 1:32'>> $settingsf\n")
        fd.write("add_cmd 'get.vin 33:64'>> $settingsf\n")
        fd.write("add_cmd 'get.vin 65:96'>> $settingsf\n")
        self.finishJSON(fd, auto_store)

        print("Time to make init file = %g\n" % (time.time()-start))
        start = time.time()

        # Send the file - begin INIT procedure
        self.doInit(fd)
        fd.close()

        print("Time for board to init = %g\n" % (time.time()-start))

    def init(self, auto_store=None):
        self.initftp(auto_store)

    def store(self, arg1='checks', arg2='noauto'):
        if self.debugging():
            print("Begining store\n")

        # Wait for ACQ to finish acquiring/postprocessing
        self.waitAcq()
        
        self.checkTrigger(arg1, arg2)
        self.loadSettings()
        self.checkTreeAndShot(arg1, arg2)
        self.storeStatusCommands()

        preTrig = self.getPreTrig()
        postTrig = self.getPostTrig()
        if self.debugging():
            print("got preTrig %d and postTrig %d\n" % (preTrig, postTrig,))

        vin1 = self.settings['get.vin 1:32']
        vin2 = self.settings['get.vin 33:64']
        vin3 = self.settings['get.vin 65:96']

        active_chan = self.getInteger(self.channels,MDSplus.DevBAD_ACTIVE_CHAN)
        if self.debugging():
            print("Active channels: %s"%active_chan)
        if active_chan == 96 :
            vinArr = eval('MDSplus.makeArray([%s, %s, %s])' % (vin1, vin2, vin3,))
        else :
            if active_chan == 64 :
                vinArr = eval('MDSplus.makeArray([%s, %s])' % (vin1, vin2,))
            else :
                vinArr = eval('MDSplus.makeArray([%s])' % (vin1,))

        for i in range(active_chan):
            self.__setattr__('channels_input_%2.2d_vmin'%(i+1,),MDSplus.Float32(vinArr[2*i]))
            self.__setattr__('channels_input_%2.2d_vmax'%(i+1,),MDSplus.Float32(vinArr[2*i+1]))
        if self.debugging():
            print("Got the calibration vins")#: %s"%(str(vins,)))

        chanMask = self.settings['getChannelMask'].split('=')[-1]
        if self.debugging():
            print(("Active channel mask: %s" % (chanMask,)))

        # Grab some settings from the tree
        trig_mode  = self.trigger_mode.record
        clock_freq = self.clock.record # [Hz]
#        clock_div  = self.clock_divider.record # [-]
        clock_dt   = 1e9/clock_freq # [ns]
        trigNode   = self.trigger

        # Beginning store phase
        last_error=None
        """ The following is for segmented storage mode """
        import Queue
        queue = Queue.Queue(); raw = list()
        if self.debugging():
            print('Buffering channels 1-4')

        # Buffer the first 4 channels
        for rchan in range(4):
            try:
                chanNode = self.__getattr__('channels_input_%2.2d' % (rchan+1,))
                buf = self.bufferChannel(chanNode,rchan,chanMask,preTrig,postTrig)
                raw.append(buf)
                queue.put(chanNode)
            except Exception as e:
                print(("Error buffering channels 1-4: ch %d\n%s" % (rchan+1, e,)))
                last_error = e

        # Event analysis (e.g. for RGM windows)
        if trig_mode == 'RGM':
            if self.debugging():
                print('RGM event analysis')
            dims_slice = self._event_analysis(raw,clock_freq,clock_dt,trigNode,preTrig)

        else: # trigger mode is TRANSIENT
            if self.debugging():
                print('Transient event analysis')
            dims_slice = [self._get_dim_slice(0,clock_freq,clock_dt,trigNode,0,len(raw[0]),preTrig)]
        if self.debugging():
            print('Dimension slice = %s\n'%(dims_slice,))

        # Store all channels (only buffer 5-32)
        for chan in range(active_chan):
            try:
                if chan in range(4):
                    chanNode = queue.get()
                    self.storeBuffer(chanNode,chan,chanMask,raw[chan],dims_slice)
                else:
                    chanNode = self.__getattr__('channels_input_%2.2d' % (chan+1,))
                    if chanNode.on and chanMask[chan:chan+1] == '1' :
                        if self.debugging():
                            print('Channel %s is ENABLED' % (chan+1,))
                        buf = self.bufferChannel(chanNode,chan,chanMask,preTrig,postTrig)
                        self.storeBuffer(chanNode,chan,chanMask,buf,dims_slice)
                    else:
                        if self.debugging():
                            print('Channel %s is DISABLED' % (chan+1,))
            except Exception as e:
                print(("Error storing channel %d\n%s" % (chan+1, e,)))
                last_error = e

        # Close socket connection
        self.dataSocketDone()
        if last_error:
            raise last_error

