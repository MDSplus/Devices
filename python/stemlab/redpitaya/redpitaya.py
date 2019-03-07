try:
    import readline
except ImportError:
    print("Module readline not available.")
else:
    import rlcompleter
    readline.parse_and_bind("tab: complete")
import ctypes as ct,os
ADC_BUFFER_SIZE = (16*1024)
SPECTR_OUT_SIG_LEN = (2*1024)
### rp_dpin_t
# Type representing digital input output pins.
RP_LED0                  =  0   # LED 0
RP_LED1                  =  1   # LED 1
RP_LED2                  =  2   # LED 2
RP_LED3                  =  3   # LED 3
RP_LED4                  =  4   # LED 4
RP_LED5                  =  5   # LED 5
RP_LED6                  =  6   # LED 6
RP_LED7                  =  7   # LED 7
RP_DIO0_P                =  8   # DIO_P 0
RP_DIO1_P                =  9   # DIO_P 1
RP_DIO2_P                = 10   # DIO_P 2
RP_DIO3_P                = 11   # DIO_P 3
RP_DIO4_P                = 12   # DIO_P 4
RP_DIO5_P                = 13   # DIO_P 5
RP_DIO6_P                = 14   # DIO_P 6
RP_DIO7_P                = 15   # DIO_P 7
RP_DIO0_N                = 16   # DIO_N 0
RP_DIO1_N                = 17   # DIO_N 1
RP_DIO2_N                = 18   # DIO_N 2
RP_DIO3_N                = 19   # DIO_N 3
RP_DIO4_N                = 20   # DIO_N 4
RP_DIO5_N                = 21   # DIO_N 5
RP_DIO6_N                = 22   # DIO_N 6
RP_DIO7_N                = 23   # DIO_N 7
### rp_pinState_t
# Type representing pin's high or low state (on/off).
RP_LOW                   =  0   # Low state
RP_HIGH                  =  1   # High state
### rp_pinDirection_t
# Type representing pin's input or output direction.
RP_IN                    =  0   # Input direction
RP_OUT                   =  1   # Output direction
### rp_apin_t
# Type representing analog input output pins.
RP_AOUT0                 =  0   # Analog output 0
RP_AOUT1                 =  1   # Analog output 1
RP_AOUT2                 =  2   # Analog output 2
RP_AOUT3                 =  3   # Analog output 3
RP_AIN0                  =  4   # Analog input 0
RP_AIN1                  =  5   # Analog input 1
RP_AIN2                  =  6   # Analog input 2
RP_AIN3                  =  7   # Analog input 3
### rp_waveform_t
RP_WAVEFORM_SINE         =  0   # Wave form sine
RP_WAVEFORM_SQUARE       =  1   # Wave form square
RP_WAVEFORM_TRIANGLE     =  2   # Wave form triangle
RP_WAVEFORM_RAMP_UP      =  3   # Wave form sawtooth (/|)
RP_WAVEFORM_RAMP_DOWN    =  4   # Wave form reversed sawtooth (|\)
RP_WAVEFORM_DC           =  5   # Wave form dc
RP_WAVEFORM_PWM          =  6   # Wave form pwm
RP_WAVEFORM_ARBITRARY    =  7   # Use defined wave form
### rp_gen_mode_t
RP_GEN_MODE_CONTINUOUS   =  0   # Continuous signal generation
RP_GEN_MODE_BURST        =  1   # Signal is generated N times, wher N is defined with rp_GenBurstCount method
RP_GEN_MODE_STREAM       =  2   # User can continuously write data to buffer
### rp_trig_src_t
RP_GEN_TRIG_SRC_INTERNAL =  1   # Internal trigger source
RP_GEN_TRIG_SRC_EXT_PE   =  2   # External trigger source positive edge
RP_GEN_TRIG_SRC_EXT_NE   =  3   # External trigger source negative edge
RP_GEN_TRIG_GATED_BURST  =  4   # External trigger gated burst
### rp_channel_t
# Type representing Input/Output channels.
RP_CH_1                  =  0   # Channel A
RP_CH_2                  =  1   # Channel B
### rp_acq_sampling_rate_t
# Type representing acquire signal sampling rate.
RP_SMP_125M              =  0   # Sample rate 125Msps; Buffer time length 131us; Decimation 1
RP_SMP_15_625M           =  1   # Sample rate 15.625Msps; Buffer time length 1.048ms; Decimation 8
RP_SMP_1_953M            =  2   # Sample rate 1.953Msps; Buffer time length 8.388ms; Decimation 64
RP_SMP_122_070K          =  3   # Sample rate 122.070ksps; Buffer time length 134.2ms; Decimation 1024
RP_SMP_15_258K           =  4   # Sample rate 15.258ksps; Buffer time length 1.073s; Decimation 8192
RP_SMP_1_907K            =  5   # Sample rate 1.907ksps; Buffer time length 8.589s; Decimation 65536
### rp_acq_decimation_t
# Type representing decimation used at acquiring signal.
RP_DEC_1                 =  0   # Sample rate 125Msps; Buffer time length 131us; Decimation 1
RP_DEC_8                 =  1   # Sample rate 15.625Msps; Buffer time length 1.048ms; Decimation 8
RP_DEC_64                =  2   # Sample rate 1.953Msps; Buffer time length 8.388ms; Decimation 64
RP_DEC_1024              =  3   # Sample rate 122.070ksps; Buffer time length 134.2ms; Decimation 1024
RP_DEC_8192              =  4   # Sample rate 15.258ksps; Buffer time length 1.073s; Decimation 8192
RP_DEC_65536             =  5   # Sample rate 1.907ksps; Buffer time length 8.589s; Decimation 65536
### rp_acq_trig_src_t
# Type representing different trigger sources used at acquiring signal.
RP_TRIG_SRC_DISABLED     =  0   # Trigger is disabled
RP_TRIG_SRC_NOW          =  1   # Trigger triggered now (immediately)
RP_TRIG_SRC_CHA_PE       =  2   # Trigger set to Channel A threshold positive edge
RP_TRIG_SRC_CHA_NE       =  3   # Trigger set to Channel A threshold negative edge
RP_TRIG_SRC_CHB_PE       =  4   # Trigger set to Channel B threshold positive edge
RP_TRIG_SRC_CHB_NE       =  5   # Trigger set to Channel B threshold negative edge
RP_TRIG_SRC_EXT_PE       =  6   # Trigger set to external trigger positive edge (DIO0_P pin)
RP_TRIG_SRC_EXT_NE       =  7   # Trigger set to external trigger negative edge (DIO0_P pin)
RP_TRIG_SRC_AWG_PE       =  8   # Trigger set to arbitrary wave generator application positive edge
RP_TRIG_SRC_AWG_NE       =  9   # Trigger set to arbitrary wave generator application negative edge
### rp_acq_trig_state_t
# Type representing different trigger states.
RP_TRIG_STATE_TRIGGERED  =  0   # Trigger is triggered/disabled
RP_TRIG_STATE_WAITING    =  1   # Trigger is set up and waiting (to be triggered)
### Calibration parameters, stored in the EEPROM device
class CALIB_PARAMS(ct.Structure):
    _fields_ = [
        ('fe_ch1_fs_g_hi', ct.c_uint32),
        ('fe_ch2_fs_g_hi', ct.c_uint32),
        ('fe_ch1_fs_g_lo', ct.c_uint32),
        ('fe_ch2_fs_g_lo', ct.c_uint32),
        ('fe_ch1_lo_offs', ct.c_uint32),
        ('fe_ch2_lo_offs', ct.c_uint32),
        ('be_ch1_fs',      ct.c_uint32),
        ('be_ch2_fs',      ct.c_uint32),
        ('be_ch1_dc_offs', ct.c_uint32),
        ('be_ch2_dc_offs', ct.c_uint32),
        ('magic',          ct.c_uint32),
        ('fe_ch1_hi_offs', ct.c_uint32),
        ('fe_ch2_hi_offs', ct.c_uint32),
    ]
