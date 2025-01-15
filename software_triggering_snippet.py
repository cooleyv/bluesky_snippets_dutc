import logging 
logger = logging.getLogger(__name__)
logger.info(__file__)

from bluesky import plan_stubs as bps
from bluesky import plans as bp
from bluesky import utils as butl
from bluesky.utils import Msg
from bluesky import preprocessors as bpp
from bluesky import plan_patterns
from ophyd import Signal, Device, Component


#import auxiliary plans
from .auxiliary_ad import *
from .auxiliary_scan import *
from .s1id_metadata import *
from .s1id_positions import *
from .s1id_beam_delivery import *
from .s1id_FPGAcontrols import *

#import devices
from ..devices.s1id_slits import *
from ..devices.suspenders import sus_mA, rsync_tally
from ..devices.s1id_scalers import *
from ..devices.global_variables import *
from ..devices.s1id_shutters import shutter_c
from ..devices.ad_dictionaries import *

#import other stuff
import os
import sys
import inspect
from itertools import chain, zip_longest
from functools import partial
from toolz import partition
import numpy as np
import time
import datetime
from collections import defaultdict
import collections
import matplotlib.pyplot as plt

# suspenders suspend a plan if a criterion is met
SUSPENDERS = [sus_mA,]  #suspend if SR current falls below threshold


## Exposure without motors ------------------------------------------

def expose(
    #area detector ops --------------
    det = None, 
    use_proc_avg = False, 
    N_avg = 1, 
    exposure_time = 0.1, 
    nframes = 1, 
    nbrights = 0, 
    ndarks = 0, 

    #scalers -----------------------
    scalers = [],   #include scaler1, scaler1E

    #physical setup -----------------
    sample_in = '',
    slits_config = '',
    settle_time = 0.5, 

    #AD file saving -----------------
    file_name = "new_file",
    folder_name = None, 

    #run control -------------------
    md = None, 

    #for development -------------
    keep_open = False
    ):
    
    """ Take an exposure with area detector and save files to tiff or h5. """ 
        
    #if no area det given, choose default 
    det = choose_default_det(det)
    if type(scalers) != list: scalers = list(scalers)
    detectors = [det] + scalers
    #prescan checks
    yield from prescan_checks(dets = [det])

    #add a junk frame if detector requires
    # nframes, nbrights, ndarks = add_junk_frame(det, nframes, nbrights, ndarks)
    
    #get first frame number
    first_frame = det.hdf1.file_number.get()

    #plan-specific metadata
    plan_md = {
           'detectors': [det.name for det in detectors],
           'plan_args': {},
           'plan_name': 'expose',
           'first_frame_num' : first_frame,
           'hints': {},
           'bcs_md' : fetch_bcs_md(),
           }
    plan_md.update(md or {})

    @bpp.stage_decorator(detectors)
    @bpp.run_decorator(md = plan_md)
    def inner_expose():

        #print first frame info (for copy-paste)
        print(f'\n \n Your next h5 file will be {first_frame}. \n')

        #set up proc filter if desired
        if use_proc_avg:
            yield from proc_averaging(det, N_avg)
            #TODO: turn on filter here, use for brights and darks anyway

        #set up internal triggering and set exposure/acquire time 
        try: 
            yield from det.internal_config(exposure_time)
        except AttributeError:
            print(f'No internal config found for {det.name}. Trying the usual PVs.')
            yield from bps.mv(det.cam.trigger_mode, 'Internal', 
                            det.cam.image_mode, 'Multiple',
                            det.cam.acquire_time, exposure_time)
        
        #select channels of interest 
        scaler1.select_channels(SCALER1_CHANNELS)
        scaler1E.select_channels(SCALER1E_CHANNELS)

        #set scaler count times
        if scaler1 in scalers:
            yield from bps.mv(scaler1.preset_time, exposure_time)
        if scaler1E in scalers:
            yield from bps.mv(scaler1E.preset_time, exposure_time)

        #TODO: check lights

        #move to start config (shields and dets, not necessarily sample)
        try:
            yield from switch_to(sample_in)
        except KeyError:
            print('WARNING! Did not find a sample_in configuration.'
                'Will not move any motors.')

        #move slits to position 
        try:
            yield from switch_to(slits_config)
        except KeyError:
            print('WARNING! Did not find a slits_config configuration.'
                'Will not move any motors.')
            
        # Set up folder to save in, if desired
        #NOTE: ONLY TIFFS ARE SAVED IN FOLDER FOR NOW!! Rsync won't see these for now
        if folder_name is not None: 
            yield from folder_prep(det, folder_name)

        #calculate _nframes to put into filewriter (brights and darks considered below)
        _nframes = int(nframes * inner.nsteps.get() / N_avg)

        #sets up tiff and hdf file name, filewriter num_images 
        #FIXME: nrights and ndarks if proc on 
        yield from save_prep(det, _nframes, nbrights, ndarks, file_name)

        #check number of rsync processes running and pause if there are too many
        yield from count_rsyncs()
        while rsync_tally.get() >= 6:
            
            print('Too many rsync processes running. '
                '\n Sleeping until some processes finish.')
            
            yield from bps.sleep(30)

            yield from count_rsyncs()   
        
        #collect brights  
        if nbrights > 0:        
            yield from collect_brights(det, nbrights, exposure_time, scalers = scalers)

        #collect darks
        if ndarks > 0: 
            yield from collect_darks(det, ndarks, exposure_time, scalers = scalers)

        if nframes > 0:   
            #change to data and set number of frames for data
            yield from exchange_data(det = det)
            yield from bps.mv(det.cam.num_images, nframes)

            #set FS control to detExp - overruled if keep_open is True
            yield from set_detExp_control(det = det)

            #press capture if not already done
            yield from write_if_new(det.hdf1.capture, 1)
            if det.tiff1.enable.get(as_string = True) == "Enable":
                yield from write_if_new(det.tiff1.capture, 1)

            #make sure shutter is open
            shutter_c.open()
            
            #if using keep_open, ignores detExp control
            if keep_open:
                yield from fs_open()

            #trigger and read
            yield from acquire_wait(det, nframes, scalers)
            
            #if using keep_open, make sure to close fast shutter at the end
            if keep_open:
                yield from fs_close()

        #wait for filewriter to finish writing 
        yield from wait_for_filewriter(det.hdf1, verbose = False)

        #start rsync for this file
        yield from rsync_kickoff(det, file_name)

        print(f"Acquisition complete.")

        #depending on which filewriter was used, print the last file number
        if det.hdf1.enable.get() == "Enable":  
            print(f'The last h5 file written was {det.hdf1.file_number.get() - 1}.')
        if det.tiff1.enable.get() == "Enable": 
            print(f'The last tiff file written was {det.tiff1.file_number.get() - 1}.')
        try: 
            if det.edf1.enable.get() == "Enable": 
                print(f'The last edf file written was {det.edf1.file_number.get() - 1}.')
        except AttributeError:
            pass

        #close current plots
        plt.close('all')

    return(yield from inner_expose())