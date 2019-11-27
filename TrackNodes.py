#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Jun 21 14:20:51 2019

This program first creates a csv file from a set of gpickle files (graphs).
The data extracted from the graphs and written in the csv are:
    - the coordinates ('x', 'y') of the nodes of degree 3
    - the frame number ('t') in which these nodes have been found
If you already have a correct csv file, it is possible to jump this step with 
the 'createCSV' switch.
Once the csv file is reated or loaded, the program does a basic tracking of the 
nodes listed in the csv file. Use the linking parameters (line 52) to adjust 
the tracking to your liking. More parameters can be found here:
https://soft-matter.github.io/trackpy/v0.4.1/generated/trackpy.link.html#trackpy.link
After the tracking, the program matches the nodes coordinates from the tracking 
to the graphs in order to add the track ID/particle as tag to the graphs 
nodes.
Finally, if 'check' is enabled, it creates an image of all the nodes 
for every track, each track being represented by a different color.

@author: Laura Xénard
"""

# Standard imports
from math import isclose
import os
import time

# Dependencies
import networkx as nx
import pandas as pd
from tqdm import tqdm
import trackpy as tp
from skimage import io, color

# Custom functions
import net_utilities as nu


def init():
    """
    Initializes parameters.
    
    # General parameters
    :param str vect_path: absolute path of the directory containing the gpickle 
        (graphs) to process
    :param str csv_path: absolute path of the csv file to create and/or load
    :param str dest_path: absolute path of the directory in which to save the 
        updated graphs and the check image. If it doesn't exist, it will be 
        created at runtime.
    :param bool verbose: verbosity switch
    
    # Linking parameters
    :param bool createCSV: True to write a csv file containing the coordinates 
        of the nodes to track, False to load an existing file
    :param bool forced_matching: True to update the graph data even if there's 
        more than 1 match for a given node, False to return an error and stop
    :param int search_range: the maximum distance a node can move between 
        frames, in pixel
    :param int memory: the maximum number of frames during which a node can 
        vanish, then reappear nearby, and be considered the same particle
    :param int adaptive_stop: when encountering an oversize subnet, retry by 
        progressively reducing search_range until the subnet is solvable. If 
        search_range becomes <= adaptive_stop, give up and raise a 
        SubnetOversizeException.
    
    # Tracking check parameters
    :param bool check: True to save an image allowing a visual checking of the 
        graphs update, False to skip this step
    :param str img_path: absolute path of the image file on which to draw the 
        nodes, should be the image corresponding to the last graph
    :param int size: size of the circle to draw for each node, in pixel
    """
    
    # General parameters
    vect_path = '/home/laura/Documents/STAGE3/outputVectorisation_1705_new_invert/output_60_70/' # graphs directory
    csv_path = '/home/laura/Documents/STAGE3/outputVectorisation_1705_new_invert/output_60_70/tracking3/nodes_for_tracking.csv' # csv file 
    dest_path = '/home/laura/Documents/STAGE3/outputVectorisation_1705_new_invert/output_60_70/tracking3/' # output directory
    verbose = True
    main_params = [vect_path, csv_path, dest_path, verbose]
    
    # Linking parameters
    createCSV = True 
    forced_matching = True
    search_range = 10
    memory = 3
    adaptive_stop = 5 
    link_params = [createCSV, forced_matching, search_range, memory, 
                   adaptive_stop]
    
    # Tracking check parameters
    check = True # True to create a check image
    img_path = '/home/laura/Documents/STAGE3/outputVectorisation_1705_new_invert/output_60_70/tracking2/MosaicTest_t070.jpg' # image file on which to draw
    size = 1 # size of the nodes drawing
    check_params = [check, img_path, size]
    
    return main_params, link_params, check_params
    
    
def matchAndInsert(df, graphs, verbose, forced_matching, log_path, log_txt):
    """
    Matches the coordinates in the csv file and those in the graphs in order 
    to insert the track ID of each node as a node tag in the graphs.
    
    :param DataFrame df: DataFrame containing nodes coordinates (x, y, t) and track ID
    :param graphs: list of graphs to update
    :type graphs: list(Graph)  
    
    :return: a list of the updated graphs
    :rtype: list(Graph)
    """
    
    length = df.shape[0]
    
    desc = 'TRACK> Updating graphs'
    for row in tqdm(df.itertuples(), total=length, unit='row', mininterval=5,
                         desc=desc, disable=not verbose, unit_scale=True):
    
        frame = getattr(row, 't')
        posX = getattr(row, 'x')
        posY = getattr(row, 'y')
        
        # List comprehension of matching nodes
        nodes = [x for x, attr in graphs[frame].nodes(data=True) 
                    if (isclose(attr['x'], posX, rel_tol=1e-6) 
                    and isclose(attr['y'], posY, rel_tol=1e-6))]
        # TODO vérifier si frame commence à 0 ou à 1 et ajuster en conséquence dans les prints
        if len(nodes) == 1:
            graphs[frame].node[nodes[0]]['tag'] = getattr(row, 'particle')
        
        elif len(nodes)>1:
            if forced_matching:
                txt = ('Non matching coordinates at frame {}, row index {}: '
                      '{} matches found, exactly one must be found. Still '
                      'affecting a tag for each node.'
                      .format(frame+1, row.Index, len(nodes)))
                log_txt = nu.printAndUpdateLog(txt, log_txt, verbose)
                
                for i, node in enumerate(nodes):
                    graphs[frame].node[nodes[i]]['tag'] = getattr(row, 
                                                                   'particle')
            else:
                txt = ('Non matching coordinates at frame {}, row index {}: '
                         '{} matches found, exactly one must be found.'
                         .format(frame+1, row.Index, len(nodes)))
                nu.writeLogAndExit(log_path, log_txt, txt)
        
        else:
            txt = ('Non matching coordinates at frame {}, row index {}: '
                     '{} matche(s) found, exactly one must be found.'
                     .format(frame+1, row.Index, len(nodes)))
            nu.writeLogAndExit(log_path, log_txt, txt)
            
    return graphs
   
def tracking(main_params, link_params, check_params, manual_log_path=''):
    """
    Creates a csv file from a set of gpickle files (optional), performs a basic
    tracking on degree 3 nodes, injects the result of the tracking in the 
    graphs and exports an image for a visual checking of the results (optional). 
    
    :param main_params: a list of the main parameters
    :type main_params: [str, str, str, bool]
    :param link_params: a list of the linking algorithm parameters
    :type link_params: [bool, bool, int, int, int]
    :param check_params: a list of parameters for creating a check image
    :type check_params: [bool, str, int]
    :param str manual_log_path: the absolute path of the log file. By default,
        a file 'log.txt' will be created at the root of the dest_path directory.
    """
    
    vect_path, csv_path, dest_path, verbose = main_params
    createCSV, forced_matching, search_range, memory, adaptive_stop = link_params
    params = {'r':search_range, 'm':memory}
    check, img_path, size = check_params
    
    # Log path determination
    if manual_log_path:
        log_path = manual_log_path
    else:    
        log_path = os.path.join(dest_path, 'log.txt')
    log_txt = ''
    
    # Creation of the dest directory if it doesn't exist
    if not os.path.exists(dest_path):
        os.mkdir(dest_path)
    
    start = time.time()
    previous_step = start
    txt = 'TRACK> Preparing the data...'
    log_txt = nu.printAndUpdateLog(txt, log_txt, verbose)
    time.sleep(1) # dirty hack to wait for the console output
    
    # Loading graphs
    files = nu.preloadFiles(vect_path, ['.gpickle'], debug=False) # finding all the gpickles
    graphs = [nx.read_gpickle(graph[0]) for graph in files] # creation of a list containing all the graphs, in order
        
    # Creation of the csv if necessary, and loading as DataFrame
    if createCSV:
        nu.createNodesCSVForTracking(files, csv_path, verbose)
    df = pd.read_csv(csv_path)
    
    timer = time.time()
    txt = 'TRACK> ...done in {:.4f} s.'.format(timer-previous_step)
    log_txt = nu.printAndUpdateLog(txt, log_txt, verbose)
    time.sleep(1) # dirty hack to wait for the console output
    previous_step = timer
    txt = 'TRACK> Tracking...'
    log_txt = nu.printAndUpdateLog(txt, log_txt, verbose)
       
    # Tracking   
    df_track = tp.link(df, search_range, memory=memory, t_column='t', 
                          adaptive_stop=adaptive_stop)

    timer = time.time()
    txt = 'TRACK> ...done in {:.4f} s.'.format(timer-previous_step)
    log_txt += txt + '\n'
    time.sleep(1) # dirty hack to wait for the console output
    previous_step = timer
    txt = 'TRACK> Updating graphs...'.format(timer-previous_step)
    log_txt += txt + '\n'
        
    # Adding nodes ID to the graphs        
    graphs = matchAndInsert(df_track, graphs, verbose, forced_matching, 
                             log_path, log_txt)
    
    timer = time.time()
    end = timer-previous_step
    txt = ('TRACK> ...done in {:.0f} min {:.4f} s.'
           .format(end // 60, end % 60))
    log_txt += txt + '\n'
    time.sleep(1) # dirty hack to wait for the console output
    previous_step = timer
    txt = 'TRACK> Saving graphs...'.format(timer-previous_step)
    log_txt += txt + '\n'    
    
    # Saving the updated graphs
    desc = 'TRACK> Saving graphs'
    for i, graph in enumerate(tqdm(graphs, total=len(graphs), desc=desc,
                                           unit='graph', disable=not verbose)):       
        
        txt = 'TRACK>    graph {} / {}'.format(i+1, len(graphs))
        log_txt += txt + '\n'
        
        # New graph name: [old name]_track_r[search_range]_m[memory].gpickle'
        graph_name = files[i][1] + '_track'
        for key, value in params.items():
            graph_name += '_' + key + str(value)
            
        path = os.path.join(dest_path, graph_name + '.gpickle')       
        nx.write_gpickle(graph, path, protocol=2) 

    timer = time.time()
    txt = 'TRACK> ...done in {:.4f} s.'.format(timer-previous_step)
    log_txt += txt + '\n'
    time.sleep(1) # dirty hack to wait for the console output
    previous_step = timer
    txt = 'TRACK> Processing check image...'.format(timer-previous_step)
    log_txt = nu.printAndUpdateLog(txt, log_txt, verbose)
    time.sleep(1) # dirty hack to wait for the console output
        
    # Saving an image to check the results   
    if check:
        img = color.gray2rgb(io.imread(img_path)) # loading the image as rgb
        colors = {} # dictionary in which we save the colors by node tag
        
        # Drawing each node with a random color for each node tag
        desc = 'TRACK>    drawing graphs nodes'
        for i, graph in enumerate(tqdm(graphs, total=len(graphs), desc=desc,
                                           unit='graph', disable=not verbose)):
            txt = 'TRACK>    drawing nodes from graph {}'.format(files[i][1])
            log_txt += txt + '\n'
            nu.drawNodesRandomColors(graph, img, size, colors)      
            
        txt = 'TRACK>    writing image...'
        log_txt = nu.printAndUpdateLog(txt, log_txt, verbose)
        io.imsave(os.path.join(dest_path, 'tracking_check.png'), img)

    timer = time.time()
    end = timer-start
    txt = 'TRACK> ...done in {:.4f} s.'.format(timer-previous_step)
    log_txt += txt + '\n'
    txt = ('TRACK> DONE in {:.0f} min {:.4f} s.'
          .format(end // 60, end % 60))
    log_txt = nu.printAndUpdateLog(txt, log_txt, verbose)
    
    # Writing the log    
    with open(log_path, 'a+') as log:
        log.write(log_txt)
    
    
if __name__ == '__main__':

    main_params, link_params, check_params = init()  
    tracking(main_params, link_params, check_params)    

    