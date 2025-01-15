"""
Users routinely need to change beamline configuration to use complementary methods
in one experiment. This includes move detectors and samples in/out of the beam, opening/
closing slit blades, and changing position in foil/attenuator wheels. 

This file contains dictionaries defining instrument configurations and plans for 
switching between them.  

"""

__all__ = [
    "POSITIONS",
    "move",
    "configs",  #signal, not dict
    "add_config", 
    "change_order", 
    "capture_config", 
    "store_configs", 
    "restore_configs",
    "delete_motor", 
    "delete_config", 
    "switch_to",
    "zero_motor", 
    # "zero_slits", 
    "check_slits",

    "enable_motor",
    "disable_motor",   
]

import logging
logger = logging.getLogger(__name__)
logger.info(__file__)

import bluesky.plan_stubs as bps
from bluesky.utils import ProgressBarManager
pbar_manager = ProgressBarManager()
from toolz import partition
from ophyd import Signal

from ..framework import oregistry

# import motors from sector 1 experimental hutches
from ..devices.s1idb_motors import *
from ..devices.s1idc_motors import *
from ..devices.s1ide_motors import *
from ..devices.s1id_slits   import *

#shortcuts for foil wheel dataframe
air_pos = FOILS.loc[FOILS.Element == 'Air', 'Pos'].values[0]
Au_pos  = FOILS.loc[FOILS.Element == 'Au',  'Pos'].values[0]
Yb_pos  = FOILS.loc[FOILS.Element == 'Yb',  'Pos'].values[0]
Bi_pos  = FOILS.loc[FOILS.Element == 'Bi',  'Pos'].values[0]
Tb_pos  = FOILS.loc[FOILS.Element == 'Tb',  'Pos'].values[0]
Hf_pos  = FOILS.loc[FOILS.Element == 'Hf',  'Pos'].values[0]
Re_pos  = FOILS.loc[FOILS.Element == 'Re',  'Pos'].values[0]
Pb_pos  = FOILS.loc[FOILS.Element == 'Pb',  'Pos'].values[0]
Ho_pos  = FOILS.loc[FOILS.Element == 'Ho',  'Pos'].values[0]
Ir_pos  = FOILS.loc[FOILS.Element == 'Ir',  'Pos'].values[0]
Pt_pos  = FOILS.loc[FOILS.Element == 'Pt',  'Pos'].values[0]
Tm_pos  = FOILS.loc[FOILS.Element == 'Tm',  'Pos'].values[0]
Ta_pos  = FOILS.loc[FOILS.Element == 'Ta',  'Pos'].values[0]


#define all motor classes that we use 
motor_classes = ["MPEMotor",     #most motors    
                 "AMCIMotor",    #anything on AMCI crate
                 "PVPositionerSoftDone",    #slit ensembles
                 "EpicsSignal",  #intended for global variables; won't work for RBV
                 "ConicalMotor", #conical hexapod motors
                 #"S1IDShutter",  #PSS shutters
                 ]

#POSITIONS are intended to remain static between experiments
# value of position will not get updated during ipython session 
# (whatever is imported into the ipython session stays)
POSITIONS = {
    cork.name      : {'in' : 100, 'out' : 120},
    shield.name    : {'in' : 0,   'out' : 220},
    tomoEus.x.name : {'in' : 0,   'out' : 220},
    tomoC.x.name   : {'in' : 0,   'out' : -200}, 
    foil.name      : {'air': air_pos,
                      'Au' : Au_pos,
                      'Yb' : Yb_pos, 
                      'Bi' : Bi_pos, 
                      'Tb' : Tb_pos,
                      'Hf' : Hf_pos, 
                      'Re' : Re_pos,
                      'Pb' : Pb_pos,
                      'Ho' : Ho_pos,
                      'Ir' : Ir_pos, 
                      'Pt' : Pt_pos, 
                      'Tm' : Tm_pos, 
                      'Ta' : Ta_pos},
    attenB.name    : {'out' : 0},

}

def move(*args):

    """Shorthand for moving a single motor. Option to call from `POSITIONS`.
    
    Example usage:
    
    RE(move(cork, 'out'))
    RE(move(samC.y, 10))
    RE(move(foil, 'air'))
    
    """

    #check that each motor has a position 
    if len(args) % 2 != 0: 
        raise ValueError('Each motor must contain a position to move to.')

    for motor, position in partition(2, args):
        #check that motor is an object; if not, choose object from registry
        if motor.__class__.__name__ == 'str':
            motor = oregistry[motor]
        if motor.__class__.__name__ not in motor_classes:
            raise TypeError(f'Motor not recognized as moveable object.'
                            f'\n Received class {motor.__class__.__name__}.')

        #if motor is MPEMotor class, it has an enable status
        if motor.__class__.__name__ == "MPEMotor":
            #check that motors are enabled 
            if motor.disable.get() == 1:
                raise ValueError(f'{motor.name} is not enabled!')

        #check whether the position is a number or string
        if type(position) == str: 
            position = POSITIONS[motor.name][position]
        elif type(position) not in [int, float]: 
            raise TypeError(f'Position type not recognized. Received {type(position)}.')

        #if motor is in classes based on MPEMotor, check limits
        if motor.__class__.__name__ in ["MPEMotor", "AMCIMotor", "ConicalMotor"]:
            #check limits 
            if position > motor.high_limit_travel.get() or position < motor.low_limit_travel.get():
                raise ValueError(f'Position requested for {motor.name} is out of limits.'
                                f'\n Received request to move to {position}.')

        #move to those positions one at a time
        yield from bps.mv(motor, position)



