# -*- coding: utf-8 -*-
"""
Created on Mon Jul 17 13:55:00 2017

@author: gawe
"""
# ========================================================================== #    
# ========================================================================== #    

from __future__ import absolute_import, with_statement, absolute_import, \
                       division, print_function, unicode_literals

import socket
#import numpy as _np
import pdb                

# ========================================================================== #    



class scpi (object):
    """SCPI class used to access Red Pitaya over an IP network."""
    delimiter = '\r\n'

    def __init__(self, host, timeout=None, port=5000):
        """Initialize object and open IP connection.
        Host IP should be a string in parentheses, like '192.168.1.100'.
        """
        self.host    = host
        self.port    = port
        self.timeout = timeout

        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

            if timeout is not None:
                self._socket.settimeout(timeout)

            self._socket.connect((host, port))
            print('connected')

        except socket.error as e:
            print('SCPI >> connect({:s}:{:d}) failed: {:s}'.format(host, port, e))

    # ========================================================== #

    def __del__(self):
        if self._socket is not None:
            self._socket.close()
        self._socket = None

    def close(self):
        """Close IP connection."""
        self.__del__()

    # ========================================================== #
    # ========================================================== #

    def rx_txt(self, chunksize = 4096):
        """Receive text string and return it after removing the delimiter."""
        msg = ''
        while 1:
            chunk = self._socket.recv(chunksize + len(self.delimiter)).decode('utf-8') # Receive chunk size of 2^n preferably
            msg += chunk
            if (len(chunk) and chunk[-2:] == self.delimiter):
                break
        return msg[:-2]

    def rx_arb(self):
        numOfBytes = 0
        """ Recieve binary data from scpi server"""
        str=''
        while (len(str) != 1):
            str = (self._socket.recv(1))
        if not (str == '#'):
            return False
        str=''
        while (len(str) != 1):
            str = (self._socket.recv(1))
        numOfNumBytes = int(str)
        if not (numOfNumBytes > 0):
            return False
        str=''
        while (len(str) != numOfNumBytes):
            str += (self._socket.recv(1))
        numOfBytes = int(str)
        str=''
        while (len(str) != numOfBytes):
            str += (self._socket.recv(1))
        return str

    def tx_txt(self, msg):
        """Send text string ending and append delimiter."""
        return self._socket.send((msg + self.delimiter).encode('utf-8'))

    def txrx_txt(self, msg):
        """Send/receive text string."""
        self.tx_txt(msg)
        return self.rx_txt()

# IEEE Mandated Commands

    def cls(self):
        """Clear Status Command"""
        return self.tx_txt('*CLS')

    def ese(self, value=int()):
        """Standard Event Status Enable Command"""
        return self.tx_txt('*ESE {}'.format(value))

    def ese_q(self):
        """Standard Event Status Enable Query"""
        return self.txrx_txt('*ESE?')

    def esr_q(self):
        """Standard Event Status Register Query"""
        return self.txrx_txt('*ESR?')

    def idn_q(self):
        """Identification Query"""
        return self.txrx_txt('*IDN?')

    def opc(self):
        """Operation Complete Command"""
        return self.tx_txt('*OPC')

    def opc_q(self):
        """Operation Complete Query"""
        return self.txrx_txt('*OPC?')

    def rst(self):
        """Reset Command"""
        return self.tx_txt('*RST')

    def sre(self):
        """Service Request Enable Command"""
        return self.tx_txt('*SRE')

    def sre_q(self):
        """Service Request Enable Query"""
        return self.txrx_txt('*SRE?')

    def stb_q(self):
        """Read Status Byte Query"""
        return self.txrx_txt('*STB?')

# end class scpi



###############################################################################




# ========================================================================== #
"""
A python base class for SCPI interfacing through SOCKETS / TCPIP connections

The part of this code that sends and receives data is based on the SCPI class
written by Luka Golinar, and Iztok Jeras of the Red Pitaya company (2015).

This code does more.  It includes the base SCPI commands that are
mandated by IEEE 488.2, and is specifically meant for interfacing/controlling
scientific hardware.
    Author:  G.M. Weir      July 25th, 2017

"""
# ========================================================================== #
# ========================================================================== #

