#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Jun 12 16:17:14 2019

This program loads a set of gpickle files (graphs) and creates an overlay of 
these graphs over a tif stack given as parameter.
The overlay can be saved as a tif stack, as a video or as a normal tif for only 
one slice of the stack. Be aware that priority is given to the creation of a 
tif stack or a video. A tif for just one slice will be created only if 'doStack'
and 'doVideo' are disabled.

@author: Laura Xénard, based on a previous version in Python 2
"""

# Standard imports
import os
import time

# Dependencies
import cv2
import networkx as nx
import numpy as np
import tifffile
from tqdm import tqdm

# Custom classes and functions
import net_utilities as nu


def init():
    """
    Initializes parameters.
    
    # General parameters
    :param str exp_path: absolute path of the experimental (grayscale) tif 
        stack file. The drawing will be done on these images.
    :param str bin_path: absolute path of the binarized tif stack file. These 
        images are used to identify those without mycelium. 
    :param str vect_path: absolute path of the directory containing the gpickle 
        (graphs) matching the binarized and grayscale images to process    
    :param str dest_path: absolute path of the directory in which to save the 
        video and/or images. If it doesn't exist, it will be created at runtime.
    :param bool verbose: verbosity switch
    :param bool debug: debugging switch
    :param bool invert: inverts the bin_stack. Must be switched on if 
        background pixels are white (255), otherwise in case of empty slices 
        they won't be detected causing the program to crash. 
    
    # Output options
    :param int doImg: slice index to just create an image for this specific 
        slice. If 0, no image is created. Supports backward indexing. If 
        doStack or doVideo are switched on, the image creation will be ignored, 
        whatever value has been passed to 'doImg'.
    :param bool doStack: True to create a tif stack of the overlay, False to 
        skip this step. Be careful when using this option, it can be quite slow 
        and the resulting file will be heavy (RGB multi-page tif).
    :param bool doVideo: True to create a video of the overlay, False to 
        skip this step.
    :param int compress: level of compression for the 'doStack' option.
        Range: 0-9: 
            0 => fast & no compression, 
            9 => very slow and compressed (3 is a good compromise)
            
    # Drawing options
    :param bool line: True to enable the edges drawing, False to disable. 
        Beware, the colors in cv2 are in BGR, not RGB!
    :param line_color: color for edges
    :type line_color: (int, int, int)
    :param int line_size: line thickness for edges, in pixel   
    :param apex_color: color for apexes (degree 1)
    :type apex_color: (int, int, int)
    :param int apex_size: circle radius for apexes, in pixel
    :param node_color: color for nodes (degree 3
    :type node_color: (int, int, int))
    :param int node_size: circle radius for nodes, in pixel
    :param body_color: color for body nodes (degree 2)
    :type body_color: (int, int, int)
    :param int body_size: circle radius for body nodes, in pixel
    """
    
    # General parameters
    exp_path = '/home/laura/Documents/stacks tif/1705_regMovie.tif' # experimental tif stack (grayscale)
    bin_path = '/home/laura/Documents/stacks tif/1705/1705_binarizedMovie.tif' # binarized tif stack
    vect_path = '/home/laura/Documents/STAGE3/1705_NET/' # gpickle directory
    dest_path = '/home/laura/Documents/STAGE3/1705_NET/superposition' # output directory
    verbose = True
    debug = True
    invert = True 
    main_params = [exp_path, bin_path, vect_path, dest_path, verbose, debug, invert]
    
    # Output options
    doImg = -1 # image index
    doStack = False 
    doVideo = False 
    compress = 3 # advice: no more than 5
    output_params = [doImg, doStack, doVideo, compress]
    
    # Drawing options (colors as BGR)
    line = True # edges drawing
    line_color = (0, 255, 0) # green 
    line_size = 1    
    apex_color = (0, 0, 255) # red
    apex_size = 5
    node_color = (255, 0, 0) # blue
    node_size = 5
    body_color = (0, 255, 0) # green
    body_size = 3
    drawing_params = [line, line_color, line_size, apex_color, apex_size,
                      node_color, node_size, body_color, body_size]
    
    return main_params, output_params, drawing_params

def createImgOverlay(sli, graph, drawing_params, notAnEmptySlice):
    """
    Creates an overlay of an image and its associated graph by drawing on the 
    image the nodes and edges of the graph using the given drawing parameters.
    
    :param ndarray sli: an array representing the image (slice) on which to 
        draw the graph
    :param nx.Graph graph: the graph to draw
    :param drawing_params: the parameters to use when drawing the graph (color, 
        radius, thickness...)
    :type drawing_params: [bool, (int, int, int), int, (int, int, int), int, 
                                 (int, int, int), int, (int, int, int), int,]
    :param bool notAnEmptySlice: True when the image 'sli' is not empty, False
        otherwise. If the image is empty, no drawing is done and a 3-dim (RGB)
        copy of the original image is returned.
        
    :return: an array representing the image of the overlay
    :rtype: 3-dim ndarray
    """
    
    (Y, X) = sli.shape
        
    # Creation of the superposition file (3 dimensions because RGB for the graph drawing)
    sli_ovl = np.zeros([Y, X, 3], np.uint8)
    sli_ovl[:, :, 0] = sli
    sli_ovl[:, :, 1] = sli
    sli_ovl[:, :, 2] = sli
    
    if notAnEmptySlice:
        line = drawing_params[0]
        line_color = drawing_params[1]
        line_size = drawing_params[2]
        apex_color = drawing_params[3]
        apex_size = drawing_params[4]
        node_color = drawing_params[5]
        node_size = drawing_params[6]
        body_color = drawing_params[7]
        body_size = drawing_params[8]
        
        graph = nx.convert_node_labels_to_integers(graph, first_label=0, 
                                                   ordering='default', 
                                                   label_attribute=None)
    
        # Creation of arrays from graph elements     
        x_node = np.fromiter(nx.get_node_attributes(graph, 'x').values(), 
                             dtype=int)        
        y_node = np.fromiter(nx.get_node_attributes(graph, 'y').values(), 
                             dtype=int)       
        degrees = np.array([degree for node, degree in nx.degree(graph)], 
                            dtype=int)   
        edges = np.array(graph.edges())
        
        # Lists of edges coordinates
        x1 = x_node[edges[:, 0]]
        y1 = y_node[edges[:, 0]]
        x2 = x_node[edges[:, 1]]
        y2 = y_node[edges[:, 1]]
    
        # Edges drawing
        if line:
            for i in range(len(x1)):
                cv2.line(sli_ovl, (x1[i], y1[i]), (x2[i], y2[i]), 
                         line_color, line_size)
    
        # Nodes drawing
        for i in range(len(x_node)):
            if degrees[i] == 1: # apex points
                color = apex_color
                size = apex_size
            elif degrees[i] == 2: # body/hypha points
                color = body_color
                size = body_size
            else: # branching/node points
                color = node_color
                size = node_size
            cv2.circle(sli_ovl, (x_node[i], y_node[i]), size, color, 
                       thickness=-1)

    return sli_ovl

def _computeIndex(value, slices_nb):
    """
    Computes the slice index for log output. The slice index is not the same 
    for an image output than for a stack or video output.
    
    :param int value: the original slice index
    :param int slices_nb: the number of slices in the image being processed
        
    :return: a new slice index taking into account the output type
    :rtype: int
    """
    
    if doImg >= 0 or doStack or doVideo:
        return value + 1
    else:
        return value % (slices_nb+1)

def overlay(main_params, output_params, drawing_params, manual_log_path=''):
    """
    Creates an overlay output from a tif stack and its associated graphs.
    The output can be an image from a specified slice, a tif stack or a video
    with all the slices. Cf init() for more details on the parameters.
    
    :param main_params: a list of the main parameters
    :type main_params: [str, str, str, str, bool, bool, bool]
    :param output_params: a list of the output parameters
    :type output_params: [int, bool, bool, int]
    :param drawing_params: a list of the drawing parameters
    :type drawing_params: [bool, (int, int, int), int, (int, int, int), int, 
                                 (int, int, int), int, (int, int, int), int,]             
    :param str manual_log_path: the absolute path of the log file. By default,
        a file 'log.txt' will be created at the root of the dest_path directory.
    """
    
    global doImg, doStack, doVideo
    
    exp_path = main_params[0]
    bin_path = main_params[1]
    vect_path = main_params[2] 
    dest_path = main_params[3] 
    verbose = main_params[4]
    debug = main_params[5]
    invert = main_params[6]
    doImg, doStack, doVideo, compress = output_params
    
    if debug:
        verbose = True
    
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
    txt = 'SUP> Loading binarized stack...'
    log_txt = nu.printAndUpdateLog(txt, log_txt, verbose)
        
    # Binarized stack loading
    bin_stack = tifffile.imread(bin_path) # loading the image as a numpy array
    bin_stack = np.array(bin_stack, dtype=np.uint8) # dtype safeguard
    if invert:
        bin_stack = np.invert(bin_stack)    
    if debug:
        txt = 'SUP>    Binarized stack shape: {}'.format(bin_stack.shape)
        log_txt = nu.printAndUpdateLog(txt, log_txt, verbose)
    slices_nb_bin = bin_stack.shape[0]    
    
    # To differentiate slices with mycelium from those without
    empty = []
    thalle = np.zeros(slices_nb_bin)
    for iSli in range(slices_nb_bin):
        sli = bin_stack[iSli, :, :].astype(np.uint8)
        thalle[iSli] = np.sum(sli)
        
        if thalle[iSli] <= 0: # empty slice
            empty.append(iSli)
    del bin_stack # not used anymore, del to free memory for the experimental stack
                    
    if debug:
        txt = 'SUP>    Number of empty slices: {}'.format(len(empty))
        log_txt = nu.printAndUpdateLog(txt, log_txt, verbose)
           
    timer = time.time()
    txt = 'SUP> ...done in {:.4f} s.'.format(timer-previous_step)
    log_txt = nu.printAndUpdateLog(txt, log_txt, verbose)
    previous_step = timer
    txt = 'SUP> Loading grayscale stack...'
    log_txt = nu.printAndUpdateLog(txt, log_txt, verbose)
    
    # Experimental stack loading (grayscale)    
    exp_stack = tifffile.imread(exp_path) # loading the image as a numpy array
    exp_stack = np.array(exp_stack, dtype=np.uint8) # dtype safeguard
    if debug:
        txt = 'SUP>    Grayscale stack shape: {}'.format(exp_stack.shape)
        log_txt = nu.printAndUpdateLog(txt, log_txt, verbose)
    slices_nb_exp, height, width = exp_stack.shape
   
    timer = time.time()
    txt = 'SUP> ...done in {:.4f} s.'.format(timer-previous_step)
    log_txt = nu.printAndUpdateLog(txt, log_txt, verbose)
    previous_step = timer
    txt = 'SUP> Loading graphs and checking alignment...'
    log_txt = nu.printAndUpdateLog(txt, log_txt, verbose)
    
    # graphs loading and sorting
    graphs = nu.preloadFiles(vect_path, ['.gpickle'], debug)
    
    # Adding elements in 'graphs' for lists alignment if not already aligned
    if slices_nb_exp != len(graphs):
        for index in empty:
            graphs.insert(index, ('empty','empty'))        
        if debug:
            txt = ('SUP>    Length of graph list after alignment: {}'
                  .format(len(graphs)))
            log_txt = nu.printAndUpdateLog(txt, log_txt, verbose)
    
    # Checking that all the lenghts are aligned    
    if slices_nb_bin == slices_nb_exp and slices_nb_exp == len(graphs):
        pass # everything is aligned
    else:    
        txt = ('ERROR: the number of slices in the binarized stack ({}), in '
              'the grayscale one({}), and the number of graphs ({}) are not '
              'equal.'.format(slices_nb_bin, slices_nb_exp, len(graphs)))
        nu.writeLogAndExit(log_path, log_txt, txt)
        
    timer = time.time()
    txt = 'SUP> ...done in {:.4f} s.'.format(timer-previous_step)
    log_txt = nu.printAndUpdateLog(txt, log_txt, verbose)
    previous_step = timer
    txt = 'SUP> Preparing output...'
    log_txt = nu.printAndUpdateLog(txt, log_txt, verbose)
             
    # Definition of the range of images to browse and process   
    rangeN = np.array([])
    if doImg: # image creation: only one slice will be processed
        if doImg >= 0: # select an image by its index
            rangeN = np.array([doImg-1])
        else: # select an image from backward
            rangeN = np.array([doImg])
    
    if doVideo or doStack: # stack or video creation: all the slices must be processed
        rangeN = range(slices_nb_exp)
        frames = [] # list to save the frames of the stack tif
        
        if doVideo:
            # Video output creation
            fourcc = cv2.VideoWriter_fourcc(*'MJPG')
            video = cv2.VideoWriter('video.avi', fourcc, 4, (width, height))
    
    if debug:
        txt = 'SUP>    rangeN: {}'.format(rangeN)
        log_txt = nu.printAndUpdateLog(txt, log_txt, verbose)
          
    timer = time.time()
    txt = 'SUP> ...done in {:.4f} s.'.format(timer-previous_step)
    log_txt = nu.printAndUpdateLog(txt, log_txt, verbose)
    time.sleep(1) # dirty hack to wait for the console output
    previous_step = timer
    start_process = timer
    txt = 'SUP> Processing images...'
    log_txt += txt + '\n'
    
    # Slices processing, one by one
    desc = 'SUP> Creating overlay'
    for iSli in tqdm(rangeN, desc=desc, unit='slice', disable=not verbose):

        txt = ('SUP>    Image {} of {}...'
              .format(_computeIndex(iSli, slices_nb_exp), slices_nb_exp))
        log_txt += txt + '\n'
        
        image = exp_stack[iSli, :, :].astype(np.uint8) # gets the slice and converts it    
        DG = nx.read_gpickle(graphs[iSli][0]) # loading the graph
        ovl = createImgOverlay(image, DG, drawing_params, thalle[iSli])        
        
        if not thalle[iSli]:
            txt = 'SUP>      This slice is empty.'.format(iSli+1, iSli)
            log_txt += txt + '\n'

        if doStack or doVideo:
            if doStack:
                frames.append(ovl)
            if doVideo:
                video.write(ovl)
        else:
            img_path = os.path.join(dest_path, graphs[iSli][1] + 
                                    '_superposition.png')
            cv2.imwrite(img_path, ovl)
            
        timer = time.time()
        txt = 'SUP>    ...done in {:.4f} s.'.format(timer-previous_step)
        log_txt += txt + '\n'
        previous_step = timer
            
    timer = time.time()
    txt = 'SUP> ...done in {:.4f} s.'.format(timer-start_process)
    log_txt += txt + '\n'
    previous_step = timer

    if doStack:         

        txt = 'SUP> Creating tif stack...'
        log_txt += txt + '\n'
            
        # Writing tif stack
        destination = os.path.join(dest_path, 'superpose.tif')
        with tifffile.TiffWriter(destination) as tiff:
            desc = 'SUP> Creating tif stack'
            for i, frame in enumerate(tqdm(frames, total=len(frames), desc=desc,
                                           unit='frame', disable=not verbose)):
                txt = ('SUP>    writing frame {} of {}'
                      .format(i+1, len(frames)))
                log_txt += txt + '\n'
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB) # color conversion for saving without cv2 
                tiff.save(frame, compress=compress)
                frames[i] = 0 # cleaning the frame once written to free up memory
        
        timer = time.time()
        txt = 'SUP> ...done in {:.4f} s.'.format(timer-previous_step)
        log_txt += txt + '\n'
        previous_step = timer
    
    if doVideo:
        time.sleep(1) # dirty hack to wait for the console output
        txt = 'SUP> Cleaning video output...'
        log_txt = nu.printAndUpdateLog(txt, log_txt, verbose)
            
        #cv2.destroyAllWindows()
        video.release()
        source = 'video.avi'
        destination = os.path.join(dest_path, 'superpose.avi')
        os.rename(source, destination)
        
        timer = time.time()
        txt = 'SUP> ...done in {:.4f} s.'.format(timer-previous_step)
        log_txt = nu.printAndUpdateLog(txt, log_txt, verbose)
        previous_step = timer
   
    timer = time.time()
    end = timer-start 
    time.sleep(1) # dirty hack to wait for the console output       
    txt = 'SUP> DONE in {:.0f} min {:.4f} s.'.format(end // 60, end % 60)
    log_txt = nu.printAndUpdateLog(txt, log_txt, verbose)
    
    # Writing the log    
    with open(log_path, 'a+') as log:
        log.write(log_txt)


if __name__ == '__main__':
    
    main_params, output_params, drawing_params = init()
    overlay(main_params, output_params, drawing_params)    