#configs are intended to change throughout an experiment, but we can initialize common ones here
CONFIGS_INIT = {
    'tomoE' : {
        'tomoEus_x' : POSITIONS['tomoEus_x']['in'], 
        'shield'    : POSITIONS['shield']['in'], 
    },

    'tomoC' : {
        'tomoC_x'   : POSITIONS['tomoC_x']['in']
    },

    'scatteringE': {
        'tomoEus_x' : POSITIONS['tomoEus_x']['out'],
        'shield'    : POSITIONS['shield']['out'],
    },

    'scatteringC' : {
        'tomoC_x'   : POSITIONS['tomoC_x']['out']
    },

    'bright':{},
    'sample_in':{},
}

#to make use of changes to configs in plans, need a signal
configs = Signal(name = "configs", value = CONFIGS_INIT)

def add_config(new_dict, new_name, overwrite = True):

    """ Add a new config or modify an existing one. """

    CONFIGS = configs.get()
    formatted_dict = {}

    #format new_dict to display motor names, not objects
    for motor, position in new_dict.items():

        #check that position is a float 
        if type(position) not in [float, int]: raise TypeError(f'Position must be a float or int. Received {position} for key {motor}.')

        #if object is given, change key to motor name
        if motor.__class__.__name__ in ['MPEMotor',"AMCIMotor", "PVPositionerSoftDone", "ApsPssShutterWithStatus", "EpicsSignal"]:
            formatted_dict[motor.name] = position
        #if string is given, leave key as is
        elif motor.__class__.__name__ == 'str':
            formatted_dict[motor] = position
        #raise error for anything else:
        else: raise TypeError(f'Motor must be an object or string. Received {motor}..')

    #check whether new_name already taken
    if new_name in CONFIGS.keys():
        print(f'New configuration for {new_name} already in `CONFIGS`.'
              f'Overwrite status is {overwrite}.')

        if overwrite:
            #overwrite and merge dictionaries together
            CONFIGS[new_name] = {**CONFIGS[new_name], **formatted_dict}
        
        else:
            #merge but do not overwrite the original 
            for key, value in formatted_dict.items(): 
                if key not in CONFIGS[new_name]:
                    CONFIGS[new_name][key] = value  

    #add it if it doesn't exist in config dictionary 
    else:
        print('New configuration not found in `CONFIGS`. Adding now.')

        CONFIGS[new_name] = formatted_dict
    
    print(f'Configuration {new_name} is now {CONFIGS[new_name]}.')

    #change configs signal to match updated CONFIGS dictionary
    yield from bps.mv(configs, CONFIGS)

def change_order(new_order, config_name):

    """ Change the order in which motors are moved in a config. 
    
    `new_order` must be a list. """

    CONFIGS = configs.get()
    ordered_config = {}

    #check that new_order is a list
    if type(new_order) != list: 
        raise TypeError(f'`new_order` must be a list. Received {type(new_order)}.')

    #check that name is a config that already exists
    if config_name not in CONFIGS.keys(): 
        raise ValueError(f'Received unknown config name {config_name}.'
                         f'Please choose from {CONFIGS.keys()}.')

    #check that all the motors are included
    if len(new_order) != len(CONFIGS[config_name]): 
        raise ValueError(f'Not all motors are included.'
                         f'Expected {len(CONFIGS[config_name])} motors, received {len(new_order)}.')

    #check that list only contains keys already existing 
    for motor in new_order:

        #objects and strings accepted, so make sure they are all strings
        if motor.__class__.__name__ in ['MPEMotor', "AMCIMotor","PVPositionerSoftDone", "ApsPssShutterWithStatus", "EpicsSignal"]:
            motor = motor.name

        elif motor.__class__.__name__ != 'str': 
            raise TypeError(f'Motor must be an object or string. Received {motor}, {type(motor)}.')

        #now compare to existing keys
        if motor not in CONFIGS[config_name].keys(): 
            raise ValueError('Received unexpected motor.'
                             'Use `add_config()` to add motors first.')
        
        #create a temp dictionary that is ordered correctly
        ordered_config[motor] = CONFIGS[config_name][motor]
    
    #delete and replace using temp dictionary (.update does not work)
    del CONFIGS[config_name]
    CONFIGS[config_name] = ordered_config

    #check output
    print(f'Configuration {config_name} is now {CONFIGS[config_name]}.')

    #update configs signal with new CONFIGS dictionary
    yield from bps.mv(configs, CONFIGS)