class RPException(Exception): pass
class RPExceptionEOED(RPException):
    def __init__(self): super(RPExceptionEOED,self).__init__("Failed to Open EEPROM Device")
class RPExceptionEOMD(RPException):
    def __init__(self): super(RPExceptionEOMD,self).__init__("Failed to Open Memory Device")
class RPExceptionECMD(RPException):
    def __init__(self): super(RPExceptionECMD,self).__init__("Failed to Close Memory Device")
class RPExceptionEMMD(RPException):
    def __init__(self): super(RPExceptionEMMD,self).__init__("Failed to Map Memory Device")
class RPExceptionEUMD(RPException):
    def __init__(self): super(RPExceptionEUMD,self).__init__("Failed to Unmap Memory Device")
class RPExceptionEOOR(RPException):
    def __init__(self): super(RPExceptionEOOR,self).__init__("Value Out Of Range")
class RPExceptionELID(RPException):
    def __init__(self): super(RPExceptionELID,self).__init__("LED Input Direction is not valid")
class RPExceptionEMRO(RPException):
    def __init__(self): super(RPExceptionEMRO,self).__init__("Modifying Read Only field")
class RPExceptionEWIP(RPException):
    def __init__(self): super(RPExceptionEWIP,self).__init__("Writing to Input Pin is not valid")
class RPExceptionEPN (RPException):
    def __init__(self): super(RPExceptionEPN,self).__init__("Invalid Pin number")
class RPExceptionUIA (RPException):
    def __init__(self): super(RPExceptionUIA,self).__init__("Uninitialized Input Argument")
class RPExceptionFCA (RPException):
    def __init__(self): super(RPExceptionFCA,self).__init__("Failed to Find Calibration Parameters")
class RPExceptionRCA (RPException):
    def __init__(self): super(RPExceptionRCA,self).__init__("Failed to Read Calibration Parameters")
class RPExceptionBTS (RPException):
    def __init__(self): super(RPExceptionBTS,self).__init__("Buffer too small")
class RPExceptionEIPV(RPException):
    def __init__(self): super(RPExceptionEIPV,self).__init__("Invalid parameter value")
class RPExceptionEUF (RPException):
    def __init__(self): super(RPExceptionEUF,self).__init__("Unsupported Feature")
class RPExceptionENN (RPException):
    def __init__(self): super(RPExceptionENN,self).__init__("Data not normalized")
class RPExceptionEFOB(RPException):
    def __init__(self): super(RPExceptionEFOB,self).__init__("Failed to open bus")
class RPExceptionEFCB(RPException):
    def __init__(self): super(RPExceptionEFCB,self).__init__("Failed to close bus")
class RPExceptionEABA(RPException):
    def __init__(self): super(RPExceptionEABA,self).__init__("Failed to acquire bus access")
class RPExceptionEFRB(RPException):
    def __init__(self): super(RPExceptionEFRB,self).__init__("Failed to read from the bus")
class RPExceptionEFWB(RPException):
    def __init__(self): super(RPExceptionEFWB,self).__init__("Failed to write to the bus")
class RPExceptionEMNC(RPException):
    def __init__(self): super(RPExceptionEMNC,self).__init__("Extension module not connected")
def check(code):
    if code ==  0: return
    if code ==  1: raise RPExceptionEOED
    if code ==  2: raise RPExceptionEOMD
    if code ==  3: raise RPExceptionECMD
    if code ==  4: raise RPExceptionEMMD
    if code ==  5: raise RPExceptionEUMD
    if code ==  6: raise RPExceptionEOOR
    if code ==  7: raise RPExceptionELID
    if code ==  8: raise RPExceptionEMRO
    if code ==  9: raise RPExceptionEWIP
    if code == 10: raise RPExceptionEPN
    if code == 11: raise RPExceptionUIA
    if code == 12: raise RPExceptionFCA
    if code == 13: raise RPExceptionRCA
    if code == 14: raise RPExceptionBTS
    if code == 15: raise RPExceptionEIPV
    if code == 16: raise RPExceptionEUF
    if code == 17: raise RPExceptionENN
    if code == 18: raise RPExceptionEFOB
    if code == 19: raise RPExceptionEFCB
    if code == 20: raise RPExceptionEABA
    if code == 21: raise RPExceptionEFRB
    if code == 22: raise RPExceptionEFWB
    if code == 23: raise RPExceptionEMNC
    raise RPException('Unknown error %d'%(code,))
