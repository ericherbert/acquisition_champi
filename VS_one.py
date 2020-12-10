#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Jun 27 13:47:50 2019

@author: laura
"""

import os
import time

import tifffile
from PIL import Image

import Vectorisation as vc
import Superposition as sp
#import TrackNodes as tn


start = time.time()

## General parameters 

# absolute path of the experimental images stack (binarized or grayscale, not RGB/RGBA)
exp_path = '/home/eh/Nextcloud/recherche/racines/acquisition_champi/Images_test/test.tiff' 
# absolute path of the binarized images stack     
bin_path = '/home/eh/Nextcloud/recherche/racines/acquisition_champi/Images_test/test.tiff'
# absolute path of the directory where the results will be stored in
dest_path = '/home/eh/Nextcloud/recherche/racines/acquisition_champi/Images_test/out/'
unstack = False # enable to save every slice of the binarized tif stack as png
verbose = True # verbosity switch for printing progress output
debug = False # debugging switch for debugging output
invert = True # inverts the images before processing (the background pixels must be black (0))
                                   
if not os.path.exists(dest_path):
    os.mkdir(dest_path)
vect_main_params = [bin_path, dest_path, unstack, verbose, debug, invert]
sup_dest_path = os.path.join(dest_path, 'superposition')
sup_main_params = [exp_path, bin_path, dest_path, sup_dest_path, verbose, debug, invert]     
tr_dest_path = os.path.join(dest_path, 'tracking')
if not os.path.exists(tr_dest_path):
    os.mkdir(tr_dest_path)
csv_path = os.path.join(tr_dest_path, 'nodes_for_tracking.csv') 
tr_main_params = [dest_path, csv_path, tr_dest_path, verbose]    
log_path = os.path.join(dest_path, 'log.txt')            


## Vectorisation parameters
      
pruning = 5 # order parameter for pruning: remove branches shorter than specified threshold
redundancy = 1 # parameter for the number of redundant nodes in the final graph
smoothing = False # enables smoothing via binary opening and closing on and off
plot = True # enables visualization of extracted networks
figure_format = 'png' # specifies desired format to save plots
graph_format = 'gpickle' # specifies desired format to save graph
dpi = 1500 # specifies resolution of plots (will be ignored if figure format is pdf)               
node_size = 4 # controls the size of the nodes displayed in the visualization of the graph
save_distance_map = False # enables saving of the euclidean distance map
vect_params = [smoothing, plot, figure_format,
               graph_format, dpi, node_size, save_distance_map, pruning, 
               redundancy]

## Superposition parameters ##

# Output options
doImg = -1 # int value to create an image of a specific slice, if 0 no image is created (not compatible with doStack or doVideo)
doStack = False # True to create a stack (slow)
doVideo = False # True to create a video of the superposition
compress = 3 # level of compression 0-9: 0 => fast & no compression, 9 => very slow and compressed (3 is a good compromise)
sup_output_params = [doImg, doStack, doVideo, compress]

# Drawing options (colors as BGR)
line = True # True to enable the drawing of the edges
line_color = (0, 255, 0) # green
line_size = 1    
apex_color = (0, 0, 255) # red
apex_size = 5
node_color = (255, 0, 0) # blue
node_size = 5
body_color = (0, 255, 0) # green
body_size = 3
sup_drawing_params = [line, line_color, line_size, apex_color, apex_size,
                  node_color, node_size, body_color, body_size]


## Tracking parameters ##

# Linking parameters
createCSV = True # True to write a csv file containing the coordinates of the nodes to track, False to load an existing file
forced_matching = True # True to update the graph data even if there's more than 1 match for a given node, False to return an error
search_range = 10 # for linking two nodes from one image to the next, in pixels
memory = 3 # the maximum number of frames during which a feature can vanish, then reappear nearby, and be considered the same particle
adaptive_stop = 5 # when encountering an oversize subnet, retry by progressively reducing search_range until the subnet is solvable
tr_link_params = [createCSV, forced_matching, search_range, memory, adaptive_stop]

# Tracking check parameters
check = True # switch to save an image allowing a visual checking of the graphs update
img_path = os.path.join(tr_dest_path, 'tracking_check.png') # absolute path of the image on which to draw all the nodes
size = 1 # size of the circle to draw for each node
tr_check_params = [check, img_path, size]


## External calls

vc.vectorize(vect_main_params, vect_params, manual_log_path=log_path)
sp.overlay(sup_main_params, sup_output_params, sup_drawing_params, 
           manual_log_path=log_path)
"""
# Extraction of the last slice of the grayscale stack for tracking check
if check:
    tif = tifffile.TiffFile(exp_path)
    last_sli = tif.asarray(-1)
    slimage = Image.fromarray(last_sli, mode='L')
    slimage.save(img_path)
    
tn.tracking(tr_main_params, tr_link_params, tr_check_params, 
            manual_log_path=log_path)

# Last line of console and log output
end = time.time() - start
txt = 'NET> ALL DONE in {:.0f} min {:.4f} s.'.format(end // 60, end % 60)
print(txt)
with open(log_path, 'a+') as log:
    log.write(txt)
"""
