#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
    Part 1:
    
    New version of net_helpers, converted to Python 3.7 and modified by 
    Laura Xénard in June 2019. Only the functions used in Vectorisation.py have 
    been kept.
        
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
    
    Part 2: (line 709)
        
    Various functions that can be helpful when dealing with graphs (extracting 
    data, drawing, loading...)
    
    *****
    
    To work, this script needs custom classes and functions from the cythonized 
    helper library. To download and install this file, please follow the 
    instructions given on Jana Lasser's GitHub:
            https://github.com/JanaLasser/network_extraction
    If the link is broken but you have the network_extraction folder, navigate 
    to the /net directory and run the following line to compile your own 
    C_net_functions.so file (it is platform dependent):
            python setup_C_net_functions.py build_ext --inplace
    This should create two files: C_net_functions.so and C_net_functions.c. The 
    first you need, the latter you can safely delete.

"""


# Standard imports
import math
import operator
import os
import sys
import time

# Dependencies
import cv2
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd
from PIL import Image
import scipy
import tifffile
from tqdm import tqdm, trange

# Custom classes and functions from the cythonized helper library
from C_net_functions import CbuildTriangles, CbruteforcePruning
from C_net_functions import CcreateTriangleAdjacencyMatrix, Cpoint

# Global switches
edgesize = 0.5
plt.ioff() # turn off matplotlib interactive mode, we save everything we plot anyway


########################
# PART 1 : net_helpers #
########################

def getContours(image):
    """
    Wrapper around openCV's cv2.findContours() function 
    (see: http://docs.opencv.org/modules/imgproc/doc/
        structural_analysis_and_shape_descriptors.html#cv2.findContours)
    Sets convenient options and converts contours to a list of ndarrays.

    :param ndarray image: input image

    :return: the contours of the image
    :rtype: ndarray
    """

    image = image.astype(np.uint8)
    
    """
    if cv2.__version__ < '3.1.0' or cv2.__version__ >= '4.1.0':
        contours, hierarchy = cv2.findContours(image, cv2.RETR_CCOMP, 
                                            cv2.CHAIN_APPROX_TC89_L1)
    else:
        image, contours, hierarchy = cv2.findContours(image, cv2.RETR_CCOMP,
                                                    cv2.CHAIN_APPROX_TC89_L1)
    """
    
    # Getting contours for any version of cv2
    tmp = cv2.findContours(image, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_TC89_L1)
    contours = tmp[0] if len(tmp) == 2 else tmp[1]
    contours = np.asarray(contours)

    return contours

def flattenContours(raw_contours):
    """
    Helper function for flattening contours consisting of nested ndarrays

    :param ndarray raw_contours: the contours to flatten

    :return: the flattened contours
    :rtype: list([int, int])
    """

    converted_contours = []
    for contour in raw_contours:
        new_contour = []
        for point in contour:
            x, y = (float(point[0][0]), float(point[0][1]))
            new_point = [x, y]
            new_contour.append(new_point)
        converted_contours.append(new_contour)
    return converted_contours

def thresholdContours(contours, threshold):
    """
    Thresholds a given list of contours by length.

    :param contours: the contours to threshold
    :type contours: list([int, int])
    :param int threshold: length threshold

    :return: the filtered contours
    :rtype: list([int, int])
    """

    thresholded_contours = []
    for c, i in zip(contours, range(len(contours))):
        if (len(c) > threshold):
            thresholded_contours.append(c)
    return thresholded_contours

def roundTripConnect(start, end):
    """
    Connects the last point in a contour to the first point.

    :param int start: index of first point
    :param int end: index of last point

    :return: contours connected to a circle
    :rtype: list((int, int))
    """
    
    return [(i, i+1) for i in range(start, end)] + [(end, start)]

def getInteriorPoint(contour):
    """
    Finds an interior point in a polygon. The function gets the whole polygon.

    :param contour: contour which we want to find an interior point for
    :type contour: [int, int]

    :return: interior point
    :rtype: [int, int]
    """

    from shapely.geometry import Point
    from shapely.geometry import Polygon
    poly = Polygon(contour)

    # Checks if the center of the contour already qualifies as interior point
    x = 0
    y = 0
    for point in contour:
        x += point[0]
        y += point[1]
    x /= len(contour)
    y /= len(contour)

    center = Point(x,y)
    if center.within(poly):
        return [x, y]
    
    # If the center is no good, invokes a more sofisticated method
    p1 = Cpoint(contour[0][0], contour[0][1])
    cp = Cpoint(contour[1][0], contour[1][1])
    p2 = Cpoint(contour[2][0], contour[2][1])

    # Rotation matrix
    def rotate(angle,vec):
        angle = math.radians(angle)
        rot = np.array([math.cos(angle), -math.sin(angle), math.sin(angle), 
                        math.cos(angle)]).reshape(2, 2)
        return np.dot(rot, vec)

    N = 0.5

    seg1 = [cp.get_x()-p1.get_x(), cp.get_y()-p1.get_y()]
    seg2 = [p2.get_x()-cp.get_x(), p2.get_y()-cp.get_y()]

    # Angle between the segments
    phi_plus = math.atan2(seg2[1], seg2[0])
    phi_minus = math.atan2(seg1[1], seg1[0])
    phi = math.degrees((math.pi - phi_plus + phi_minus) % (2*math.pi))

    # Contour finding seems to not always go counter-clockwise around contours
    # which makes life difficult -> need to check if found interior point is
    # inside the polygon and if not, take 360-phi and find another point with
    # this angle
    is_interior_point = False

    #180 degree case, maybe obsolete
    if(phi == 180):
        rot_seg = rotate(90,seg2)
        int_point = [cp.get_x() - N*rot_seg[0] , cp.get_y() - N*rot_seg[1]]
        test_point = Point(int_point)

        if(not test_point.within(poly)):
            rot_seg = rotate(-90,seg2)
            int_point = [cp.get_x() - N*rot_seg[0] , cp.get_y() - N*rot_seg[1]]
            test_point = Point(int_point)

            if test_point.within(poly):
                is_interior_point = True

            # If nothing else helps: find interior point by sampling all points
            # on a circle with radius N with 1 degree difference
            else:
                angle = 0
                while (is_interior_point == False and angle < 361):
                    rot_seg = rotate(angle,seg2)
                    int_point = [cp.get_x() + N*rot_seg[0],
                                 cp.get_y() +N*rot_seg[1]]
                    test_point = Point(int_point)
                    angle +=1
                    if test_point.within(poly):
                        is_interior_point = True

    else:
        # "normal" case
        rot_seg = rotate(0.5*phi, seg2)
        int_point = [cp.get_x() + N*rot_seg[0], cp.get_y() + N*rot_seg[1]]
        test_point = Point(int_point)

        if(not test_point.within(poly)):
            rot_seg = rotate(-0.5*phi, seg2)
            int_point = [cp.get_x() + N*rot_seg[0], cp.get_y() + N*rot_seg[1]]

            test_point = Point(int_point)
            if test_point.within(poly):
                is_interior_point = True

            # If nothing else helps: find interior point by sampling all points
            # on a circle with radius N with 1 degree difference
            else:
                angle = 0
                while (is_interior_point == False and angle < 361):
                    rot_seg = rotate(angle, seg2)
                    int_point = [cp.get_x() + N*rot_seg[0], 
                                 cp.get_y() + N*rot_seg[1]]
                    test_point = Point(int_point)
                    angle += 1
                    if test_point.within(poly):
                        is_interior_point = True
    return (int_point[0], int_point[1])

def createTriangleAdjacencyMatrix(all_triangles):
    """
    CcreateTriangleAdjacencyMatrix wrapper from the cythonized helper library.
    """
    
    return CcreateTriangleAdjacencyMatrix(list(all_triangles))

def buildTriangles(triangulation):
    """
    CbuildTriangles wrapper from the cythonized helper library.
    """
    
    points = list(triangulation.points)
    for p in points:
        p[0] = np.round(p[0])
        p[1] = np.round(p[1])
    triangle_point_indices = list(triangulation.elements)
    return CbuildTriangles(points, triangle_point_indices)

def bruteforcePruning(triangles, order, verbose):
    """
    bruteforcePruning wrapper from the cythonized helper library.
    """
    
    return CbruteforcePruning(np.asarray(triangles), order, verbose)

def createGraph(adjacency_matrix, all_triangles):
    """
    Creates a graph from the adjacency matrix and the radii and euclidean
    distances stored in the distance map and list of all triangles.

    :param adjacency_matrix: matrix containing triangle neighborhood
        relations
    :type adjacency_matrix: lil2 matrix
    :param all_triangles: list containing all triangles still present in the 
        network
    :type all_triangles: list of triangle objects

    :return: graph of the network created from the triangle adjacency matrix
    :rtype: nx.Graph
    """

    # Creates basic graph from neighborhood relations
    G = nx.Graph(adjacency_matrix)

    # Extracts and sets x-coordinates of nodes from triangle centers
    x = [triangle.get_center().get_x() for triangle in all_triangles]
    attr = dict(zip(np.arange(len(x)), x))
    nx.set_node_attributes(G, attr, 'x')

    # Extracts and sets y-coordinates of nodes from triangle centers
    y = [triangle.get_center().get_y() for triangle in all_triangles]
    attr = dict(zip(np.arange(len(y)), y))
    nx.set_node_attributes(G, attr, 'y')

    # Extracts triangle radii and sets them as thickness for nodes
    radius_node = [triangle.get_radius() for triangle in all_triangles]
    attr = dict(zip(np.arange(len(radius_node)), radius_node))
    nx.set_node_attributes(G, attr, 'conductivity')

    # Sets thickness of edges as mean over the thickness of the nodes it connects
    radius_edge = [(G.node[edge[0]]['conductivity'] + 
                    G.node[edge[1]]['conductivity'])/2.0 for edge in G.edges()]
    attr = dict(zip(G.edges(), radius_edge))
    nx.set_edge_attributes(G, attr, 'conductivity')

    # Sets length of the edges
    length_edge = [math.sqrt((G.node[edge[0]]['x']-G.node[edge[1]]['x'])**2 + 
                             (G.node[edge[0]]['y']-G.node[edge[1]]['y'])**2 ) 
                        for edge in G.edges()]
    attr = dict(zip(G.edges(), length_edge))
    nx.set_edge_attributes(G, attr, 'weight')

    y = [triangle.get_center().get_y() for triangle in all_triangles]
    y = np.array(y)
    y = list(y)
    attr = dict(zip(np.arange(len(y)), y))
    nx.set_node_attributes(G, attr, 'y')

    return G

def removeRedundantNodes(G, verbose, mode):
    """
    Removes a specified number of redundant nodes from the graph. Nodes
    should be removed in place but the graph is returned nevertheless.

    :param nx.Graph G: graph from which the nodes are removed
    :param bool verbose: verbosity switch
    :param str mode: can be 'all' or 'half' which will remove either all nodes 
        of degree 2 or half of the nodes of degree 2. If mode is something else, 
        the function will return before the first iteration. Defaults to 'all'.

    :return: reduced graph
    :rtype: nx.Graph
    """
    
    if (type(G) == scipy.sparse.lil.lil_matrix):
        G = nx.Graph(G)
    order = G.order()
    new_order = 0
    i = 0

    while(True):
        if mode == 1:
            if i > 2:
                break
        if mode == 0:
            if new_order == order:break
        if mode == 2:
            break

        nodelist = {}
        for node in G.nodes():
            neighbors = list(G.neighbors(node))
            if(len(neighbors)==2):
                n1 = neighbors[0]
                n2 = neighbors[1]
                w1 = G.edges[node, n1]['weight']
                w2 = G.edges[node, n2]['weight']
                length = float(w1) + float(w2)
                
                c1 = G.edges[node, n1]['conductivity']
                c2 = G.edges[node, n2]['conductivity']
                
                # TODO: figure out why length can be zero
                if length == 0: length = 1
                radius = (c1*w1+c2*w2) / length
                G.add_edge(n1,n2, weight = length, conductivity = radius )
                if n1 not in nodelist and n2 not in nodelist:
                    nodelist.update({node:node})

        # Sometimes when the graph does not contain any branches (e.g. one
        # single line) the redundant node removal ends up with a triangle at
        # the end, god knows why. This is a dirty hack to remove one of the
        # three final nodes so a straight line is left which represents the
        # correct topology but maybe not entirely correct coordinates.
        if len(nodelist) == len(list(G.nodes()))-1:
            G.remove_node(nodelist[1])
        else:
            for node in nodelist.keys():
                G.remove_node(node)

        order = new_order
        new_order = G.order()
        if verbose:
            print("\t from removeRedundantNodes: collapsing iteration ",i)
        i += 1
        if order == new_order:
            break
    return G

def drawGraphTriangulation(G, triangles, image_name, dest, distance_map,
                           figure_format, dpi):
    """
    Draws and saves a graph and its associated triangles.
    
    :param nx.Graph G: graph to draw
    :param triangle:
    :type triangles:
    :param str img_name: the name of the image currently being worked on
    :param str dest_path: the output directory
    :param ndarray distance_map: the distance map of the image
    :param str figure_format: the wanted format for the triangulation figure 
        output 
    :param int dpi: the wanted resolution for the figure
    """
    
    plt.clf()
    ax = plt.gca()
    ax.set_aspect('equal', 'datalim')
    distance_map = np.where(distance_map > 0, (distance_map)**1.5 + 20, 0)
    ax.imshow(np.abs(distance_map-255), cmap='gray')
    plt.title('Triangulation: ' + image_name)
    colors = {'junction':['orange', 3], 'normal':['purple', 1], 
              'end':['red', 2]}

    # Normal triangles
    for i, t in enumerate(triangles):
            x = [t.get_p1().get_x(), t.get_p2().get_x(), t.get_p3().get_x(),
                 t.get_p1().get_x()]  
            y = [t.get_p1().get_y(), t.get_p2().get_y(), 
                 t.get_p3().get_y(), t.get_p1().get_y()]
            c = colors[t.get_type()][0]
            zorder = colors[t.get_type()][1]
            ax.plot(x, y, 'o', color='black', linewidth=3, zorder=zorder,
                    markersize=0.3, mew=0, alpha=1.0)
            ax.fill(x, y, facecolor=c, alpha=0.25,
                    edgecolor=c, linewidth=0.05)
            
    scale = 1
    pos = {}
    for k in G.node.keys():
        pos[k] = (G.node[k]['x']*scale, G.node[k]['y']*scale)

    widths = np.array([G[e[0]][e[1]]['conductivity'] for e in G.edges()])*scale
    widths = 15./(np.amax(widths)*13)*widths

    nx.draw_networkx_edges(G, pos=pos, width=widths, edgecolor='DimGray', 
                           alpha=0.4)
    
    colors = {3:'green', 2:'green', 1:'green'}
    for node in G.nodes(data=True):
        x = node[1]['x']*scale
        y = node[1]['y']*scale
        typ = len(list(nx.neighbors(G, node[0])))
        if typ > 3:
            typ = 3
        if typ < 4:
            c = colors[typ]
            plt.plot(x, y, '+', color=c, markersize=0.3, mec=c)
    plt.savefig(os.path.join(dest, image_name + '_graph_and_triangulation.') + 
                figure_format, bbox_inches='tight', dpi=dpi)

def _drawGraph(G, verbose, n_size, height):
    """
    Draws the leaf network using the thickness-data stored in the edges
    edges of the graph and the coordinates stored in the nodes.
    
    :param nx.GraphG: graph to be drawn
    :param bool verbose: verbosity switch
    :param n_size: the size of the nodes in the graph image
    :param int height: the image height
    """

    start = time.clock()
    scale = 1
    ax = plt.gca()
    ax.set_aspect('equal')
    plt.axis('off')
    pos = {}
    for k in G.node.keys():
        pos[k] = (G.node[k]['x']*scale, height - G.node[k]['y']*scale)
    
    # Edges drawing
    edgelist = [(e[0], e[1]) for e in G.edges(data=True) if e[2]['weight']<1000]
    widths = np.array([G[e[0]][e[1]]['conductivity'] for e in edgelist])*scale
    widths = 15. / (np.amax(widths)*2) * widths * edgesize
    nx.draw_networkx_edges(G, pos=pos, width=widths, edge_color='DarkSlateGray',
                           edgelist=edgelist)
    
    # Nodes drawing
    # TODO: find out why degrees can be > 3!
    color_dict = {3:'orange', 2:'purple', 1:'red'}
    colors = []
    for node in G.nodes():
        degree = nx.degree(G, node)
        if degree > 3:
            degree = 3
        colors.append(color_dict[degree])
    nx.draw_networkx_nodes(G, pos=pos, alpha=1,node_size=n_size,
                           node_color=colors, linewidths=0, node_shape='o')

    if verbose:
        print("\t from _drawGraph: drawing took %1.2f sec"%(time.clock()-start))

def drawAndSave(G, image_name, dest, parameters, verbose, plot, figure_format,
                dpi, graph_format, n_size, height):
    """
    Draws a graph calling the helper function _drawGraph and saves it at
    destination "dest" with the name "image_name" + "_graph"

    :param nx.Graph G: graph to be drawn
    :param str image_name: name of the input image,used for saving the plot
    :param str dest: path of the ouput directory where the drawing will be saved
    :param parameters: a dictionnary matching parameters name with their values
    :type parameters: dict{str : int}     
    :param bool verbose: verbosity switch
    :param bool plot: enables the writing of the graph and triangulation figure
    :param str figure_format: the wanted format for the graph and triangulation 
        figure output
    :param int dpi: the wanted resolution for the figure and the graph image
    :param str graph_format: the wanted format for the graph image output 
    :param int n_size: the size of the nodes in the graph image
    :param int height: the image height
    """
    
    start = time.clock()
       
    Gcc = sorted(nx.connected_component_subgraphs(G), key=len, reverse=True)
    G = Gcc[0]
        
    graph_name = image_name + '_graph'
    for key, value in zip(parameters.keys(), parameters.values()):
        graph_name += '_' + key + str(value)

    if plot:
        plt.clf()
        _drawGraph(G, verbose, n_size, height)
        plt.savefig(os.path.join(dest, graph_name + '.' + figure_format), 
                    dpi=dpi, bbox_inches='tight')

    figure_save = time.clock()
    
    if graph_format == 'gpickle':
        nx.write_gpickle(G, os.path.join(dest, graph_name + '.gpickle'), 
                         protocol=2)
        
    else: # these formats have not been tested in Python 3
        save_function_dict = {'adjlist':[nx.write_adjlist,'.adjlist'],
              'gml': [nx.write_gml,'.gml'],
              'graphml':[nx.write_graphml,'graphml'],
              'edgelist':[nx.write_edgelist,'.edgelist'],
              'yaml': [nx.write_yaml,'.yaml'],
              'weighted_edgelist': [nx.write_weighted_edgelist,'.edgelist'],
              'multiline_adjlist': [nx.write_multiline_adjlist,'.adjlist'],
              'gexf': [nx.write_gexf,'.gexf'],
              'pajek': [nx.write_pajek,'.net']}
        
        writefunc = save_function_dict[graph_format][0]
        writeformat = save_function_dict[graph_format][1]
        if graph_format in save_function_dict:
            if graph_format == 'graphml' or graph_format == 'gexf':
                G = _convertNumbers(G)
            writefunc(G, os.path.join(dest, graph_name + writeformat))
        else:
            print("Unknown graph format!")

    graph_save = time.clock()
    if verbose:
        print("\t from drawAndSave: figure saving took %1.2f sec"\
              %(figure_save-start))
        print("\t from drawAndSave: graph saving took %1.2f sec"\
              %(graph_save-figure_save))
    plt.close()

def _convertNumbers(G):
    """
    Converts the nodes and edges attributes of a graph to float. 
    
    :param nx.Graph G: the graph whose attributes must be converted to float
    
    :return: the converted graph
    :rtype: nx.Graph
    """
    
    for n in G.nodes(data=True):
        n[1]['x'] = float(n[1]['x'])
        n[1]['y'] = float(n[1]['y'])
        n[1]['conductivity'] = float(n[1]['conductivity'])
    for e in G.edges(data=True):
        e[2]['weight'] = float(e[2]['weight'])
        e[2]['conductivity'] = float(e[2]['conductivity'])
    return G

def drawTriangulation(triangles, image_name, dest, distance_map, 
                      figure_format, dpi):
    """
    Draws and saves an illustration of the triangulation. Triangles are
    already classified in end-triangles (red), normal-triangles (purple)
    and junction-triangles (orange).

    :param triangle_classes: list of lists of end-, normal and junction 
        triangles
    :param str image_name: image name, used for saving the plot
    :param str dest: path of the ouput directory where the drawing will be 
        saved
    :param ndarray distance_map: the distance map of the image
    :param str figure_format: the wanted format for the graph and triangulation 
        figure output
    :param int dpi: the wanted resolution for the figure and the graph image
    """
    
    plt.clf()
    ax = plt.gca()
    ax.set_aspect('equal', 'datalim')
    plt.title("Triangulation: " + image_name)
    colors = {"junction":["orange", 3], "normal":["purple", 1], 
              "end":["red", 2]}

    # Normal triangles
    for i, t in enumerate(triangles):
            x = [t.get_p1().get_x(), t.get_p2().get_x(),
                 t.get_p3().get_x(), t.get_p1().get_x()]
            y = [t.get_p1().get_y(), t.get_p2().get_y(), 
                 t.get_p3().get_y(), t.get_p1().get_y()]

            c = colors[t.get_type()][0]
            zorder = colors[t.get_type()][1]
            ax.plot(x, y, 'o', color=c, linewidth=3, zorder=zorder,
                     markersize=0.1, mew=0, alpha=1.0)
            ax.fill(x, y, facecolor=c, alpha=0.45,
                    edgecolor=c, linewidth=0.05)
    
    plt.gca().invert_yaxis() # because nx/plt origin = bottom left and image = top left
    plt.savefig(os.path.join(dest,image_name + "_triangulation" + '.pdf'), 
                dpi=dpi)
    plt.close()

def drawContours(height, contour_list, image_name, dest, figure_format, dpi):
    """
    Draws and saves the list of contours it is provided with.

    :param int height: the image height
    :param contour_list:
    :type contour_list: list([int, int])
    :param str image_name: image name, used for saving the plot
    :param str dest: path of the ouput directory where the drawing will be 
        saved
    :param str figure_format: the wanted format for the graph and triangulation 
        figure output
    :param int dpi: the wanted resolution for the figure and the graph image
    """
    
    from copy import deepcopy
    contour_list = deepcopy(contour_list)
    
    plt.clf()
    plt.title('Contours: ' + image_name)
    ax = plt.gca()
    ax.set_aspect('equal', 'datalim')
    coordinates = False # flag to turn on plotting of coordinates next to every contour point

    # Contours represented as circles for every point in the contour, connected by lines
    for c,i in zip(contour_list, range(len(contour_list))):
        c.append((c[0][0], c[0][1]))
        c = np.asarray(c)
        plt.plot(c[0:, 0], height-c[0:, 1], color='black', marker='o', 
                 markersize=2, mfc='FireBrick', mew = 0.1, alpha=0.7, 
                 linewidth=1)

        # Optional plotting of coordinates
        if coordinates:
            for point in c:
                coordinate_string = '(' + str(point[0]) + ',' + str(point[1]) + ')'
                plt.text(point[0], point[1], coordinate_string, fontsize=0.1)

    plt.savefig(os.path.join(dest, image_name + '_contours' + '.' 
                             + figure_format), dpi=dpi)
    plt.close()
    
    
######################
# PART 2 : utilities #
######################
    
def printAndUpdateLog(txt, log_txt, verbose):
    """
    Updates the log string 'log_txt' with the string 'txt'. If verbosity 
    behaviour is on, also prints 'txt' to the console.
    
    :param str txt: the string to add to 'log_txt'
    :param str log_txt: the log string to update
    :param bool verbose: verbosity switch to print information
        
    :return: the updated log string
    :rtype: str
    """
    
    log_txt += txt + '\n'
    if verbose:
        print(txt)   
    return log_txt  

def writeLogAndExit(log_path, log_txt, txt):
    """
    Updates the log string 'log_txt' with the string 'txt' and writes the log
    string into the log file of path 'log_path'.
    
    :param str log_path: the absolute path of the log file
    :param str log_txt: the log string to update
    :param str txt: the string to add to 'log_txt'
    """
    log_txt += txt
    with open(log_path, 'a+') as log:
        log.write(log_txt)
    sys.exit(txt)  
    
def unstackTif(img_path, ext, invert, verbose):
    """
    Unstacks a multi-page tif file and saves each page as an individual image 
    in the specified format. Confirmed supported formats: '.tif', '.tiff', 
    '.png', '.jpg', '.jpeg', '.bmp', '.pbm'.
    
    :param str img_path: the absolute path of the file to unstack
    :param str ext: the wanted format for the unstacked images (like '.tif')
    :param bool invert: True to invert the stack before processing, False otherwise
    :param bool verbose: True to activate verbose behaviour, False to deactivate
    """
    
    img_name = os.path.splitext(os.path.basename(img_path))[0]
    dest_path = os.path.join(os.path.dirname(img_path), img_name + '_unstacked')
    img_name = os.path.splitext(os.path.basename(img_path))[0]
    
    if not os.path.exists(dest_path):
        os.mkdir(dest_path)
    
    img = tifffile.imread(img_path) # loading the image as a numpy array
    img = np.array(img, dtype=np.uint8) # safeguard
    if invert:
        img = np.invert(img)                                                   
    slices = [img[i] for i in range(img.shape[0])]
    
    for i in trange(len(slices), desc='    Unstacking images', disable=verbose, 
                         unit='img', dynamic_ncols=True):
        for i, sli in enumerate(slices):            
            filling = len(str(len(slices)))
            sli_name = img_name + '_' + str(i+1).zfill(filling)
            slimage = Image.fromarray(sli, mode='L')
            slimage.save(os.path.join(dest_path, sli_name + ext))
    
def checkExtension(path, ext):
    """
    Checks if the file of path 'path' has the extension 'ext'.
    
    :param str path: the absolute path of the file to check
    :param ext: a list of string of accepted extension, like ['.tif', '.tiff']
    :type ext: list(str)
    
    :return: True if the file has the wanted extension, False otherwise
    :rtype: bool
    """
    
    fileFormat = os.path.splitext(path)[1] # extension of the file
    if fileFormat in ext:
        return True
    else:
        return False

def preloadFiles(path, ext, debug=False):
    """
    Browses a directory to find, preload and order all the files with an 
    expected extension.
    
    :param str path: absolute path of the directory to browse
    :param ext: a list of strings of accepted extension, like ['.tif', '.tiff']
    :type ext: list(str)
    
    :return: a list of tuples: (absolute path of the file, name of the file)
    :rtype: list((str, str))
    """
    
    files = []
    try:
        with os.scandir(path) as dirIt:
            for entry in dirIt:
                if checkExtension(entry, ext):                        
                    file_name = os.path.splitext(os.path.basename(entry.path))[0]
                    files.append((entry.path, file_name))
            if debug:
                print('preloadFiles> Number of files found: {}'
                      .format(len(files)))
        files.sort(key = operator.itemgetter(1)) # sorting the list by file name
    except IOError as e:
        sys.exit('preloadFiles> {}'.format(e))
    
    if debug:
        print('preloadFiles> {}'.format(files))
    
    return files
    
def createNodesCSVForTracking(graphs, dest_path, verbose):
    """
    Creates and saves a csv file of nodes coordinates (x, y, t) from a list of
    graphs.
    
    :param graphs: a list of couples of strings. The first element of the 
        couple is the absolute path of a graph, the second its name.
    :type graphs: list((str, str))
    :param str dest_path: the path of the csv file to write
    :param bool verbose: verbosity switch
    """
    
    df = pd.DataFrame() # DataFrame to hold the result
    desc = '   UTI> Extracting data from graph'
    for t, graph in enumerate(tqdm(graphs, total=len(graphs), unit='graph',
                                   desc=desc, disable=not verbose)):
        
        G = nx.read_gpickle(graph[0])
        if not nx.is_empty(G):
            dfNodesG = extractDataForCSV(G, extract_edges=False, 
                   extract_nodes=True, extract_degrees=[3], show_degrees=False)
            removeColumns(dfNodesG, ['conductivity']) # no need for this column   
            dfNodesG['t'] = t # adding time column
            df = pd.concat([df, dfNodesG], ignore_index=True) # updating the DataFrame
    
    df.to_csv(dest_path, index=False)
    
def extractDataForCSV(G, extract_edges=True, extract_nodes=True, 
                      extract_degrees=[], show_degrees=True):
    """
    Extracts DataFrames from a graph for writing into a csv file.
    
    :param nx.Graph G: the graph from which to extract data
    :param bool extract_edges: True to extract edges data, False otherwise
    :param bool extract_nodes: True to extract nodes data, False otherwise
    :param in extract_degrees: a list of the kind of nodes to extract, 
        identified by their degree. Example: 
            degrees=[] => extract all nodes
            degrees=[1] => extract only degree 1 nodes
            degrees=[1, 3] => extract nodes with degree 1 or 3
    :param bool show_degrees: True to add a column indicating the nodes degree
    
    :return: a DataFrame of edges if created, a DataFrame of nodes if created
    :rtype: pd.DataFrame or (pd.DataFrame, pd.DataFrame)
    """
    
    # Converting nodes label to successive integers for easier use
    G = nx.convert_node_labels_to_integers(G, first_label=0, 
                                               ordering='default', 
                                               label_attribute=None)   
    # Edges extraction
    if extract_edges:
        
        # Creation of a DataFrame from the edges attributes
        edges = G.edges(data=True)
        data = [x[2] for x in edges]
        dfEdges = pd.DataFrame(data)
        
        # Preparing data for the nodes coordinates
        x_node = np.fromiter(nx.get_node_attributes(G, 'x').values(), dtype=int) # list of node abscissa by node id       
        y_node = np.fromiter(nx.get_node_attributes(G, 'y').values(), dtype=int) # list of node ordinate by node id
        
        node1 = [x[0] for x in edges] # list of edges first node id
        node2 = [x[1] for x in edges] # list of edges second node id      
        
        # Adding the nodes coordinates
        dfEdges['n1_x'] = [x_node[i] for i in node1]
        dfEdges['n1_y'] = [y_node[i] for i in node1]
        dfEdges['n2_x'] = [x_node[i] for i in node2]
        dfEdges['n2_y'] = [y_node[i] for i in node2]
      
        if not extract_nodes:
            return dfEdges
        
    # Nodes extraction
    if extract_nodes:
        
        # Creation of a DataFrame from the nodes attributes
        nodes = G.nodes(data=True)
        data = [x[1] for x in nodes]       
        dfNodes = pd.DataFrame(data)

        # Adding the degree column for later selection
        degrees = np.array([degree for node, degree in nx.degree(G)], dtype=int)
        dfNodes['degree'] = degrees
        
        # Extraction of nodes of specified degree
        if len(extract_degrees) > 0: 
            dfNodes = dfNodes[dfNodes['degree'].isin(extract_degrees)]
        
        # Removing the degree column if necessary
        if not show_degrees:
            removeColumns(dfNodes, ['degree'])
                
        if not extract_edges:
            return dfNodes
    
    return dfEdges, dfNodes
               
def removeColumnsCSV(path, columns, overwrite=False):
    """
    Removes the specified columns of a csv file.
    
    :param str path: absolute path of the csv file to modify
    :param columns: list of the columns to remove
    :type columns: list(string)
    :params bool overwrite: True to overwrite the old csv with the new one, 
        False otherwise. In this case, the new csv file will be named as such: 
            oldname_minus_columnname
    """
    
    try:    
        data = pd.read_csv(path)
        
        # Removing the unwanted columns
        data = removeColumns(data, columns)
            
        # Saving the new csv
        if not overwrite:
            path = os.path.splitext(path)[0] + '_minus'
            for col in columns:
                path += '_' + col
            path += '.csv'
        data.to_csv(path, index=False)
    except IOError as e:
        sys.exit(e)
        
def removeColumns(data, columns):
    """
    Removes the specified columns of a DataFrame.
    
    :param pd.DataFrame data: the DataFrame we want to remove columns from
    :param columns: list of the columns to remove
    :type columns: list(string)
    """
    
    # Removing the unwanted columns
    for col in columns:
        data.drop(col, axis=1, inplace=True)

def drawNodesRandomColors(G, img, size, colors):
    """
    Draws the nodes of a graph on an image. The color of each node is given by
    its tag. If the tag is not listed in colors, it is added and linked with a 
    random color.
    
    :param nx.Graph G: the graph containing the nodes to draw
    :param ndarray img: the image on which to draw
    :param int size: the size of the circles to draw in pixels
    :param colors: a dictionary assigning a color to each node tag
    :type colors: dict{int: (int, int, int)}
    """
    
    G = nx.convert_node_labels_to_integers(G, first_label=0, 
                                               ordering='default', 
                                               label_attribute=None)
    
    dict_tag = nx.get_node_attributes(G, 'tag')
    
    # Nodes drawing
    for node_id, node_tag in dict_tag.items():
        
        x = int(G.node[node_id]['x'])
        y = int(G.node[node_id]['y'])
        
        if node_tag in colors:
            color = colors[node_tag]
        else:
            color = np.random.choice(range(256), 3)
            color = (int(color[0]), int(color[1]), int(color[2]))
            colors[node_tag] = color
        
        cv2.circle(img, (x, y), size, color=color, thickness=-1)
