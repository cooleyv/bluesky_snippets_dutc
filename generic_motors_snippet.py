""" 
Modify EpicsMotor for the MPE group and create a lens device. 
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