class redpitaya():
    @staticmethod
    def loadfpga():
        os.system('cat /opt/redpitaya/fpga/fpga_0.94.bit > /dev/xdevcfg')
    _released = False
    _lib = None
    @property
    def lib(self):
        if self.__class__._released:
            raise RPException("rp.Release has been called already restart program first.")
        return self.__class__._lib
    def __init__(self):
        """
        Initializes the library. It must be called first, before any other library method.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        if self.lib is None:
            redpitaya._lib = ct.CDLL('/opt/redpitaya/lib/librp.so')
            self._lib.rp_GetError.restype = ct.c_char_p
            self._lib.rp_GetVersion.restype = ct.c_char_p
            self._lib.rp_GetCalibrationSettings.restype = CALIB_PARAMS
            self._lib.rp_CmnCnvCntToV.restype = ct.c_float
            check(self._lib.rp_Init())
    def CalibInit(self):
        check(self.lib.rp_CalibInit())
    def Release(self):
        """
        Releases the library resources. It must be called last, after library is not used anymore. Typically before
        application exits.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        check(self.lib.rp_Release())
        redpitaya._released = True
    def Reset(self):
        """
        Resets all modules. Typically calles after rp_Init()
        application exits.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        check(self.lib.rp_Reset())
    def GetVersion(self):
        """
        Retrieves the library version number
        @return Library version
        """
        return self.lib.rp_GetVersion()
    def GetError(self,code):
        """
        Returns textual representation of error code.
        @param errorCode Error code returned from API.
        @return Textual representation of error given error code.
        """
        return self.lib.rp_GetError(ct.c_int32(code))
    def EnableDigitalLoop(self,enable):
        """
        Enable or disables digital loop. This internally connect output to input
        @param enable True if you want to enable this feature or false if you want to disable it
        Each rp_GetCalibrationSettings call returns the same cached setting values.
        @return Calibration settings
        """
        check(self.lib.rp_EnableDigitalLoop(ct.c_bool(enable)))
    def GetCalibrationSettings(self):
        """
        Returns calibration settings.
        These calibration settings are populated only once from EEPROM at rp_Init().
        Each rp_GetCalibrationSettings call returns the same cached setting values.
        @return Calibration settings
        """
        return self.lib.rp_GetCalibrationSettings()
    def CalibrateFrontEndOffset(self,channel,gain):
        """
        Calibrates input channel offset. This input channel must be grounded to calibrate properly.
        Calibration data is written to EPROM and repopulated so that rp_GetCalibrationSettings works properly.
        @param channel Channel witch is going to be calibrated
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        out_params = CALIB_PARAMS()
        check(self.lib.rp_CalibrateFrontEndOffset(ct.c_uint32(channel),ct.c_uint32(gain),ct.byref(out_params)))
        return out_params
    def CalibrateFrontEndScaleLV(self,channel,referentialVoltage):
        """
        Calibrates input channel low voltage scale. Jumpers must be set to LV.
        This input channel must be connected to stable positive source.
        Calibration data is written to EPROM and repopulated so that rp_GetCalibrationSettings works properly.
        @param channel Channel witch is going to be calibrated
        @param referentialVoltage Voltage of the source.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        out_params = CALIB_PARAMS()
        check(self.lib.rp_CalibrateFrontEndScaleLV(ct.c_uint32(channel),ct.c_float(referentialVoltage),ct.byref(out_params)))
        return out_params
    def CalibrateFrontEndScaleHV(self,channel,referentialVoltage):
        """
        Calibrates input channel high voltage scale. Jumpers must be set to HV.
        This input channel must be connected to stable positive source.
        Calibration data is written to EPROM and repopulated so that rp_GetCalibrationSettings works properly.
        @param channel Channel witch is going to be calibrated
        @param referentialVoltage Voltage of the source.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        out_params = CALIB_PARAMS()
        check(self.lib.rp_CalibrateFrontEndScaleHV(ct.c_uint32(channel),ct.c_float(referentialVoltage),ct.byref(out_params)))
        return out_params
    def CalibrateBackEndOffset(self,channel):
        """
        Calibrates output channel offset.
        This input channel must be connected to calibrated input channel with came number (CH1 to CH1 and CH2 to CH2).
        Calibration data is written to EPROM and repopulated so that rp_GetCalibrationSettings works properly.
        @param channel Channel witch is going to be calibrated
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        check(self.lib.rp_CalibrateBackEndOffset(ct.c_uint32(channel)))
    def CalibrateBackEndScale(self,channel):
        """
        Calibrates output channel voltage scale.
        This input channel must be connected to calibrated input channel with came number (CH1 to CH1 and CH2 to CH2).
        Calibration data is written to EPROM and repopulated so that rp_GetCalibrationSettings works properly.
        @param channel Channel witch is going to be calibrated
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        check(self.lib.rp_CalibrateBackEndScale(ct.c_uint32(channel)))
    def CalibrateBackEnd(self,channel):
        """
        Calibrates output channel.
        This input channel must be connected to calibrated input channel with came number (CH1 to CH1 and CH2 to CH2).
        Calibration data is written to EPROM and repopulated so that rp_GetCalibrationSettings works properly.
        @param channel Channel witch is going to be calibrated
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        out_params = CALIB_PARAMS()
        check(self.lib.rp_CalibrateBackEnd(ct.c_uint32(channel),ct.byref(out_params)))
        return out_params
    def CalibrationReset(self):
        """
        Set default calibration values.
        Calibration data is written to EPROM and repopulated so that rp_GetCalibrationSettings works properly.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        check(self.lib.rp_CalibrationReset())
    def CalibrationSetCachedParams(self):
        """
        Set saved calibration values in case of roll-back calibration.
        Calibration data is written to EPROM and repopulated so that rp_GetCalibrationSettings works properly.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        check(self.lib.rp_CalibrationSetCachedParams())
    def CalibrationWriteParams(self,calib_params):
        """
        Write calibration values.
        Calibration data is written to EPROM and repopulated so that rp_GetCalibrationSettings works properly.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        check(self.lib.rp_CalibrationWriteParams(CALIB_PARAMS(calib_params)))
    def IdGetID(self):
        """
        Gets FPGA Synthesized ID
        """
        id = ct.c_uint32()
        check(self.lib.rp_IdGetID(ct.byref(id)))
        return id.value
    def IdGetDNA(self):
        """
        Gets FPGA Unique DNA
        """
        dna = ct.c_uint64()
        check(self.lib.rp_IdGetDNA(ct.byref(dna)))
        return dna.value
    def LEDSetState(self,state):
        check(self.lib.rp_LEDSetState(ct.c_uint32(state)))
    def LEDGetState(self):
        state = ct.c_uint32()
        check(self.lib.rp_LEDGetState(ct.byref(state)))
        return state.value
    def GPIOnSetDirection(self,direction):
        check(self.lib.rp_GPIOnSetDirection(ct.c_uint32(direction)))
    def GPIOnGetDirection(self):
        direction = ct.c_uint32()
        check(self.lib.rp_GPIOnGetDirection(ct.byref(direction)))
        return direction.value
    def GPIOnSetState(self,state):
        check(self.lib.rp_GPIOnSetState(ct.c_uint32(state)))
    def GPIOnGetState(self):
        state = ct.c_uint32()
        check(self.lib.rp_GPIOnGetState(ct.byref(state)))
        return state.value
    def GPIOpSetDirection(self,direction):
        check(self.lib.rp_GPIOpSetDirection(ct.c_uint32(direction)))
    def GPIOpGetDirection(self):
        direction = ct.c_uint32()
        check(self.lib.rp_GPIOpGetDirection(ct.byref(direction)))
        return direction.value
    def GPIOpSetState(self,state):
        check(self.lib.rp_GPIOpSetState(ct.c_uint32(state)))
    def GPIOpGetState(self):
        state = ct.c_uint32()
        check(self.lib.rp_GPIOpGetState(ct.byref(state)))
        return state.value
    def DpinReset(self):
        """
        Sets digital pins to default values. Pins DIO1_P - DIO7_P, RP_DIO0_N - RP_DIO7_N are set al OUTPUT and to LOW. LEDs are set to LOW/OFF
        """
        check(self.lib.rp_DpinReset())
    def DpinSetState(self,pin,state):
        """
        Sets digital input output pin state.
        @param pin    Digital input output pin.
        @param state  High/Low state that will be set at the given pin.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        check(self.lib.rp_DpinSetState(ct.c_uint32(pin),ct.c_uint32(state)))
    def DpinGetState(self,pin):
        """
        Gets digital input output pin state.
        @param pin    Digital input output pin.
        @param state  High/Low state that is set at the given pin.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        state = ct.c_uint32()
        check(self.lib.rp_DpinGetState(ct.c_uint32(pin),ct.byref(state)))
        return state.value
    def DpinSetDirection(self,pin,direction):
        """
        Sets digital input output pin direction. LED pins are already automatically set to the output direction,
        and they cannot be set to the input direction. DIOx_P and DIOx_N are must set either output or input direction
        before they can be used. When set to input direction, it is not allowed to write into these pins.
        @param pin        Digital input output pin.
        @param direction  In/Out direction that will be set at the given pin.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        check(self.lib.rp_DpinSetDirection(ct.c_uint32(pin),ct.c_uint32(direction)))
    def DpinGetDirection(self,pin):
        """
        Gets digital input output pin direction.
        @param pin        Digital input output pin.
        @param direction  In/Out direction that is set at the given pin.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        direction = ct.c_uint32()
        check(self.lib.rp_DpinGetDirection(ct.c_uint32(pin),ct.byref(direction)))
        return direction.value
    def ApinReset(self):
        """
        Sets analog outputs to default values (0V).
        """
        check(self.lib.rp_ApinReset())
    def ApinGetValue(self,pin):
        """
        Gets value from analog pin in volts.
        @param pin    Analog pin.
        @param value  Value on analog pin in volts
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        value = ct.c_float()
        check(self.lib.rp_ApinGetValue(ct.c_uint32(pin),ct.byref(value)))
        return value.value
    def ApinGetValueRaw(self,pin):
        """
        Gets raw value from analog pin.
        @param pin    Analog pin.
        @param value  Raw value on analog pin
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        value = ct.c_uint32()
        check(self.lib.rp_ApinGetValueRaw(ct.c_uint32(pin),ct.byref(value)))
        return value.value
    def ApinSetValue(self,pin,value):
        """
        Sets value in volts on analog output pin.
        @param pin    Analog output pin.
        @param value  Value in volts to be set on given output pin.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        check(self.lib.rp_ApinSetValue(ct.c_uint32(pin),ct.c_float(value)))
    def ApinSetValueRaw(self,pin,value):
        """
        Sets raw value on analog output pin.
        @param pin    Analog output pin.
        @param value  Raw value to be set on given output pin.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        check(self.lib.rp_ApinSetValueRaw(ct.c_uint32(pin),ct.c_uint32(value)))
    def ApinGetRange(self,pin):
        """
        Gets range in volts on specific pin.
        @param pin      Analog input output pin.
        @param min_val  Minimum value in volts on given pin.
        @param max_val  Maximum value in volts on given pin.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        min_val = ct.c_float()
        max_val = ct.c_float()
        check(self.lib.rp_ApinGetRange(ct.c_uint32(pin),ct.byref(min_val),ct.byref(max_val)))
        return min_val.value,max_val.value
    def AIpinGetValue(self,pin):
        """
        Gets value from analog pin in volts.
        @param pin    pin index
        @param value  voltage
        @return       RP_OK - successful, RP_E* - failure
        """
        value = ct.c_float()
        check(self.lib.rp_AIpinGetValue(ct.c_uint32(pin),ct.byref(value)))
        return value.value
    def AIpinGetValueRaw(self,pin):
        """
        Gets raw value from analog pin.
        @param pin    pin index
        @param value  raw 12 bit XADC value
        @return       RP_OK - successful, RP_E* - failure
        """
        value = ct.c_uint32()
        check(self.lib.rp_AIpinGetValueRaw(ct.c_uint32(pin),ct.byref(value)))
        return value.value
    def AOpinReset(self):
        """
        Sets analog outputs to default values (0V).
        """
        check(self.lib.rp_AOpinReset())
    def AOpinGetValue(self,pin):
        """
        Gets value from analog pin in volts.
        @param pin    Analog output pin index.
        @param value  Value on analog pin in volts
        @return       RP_OK - successful, RP_E* - failure
        """
        value = ct.c_float()
        check(self.lib.rp_AOpinGetValue(ct.c_uint32(pin),ct.byref(value)))
        return value.value
    def AOpinGetValueRaw(self,pin):
        """
        Gets raw value from analog pin.
        @param pin    Analog output pin index.
        @param value  Raw value on analog pin
        @return       RP_OK - successful, RP_E* - failure
        """
        value = ct.c_uint32()
        check(self.lib.rp_AOpinGetValueRaw(ct.c_uint32(pin),ct.byref(value)))
        return value.value
    def AOpinSetValue(self,pin,value):
        """
        Sets value in volts on analog output pin.
        @param pin    Analog output pin index.
        @param value  Value in volts to be set on given output pin.
        @return       RP_OK - successful, RP_E* - failure
        """
        check(self.lib.rp_AOpinSetValue(ct.c_uint32(pin),ct.c_float(value)))
    def AOpinSetValueRaw(self,pin,value):
        """
        Sets raw value on analog output pin.
        @param pin    Analog output pin index.
        @param value  Raw value to be set on given output pin.
        @return       RP_OK - successful, RP_E* - failure
        """
        check(self.lib.rp_AOpinSetValueRaw(ct.c_uint32(pin),ct.c_uint32(value)))
    def AOpinGetRange(self,pin):
        """
        Gets range in volts on specific pin.
        @param pin      Analog input output pin index.
        @param min_val  Minimum value in volts on given pin.
        @param max_val  Maximum value in volts on given pin.
        @return       RP_OK - successful, RP_E* - failure
        """
        min_val = ct.c_float()
        max_val = ct.c_float()
        check(self.lib.rp_AOpinGetRange(ct.c_uint32(pin),ct.byref(min_val),ct.byref(max_val)))
        return min_val.value,max_val.value
    def AcqSetArmKeep(self,enable):
        """
        Enables continous acquirement even after trigger has happened.
        @param enable True for enabling and false disabling
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        check(self.lib.rp_AcqSetArmKeep(ct.c_bool(enable)))
    def AcqSetDecimation(self,decimation):
        """
        Sets the decimation used at acquiring signal. There is only a set of pre-defined decimation
        values which can be specified. See the #rp_acq_decimation_t enum values.
        @param decimation Specify one of pre-defined decimation values
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        check(self.lib.rp_AcqSetDecimation(ct.c_uint32(decimation)))
    def AcqGetDecimation(self):
        """
        Gets the decimation used at acquiring signal. There is only a set of pre-defined decimation
        values which can be specified. See the #rp_acq_decimation_t enum values.
        @param decimation Returns one of pre-defined decimation values which is currently set.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        decimation = ct.c_uint32()
        check(self.lib.rp_AcqGetDecimation(ct.byref(decimation)))
        return decimation.value
    def AcqGetDecimationFactor(self):
        """
        Gets the decimation factor used at acquiring signal in a numerical form. Although this method returns an integer
        value representing the current factor of the decimation, there is only a set of pre-defined decimation
        factor values which can be returned. See the #rp_acq_decimation_t enum values.
        @param decimation Returns decimation factor value which is currently set.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        decimation = ct.c_uint32()
        check(self.lib.rp_AcqGetDecimationFactor(ct.byref(decimation)))
        return decimation.value
    def AcqSetSamplingRate(self,sampling_rate):
        """
        Sets the sampling rate for acquiring signal. There is only a set of pre-defined sampling rate
        values which can be specified. See the #rp_acq_sampling_rate_t enum values.
        @param sampling_rate Specify one of pre-defined sampling rate value
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        check(self.lib.rp_AcqSetSamplingRate(ct.c_uint32(sampling_rate)))
    def AcqGetSamplingRate(self):
        """
        Gets the sampling rate for acquiring signal. There is only a set of pre-defined sampling rate
        values which can be returned. See the #rp_acq_sampling_rate_t enum values.
        @param sampling_rate Returns one of pre-defined sampling rate value which is currently set
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        sampling_rate = ct.c_uint32()
        check(self.lib.rp_AcqGetSamplingRate(ct.byref(sampling_rate)))
        return sampling_rate.value
    def AcqGetSamplingRateHz(self):
        """
        Gets the sampling rate for acquiring signal in a numerical form in Hz. Although this method returns a float
        value representing the current value of the sampling rate, there is only a set of pre-defined sampling rate
        values which can be returned. See the #rp_acq_sampling_rate_t enum values.
        @param sampling_rate returns currently set sampling rate in Hz
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        sampling_rate = ct.c_float()
        check(self.lib.rp_AcqGetSamplingRateHz(ct.byref(sampling_rate)))
        return sampling_rate.value
    def AcqSetAveraging(self,enabled):
        """
        Enables or disables averaging of data between samples.
        Data between samples can be averaged by setting the averaging flag in the Data decimation register.
        @param enabled When true, the averaging is enabled, otherwise it is disabled.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        check(self.lib.rp_AcqSetAveraging(ct.c_bool(enabled)))
    def AcqGetAveraging(self):
        """
        Returns information if averaging of data between samples is enabled or disabled.
        Data between samples can be averaged by setting the averaging flag in the Data decimation register.
        @param enabled Set to true when the averaging is enabled, otherwise is it set to false.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        enabled = ct.c_bool()
        check(self.lib.rp_AcqGetAveraging(ct.byref(enabled)))
        return enabled.value
    def AcqSetTriggerSrc(self,source):
        """
        Sets the trigger source used at acquiring signal. When acquiring is started,
        the FPGA waits for the trigger condition on the specified source and when the condition is met, it
        starts writing the signal to the buffer.
        @param source Trigger source.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        check(self.lib.rp_AcqSetTriggerSrc(ct.c_uint32(source)))
    def AcqGetTriggerSrc(self):
        """
        Gets the trigger source used at acquiring signal. When acquiring is started,
        the FPGA waits for the trigger condition on the specified source and when the condition is met, it
        starts writing the signal to the buffer.
        @param source Currently set trigger source.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        source = ct.c_uint32()
        check(self.lib.rp_AcqGetTriggerSrc(ct.byref(source)))
        return source.value
    def AcqGetTriggerState(self):
        """
        Returns the trigger state. Either it is waiting for a trigger to happen, or it has already been triggered.
        By default it is in the triggered state, which is treated the same as disabled.
        @param state Trigger state
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        state = ct.c_uint32()
        check(self.lib.rp_AcqGetTriggerState(ct.byref(state)))
        return state.value
    def AcqSetTriggerDelay(self,decimated_data_num):
        """
        Sets the number of decimated data after trigger written into memory.
        @param decimated_data_num Number of decimated data. It must not be higher than the ADC buffer size.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        check(self.lib.rp_AcqSetTriggerDelay(ct.c_int32(decimated_data_num)))
    def AcqGetTriggerDelay(self):
        """
        Returns current number of decimated data after trigger written into memory.
        @param decimated_data_num Number of decimated data.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        decimated_data_num = ct.c_int32()
        check(self.lib.rp_AcqGetTriggerDelay(ct.byref(decimated_data_num)))
        return decimated_data_num.value
    def AcqSetTriggerDelayNs(self,time_ns):
        """
        Sets the amount of decimated data in nanoseconds after trigger written into memory.
        @param time_ns Time in nanoseconds. Number of ADC samples within the specified
        time must not be higher than the ADC buffer size.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        check(self.lib.rp_AcqSetTriggerDelayNs(ct.c_int64(time_ns)))
    def AcqGetTriggerDelayNs(self):
        """
        Returns the current amount of decimated data in nanoseconds after trigger written into memory.
        @param time_ns Time in nanoseconds.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        time_ns = ct.c_int64()
        check(self.lib.rp_AcqGetTriggerDelayNs(ct.byref(time_ns)))
        return time_ns.value
    def AcqGetPreTriggerCounter(self):
        """
        Returns the number of valid data ponts before trigger.
        @param time_ns number of data points.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        value = ct.c_uint32()
        check(self.lib.rp_AcqGetPreTriggerCounter(ct.byref(value)))
        return value.value
    def AcqSetTriggerLevel(self,channel,voltage):
        """
        Sets the trigger threshold value in volts. Makes the trigger when ADC value crosses this value.
        @param voltage Threshold value for the channel
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        check(self.lib.rp_AcqSetTriggerLevel(ct.c_uint32(channel),ct.c_float(voltage)))
    def AcqGetTriggerLevel(self):
        """
        Gets currently set trigger threshold value in volts
        @param voltage Current threshold value for the channel
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        voltage = ct.c_float()
        check(self.lib.rp_AcqGetTriggerLevel(ct.byref(voltage)))
        return voltage.value
    def AcqSetTriggerHyst(self,voltage):
        """
        Sets the trigger threshold hysteresis value in volts.
        Value must be outside to enable the trigger again.
        @param voltage Threshold hysteresis value for the channel
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        check(self.lib.rp_AcqSetTriggerHyst(ct.c_float(voltage)))
    def AcqGetTriggerHyst(self):
        """
        Gets currently set trigger threshold hysteresis value in volts
        @param voltage Current threshold hysteresis value for the channel
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        voltage = ct.c_float()
        check(self.lib.rp_AcqGetTriggerHyst(ct.byref(voltage)))
        return voltage.value
    def AcqSetGain(self,channel,state):
        """
        Sets the acquire gain state. The gain should be set to the same value as it is set on the Red Pitaya
        hardware by the LV/HV gain jumpers. LV = 1V; HV = 20V.
        @param channel Channel A or B
        @param state High or Low state
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        check(self.lib.rp_AcqSetGain(ct.c_uint32(channel),ct.c_uint32(state)))
    def AcqGetGain(self,channel):
        """
        Returns the currently set acquire gain state in the library. It may not be set to the same value as
        it is set on the Red Pitaya hardware by the LV/HV gain jumpers. LV = 1V; HV = 20V.
        @param channel Channel A or B
        @param state Currently set High or Low state in the library.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        state = ct.c_uint32()
        check(self.lib.rp_AcqGetGain(ct.c_uint32(channel),ct.byref(state)))
        return state.value
    def AcqGetGainV(self,channel):
        """
        Returns the currently set acquire gain in the library. It may not be set to the same value as
        it is set on the Red Pitaya hardware by the LV/HV gain jumpers. Returns value in Volts.
        @param channel Channel A or B
        @param voltage Currently set gain in the library. 1.0 or 20.0 Volts
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        voltage = ct.c_float()
        check(self.lib.rp_AcqGetGainV(ct.c_uint32(channel),ct.byref(voltage)))
        return voltage.value
    def AcqGetWritePointer(self):
        """
        Returns current position of ADC write pointer.
        @param pos Write pointer position
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        pos = ct.c_uint32()
        check(self.lib.rp_AcqGetWritePointer(ct.byref(pos)))
        return pos.value
    def AcqGetWritePointerAtTrig(self):
        """
        Returns position of ADC write pointer at time when trigger arrived.
        @param pos Write pointer position
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        pos = ct.c_uint32()
        check(self.lib.rp_AcqGetWritePointerAtTrig(ct.byref(pos)))
        return pos.value
    def AcqStart(self):
        """
        Starts the acquire. Signals coming from the input channels are acquired and written into memory.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        check(self.lib.rp_AcqStart())
    def AcqStop(self):
        """
        Stops the acquire.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        check(self.lib.rp_AcqStop())
    def AcqReset(self):
        """
        Resets the acquire writing state machine.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        check(self.lib.rp_AcqReset())
    def AcqGetNormalizedDataPos(self,pos):
        """
        Normalizes the ADC buffer position. Returns the modulo operation of ADC buffer size...
        @param pos position to be normalized
        @return Normalized position (pos % ADC_BUFFER_SIZE)
        """
        return self.lib.rp_AcqGetNormalizedDataPos(ct.c_uint32(pos))
    def AcqGetDataPosRaw(self,channel,start_pos,end_pos):
        """
        Returns the ADC buffer in raw units from start to end position.
        @param channel Channel A or B for which we want to retrieve the ADC buffer.
        @param start_pos Starting position of the ADC buffer to retrieve.
        @param end_pos Ending position of the ADC buffer to retrieve.
        @param buffer The output buffer gets filled with the selected part of the ADC buffer.
        @param buffer_size Length of input buffer. Returns length of filled buffer. In case of too small buffer, required size is returned.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        size   = end_pos-start_pos+1
        csize = ct.c_uint32(size)
        buff = (ct.c_int16*size)()
        check(self.lib.rp_AcqGetDataPosRaw(ct.c_uint32(channel),ct.c_uint32(start_pos),ct.c_uint32(end_pos),buff,ct.byref(csize)))
        return list(buff)
    def AcqGetDataPosV(self,channel,start_pos,end_pos):
        """
        Returns the ADC buffer in Volt units from start to end position.
        @param channel Channel A or B for which we want to retrieve the ADC buffer.
        @param start_pos Starting position of the ADC buffer to retrieve.
        @param end_pos Ending position of the ADC buffer to retrieve.
        @param buffer The output buffer gets filled with the selected part of the ADC buffer.
        @param buffer_size Length of input buffer. Returns length of filled buffer. In case of too small buffer, required size is returned.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        size   = end_pos-start_pos+1
        csize = ct.c_uint32(size)
        buff = (ct.c_float*size)()
        check(self.lib.rp_AcqGetDataPosV(ct.c_uint32(channel),ct.c_uint32(start_pos),ct.c_uint32(end_pos),buff,ct.byref(csize)))
        return list(buff)
    def AcqGetDataRaw(self,channel,pos,size):
        """
        Returns the ADC buffer in raw units from specified position and desired size.
        Output buffer must be at least 'size' long.
        @param channel Channel A or B for which we want to retrieve the ADC buffer.
        @param pos Starting position of the ADC buffer to retrieve.
        @param size Length of the ADC buffer to retrieve. Returns length of filled buffer. In case of too small buffer, required size is returned.
        @param buffer The output buffer gets filled with the selected part of the ADC buffer.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        csize = ct.c_uint32(size)
        buff = (ct.c_int16*size)()
        check(self.lib.rp_AcqGetDataRaw(ct.c_uint32(channel),ct.c_uint32(pos),ct.byref(csize),buff))
        return list(buff)
    def AcqGetDataRawV2(self,pos,size):
        """
        Returns the ADC buffer in raw units from specified position and desired size.
        Output buffer must be at least 'size' long.
        @param pos Starting position of the ADC buffer to retrieve.
        @param size Length of the ADC buffer to retrieve. Returns length of filled buffer. In case of too small buffer, required size is returned.
        @param buffer1 The output buffer gets filled with the selected part of the ADC buffer for channel 1.
        @param buffer2 The output buffer gets filled with the selected part of the ADC buffer for channel 2.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        csize = ct.c_uint32(size)
        buf1 = (ct.c_int16*size)()
        buf2 = (ct.c_int16*size)()
        check(self.lib.rp_AcqGetDataRawV2(ct.c_uint32(pos),ct.byref(csize),buf1,buf2))
        return list(buf1),list(buf2)
    def AcqGetOldestDataRaw(self,channel,size):
        """
        Returns the ADC buffer in raw units from the oldest sample to the newest one.
        Output buffer must be at least 'size' long.
        CAUTION: Use this method only when write pointer has stopped (Trigger happened and writing stopped).
        @param channel Channel A or B for which we want to retrieve the ADC buffer.
        @param size Length of the ADC buffer to retrieve. Returns length of filled buffer. In case of too small buffer, required size is returned.
        @param buffer The output buffer gets filled with the selected part of the ADC buffer.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        csize = ct.c_uint32(size)
        buff = (ct.c_int16*size)()
        check(self.lib.rp_AcqGetOldestDataRaw(ct.c_uint32(channel),ct.byref(csize),buff))
        return list(buff)
    def AcqGetLatestDataRaw(self,channel,size):
        """
        Returns the latest ADC buffer samples in raw units.
        Output buffer must be at least 'size' long.
        @param channel Channel A or B for which we want to retrieve the ADC buffer.
        @param size Length of the ADC buffer to retrieve. Returns length of filled buffer. In case of too small buffer, required size is returned.
        @param buffer The output buffer gets filled with the selected part of the ADC buffer.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        csize = ct.c_uint32(size)
        buff  = (ct.c_int16*size)()
        check(self.lib.rp_AcqGetLatestDataRaw(ct.c_uint32(channel),ct.byref(csize),buff))
        return list(buff)
    def AcqGetDataV(self,channel,pos,size):
        """
        Returns the ADC buffer in Volt units from specified position and desired size.
        Output buffer must be at least 'size' long.
        @param channel Channel A or B for which we want to retrieve the ADC buffer.
        @param pos Starting position of the ADC buffer to retrieve
        @param size Length of the ADC buffer to retrieve. Returns length of filled buffer. In case of too small buffer, required size is returned.
        @param buffer The output buffer gets filled with the selected part of the ADC buffer.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        csize = ct.c_uint32(size)
        buff  = (ct.c_float*size)()
        check(self.lib.rp_AcqGetDataV(ct.c_uint32(channel),ct.c_uint32(pos),ct.byref(csize),buff))
        return list(buff)
    def AcqGetDataV2(self,pos,size):
        """
        Returns the ADC buffer in Volt units from specified position and desired size.
        Output buffer must be at least 'size' long.
        @param pos Starting position of the ADC buffer to retrieve
        @param size Length of the ADC buffer to retrieve. Returns length of filled buffer. In case of too small buffer, required size is returned.
        @param buffer1 The output buffer gets filled with the selected part of the ADC buffer for channel 1.
        @param buffer2 The output buffer gets filled with the selected part of the ADC buffer for channel 2.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        csize = ct.c_uint32(size)
        buf1  = (ct.c_float*size)()
        buf2  = (ct.c_float*size)()
        check(self.lib.rp_AcqGetDataV2(ct.c_uint32(pos),ct.byref(csize),buf1,buf2))
        return list(buf1),list(buf2)
    def AcqGetOldestDataV(self,channel,size):
        """
        Returns the ADC buffer in Volt units from the oldest sample to the newest one.
        Output buffer must be at least 'size' long.
        CAUTION: Use this method only when write pointer has stopped (Trigger happened and writing stopped).
        @param channel Channel A or B for which we want to retrieve the ADC buffer.
        @param size Length of the ADC buffer to retrieve. Returns length of filled buffer. In case of too small buffer, required size is returned.
        @param buffer The output buffer gets filled with the selected part of the ADC buffer.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        csize = ct.c_uint32(size)
        buff  = (ct.c_float*size)()
        check(self.lib.rp_AcqGetOldestDataV(ct.c_uint32(channel),ct.byref(csize),ct.byref(buff)))
        return list(buff)
    def AcqGetLatestDataV(self,channel,size):
        """
        Returns the latest ADC buffer samples in Volt units.
        Output buffer must be at least 'size' long.
        @param channel Channel A or B for which we want to retrieve the ADC buffer.
        @param size Length of the ADC buffer to retrieve. Returns length of filled buffer. In case of too small buffer, required size is returned.
        @param buffer The output buffer gets filled with the selected part of the ADC buffer.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        csize = ct.c_uint32(size)
        buff  = (ct.c_float*size)()
        check(self.lib.rp_AcqGetLatestDataV(ct.c_uint32(channel),ct.byref(csize),ct.byref(buff)))
        return list(buff)
    def AcqGetBufSize(self):
        size = ct.c_uint32()
        check(self.lib.rp_AcqGetBufSize(ct.byref(size)))
        return size.value
    def GenReset(self):
        """
        Sets generate to default values.
        """
        check(self.lib.rp_GenReset())
    def GenOutEnable(self,channel):
        """
        Enables output
        @param channel Channel A or B which we want to enable
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        check(self.lib.rp_GenOutEnable(ct.c_uint32(channel)))
    def GenOutDisable(self,channel):
        """
        Disables output
        @param channel Channel A or B which we want to disable
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        check(self.lib.rp_GenOutDisable(ct.c_uint32(channel)))
    def GenOutIsEnabled(self,channel):
        """
        Gets value true if channel is enabled otherwise return false.
        @param channel Channel A or B.
        @param value Pointer where value will be returned
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        value = ct.c_bool()
        check(self.lib.rp_GenOutIsEnabled(ct.c_uint32(channel),ct.byref(value)))
        return value.value
    def GenAmp(self,channel,amplitude):
        """
        Sets channel signal peak to peak amplitude.
        @param channel Channel A or B for witch we want to set amplitude
        @param amplitude Amplitude of the generated signal. From 0 to max value. Max amplitude is 1
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        check(self.lib.rp_GenAmp(ct.c_uint32(channel),ct.c_float(amplitude)))
    def GenGetAmp(self,channel):
        """
        Gets channel signal peak to peak amplitude.
        @param channel Channel A or B for witch we want to get amplitude.
        @param amplitude Pointer where value will be returned.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        amplitude = ct.c_float()
        check(self.lib.rp_GenGetAmp(ct.c_uint32(channel),ct.byref(amplitude)))
        return amplitude.value
    def GenOffset(self,channel,offset):
        """
        Sets DC offset of the signal. signal = signal + DC_offset.
        @param channel Channel A or B for witch we want to set DC offset.
        @param offset DC offset of the generated signal. Max offset is 2.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        check(self.lib.rp_GenOffset(ct.c_uint32(channel),ct.c_float(offset)))
    def GenGetOffset(self,channel):
        """
        Gets DC offset of the signal.
        @param channel Channel A or B for witch we want to get amplitude.
        @param offset Pointer where value will be returned.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        offset = ct.c_float()
        check(self.lib.rp_GenGetOffset(ct.c_uint32(channel),ct.byref(offset)))
        return offset.value
    def GenFreq(self,channel,frequency):
        """
        Sets channel signal frequency.
        @param channel Channel A or B for witch we want to set frequency.
        @param frequency Frequency of the generated signal in Hz.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        check(self.lib.rp_GenFreq(ct.c_uint32(channel),ct.c_float(frequency)))
    def GenGetFreq(self,channel):
        """
        Gets channel signal frequency.
        @param channel Channel A or B for witch we want to get frequency.
        @param frequency Pointer where value will be returned.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        frequency = ct.c_float()
        check(self.lib.rp_GenGetFreq(ct.c_uint32(channel),ct.byref(frequency)))
        return frequency.value
    def GenPhase(self,channel,phase):
        """
        Sets channel signal phase. This shifts the signal in time.
        @param channel Channel A or B for witch we want to set phase.
        @param phase Phase in degrees of the generated signal. From 0 deg to 180 deg.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        check(self.lib.rp_GenPhase(ct.c_uint32(channel),ct.c_float(phase)))
    def GenGetPhase(self,channel):
        """
        Gets channel signal phase.
        @param channel Channel A or B for witch we want to get phase.
        @param phase Pointer where value will be returned.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        phase = ct.c_float()
        check(self.lib.rp_GenGetPhase(ct.c_uint32(channel),ct.byref(phase)))
        return phase.value
    def GenWaveform(self,channel,type):
        """
        Sets channel signal waveform. This determines how the signal looks.
        @param channel Channel A or B for witch we want to set waveform type.
        @param form Wave form of the generated signal [SINE, SQUARE, TRIANGLE, SAWTOOTH, PWM, DC, ARBITRARY].
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        check(self.lib.rp_GenWaveform(ct.c_uint32(channel),ct.c_uint32(type)))
    def GenGetWaveform(self,channel):
        """
        Gets channel signal waveform.
        @param channel Channel A or B for witch we want to get waveform.
        @param type Pointer where value will be returned.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        type = ct.c_uint32()
        check(self.lib.rp_GenGetWaveform(ct.c_uint32(channel),ct.byref(type)))
        return type.value
    def GenArbWaveform(self,channel,length):
        """
        Sets user defined waveform.
        @param channel Channel A or B for witch we want to set waveform.
        @param waveform Use defined wave form, where min is -1V an max is 1V.
        @param length Length of waveform.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        waveform = ct.c_float()
        check(self.lib.rp_GenArbWaveform(ct.c_uint32(channel),ct.byref(waveform),ct.c_uint32(length)))
        return waveform.value
    def GenGetArbWaveform(self,channel):
        """
        Gets user defined waveform.
        @param channel Channel A or B for witch we want to get waveform.
        @param waveform Pointer where waveform will be returned.
        @param length Pointer where waveform length will be returned.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        waveform = ct.c_float()
        length = ct.c_uint32()
        check(self.lib.rp_GenGetArbWaveform(ct.c_uint32(channel),ct.byref(waveform),ct.byref(length)))
        return waveform.value,length.value
    def GenDutyCycle(self,channel,ratio):
        """
        Sets duty cycle of PWM signal.
        @param channel Channel A or B for witch we want to set duty cycle.
        @param ratio Ratio betwen the time when signal in HIGH vs the time when signal is LOW.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        check(self.lib.rp_GenDutyCycle(ct.c_uint32(channel),ct.c_float(ratio)))
    def GenGetDutyCycle(self,channel):
        """
        Gets duty cycle of PWM signal.
        @param channel Channel A or B for witch we want to get duty cycle.
        @param ratio Pointer where value will be returned.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        ratio = ct.c_float()
        check(self.lib.rp_GenGetDutyCycle(ct.c_uint32(channel),ct.byref(ratio)))
        return ratio.value
    def GenMode(self,channel,mode):
        """
        Sets generation mode.
        @param channel Channel A or B for witch we want to set generation mode.
        @param mode Type of signal generation (CONTINUOUS, BURST, STREAM).
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        check(self.lib.rp_GenMode(ct.c_uint32(channel),ct.c_uint32(mode)))
    def GenGetMode(self,channel):
        """
        Gets generation mode.
        @param channel Channel A or B for witch we want to get generation mode.
        @param mode Pointer where value will be returned.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        mode = ct.c_uint32()
        check(self.lib.rp_GenGetMode(ct.c_uint32(channel),ct.byref(mode)))
        return mode.value
    def GenBurstCount(self,channel,num):
        """
        Sets number of generated waveforms in a burst.
        @param channel Channel A or B for witch we want to set number of generated waveforms in a burst.
        @param num Number of generated waveforms. If -1 a continuous signal will be generated.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        check(self.lib.rp_GenBurstCount(ct.c_uint32(channel),ct.c_int(num)))
    def GenGetBurstCount(self,channel):
        """
        Gets number of generated waveforms in a burst.
        @param channel Channel A or B for witch we want to get number of generated waveforms in a burst.
        @param num Pointer where value will be returned.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        num = ct.c_int()
        check(self.lib.rp_GenGetBurstCount(ct.c_uint32(channel),ct.byref(num)))
        return num.value
    def GenBurstRepetitions(self,channel,repetitions):
        """
        Sets number of burst repetitions. This determines how many bursts will be generated.
        @param channel Channel A or B for witch we want to set number of burst repetitions.
        @param repetitions Number of generated bursts. If -1, infinite bursts will be generated.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        check(self.lib.rp_GenBurstRepetitions(ct.c_uint32(channel),ct.c_int(repetitions)))
    def GenGetBurstRepetitions(self,channel):
        """
        Gets number of burst repetitions.
        @param channel Channel A or B for witch we want to get number of burst repetitions.
        @param repetitions Pointer where value will be returned.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        repetitions = ct.c_int()
        check(self.lib.rp_GenGetBurstRepetitions(ct.c_uint32(channel),ct.byref(repetitions)))
        return repetitions.value
    def GenBurstPeriod(self,channel,period):
        """
        Sets the time/period of one burst in micro seconds. Period must be equal or greater then the time of one burst.
        If it is greater than the difference will be the delay between two consequential bursts.
        @param channel Channel A or B for witch we want to set burst period.
        @param period Time in micro seconds.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        check(self.lib.rp_GenBurstPeriod(ct.c_uint32(channel),ct.c_uint32(period)))
    def GenGetBurstPeriod(self,channel):
        """
        Gets the period of one burst in micro seconds.
        @param channel Channel A or B for witch we want to get burst period.
        @param period Pointer where value will be returned.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        period = ct.c_uint32()
        check(self.lib.rp_GenGetBurstPeriod(ct.c_uint32(channel),ct.byref(period)))
        return period.value
    def GenTriggerSource(self,channel,src):
        """
        Sets trigger source.
        @param channel Channel A or B for witch we want to set trigger source.
        @param src Trigger source (INTERNAL, EXTERNAL_PE, EXTERNAL_NE, GATED_BURST).
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        check(self.lib.rp_GenTriggerSource(ct.c_uint32(channel),ct.c_uint32(src)))
    def GenGetTriggerSource(self,channel):
        """
        Gets trigger source.
        @param channel Channel A or B for witch we want to get burst period.
        @param src Pointer where value will be returned.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        src = ct.c_uint32()
        check(self.lib.rp_GenGetTriggerSource(ct.c_uint32(channel),ct.byref(src)))
        return src.value
    def GenTrigger(self,channel):
        """
        Sets Trigger for specified channel/channels.
        @param mask Mask determines channel: 1->ch1, 2->ch2, 3->ch1&ch2.
        @return If the function is successful, the return value is RP_OK.
        If the function is unsuccessful, the return value is any of RP_E* values that indicate an error.
        """
        check(self.lib.rp_GenTrigger(ct.c_uint32(channel)))
    def CmnCnvCntToV(self,field_len, cnts, adc_max_v, calibScale, calib_dc_off, user_dc_off):
        return self.lib.rp_CmnCnvCntToV(ct.c_uint32(field_len),ct.c_uint32(cnts),ct.c_float(adc_max_v),ct.c_uint32(calibScale),ct.c_int32(calib_dc_off),ct.c_float(user_dc_off))
