""" 
Bluesky uses the ophyd package to communicate with motors through channel-access protocol (aka EPICS). 
Here we modify the vanilla ophyd EpicsMotor class to include additional attributes/information about our motors. 
We then use this modified class to create devices that represent (and control) physical devices in our experimental 
hutches. The example here is a stack of six motors to move a lens (x, y, z translation, roll, pitch, and yaw (tilts)).

We also developed generic devices that account for these 6 degrees of freedom. 
"""

import logging
logger = logging.getLogger(__name__)
logger.info(__file__)

from ophyd import FormattedComponent, EpicsMotor, Device, Component, EpicsSignal, EpicsSignalRO

""" 
Begin generic device definitions here.
"""

class MPEMotor(EpicsMotor):
    #used in fastsweep plans
    backlash_dist = Component(EpicsSignal, ".BDST", kind = "normal", auto_monitor = True)   #.BDST = process variable suffix 
    motor_step_size = Component(EpicsSignal, ".MRES", kind = "config")
    disable = Component(EpicsSignal, "_able.VAL", kind = "config")
    disable_readback = Component(EpicsSignalRO, "_able.RBV", kind = "omitted")
    
    #motor record PVs
    description = Component(EpicsSignal, ".DESC", kind = 'config')
    speed_rps = Component(EpicsSignal, ".S", kind = "config")  #Rev per sec
    backup_speed_rps = Component(EpicsSignal, ".SBAK", kind = 'config')  #Rev per sec
    max_speed_rps = Component(EpicsSignal, ".SMAX", kind = 'config') #Rev per sec
    base_speed_rps = Component(EpicsSignal, ".SBAS", kind = 'config')    #Rev per sec
    backup_acceleration = Component(EpicsSignal, ".BACC", kind = 'config')
    move_fraction = Component(EpicsSignal, ".FRAC", kind = 'config')
    home_speed_eps = Component(EpicsSignal, ".HVEL", kind = 'config')    #EGU per sec
    motor_res_spr = Component(EpicsSignal, ".SREV", kind = 'config') #steps per rev
    motor_res_epr = Component(EpicsSignal, ".UREV", kind = 'config') #EGU per rev
    direction = Component(EpicsSignal, ".DIR", kind = 'config')
    display_precision = Component(EpicsSignal, ".PREC", kind = 'config')

    velocity = Component(EpicsSignal, '.VELO', kind = "normal")
    # #setting or using motor
    # set_mode = Component(EpicsSignal, ".SET")   #NOT TO BE CONFUSED with `.set` method

class Lens1C(Device):
    x   = Component(MPEMotor, "m99")    #m99 = motor channel 99
    y   = Component(MPEMotor, "m100")
    z   = Component(MPEMotor, "m101")
    th  = Component(MPEMotor, "m102")
    phi = Component(MPEMotor, "m103")
    chi = Component(MPEMotor, "m104")

lens1 = Lens1C("1idc:", name = "lens1") #1idc: = input/output controller prefix for these motors

class Generic5DOFDevice(Device):
    #Generic device with 5 degrees of freedom (no motion in Z)
    
    x       = FormattedComponent(MPEMotor, "{prefix}{xpv}")
    y       = FormattedComponent(MPEMotor, "{prefix}{ypv}")
    rotx    = FormattedComponent(MPEMotor, "{prefix}{rotxpv}")
    roty    = FormattedComponent(MPEMotor, "{prefix}{rotypv}")
    rotz    = FormattedComponent(MPEMotor, "{prefix}{rotzpv}")

    def __init__(self, prefix = "", *, xpv="", ypv="",rotxpv="", rotypv="", rotzpv="", **kwargs):
        self.prefix = prefix
        self.xpv = xpv
        self.ypv = ypv
        self.rotxpv = rotxpv
        self.rotypv = rotypv
        self.rotzpv = rotzpv
        super().__init__(prefix=prefix, **kwargs)

class Generic6DOFDevice(Generic5DOFDevice):
    #Generic device with 6 degrees of freedom (includes Z)
    
    z = FormattedComponent(MPEMotor, "{prefix}{zpv}")

    def __init__(self, prefix="", *,xpv="", ypv="", zpv="", rotxpv="", rotypv="", rotzpv="",**kwargs):
        self.zpv = zpv
        super().__init__(
            prefix=prefix,
            xpv=xpv, ypv=ypv, 
            rotxpv=rotxpv, rotypv=rotypv, rotzpv=rotzpv, 
            **kwargs
        )

lens2 = Generic5DOFDevice(
    #upright
    "1ide1:", 
    name   = "lens2_e",
    xpv    = "m118",    
    ypv    = "m29",
    rotxpv = "m32",    
    rotypv = "m120",    
    rotzpv = "m33"
)