class _scpi_base(object):
    """ This base class contains wrappers around SCPI commands that are mandated
    by IEEE 488.2"""
#    if os.name.find('posix')>-1:
    delimiter = '\n'
#    else:
#        delimiter = '\r\n'

    def init(self, host=None, timeout=1.0, port=None, verbose=True):
        """Initialize object ... don't open IP connection quite yet
        Host IP should be a string in parentheses, like '192.168.1.100'.
        """
        self.host    = host
        self.port    = port
        self.timeout = timeout
        self.verbose = verbose
        if self.verbose:
            print("\n host: %s \n timeout: %2.1f \n port: %s \n"%(host,timeout,port))
        # endif
     # end def __init__

    def initialize_device(self):
        """
        Establish the IP connection, perform device self-tests and then get
        the ID and options from the device
        """

#        pdb.set_trace()

        # Establish the IP connection
        self._connection = self.establish_connection()

        if not self._connection:
            return 0

        # Test the IP connection and device status
#        try:
        self.test_connection()
        if self.verbose: print('connection tested')
#        except:
#            if self.verbose: print('Failed to test the device, probably not a supported command')
#            pass
                            
        # Get and store information about the device, including the device ID
#        try:
        self.IDN = self.get_IDN()
        if self.verbose: print('IDN is '+self.IDN)
#        except:
#            if self.verbose: print('Failed to get an IDN, probably not a supported command')
#            pass
        
        # Query the instrument options available and store them in a list
#        try:
        self.instrument_options = self.get_options()
        if self.verbose: print('instrument options are :'+self.instrument_options)
#        except:
#            if self.verbose: print('Failed to get instrument options, probably not a supported command')                        
 
        if hasattr(self, "_devicetestresult"):
            return self._devicetestresult
        else: 
            return 0

    # end def initialize_device

    # ========================================================== #
    # ========================================================== #

    def talk(self, connection, request, verbose=None):
        if verbose is None:
            verbose = self.verbose
        # endif

        return self.socket_talk(connection, request, verbose)

    def establish_connection(self):
        """
        =====> Establish connection to the SCPI device through a socket <=====
        """
        try:
            self.sckt = self.create_socket() # self.host, self.port)
            # print(0)
            self.remote_ip = self.connect_socket(self.host, self.port)
            # print(1)
            #if self.verbose:   # error here
            #    print('Established socket connection to remote %s through %s:%i'%(self.remoteip, self.host, self.port))
        except:
            if self.verbose: print('Failed to establish socket connection to remote device')
            return 0
        # end try
        return 1
    # end def establish_connection

    def test_connection(self):
        self._devicetestresult = self.self_test()
    # end def test_connection()

    #TODO # Does this work?    Double check
    def __del__(self):
        if self.sckt is not None:
            try: self.sckt.close()
            except: raise
            # end try
        self.sckt = None
#
    # ========================================================== #
    # ========================================================== #

    def create_socket(self):
        """
        Create a socket to the remote host along the port specified
        """
        try:            #create an AF_INET, STREAM socket (TCP)
            self.sckt = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

            if self.timeout is not None:
                self.sckt.settimeout(self.timeout)
            # endif

        except socket.error as e:
            if self.verbose:
                print('SCPI >> connect({:s}:{:d}) failed: {:s}'.format(self.host, self.port, e))
        return self.sckt
    # end def create_socket

    def connect_socket(self, host=None, port=None):
        """
        Make a connection to the remote host along the port specified
        """
        if host is None and hasattr(self, 'host'):
            host = self.host
        else:
            self.host = host
        # end if
        if port is None and hasattr(self, 'port'):
            port = self.port
        else:
            self.port = port
        # end if

        try:
            self.remote_ip = socket.gethostbyname( host )
            if self.verbose: print('Host: %s, IP: %s'%(host, self.remote_ip))
        except socket.gaierror:
            #could not resolve
            if self.verbose: print('Hostname could not be resolved. Exiting')
            # sys.exit()

        try:
            try:     self.sckt.connect((self.remote_ip , "%i"%(self.port,)))
            except:  self.sckt.connect((self.remote_ip , self.port))
        except :
            if self.verbose: print('Unable to connect to remote host %s through port %s'%(self.remote_ip, self.port))
        # end try

        return self.remote_ip

        # ========== #

    def socket_talk(self, socket, request, verbose=None):
        """
        Use an existing socket to send the SCPI request to the connected device

        If the request is a query, then forward the answer from the socket
        """
        if verbose is None:
            if hasattr(self, 'verbose'): verbose = self.verbose
            else: verbose = True
            # endif
        # endif
        answer = "okay"
