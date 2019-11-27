#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed May 29 14:25:51 2019

Versions:
- confirmed with Python 3.7.3, probably with any Python 3, but NOT Python 2
- confirmed with NetworkX 2.3, probably with any NetworkX 2, but NOT NetworkX 1 
- confirmed with Matplotlib 3.1.1

Graphs conversion, part 2:
- unpickling of the graphs created with Graphs_conversion_part1_(python2).py
- saving of the graphs in PNG format (optional)
- inverting the y axis (optional)
- saving of the graphs by NetworkX gpickle

@author: Laura Xénard
"""

# Standard imports
import os
import time

# Dependencies
import matplotlib.pyplot as plt
import networkx as nx
import pickle

# Custom functions
import net_utilities as nu


def init():
    """
    Initializes parameters.

    folder_pickles_to_convert str: absolute path of the directory containing
        the pickle files to load and save as gpickle files in Python 3
        
    folder_gpickles_to_save str: absolute path of the directory where to save
        the Python 3 gpickle files and the optional graphes
        
    img_height int: the height of the binarized images, to invert y axis. 0 to 
        disable the inverting.
        
    verbose bool: verbosity switch
    
    save_png bool: if True, saves each converted graph as a png file but it's
        muuuuuch slower
    
    edge_size int: edges size for the graphs drawing
        
    node_size int: nodes size for the graphs drawing
    
    dpi int: resolution for the png files
    """

    folder_pickles_to_convert = '/home/hyphes/LAURA/tests/Conversion_gpickle/outputVectorisation_1705/Pickles_temp'
    folder_gpickles_to_save = '/home/hyphes/LAURA/tests/Conversion_gpickle/outputVectorisation_1705/Gpickles_converted'
    img_height = 6832
    verbose = True
    
    params = [verbose, folder_pickles_to_convert, folder_gpickles_to_save, 
              img_height]
    
    # Saving of the graphs
    save_png = True 
    edge_size = 0.5
    node_size = 8
    dpi = 2000
    
    params_img = [save_png, edge_size, node_size, dpi]
    
    return params, params_img
   
def convertAttributes(G, img_height):
    """
    Converts the keys of the nodes and edges dictionaries. Those keys represent 
    the name of the nodes and edges attributes.
    - old format, i.e when loading a graph for conversion from Python 2.7 to 
        Python 3.7: b'attribute_name'
    - new format, i.e when creating a graph with the Vectorisation.py file in 
        Python 3.7: 'attribute_name'
    It also inverts the y axis of nodes coordinates because the origin of both 
    networkx graphs and matplotlib are at the BOTTOM left. In image processing, 
    the origin of an image is always at the TOP left. So converting to avoid 
    later compatibility issues.
    
    :param nx.Graph G: the graph whose attributes we want to convert
    :param int img_height: the height of the binarized images, to invert y axis
    
    :return: a graph with converted attributes
    :rtype: nx.Graph    
    """
    
    # Getting all the nodes attributes
    node_attributes = set([k for n in G.nodes for k in G.nodes[n].keys()])
    
    # Copying the attribute values under the new_key and updating y value
    for old_key in node_attributes:
        
        nodes_attr_value = G.nodes(old_key) # getting all of the nodes value for this attribute/key
        new_key = old_key.decode('utf-8') # converting bytes string literal to string
        
        if img_height:
            if new_key == 'y': # substracting image height to invert the y axis
                nodes_attr_value = [(node[0], img_height-node[1]) for node 
                                    in nodes_attr_value]
   
        nodes_attr_value = dict(nodes_attr_value) # converting to dictionnary for an easier injecting in the graph
        nx.set_node_attributes(G, nodes_attr_value, new_key) # adding new attribute

    # Cleaning the old_key attributes
    for node, data in G.nodes(data=True):
        for old_key in node_attributes:
            data.pop(old_key, None)
    
    # Same for edges, without inverting y axis
    edges_attr = set([k for n in G.edges for k in G.edges[n].keys()])
    
    for old_key in edges_attr:
        edges_attr_value = nx.get_edge_attributes(G, old_key)
        new_key = old_key.decode('utf-8') # converting bytes string literal to string
        nx.set_edge_attributes(G, edges_attr_value, new_key)

    for node1, node2, data in G.edges(data=True):
        for old_key in edges_attr:
            data.pop(old_key, None)
        
    return G   


if __name__ == "__main__":
    
    params, params_img = init()
    verbose = params[0]
    folder_pickles_to_convert = params[1]
    folder_gpickles_to_save = params[2]
    img_height = params[3]
    save_png = params_img[0]
    edge_size = params_img[1]
    node_size = params_img[2]
    dpi = params_img[3]   
    nb_pickle = 0
    
    # Creation of the dest directory if it doesn't exist
    if not os.path.exists(folder_gpickles_to_save):
        os.mkdir(folder_gpickles_to_save)
    
    if verbose:
        print('Parameters: ')
        print('- folder containing the pickles to convert: {}'
              .format(folder_pickles_to_convert))
        print('- folder containing the newly created gpickles: {}'
              .format(folder_gpickles_to_save))
        start = time.time()
        print('\n Converting the pickles...')
    
    try:    
        with os.scandir(folder_pickles_to_convert) as dirIt:
            for entry in dirIt:
                if nu.checkExtension(entry.path, ['.pickle']):
                    
                    basename = os.path.basename(entry.path)
                    filename = os.path.splitext(basename)[0]
                    
                    # Updating filename to match new naming format and avoid confusion
                    # Old: starts at 0, new: starts at 1
                    separator = '_'
                    filename = filename.split(separator)
                    for i, part in enumerate(filename):
                        if part.isdigit():
                            part = int(part) + 1
                            filename[i] = str(part).zfill(4)
                    filename = separator.join(filename)
                    
                    if verbose:
                        start_entry = time.time()
                        print('\tProcessing file {}...'.format(basename))
                    
                    nb_pickle += 1
                    
                    with open(entry.path, 'rb') as file:
                        nodes, edges = pickle.load(file, encoding='bytes')
            
                    # Graph reconstruction
                    G = nx.Graph()
                    G.add_nodes_from(nodes)
                    G.add_edges_from(edges)
                    G = convertAttributes(G, img_height)
                    
                    if save_png:
                        
                        if verbose:
                            start_graph = time.time()
                            print('\t\tCreating and saving graph...')
                            
                        nu._drawGraph(G, node_size, edge_size, img_height)
                        png_path = os.path.join(folder_gpickles_to_save, 
                                                filename + '.png')
                        plt.savefig(png_path, dpi=dpi, bbox_inches='tight')
                        plt.close()
                        
                        if verbose:
                            end_graph = time.time()
                            print('\t\t...done in {:.4f}s.'.format(end_graph-start_graph))
                    
                    # Creation of the gpickle file                    
                    if verbose:
                            start_gpickle = time.time()
                            print('\t\tSaving gpickle...')                    
                    gpickle_path = os.path.join(folder_gpickles_to_save, 
                                                filename + '.gpickle')
                    nx.write_gpickle(G, gpickle_path)
                    
                    if verbose:
                        end_gpickle = time.time()
                        print('\t\t...done in {:.4f}s.'.format(end_gpickle-start_gpickle))
                        end_entry = time.time()
                        print('\t...done in {:.4f}s.'.format(end_entry-start_entry))

    except FileNotFoundError:
        print(False, "ERROR with the folder containing the pickle files "
              "to convert: directory not found.") 
    except NotADirectoryError:
        print(False, "ERROR with the folder containing the pickle files "
                "to convert: the specified path does not match a directory.")
        
    if verbose:
        end = time.time()
        print('...conversion of {} file(s) done in {:.4f}s.'
              .format(nb_pickle, end-start))
