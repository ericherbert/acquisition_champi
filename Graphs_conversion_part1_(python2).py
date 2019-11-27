#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""
Created on Wed May 29 10:59:33 2019

Versions:
- confirmed with Python 2.7, probably with any Python 2, but NOT Python 3
- confirmed with NetworkX 1.9 and 1.11, probably with any < NetworkX 2 
- confirmed with Matplolib 2.2.3 and 2.2.4

Graphs conversion, part 1:
- unpickling of the graphs saved in Python 2 by NetworkX gpickle
- saving of the graphs by pickle for later use in Python 3

@author: Laura Xénard
"""

import os
import time

import networkx as nx
import pickle

def init():
    """
    Parameters initialization.
    
    """
    
    verbose = True # True for turning on verbose behaviour, False otherwise
    
    folder_gpickles_to_convert = '/home/hyphes/LAURA/tests/Conversion_gpickle/outputVectorisation_1705/'
    folder_pickles_to_save = '/home/hyphes/LAURA/tests/Conversion_gpickle/outputVectorisation_1705/Pickles_temp/'
       
    return verbose, folder_gpickles_to_convert, folder_pickles_to_save

def is_gpickle(path):
    """
    Checks that the element of path 'path' is a gpickle file.
    Returns True if it's a gpickle file, False otherwise.
    
    """

    fileFormat = os.path.splitext(path)[1] # extension of the file
    if fileFormat == '.gpickle':
        return True
    else:
        return False


if __name__ == "__main__":
    
    verbose, folder_gpickles_to_convert, folder_pickles_to_save = init()
    nb_gpickle = 0
    
    # Creation of the dest directory if it doesn't exist
    if not os.path.exists(folder_pickles_to_save):
        os.mkdir(folder_pickles_to_save)
    
    if verbose:
        print('Parameters: ')
        print('- folder containing the gpickles to convert: {}'
              .format(folder_gpickles_to_convert))
        print('- folder containing the newly created pickles: {}'
              .format(folder_pickles_to_save))
        start = time.time()
        print('\n Converting the gpickles...')
    
    # Computing each gpickle file, one by one
    for elt in os.listdir(folder_gpickles_to_convert):  
        if is_gpickle(elt):
            
            if verbose:
                start_elt = time.time()
                print('\tProcessing file {}...'.format(elt))
            
            nb_gpickle += 1
            path = os.path.join(folder_gpickles_to_convert, elt)
            G = nx.read_gpickle(path)
            filename = os.path.join(folder_pickles_to_save, 
                                    os.path.splitext(elt)[0] + '.pickle')
            with open(filename, 'wb') as file:
                pickle.dump([G.nodes(data=True), G.edges(data=True)], file)
                
            if verbose:
                end_elt = time.time()
                print('\t...done in {:.4f}s.'.format(end_elt-start_elt))
                
    if verbose:
        end = time.time()
        print('...conversion of {} file(s) done in {:.4f}s.'
              .format(nb_gpickle, end-start))          