#        try:                               #Send the whole string
        if 1:
            socket.sendall(request + self.delimiter)
#        except socket.error:                #Send failed
#            if self.verbose: print('Send ' + request + ' failed')
#             sys.exit()
#       end try

#        if request.find("?") > 0:
#             answer = socket.recv(1024)
#             return answer
#        else:
#             socket.sendall(":syst:error?" + self.delimiter)
#             answer = socket.recv(1024)

#        if request.find("?") == -1:
#            self.tx_txt(":syst:error?")
#        # end if
        answer = self.rx_txt()
        return answer

    def close(self):
        """Close IP connection."""
        self.__del__()

    # ========================================================== #
    # ========================================================== #

    def rx_txt(self, chunksize=4096):
        """Receive text string and return it after removing the delimiter."""
        msg = ''
        timeout=False
        while 1:
            try:
                chunk = self.sckt.recv(chunksize + len(self.delimiter)).decode('utf-8') # Receive chunk size of 2^n preferably
                msg += chunk
            except socket.timeout:
                # print("timeout error")
                timeout=True

            if timeout:
#            if (len(chunk) and chunk[-2:] == self.delimiter) or timeout==True:
#            if (len(chunk) and chunk[-2:] == self.delimiter) or (len(chunk) and chunk[-3:] == self.delimiter+'> ') or timeout==False:
                break
        return msg[:-2]

    def rx_arb(self):
        numOfBytes = 0
        """ Recieve binary data from scpi server"""
        strval=''
        while (len(strval) != 1):
            try:
                strval = (self.sckt.recv(1))
            except socket.timeout:
                break
        if not (strval == '#'):
            return False
        strval=''
        while (len(strval) != 1):
            try:
                strval = (self.sckt.recv(1))
            except socket.timeout:
                break
        numOfNumBytes = int(strval)
        if not (numOfNumBytes > 0):
            return False
        strval=''
        while (len(strval) != numOfNumBytes):
            try:
                strval += (self.sckt.recv(1))
            except socket.timeout:
                break
        numOfBytes = int(strval)
        strval=''
        while (len(strval) != numOfBytes):
            try:
                strval += (self.sckt.recv(1))
            except socket.timeout:
                break
        return strval

    def tx_txt(self, msg):
        """Send text string ending and append delimiter."""
        return self.sckt.send((msg + self.delimiter).encode('utf-8'))
    
    def txrx_txt(self, msg):
        """Send/receive text string."""
        self.tx_txt(msg)
        return self.rx_txt()

    # ========================================================== #
    # ========================================================== #

    def clear_status(self):
        """
        *CLS - *CLS Clear Status Command
        The Clear Status (CLS) command clears the status byte by emptying the error queue and clearing all the
        event registers including the Data Questionable Event Register, the Standard Event
        Status Register, the Standard Operation Status Register and any other registers that are
        summarized in the status byte.
        """
        err = self.talk(self.sckt, '*CLS')
        return err

    # ==== #

    def set_ESE(self, data=int()):
        """
        *ESE <data> - *ESE Standard Event Status Enable Command
        The Standard Event Status Enable (ESE) command sets the Standard Event Status Enable
        Register. The variable <data> represents the sum of the bits that will be enabled.
        Range 0–255
        Remarks The setting enabled by this command is not affected by signal generator preset or
        *RST. However, cycling the signal generator power will reset this register to zero.
        """
        err = self.talk(self.sckt, '*ESE %i'%(data,))
        self.get_ESE()
        return err

    def get_ESE(self):
        """
        *ESE? - *ESE? Standard Event Status Enable Query
        The Standard Event Status Enable (ESE) query returns the value of the Standard Event Status
        Enable Register.
        """
        self._ESE = self.talk(self.sckt, '*ESE?')
        return self._ESE

