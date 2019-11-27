#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
    Copyright (C) 2015  Jana Lasser Max Planck Institute for Dynamics and
    Self Organization Goettingen

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program. If not, see <http://www.gnu.org/licenses/>.

    If you find any bugs or have any suggestions, please contact me at
    jana.lasser@ds.mpg.de

    Converted to Python 3.7 and modified by Laura Xénard in June 2019.
    
    
    Parameters handling:
        !!!! This program is intended to be used with binarized images. The 
        supported formats are tif, png, bmp, pgm. The jpg/jpeg format does not 
        work. Other formats have not been tested.
        For grayscale and RGB/RGBA images, you may encounter some troubles. The 
        best way to deal with this is to convert the images (with ImageJ for 
        example) before loading them for the vectorisation. Otherwise, use the 
        'verbose, 'debug', 'plot' and 'save_distance_map' options to see what 
        went wrong and try to correct it.

        
    Podospora anserina network vectorisation usual parameters        
------------------
        
        pruning = 5
        redundancy = 1
        invert = True                                         
        smoothing = False
        plot = True
        figure_format = 'png'
        graph_format = 'gpickle'
        dpi = 1500
        node_size = 4
        save_distance_map = True
        
"""

# Standard imports
import os
import time
import operator

# Dependencies
import tifffile
from scipy import ndimage as ndi
import networkx as nx
import numpy as np	
import meshpy.triangle as triangle
from skimage.morphology import binary_opening, binary_closing, disk
from PIL import Image
	
# Custom functions
import net_utilities as nu


def init():
    """
    Initializes parameters.
    
    # General parameters
    
    source_path str : absolute path of the file/directory to vectorize.
        If 'source_path' is a directory, the program will process sequentially 
        all the images contained in this directory. If it's a file, it will 
        only process this one file. The images must be binarized 8-bit images. 
        
    dest_path str: absolute path of the directory in which to save the 
        results (gpickle files, graph images...). If it doesn't exist, it will
        be created at runtime.
        
    unstack bool: if enabled, the program will save every slice of the 
        tif stacks encountered in [dest_path]/unstacked_slices/. If this 
        directory does not exist, it will be created at runtime. The slices 
        will be name like this: stackname_slicenumber.png.The slice number is 
        left padded with 0 to ease later processing.
        
    verbose bool: verbosity switch. If set to True, the program will 
        then print its current processing step as  well as the time it needed 
        for the last step. For some steps (usually the ones that take longer) 
        information about the current state of the program is given in more 
        detail to be able to trace the program's progress.
        
    debug bool: debugging switch. If set to True, turns on additional 
        debug output. Also saves additional visualizations of the processing 
        like a plot of the contours and the triangulation. May consume a 
        considerable additional amount of time because the additional figures 
        take quite long to plot and save.
        
    invert bool: inverts the images. Must be switched on if background 
        pixels are white (255). Otherwise in case of empty slices they won't be 
        detected causing the program to crash.
    
    
    # Other parameters
    
    pruning int: pruning threshold. Branches shorter than the threshold 
        specified with pruning will be removed from the network. This is done 
        to reduce the number of surplus branches due to noisy contours of the 
        network. Defaults to 5 which has proven to be a reasonable number of 
        nodes to prune away.
        
    redundancy int: when redundancy = 0, a graph-object with no 
        redundant nodes (i.e. nodes with degree 2) will be saved.
        When redundancy = 1, a graph-object with half the redundant nodes as 
        well as one without redundant nodes will be saved.
        When redundancy = 2, a graph-object with all redundant nodes as well as
        one with half the redundant nodes and one with no redundant nodes will 
        be saved.    
        
    smoothing bool: if enabled, the binary image will be smoothed using 
        binary opening and closing operations. The kernel size of said
        operations can be controlled by passing an integer as parameter. 
        The right kernel size is highly dependant on the resolution of the 
        image. As a rule of thumb choose a kernel size below the width of the 
        smallest feature in the image (in pixels).
        
    plot bool: enables visualization (plotting) of the created graphs.
        The visualization is done using matplotlib and in general gets very
        slow when dealing with large networks. As a rule of thumb it is 
        encouraged to only plot networks when they contain fewer than 10^5
        nodes. The format the plot will be saved in as well as its resolution
        (if not saved as vector graphic) must be specified using the 
        'figure_format' and 'dpi' parameters. If you want to visualize really 
        large networks, saving them as .png with a high dpi (>2000 so features 
        are still recognizeable) might work.
        
    figure_format str: sets the output format of plots (networks or 
        debugging plots) to the desired format. Supported formats include: pdf, 
        png, jpg, tif (look at matplotlib's safefig-function for a complete 
        list). In general if the plot is needed for a report/publication, pdf 
        is recommended as they can easily be modified and beautified using a
        vector graphics editor. Saving as pdf is relatively time-inefficient.
        If one wants to visualize large plots, I would recommend saving them
        as png with a high resolution (use 'dpi' parameter to crank up 
        resolution). This saves time and yields acceptable results.
        
    graph_format str: sets the output format of graphs to the desired 
        format. Supported formats are [gpickle, adjlist, gml, graphml, yaml,
        edgelist, weighted_edgelist, multiline_adjlist, gexf, pajek]. Have a 
        look at the different networkx.write_ ... functions for an in detail 
        explanation. Only the gpickle output has been tested in Python 3.7.
        
    dpi int: sets the resolution (dots per inch) for plots (networks or 
        debugging plots). High resolutions take longer to save and create 
        larger image files. Low resolutions sometimes make it hard to recognize 
        smaller details in networks.
        
    node_size int: controls the size of the nodes displayed in graph
        visualization. If node_size = 0, only edges and no nodes are plotted.
        
    save_distance_map bool: enables saving of the euclidean distance map 
        created during the network extraction process. 
    """
    
    # General parameters        
    source_path = '/home/hyphes/LAURA/stacks_tif/1705_binarizedMovie_1_6.tif' # directory or image to vectorize
    dest_path = '/home/hyphes/LAURA/tests/1705_1_6_quatro' # output directory
    unstack = False  # saves each slice as a separated image
    verbose = True 
    debug = False
    invert = True # inverts the images before processing                                                       
    main_params = [source_path, dest_path, unstack, verbose, debug, invert]
    
    # Other parameters      
    pruning = 5
    redundancy = 1
    smoothing = False
    plot = False    
    figure_format = 'png'  
    graph_format = 'gpickle'    
    dpi = 1500               
    node_size = 4             
    save_distance_map = False
    vect_params = [smoothing, plot, figure_format,
                   graph_format, dpi, node_size, save_distance_map, pruning, 
                   redundancy]                                              
    
    return main_params, vect_params

def createContours(image, img_name, height, debug, dest_path, figure_format, 
                   dpi, verbose):
    """
    - Finds the contours of the features present in the image : these contours 
    are approximated using the Teh-Chin-dominant-point detection-algorithm 
    (see Teh, C.H. and Chin, R.T., On the Detection of Dominant Pointson 
    Digital Curve. PAMI 11 8, pp 859-872 (1989)).
    - Finds the longest contour within the set of contours.
    
    :param ndarray image: the image (distance_map) from which to find contours
    :param str img_name: the image name
    :param int height: the image height in pixel        
    :param bool debug: debugging switch        
    :param str dest_path: absolute path of the output directory       
    :param str figure_format: plots and figures saving format
    :param int dpi: plots and figures resolution

    :return: the index of the longuest contour and a list of the flattened 
        contours
    :rtype: (int, list([int, int]))
    """
    
    global log_txt
    
    raw_contours = nu.getContours(image) # extracts raw contours
    flattened_contours = nu.flattenContours(raw_contours) # flattens nested contour list
    
    if debug:
        txt = ('VECT>        Contours converted, we have {} contour(s).'
              .format(len(flattened_contours)))
        log_txt = nu.printAndUpdateLog(txt, log_txt, verbose)
    													                
    flattened_contours = nu.thresholdContours(flattened_contours, 3) # filters out contours smaller than 3 in case there are any left
    
    if debug:
        nu.drawContours(height, flattened_contours, img_name, dest_path,
                        figure_format, dpi)
    											                 
    longuest_length = 0	# length of longuest contour
    
    # To find position of longest contour (i.e longuest_index)
    for c in range(len(flattened_contours)):
        if(len(flattened_contours[c]) > longuest_length):
            longuest_length = len(flattened_contours[c])
            longuest_index = c
    
    return longuest_index, flattened_contours

def createMesh(longuest_index, flattened_contours):
    """
    Creates the mesh of points and facets where every facet is the plane 
    spanned by one contour.
    
    :param int longuest_index: the index of the longuest contour
    :param flattened_contours: a list of the flattened contours
    :type flattened_contours: list([int, int])
        
    :return: an array of mesh points, a list of mesh facets and a list of hole 
        points
    :rtype: (ndarray, list((int, int)), list((int, int)))
    """

    flattened_contours = np.asarray(flattened_contours) # adds a bit of noise to increase stability of triangulation algorithm
    for c in flattened_contours:
        for p in c:
            p[0] = p[0] + 0.1 * np.random.rand()
            p[1] = p[1] + 0.1 * np.random.rand()
       			     
    mesh_points = flattened_contours[longuest_index] # first adds longuest contour to mesh
    mesh_facets = nu.roundTripConnect(0, len(mesh_points)-1)	# creates facets from the longest contour
    
    hole_points = [] # every contour other than the longuest one needs an interior point
    for i in range(len(flattened_contours)):	 # traverses all contours   
        curr_length = len(mesh_points)									
        if(i == longuest_index): # ignores longuest contour
            pass
        else: # finds a point that lies within the contour
            contour = flattened_contours[i]
            interior_point = nu.getInteriorPoint(contour)        										
            hole_points.append((interior_point[0], interior_point[1])) # adds point to list of interior points
            mesh_points.extend(contour) # adds contours identified by their interior points to the mesh
            mesh_facets.extend(nu.roundTripConnect(curr_length, 
                                                   len(mesh_points)-1)) # adds facets to the mesh    
    
    return mesh_points, mesh_facets, hole_points

def createTriangulation(mesh_points, mesh_facets, hole_points):      
    """
    - Sets the points we want to triangulate.
    - Marks the holes we want to ignore by their interior points.
    - Triangulation: no interior steiner points, we want triangles to fill
    the whole space between two boundaries. Allowing for quality meshing
    would also mess with the triangulation we want.
    
    :param ndarray mesh_points: an array of mesh points
    :param mesh_facets: a list of mesh facets
    :type mesh_facets: list((int, int))
    :param hole_points: a list of hole points
    :type hole_points: list((int, int))
        
    :return: triangulation
    :rtype: meshpy.triangle.MeshInfo
    """
    
    info = triangle.MeshInfo() # creates triangulation object
    info.set_points(mesh_points)	 # sets points to be triangulated
    if(len(hole_points) > 0):									     
    	info.set_holes(hole_points) # sets holes (contours) to be ignored
    info.set_facets(mesh_facets) # sets facets
    triangulation = triangle.build(info, verbose=False, quality_meshing=False,
                                   allow_boundary_steiner=False, 
                                   allow_volume_steiner=False)    
    return triangulation

def triangleClassification(triangulation, debug, verbose):       
    """
    - Builds triangle-objects from the triangulation.
    - Sets the type of each triangle (junction, normal, end or isolated)
    depending on how many neighbors it has.
    - Sets the radius of each triangle by looking up its 'midpoint'
    in the distance map.
    - Gets rid of isolated triangles.
    
    :param triangulation: triangulation obtained from a distance map
    :type triangulation: meshpy.triangle.MeshInfo
    :param bool debug: debugging switch
    :param bool verbose: verbosity switch
    
    :return: a list of triangles without isolated ones and a list of the 
        indices of isolated triangles
    :rtype: (list(CshapeTriangle), list())
    """
    
    global log_txt
    
    triangles = nu.buildTriangles(triangulation)	 # builds triangles                                                                 
    junction = 0
    normal = 0
    end = 0
    isolated_indices = []

    # Counting the number of each triangle type for debugging
    for i, t in enumerate(triangles):
        t.init_triangle_mesh() # sets the triangle's type 
        if t.get_type() == 'junction':
            junction += 1
        elif t.get_type() == 'normal':
            normal += 1
        elif t.get_type() == 'end':
            end += 1
        elif t.get_type() == 'isolated':
            isolated_indices.append(i)
    triangles = list(np.delete(np.asarray(triangles), isolated_indices)) # removes isolated triangles from the list of triangles
    
    if debug:
        txt = ('VECT>         Triangle types:')
        log_txt = nu.printAndUpdateLog(txt, log_txt, verbose)
        txt = ('VECT>           junction: {}, normal: {}, end: {}, isolated: {}'
              .format(junction, normal, end, len(isolated_indices)))
        log_txt = nu.printAndUpdateLog(txt, log_txt, verbose)
        
    return triangles, isolated_indices

def graphPruning(triangles, height, distance_map, verbose, debug, 
                 dest_path, img_name, figure_format, dpi, pruning):
    """
    Prunes away the outermost branches to avoid surplus branches due to 
    noisy contours.
    
    :param triangles: a list of triangles found in the image
    :type triangles: list(CshapeTriangle)
    :param int height: image height
    :param ndarray distance_map: the distance map of the image
    :param bool verbose: verbosity switch
    :param bool debug: debugging switch
    :param str dest_path: the output directory 
    :param str img_name: the name of the image currently being worked on
    :param str figure_format: the wanted format for the triangulation figure 
        output 
    :param int dpi: the wanted resolution for the figure
    :param int pruning: branches pruning threshold  

    :return: a list of the remaining triangles after pruning
    :rtype: list(CshapeTriangle)
    """
    
    global log_txt
    
    triangles = nu.bruteforcePruning(triangles, pruning, verbose) # prunes away the 'pruning' number of triangles at the ends of the network
    
    default_triangles = 0
    junction = 0
    normal = 0
    end = 0
    isolated = 0
    
    # Counting the number of each triangle type for debugging
    for t in triangles:
        t.init_triangle_mesh()
        default_triangles += t.set_center(distance_map)
        if t.get_type() == 'junction':
            junction += 1
        elif t.get_type() == 'normal':
            normal += 1
        elif t.get_type() == 'end':
            end += 1
        elif t.get_type() == 'isolated':
            isolated += 1
    
    if debug:
        nu.drawTriangulation(triangles, img_name, dest_path, 
                             distance_map, figure_format, dpi)
        txt = ('VECT>         Triangles defaulted to zero: {}'
              .format(default_triangles))
        log_txt = nu.printAndUpdateLog(txt, log_txt, verbose)
        txt = ('VECT>         Triangle types:')
        log_txt = nu.printAndUpdateLog(txt, log_txt, verbose)
        txt = ('VECT>           junction: {}, normal: {}, end: {}, isolated: {}'
              .format(junction, normal, end, isolated))
        log_txt = nu.printAndUpdateLog(txt, log_txt, verbose)
        
    return triangles

def cleanAndSaveGraph(G, triangles, distance_map, img_name, dest_path, verbose, 
                      debug, params, plot, figure_format, dpi, graph_format, 
                      node_size, height):   
    """
    - If so specified, removes half the redundant nodes (i.e. nodes with
    degree 2), draws and saves the graph.
    - If so specified, removes all the redundant nodes, draws and saves the 
    graph.
        
    :param nx.Graph G: the graph currently being worked on
    :param triangles: the list of triangles found in the image
    :type triangles: list(CshapeTriangle)
    :param ndarray distance_map: the distance map of the image
    :param str img_name: the name of the image currently being worked on
    :param str dest_path: the output directory 
    :param bool verbose: verbosity switch
    :param bool debug: debugging switch
    :param params: a dictionnary matching parameters name with their values
    :type params: dict{str : int}
    :param bool plot: enables the writing of the graph and triangulation figure
    :param str figure_format: the wanted format for the graph and triangulation 
        figure output 
    :param int dpi: the wanted resolution for the figure and the graph image
    :param graph_format: the wanted format for the graph image output 
    :param int node_size: the size of the nodes in the graph image
    :param int height: the image height
    """
        
    redundancy = params['r']
    
    # Draws and saves graph with redundant nodes
    if redundancy == 2: 
        nu.drawAndSave(G, img_name, dest_path, params, verbose, plot, 
                       figure_format, dpi, graph_format, node_size, height)                                                   
    if debug:
        nu.drawGraphTriangulation(G, triangles, img_name, dest_path, 
                                  distance_map, figure_format, dpi)
    
    # Draws and saves graph with half redundant nodes
    if redundancy == 1:                                                            
        G = nu.removeRedundantNodes(G, verbose, 1)
        nu.drawAndSave(G, img_name, dest_path, params, verbose, plot, 
                       figure_format, dpi, graph_format, node_size, height)
    
    # Draws and saves graph without redundant nodes
    if redundancy == 0:   
        G = nu.removeRedundantNodes(G, verbose, 0) 
        nu.drawAndSave(G, img_name, dest_path, params, verbose, plot, 
                       figure_format, dpi, graph_format, node_size, height)			


def vectorize(main_params, vect_params, manual_log_path=''):
    """
    Vectorizes binarized images with the given parameters.
    
    :param main_params: a list of the main parameters
    :type main_params: [str, str, bool, bool, bool, bool]
    :param vect_params: a list of the vectorisation parameters
    :type vect_params: [bool, bool, str, str, int, int, bool, int, int]
    :param str manual_log_path: the absolute path of the log file. By default,
        a file 'log.txt' will be created at the root of the dest_path directory.
    """
    
    global log_txt
    
    source_path = main_params[0]
    dest_path = main_params[1]
    unstack = main_params[2]
    verbose = main_params[3]
    debug = main_params[4]      
    invert = main_params[5]
    smoothing = vect_params[0]
    plot = vect_params[1]
    figure_format = vect_params[2]            
    graph_format = vect_params[3]
    dpi = vect_params[4]
    node_size = vect_params[5]
    save_distance_map = vect_params[6]
    pruning = vect_params[7]
    redundancy = vect_params[8]
    params = {'r':redundancy, 'p':pruning}
    
    if debug:
        verbose = True
    
    # Log path determination
    if manual_log_path:
        log_path = manual_log_path
    else:    
        log_path = os.path.join(dest_path, 'log.txt')
    log_txt = ''
    
        
    start = time.time()
    previous_step = start
    txt = 'VECT> Initialization...'
    log_txt = nu.printAndUpdateLog(txt, log_txt, verbose)
    
    # Creation of a list of the images to vectorize
    images = []
    if os.path.exists(source_path):    
        if os.path.isdir(source_path):        
            with os.scandir(source_path) as dirIt:
                for entry in dirIt:
                    if os.path.isfile(entry):                        
                        img_name = os.path.splitext(os.path.basename(entry.path))[0]
                        images.append((entry.path, img_name))
            images.sort(key = operator.itemgetter(1))
        else:
            img_name = os.path.splitext(os.path.basename(source_path))[0]
            images.append((source_path, img_name))
    else:
        txt = ('The source_path given as parameter does not refer to '
               'an existing path.')
        log_txt += txt
        nu.writeLogAndExit(log_path, log_txt, txt)
    
    if debug:
        txt = 'VECT>     Number of images to vectorize: {}'.format(len(images))
        log_txt = nu.printAndUpdateLog(txt, log_txt, verbose)
        for img in images:
            txt = 'VECT>     {}'.format(img)
            log_txt = nu.printAndUpdateLog(txt, log_txt, verbose)
    
    # Creation of the dest directory if it doesn't exist
    if not os.path.exists(dest_path):
        os.mkdir(dest_path)
    
    # Creation of slices directory if necessary
    if unstack:
        slices_path = os.path.join(dest_path, 'unstacked_slices')
        if not os.path.exists(slices_path):
            os.mkdir(slices_path)
   
    timer = time.time()
    txt = 'VECT> ...done in {:.4f} s.'.format(timer-previous_step)
    log_txt = nu.printAndUpdateLog(txt, log_txt, verbose)
    previous_step = timer
    
    current_img = 1           
    for img in images:
        
        start_vect = time.time()
        txt = ('VECT> Vectorization of image {} ({} of {})...'
              .format(img[1], current_img, len(images)))
        log_txt = nu.printAndUpdateLog(txt, log_txt, verbose)
        txt = 'VECT>    Image loading and slicing...'
        log_txt = nu.printAndUpdateLog(txt, log_txt, verbose)
        
        im = tifffile.imread(img[0]) # loading the image as a numpy array
        im = np.array(im, dtype=np.uint8) # dtype safeguard
        
        if debug:            
            txt = 'VECT>      Image number of dimensions: {}'.format(im.ndim)
            log_txt = nu.printAndUpdateLog(txt, log_txt, verbose)
            txt = 'VECT>      Image shape: {}'.format(im.shape)
            log_txt = nu.printAndUpdateLog(txt, log_txt, verbose)
                                             
        if invert:
            im = np.invert(im) # inverting the image so as to have a black background
                
        if im.ndim == 2: # if the image is a simple tif and not a stack
            slices = [im]        
        else: # if the image is a tif stack or RGB/RGBA                        
            if im.shape[-1] == 3 or im.shape[-1] == 4: # RGB/RGBA          
                txt = ('ERROR: the stack to vectorize must be binarized or '
                         'grayscale. RGB and RGBA are not supported.')
                nu.writeLogAndExit(log_path, log_txt, txt)
            else:  # stack 
                slices = [im[i] for i in range(im.shape[0])]
        
        timer = time.time()
        txt = 'VECT>    ...done in {:.4f} s.'.format(timer-previous_step)
        log_txt = nu.printAndUpdateLog(txt, log_txt, verbose)
        previous_step = timer
        
        # Iterating over the slices (1 if simple tif, more if tif stack )
        for i, sli in enumerate(slices):
            
            if len(slices) == 1: # if simple tif
                sli_name = img[1]
                
            else: # if tif stack
                filling = len(str(len(slices)))
                sli_name = img[1] + '_' + str(i+1).zfill(filling)
                
                # Saving the slice as a png file for later use
                if unstack:
                    slimage = Image.fromarray(sli, mode='L')
                    slimage.save(os.path.join(slices_path, sli_name + '.png'))
                   
            # If there's no white pixel in the slice, saving empty graph and jumping directly to the next slice
            if np.sum(sli) <= 0:
                txt = ('VECT>    The slice {} of {} is empty, saving empty ' 
                      'graph and jumping to the next one.'.format(i+1, img[1]))
                log_txt = nu.printAndUpdateLog(txt, log_txt, verbose)
                G = nx.Graph()
                
                sli_name += '_graph'
                for key, value in params.items():
                    sli_name += '_' + key + str(value)
                nx.write_gpickle(G, os.path.join(dest_path, sli_name + '.gpickle'))
                continue

            start_sli = time.time()
            previous_step = start_sli        
            txt = ('VECT>    Vectorization of slice {} of {}...'
                  .format(i+1, len(slices)))
            log_txt = nu.printAndUpdateLog(txt, log_txt, verbose)
            txt = ('VECT>       Slice preparation...')
            log_txt = nu.printAndUpdateLog(txt, log_txt, verbose)
            
            if smoothing: # standard binary image noise-removal with opening followed by closing
                sli = binary_opening(sli, disk(smoothing)) # maybe remove this processing step if depicted structures are really tiny
                sli = binary_closing(sli, disk(smoothing))
                
            if debug:
                slimage = Image.fromarray(sli, mode='L')
                slimage.save(os.path.join(dest_path, sli_name + 
                                          '_processed.png'))
            
            # Creation of the distance_map
            distance_map = ndi.distance_transform_edt(sli)
            height, width = distance_map.shape    
            
            if save_distance_map:
                dist_map = distance_map.astype(np.uint32)
                dist_map = Image.fromarray(dist_map, mode='I')
                dist_map.save(os.path.join(dest_path, sli_name + '_dm.png')) # saves the distance map in case we need it later
            
            distance_map = distance_map.astype(np.int) # conversion to int for C_net_functions compatibility

            timer = time.time()            
            txt = ('VECT>       ...done in {:.4f} s.'
                  .format(timer-previous_step))
            log_txt = nu.printAndUpdateLog(txt, log_txt, verbose)
            previous_step = timer
            txt = 'VECT>       Contour extraction and thresholding...'
            log_txt = nu.printAndUpdateLog(txt, log_txt, verbose)
                
            longuest_index, flattened_contours = createContours(sli, sli_name, 
                                                                height, debug, 
                                                                dest_path, 
                                                                figure_format, 
                                                                dpi, verbose)
                
            timer = time.time()
            txt = ('VECT>       ...done in {:.4f} s.'
                   .format(timer-previous_step))
            log_txt = nu.printAndUpdateLog(txt, log_txt, verbose)
            previous_step = timer
            txt = 'VECT>       Mesh creation...'
            log_txt = nu.printAndUpdateLog(txt, log_txt, verbose)
                
            mesh_points, mesh_facets, hole_points = createMesh(longuest_index,
                                                               flattened_contours)

            timer = time.time()
            txt = ('VECT>       ...done in {:.4f} s.'
                  .format(timer-previous_step))
            log_txt = nu.printAndUpdateLog(txt, log_txt, verbose)
            previous_step = timer
            txt = 'VECT>       Triangulation...'
            log_txt = nu.printAndUpdateLog(txt, log_txt, verbose)
                
            triangulation = createTriangulation(mesh_points, mesh_facets, 
                                                hole_points)    
            
            timer = time.time()
            txt = ('VECT>       ...done in {:.4f} s.'
                  .format(timer-previous_step))
            log_txt = nu.printAndUpdateLog(txt, log_txt, verbose)
            previous_step = timer
            txt = ('VECT>       Setup of triangles and neighborhood '
                  'relations...')
            log_txt = nu.printAndUpdateLog(txt, log_txt, verbose)
        
            triangles, isolated_indices = triangleClassification(triangulation,
                                                                 debug, verbose)

            timer = time.time()
            txt = ('VECT>       ...done in {:.4f} s.'
                  .format(timer-previous_step))
            log_txt = nu.printAndUpdateLog(txt, log_txt, verbose)
            previous_step = timer
            txt = 'VECT>       Pruning...'
            log_txt = nu.printAndUpdateLog(txt, log_txt, verbose)
                
            triangles = graphPruning(triangles, height, distance_map, verbose, 
                                     debug, dest_path, sli_name, figure_format, 
                                     dpi, pruning)

            timer = time.time()
            txt = ('VECT>       ...done in {:.4f} s.'
                  .format(timer-previous_step))
            log_txt = nu.printAndUpdateLog(txt, log_txt, verbose)
            previous_step = timer
            txt = 'VECT>       Graph creation...'
            log_txt = nu.printAndUpdateLog(txt, log_txt, verbose)
    
            adjacency_matrix = nu.createTriangleAdjacencyMatrix(triangles)
            G = nu.createGraph(adjacency_matrix, triangles)
    
            timer = time.time()
            txt = ('VECT>       ...done in {:.4f} s.'
                  .format(timer-previous_step))
            log_txt = nu.printAndUpdateLog(txt, log_txt, verbose)
            previous_step = timer
            txt = ('VECT>       Removal of redundant nodes, drawing and '
                   'saving of the graph...')
            log_txt = nu.printAndUpdateLog(txt, log_txt, verbose)
    
            cleanAndSaveGraph(G, triangles, distance_map, sli_name, dest_path, 
                              verbose, debug, params, plot, figure_format, dpi, 
                              graph_format, node_size, height)

            timer = time.time()
            txt = ('VECT>       ...done in {:.4f} s.'
                   .format(timer-previous_step))
            log_txt = nu.printAndUpdateLog(txt, log_txt, verbose)
            txt = ('VECT>    ...slice {} of {} done in {:.4f} s.'
                   .format(i+1, len(slices), timer-start_sli))   
            log_txt = nu.printAndUpdateLog(txt, log_txt, verbose)    								
            
        timer = time.time()
        txt = ('VECT> ...image {} done in {:.4f} s.'
               .format(img[1], timer-start_vect))
        log_txt = nu.printAndUpdateLog(txt, log_txt, verbose)
            
        current_img += 1   

    end = time.time()-start
    txt = ('VECT> DONE in {:.0f} min {:.4f} s.'.format(end // 60,
          end % 60))    
    log_txt = nu.printAndUpdateLog(txt, log_txt, verbose)
    
    # Writing the log    
    with open(log_path, 'a+') as log:
        log.write(log_txt)


if __name__ == '__main__':
   
    main_params, vect_params = init()    
    vectorize(main_params, vect_params)   