def capture_config(config_name, device = None, motor = None, overwrite = True):

    """ Capture current position of device or single motor and add
    it to configuration. Will be added at the end of configuration. """

    #make sure motor or device is specified
    if device is None and motor is None:
        raise ValueError('Must specify a device or a motor.')

    #make sure only one is specified
    if device is not None and motor is not None:
        raise ValueError('Must specify device OR a single motor, not both.')

    #initialize motors list
    motors = []

    #if device is specified, find all the motors associated
    if device is not None: 
        #get all motors
        for motor in device.hints['fields']:
            if oregistry[motor].__class__.__name__ in motor_classes:
                motors.append(oregistry[motor])
            else:
                raise TypeError(f'{motor.name} is not recognized as a motor object.'
                                f'\n Received class {motor.__class__.__name__}.')
            
    elif motor is not None: 
        if motor.__class__.__name__ in motor_classes:
            motors = [motor]
        else: 
            raise TypeError(f'{motor.name} is not recognized as a motor object.'
                            f'\n Received class {motor.__class__.__name__}.')
    

    #initialize a dictionary to hold positions
    capture_dict = {}
    for i in range(len(motors)):
        temp_mot = motors[i]
        capture_dict[temp_mot.name] = temp_mot.position

    #add capture_dict to CONFIGS (prints result at the end)
    yield from add_config(capture_dict, config_name, overwrite = overwrite)

    #add_config also updates configs signal

def delete_motor(motor, config_name):

    """Remove a motor from a configuration."""
    
    CONFIGS = configs.get()

    #make sure motor is an object or str
    if motor.__class__.__name__ == 'str':
        motor_name = motor
    
    elif motor.__class__.__name__ in ['MPEMotor',"AMCIMotor", "PVPositionerSoftDone", "ApsPssShutterWithStatus", "EpicsSignal"]: 
        motor_name = motor.name
    else:
        raise TypeError(f'{motor} is not an accepted object type. Received class {motor.__class__.__name__}.')

    del CONFIGS[config_name][motor_name]

    #update configs signal
    yield from bps.mv(configs, CONFIGS)

def delete_config(config_name):

    """Delete the entire configuration."""

    CONFIGS = configs.get()

    del CONFIGS[config_name]

    #update configs signal 
    yield from bps.mv(configs, CONFIGS)

def switch_to(config_name):

    """Move motors according to a configuration dictionary. Will move motors in dict order.
    
    TODO: error handling
    """

    #fetch CONFIGS  
    CONFIGS = configs.get()

    if config_name not in CONFIGS: 
        raise KeyError(f'config_name {config_name} not in CONFIGS.')

    #move motors one at a time
    for motor_name in CONFIGS[config_name].keys():
        
        print(f'moving {motor_name}')
        motor = oregistry[motor_name]
        
        yield from move(motor, CONFIGS[config_name][motor_name])
    

##Other plans relating to motor positions

def zero_motor(motor):

    """ Set current position of motor to 0 using set button. 
    Only sets user position, not dial. """

    #click set button 
    yield from bps.mv(motor.set_use_switch, 'Set')

    #zero out
    yield from bps.mv(motor.user_setpoint, 0)

    #click use button 
    yield from bps.mv(motor.set_use_switch, 'Use')

def check_slits(h_closed = 0.1, v_closed = 0.1, verbose = True):

    """ Check position of slits by closing one at a time.
    Requires tomo camera to be continuously acquiring before running. """

    print('Warning! Assuming tomo camera already acquiring.')

    slits = [KslitB, KslitCus, KslitCds, KslitEus, KslitEds]
    differences = {}

    for s in slits: 

        #print which slit is closing 
        print(f'Now closing {s.name}.')

        #remember original positions
        init_hsize = s.hsize.readback.get()
        init_vsize = s.vsize.readback.get()
        init_hcenter = s.hcenter.readback.get()
        init_vcenter = s.vcenter.readback.get()

        #close slits
        yield from bps.mv(
            s.hsize, h_closed, 
            s.vsize, v_closed
        )

        #pause and let user adjust as needed
        user_input = 'no'
        while user_input != 'ok':
            user_input = input('Adjust slit position now.' 
                               'Type "ok" and press Enter when ready to move next slit.')

        #record differences
        differences[s.hcenter.name] = s.hcenter.readback.get() - init_hcenter
        differences[s.vcenter.name] = s.vcenter.readback.get() - init_vcenter

        #open slits to original size
        print(f'Opening {s.name}.')
        yield from bps.mv(
            s.hsize, init_hsize,
            s.vsize, init_vsize
        )

    #print differences if desired
    if verbose:
        print(f"Slit centers moved the following amounts:"
              f"{differences}.")

def enable_motor(motor):

    """ Plan stub to enable a motor. """

    if motor.__class__.__name__ == "MPEMotor":
        yield from bps.mv(motor.disable, 0)

    else: 
        raise ValueError(f' {motor.name} does not have enable/disable PV'
                         'known to bluesky.')

def disable_motor(motor):

    """Plan stub to disable a motor. """

    if motor.__class__.__name__ == "MPEMotor":
        yield from bps.mv(motor.disable, 1)

    else: 
        raise ValueError(f' {motor.name} does not have enable/disable PV'
                         'known to bluesky.')
    