#    @property
#    def ESE(self):
#        self.get_ESE()
#        return self._ESE
#    @ESE.setter
#    def ESE(self, val):
#        self.set_ESE(val)
#    @ESE.deleter
#    def ESE(self):
#        del self._ESE

    # ==== #


    def get_ESR(self):
        """
        *ESR? - *ESR? Standard Event Status Register Query
        The Standard Event Status Register (ESR) query returns the value of the Standard Event Status
        Register.

        NOTE: Reading the Standard Event Status Register clears it

        Remarks The Register is not affected by signal generator preset or *RST. However, cycling the signal
        generator power will reset this register to zero.
        """
        self._ESR = self.talk(self.sckt, '*ESR?')
        return self._ESR

#    @property
#    def ESR(self):
#        self.get_ESR()
#        return self._ESR
##    @ESR.setter
##    def ESR(self, val):
##        self.set_ESR(val)
#    @ESR.deleter
#    def ESR(self):
#        del self._ESR
    # ==== #

    def get_IDN(self):
        """
        *IDN? - *IDN? Identification Query
        The Identification (IDN) query outputs an identifying string. The response will show the
        following information: <company name>, <model number>, <serial number>, <firmware
        revision>
        """
        self._IDN = self.talk(self.sckt, '*IDN?')
        if self.verbose: print(self._IDN)
        return self._IDN

#    @property
#    def IDN(self):
#        self.get_IDN()
#        return self._IDN
##    @IDN.setter
##    def IDN(self, val):
##        self.set_IDN(val)
#    @IDN.deleter
#    def IDN(self):
#        del self._IDN

    # ==== #

    def set_OPC(self):
        """
        *OPC - *OPC Operation Complete Command
        The Operation Complete (OPC) command sets bit 0 in the Standard Event Status Register when all
        pending operations have finished.
        The Operation Complete command causes the device to set the operation complete bit (bit 0) in the
        Standard Event Status Register when all pending operations have been finished.
        """
        err = self.talk(self.sckt, '*OPC')
        return err

    def get_OPC(self):
        """
        *OPC? - *OPC? Operation Complete Query
        The Operation Complete (OPC) query returns the ASCII character 1 in the Standard Event Status
        Register when all pending operations have finished.
        This query stops any new commands from being processed until the current processing is complete.
        This command blocks the communication until all operations are complete (i.e. the timeout setting
        should be longer than the longest sweep).
        """
        self._OPC = self.talk(self.sckt, '*OPC?')
        return self._OPC

#    @property
#    def OPC(self):
#        self.get_OPC()
#        return self._OPC
#    @OPC.setter
#    def OPC(self, val):
#        self.set_OPC()
#    @OPC.deleter
#    def OPC(self):
#        del self._OPC
    # ==== #

    def get_options(self):
        """
        *OPT? -
        The options (OPT) query returns a comma-separated list of all of the instrument options
        currently installed on the signal generator.
        """
        self._scpi_options = self.talk(self.sckt, '*OPT?')
        return self._scpi_options

    @property
    def scpi_options(self):
        self.get_options()
        return self._scpi_options
#    @scpi_options.setter
#    def scpi_options(self, val):
#        self.set_options(val)
    @scpi_options.deleter
    def scpi_options(self):
        del self._scpi_options

#    @property
#    def OPT(self):
#        self.get_options()
#        return self._scpi_options
##    @OPT.setter
##    def OPT(self, val):
##        self.set_OPT(val)
#    @OPT.deleter
#    def OPT(self):
#        del self._scpi_options

    # ==== #

    def set_PSC(self, onoff):
        """
        *PSC ON|OFF|1|0

        The Power-On Status Clear (PSC) command controls the automatic
        power-on clearing of the Service Request Enable Register,
        the Standard Event Status Enable Register, and device-specific
        event enable registers.
            ON(1)   This choice enables the power-on clearing of the listed registers.
            OFF(0)  This choice disables the clearing of the listed registers
                    and they retain their status when a power-on condition occurs.
        """
        if type(onoff) == type(''):
            if onoff.lower().find('on')>-1:
                onoff = 1
            elif onoff.lower().find('off')>-1:
                onoff = 0
        else:
            if onoff:
                onoff = 1
            else:
                onoff = 0
        # end if onoff parser
        err = self.talk(self.sckt, '*PSC %i'%(onoff,))
        self.get_PSC()
        return err

    def get_PSC(self):
        """
        The Power-On Status Clear (PSC) query returns the flag setting as enabled by the *PSC command.
        """
        self._PSC = self.talk(self.sckt, '*PSC?')
        return self._PSC

#    @property
#    def PSC(self):
#        self.get_PSC()
#        return self._PSC
#    @PSC.setter
#    def PSC(self, val):
#        self.set_PSC(val)
#    @PSC.deleter
#    def PSC(self):
#        del self._PSC

    # ==== #


    def recall_state(self, reg):
        """
        *RCL <reg>
        The Recall (RCL) command recalls the state from the specified memory register <reg>.
        """
        self._RCL = self.talk(self.sckt, '*RCL %s'%(str(reg),))
        return self._RCL

#    @property
#    def RCL(self):
#        return self._RCL
#    @RCL.setter
#    def RCL(self, val):
#        self.recall_state(val)
#    @RCL.deleter
#    def RCL(self):
#        del self._RCL

    # =============================================== #

    def reset_device(self):
        """
        *RST affected - *RST Reset Command
        The Reset (RST) command resets most signal generator functions to factory- defined conditions.
        Remarks Each command shows the [*RST] default value if the setting is affected.
        """
        err = self.talk(self.sckt, '*RST')
        return err

    def save_state(self, reg):
        """
        *SAV <reg>
        The Save (SAV) command saves signal generator settings to the specified memory register
        <reg>.
        Remarks The save function does not save all signal generator settings. Refer to the User’s Guide
        for more information on the save function. :
        """
        err = self.talk(self.sckt, '*SAV %s'%(str(reg),))
        return err

    # ================================================ #

    def set_SRE(self, data):
        """
        *SRE <data> - *SRE Service Request Enable Command

        The Service Request Enable (SRE) command sets the value of the Service Request Enable Register. The
        variable <data> is the decimal sum of the bits that will be enabled. Bit 6 (value 64) is ignored and
        cannot be set by this command.
        Range 0–255
        The setting enabled by this command is not affected by signal generator preset or
        *RST. However, cycling the signal generator power will reset it to zero.
        """
        err = self.talk(self.sckt, '*SRE %s'%(str(data),))
        return err

    def get_SRE(self):
        """
        *SRE? - *SRE? Service Request Enable Query
        The Service Request Enable (SRE) query returns the value of the Service Request Enable
        Register.
        Range 0–63 & 128-191   (64-127 is equiv. to 0 to 63)
        """
        self._SRE = self.talk(self.sckt, '*SRE?')
        return self._SRE

#    @property
#    def SRE(self):
#        self.get_SRE()
#        return self._SRE
#    @SRE.setter
#    def SRE(self, val):
#        self.set_SRE(val)
#    @SRE.deleter
#    def SRE(self):
#        del self._SRE

    # ==== #

    def get_STB(self):
        """
        *STB? - *STB? Read Status Byte Query
        The Read Status Byte (STB) query returns the value of the status byte including the master
        summary status (MSS) bit.
        Range 0–255
        """
        self._STB = self.talk(self.sckt, '*STB?')
        return self._STB

#    @property
#    def STB(self):
#        self.get_STB()
#        return self._STB
##    @STB.setter
##    def STB(self, val):
##        self.set_STB(val)
#    @STB.deleter
#    def STB(self):
#        del self._STB

    # ==== #

    def trigger_LAN(self):
        """
        *TRG
        The Trigger (TRG) command triggers the device if LAN is the selected trigger source, otherwise,
        *TRG is ignored.
        """
        err = self.talk(self.sckt, '*TRG')
        return err

    def self_test(self):
        """
        *TST? - *TST? Self-Test Query
        The Self-Test (TST) query initiates the internal self- test and returns one of the following results:
        0 This shows that all tests passed.
        1 This shows that one or more tests failed.
        """
        self.self_test_result = self.talk(self.sckt, '*TST?')
        if self.verbose: print(self.self_test_result)
        if self.self_test_result.find('0')>=-1:
            if self.verbose: print("All tests passed sucessfully")
            return 1
        elif self.self_test_result.lower().find('bad command')>-1:
            if self.verbose: print("LC Tech reflectometer connection successful")
            return 1
        else:
            if self.verbose: print("One or more tests failed")
            return 0
        # endif

    def wait(self):
        """
        *WAI - *WAI Wait-to-Continue Command
        The Wait- to- Continue (WAI) command causes the signal generator to wait until all pending
        commands are completed, before executing any other commands.
        """
        err = self.talk(self.sckt, '*WAI')
        return err

# end class _scpi_base


# ========================================================================== #
# ========================================================================== #


#


###############################################################################


class commands(_scpi_base):
    """
    This class wraps around the SCPI commands that are specific to the Red Pitaya     
    signal generator / oscilloscope functions
    """     
    def __init__(self, host, timeout, port, verbose):
        self.host = host
        self.timeout = timeout
        self.port = port
        self.verbose = verbose
        
        # Call the init method of the _scpi_base class
        super(commands, self).__init__(self.host, self.timeout, self.port, self.verbose)

        # Initialize the connection to the device, perform self tests and get 
        # the ID / options available
        self.initialize_device()
        
        # reinitialize the SCPI methods with the appropriate talk method and 
        # socket to connect through for communication with the reflectometer
        self.init_SCPI_methods(self.talk, self.sckt)     
        self.reset_device()                       

        # Pull out the information about the current state of the device
        self.parse_status(verbose=verbose)
    # end def __init__


    def init_SCPI_methods(self):
        if not hasattr(self, '_devicetestresult'):
            self.self_test()
        # end if
            
        if self._devicetestresult.find('0')>-1:
            if self.verbose: 
                print('Failed 1 or more internal device tests')
            # endif
            return self._devicetestresult                
        elif self.verbose:
            print('Passed all internal tests')                               
        # endif
            
        # to refer to the inner class, you must use self.(InnerClass)
        # Must replace the inner class call with an instance of that class
        # The instances need to have access to talk method, and socket connection in the outer class
        self.Triggers = Triggers(self.talk, self.sckt)  # TRIG:IMM - immediately trigger
        self.OscillatorA = Source(self.talk, self.sckt) # SOUR<n>, OUTPUT​<n>
        self.OscillatorB = Source(self.talk, self.sckt)
        self.PinIO = PinIO(self.talk, self.sckt)        # DIG:PIN, ANALOG:PIN
        self.Acquire = Acquire(self.talk, self.sckt)  

        self.Status = Status(self.talk, self.sckt)
        self.System = System(self.talk, self.sckt)        
    # end def init               
# end class commands

# =============================================================== #
# =============================================================== #


class Triggers(object):
    """
    """
    def __init__(self, talk_method, connection):
        self.talk = talk_method
        self.sckt = connection
        
        self.get_Waveform()
        self.set_FreqDelay()
        self.get_FreqDelay()  
             
    # end def __init__

    # =========== #
# end class Triggers

# =============================================================== #

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
        
#

class Source(object):
    """
    """
    def __init__(self, talk_method, connection):
        self.talk = talk_method
        self.sckt = connection
        
        self.get_Waveform()
        self.set_FreqDelay()
        self.get_FreqDelay()  
             
    # end def __init__

    # =========== #

    def set_Waveform(self, waveform='arbitrary'):
        """
        """
        pass
        return err
    # end def set_Waveform

    def get_Waveform(self):
        """
        """
        pass
        return waveform
    # end def get_Waveform

    # =========== #

    def set_FreqDelay(self, fdelay=6.5):
        """
        """
        pass
        return err
    # end def set_FreqDelay
        

    def get_FreqDelay(self):
        """
        """
        pass
        return fdelay
    # end def get_FreqDelay

    # =========== #
        
# end class Source


# =============================================================== #

class PinIO(object):
    """
    """
    def __init__(self, talk_method, connection):
        self.talk = talk_method
        self.sckt = connection
        
        self.get_PinIO()
        self.get_PinInputState()  
        self.get_PinOutputState()               
    # end def __init__

    # =========== #
# end class PinIO

# =============================================================== #


class Acquire(object):
    """
    """
    def __init__(self, talk_method, connection):
        self.talk = talk_method
        self.sckt = connection
        
        self.get_Waveform()
        self.set_FreqDelay()
        self.get_FreqDelay()  
             
    # end def __init__

    # =========== #
# end class Acquire

# =============================================================== #


class Status(object):
    """
    """
    def __init__(self, talk_method, connection):
        self.talk = talk_method
        self.sckt = connection
        
        self.get_Waveform()
        self.set_FreqDelay()
        self.get_FreqDelay()  
             
    # end def __init__

    # =========== #
# end class Status

# =============================================================== #


class System(object):
    """
    """
    def __init__(self, talk_method, connection):
        self.talk = talk_method
        self.sckt = connection
        
        self.get_Waveform()
        self.set_FreqDelay()
        self.get_FreqDelay()  
             
    # end def __init__

    # =========== #
# end class System

# =============================================================== #
# =============================================================== #


def __scl_GHz2KHz(self, FreqKHz):
    """
    helper function for scaling to KHz when function requires int(75e6) type input (75 GHz)
    """
    if FreqKHz<200:
        # assume value is given in GHz
        FreqKHz = int( 1e6*float(FreqKHz) )
    # endif
#        if type(FreqKHz) != type(int()):
#            FreqKHz = int(FreqKHz)
#        # end if            
    FreqKHz = int(FreqKHz)
    return FreqKHz   
    
def __scl_s2us(self, TimeUS):
    """
    helper function for scaling to micro-seconds when function requires int(1000) type input (1 ms)
    """
    if TimeUS<1e-3:
        # assume value is given in s
        TimeUS = int( 1e6*float(TimeUS) )
    # endif
#        if type(TimeUS) != type(int()):
#            TimeUS = int(TimeUS)
#        # end if            
    TimeUS = int(TimeUS)
    return TimeUS
        
def __parse_onoff(onoff):
#    onoff = __parse_onoff(onoff)
    if type(onoff) == type(''):
        if onoff.upper().find('D')>-1 or onoff.upper().find('OFF')>-1 or onoff.upper().find('0'):
            onoff = int(0)
        else:
            onoff = int(1)
    # endif
    if onoff:
        onoff = int(1)
    else:
        onoff = int(0)
    return onoff
    
def __parse_str2list(strin):
    if strin.find(',')>-1:
        dat = strin.split(',')
    elif strin.find(' ')>-1:
        dat = strin.split(' ')
    # Convert the tuple of strings into a list of floats
    return [float(val) for val in dat]
        
# ========================================================================== #    
# ========================================================================== #    
        
        
 