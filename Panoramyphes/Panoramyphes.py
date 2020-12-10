#!/usr/bin/env python3

"""
This application is meant to work with a TIS Camera and two Mercury Step controllers.
It gives a "realtime" video feed of the camera (there's a really slight delay).
It can be used on a sample to take simple pictures, or tiles for a panorama. These captures
can be programmed to be made at regular intervals for a specified amount of time.

License : GNU GPLv3
Author : Laura Xénard, based on a previous version made/updated by several unknown people.


### Code tips about the use of the platine ###

The 'device' below refers to a controller.
The two controller used here are only 1 axis controllers, so the 'axis' below is always 1.
These controllers have a range of 50mm. The coordinates are in mm too.
The precision is at least 0.1 mm.

device.ACC(axis, acceleration_value) => sets the acceleration
device.MOV(axis, coordinate) => moves to the specified ABSOLUTE coordinate
device.MVR(axis, coordinate) => moves to the specified RELATIVE coordinate
device.qTMN()['axis'] => gets the minimun of the device range
device.qTMX()['axis'] => gets the maximum of the device range
device.qPOS()['axis'] => gets the current coordinate of the device

Look for examples in the code below.
"""

# TODO: 
# - there's a progress bar half implemented, but it won't break anything
# - the status bar is not perfect, it's OK for a classic use but as soon as you
# try something funny, the messages won't match

# To change the steps size on manual move: line 1000
# To change the stitching script: line 1516
# To change decimation: line 1567

# Standard imports
import datetime
import locale
import operator
import os
import re
import subprocess
import sys
import threading
import time
from queue import Queue

# Dependencies
import cv2
import numpy as np
import pause
import serial.tools.list_ports
from natsort import natsorted, ns
from pipython import GCSDevice, pitools

# PyGOject
import gi
gi.require_version('Gdk', '3.0')
gi.require_version('Gst', '1.0')
gi.require_version('Gtk', '3.0')
gi.require_version('Tcam', '0.1')
from gi.repository import Gdk, Gio, GLib, GObject, Gst, Gtk, Tcam

# Custom module (from TIS, the camera manufacturer)
from properties import PropertyDialog

locale.setlocale(locale.LC_ALL, 'en_US.utf8')

# Deactivation of DeprecationWarning because of images in MenuItem
"""
if not sys.warnoptions:
    import warnings
    warnings.filterwarnings("ignore", category=DeprecationWarning)
"""


class TisCameraWindow(Gtk.ApplicationWindow):

    def __init__(self, app):
        Gtk.ApplicationWindow.__init__(self, title='Panoramyphes', application=app)

        ## Attributes

        # GUI
        self.vbox = Gtk.VBox() # main container
        self.hbox = Gtk.HBox() # container for bottom line
        self.menubox = Gtk.HBox() # container for menubar and device serial number
        self.menubar = Gtk.MenuBar()
        self.display_widget = Gtk.Frame() # for displaying the video
        self.statusbar = Gtk.Statusbar() # for status messages and tips
        self.progressbar = Gtk.ProgressBar()
        self.sep_status = Gtk.Separator()
        self.label_coord = Gtk.Label() # for displaying platine coordinates in 'real time'
        self.context_id = self.statusbar.get_context_id('Statusbar')

        # Platine
        self.x_step = 0
        self.y_step = 0
        self.x_rangemin = gcs_x.qTMN()['1']
        self.x_rangemax = gcs_x.qTMX()['1']
        self.y_rangemin = gcs_y.qTMN()['1']
        self.y_rangemax = gcs_y.qTMX()['1']

        print('Platine state before initialization:')
        print('  coord ({}, {})'.format(self.x_rangemax - gcs_x.qPOS()['1'], gcs_y.qPOS()['1']))
        print('  x_rangemin: {}'.format(self.x_rangemin))
        print('  x_rangemax: {}'.format(self.x_rangemax))
        print('  y_rangemin: {}'.format(self.y_rangemin))
        print('  y_rangemax: {}'.format(self.y_rangemax))

        # Panorama settings (default)
        self.size_x = 1920
        self.size_y = 1200
        self.d_lx = 10 # x-size of the pano (in mm)
        self.d_ly = 10 # y-size of the pano (in mm)
        self.d_ovl = 20 # tiles overlay
        self.d_pause_img = 4 # time between 2 tiles (needed for the platine motion)
        self.d_pause_pano = 600 # time between 2 pano
        self.d_nb_pano = 250 # number of pano to do
        self.end_capture = False # flag for interrupting a capture

        # Current settings
        self.lx = self.d_lx
        self.ly = self.d_ly
        self.ovl = self.d_ovl
        self.pause_img = self.d_pause_img
        self.pause_pano = self.d_pause_pano
        self.nb_pano = self.d_nb_pano

        ## GUI

        self.set_icon_from_file('Champix/champix1.png')

        # Menu Capture
        m_capture = Gtk.MenuItem.new_with_label('Capture')
        sm_capture = Gtk.Menu()

        img = Gtk.Image()
        img.set_from_file('Champix/champminix8.png')
        sme_pano = Gtk.ImageMenuItem(label='Panoramas')
        sme_pano.set_image(img)
        sme_pano.connect('activate', self.handle_panoramas)
        sm_capture.append(sme_pano)

        img = Gtk.Image()
        img.set_from_file('Champix/champminix10.png')
        sme_pic = Gtk.ImageMenuItem(label='Pictures')
        sme_pic.set_image(img)
        sme_pic.connect('activate', self.handle_pictures)
        sm_capture.append(sme_pic)

        img = Gtk.Image()
        img.set_from_file('Champix/champminix3.png')
        sme_end = Gtk.ImageMenuItem(label='End Capture')
        sme_end.set_image(img)
        sme_end.connect('activate', self.handle_end)
        sm_capture.append(sme_end)

        m_capture.set_submenu(sm_capture)
        self.menubar.add(m_capture)

        # Menu Motion
        m_motion = Gtk.MenuItem.new_with_label('Motion')
        sm_motion = Gtk.Menu()

        img = Gtk.Image()
        img.set_from_file('Champix/champminix4.png')
        sme_auto = Gtk.ImageMenuItem(label='Auto')
        sme_auto.set_image(img)
        sme_auto.connect('activate', self.handle_autoMove)
        sm_motion.append(sme_auto)

        img = Gtk.Image()
        img.set_from_file('Champix/champminix9.png')
        sme_manual = Gtk.ImageMenuItem(label='Manual')
        sme_manual.set_image(img)
        sme_manual.connect('activate', self.handle_manualMove)
        sm_motion.append(sme_manual)

        sm_motion.append(Gtk.SeparatorMenuItem())

        img = Gtk.Image()
        img.set_from_file('Champix/champminix6.png')
        sme_origin = Gtk.ImageMenuItem(label='Go to Origin')
        sme_origin.set_image(img)
        sme_origin.connect('activate', self.handle_moveToOrigin)
        sm_motion.append(sme_origin)

        img = Gtk.Image()
        img.set_from_file('Champix/champminix2.png')
        sme_center = Gtk.ImageMenuItem(label='Go to Center')
        sme_center.set_image(img)
        sme_center.connect('activate', self.handle_moveToCenter)
        sm_motion.append(sme_center)

        m_motion.set_submenu(sm_motion)
        self.menubar.add(m_motion)

        # Menu Settings
        m_settings = Gtk.MenuItem.new_with_label('Settings')
        sm_settings = Gtk.Menu()

        img = Gtk.Image()
        img.set_from_file('Champix/champminix5.png')
        sme_cali = Gtk.ImageMenuItem(label='Platine Calibration')
        sme_cali.set_image(img)
        sme_cali.connect('activate', self.handle_calibration, True)
        sm_settings.append(sme_cali)

        sm_settings.append(Gtk.SeparatorMenuItem())

        img = Gtk.Image()
        img.set_from_file('Champix/champminix11.png')
        sme_prop = Gtk.ImageMenuItem(label='Camera Properties')
        sme_prop.set_image(img)
        sme_prop.connect('activate', self.handle_properties)
        sm_settings.append(sme_prop)

        m_settings.set_submenu(sm_settings)
        self.menubar.add(m_settings)

        # Display frame
        self.pipeline = self.create_pipeline()
        self.display_widget = self.pipeline.get_by_name('sink').get_property('widget')
        src = self.pipeline.get_by_name('src')
        src.set_state(Gst.State.READY)

        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect('message::eos', self.on_eos)

        # Attaching widgets/containers
        self.hbox.set_size_request(-1, 39)
        self.hbox.pack_start(self.statusbar, True, True, 0)
        self.hbox.pack_start(self.progressbar, False, False, 10)
        self.hbox.pack_end(self.label_coord, False, False, 8)
        self.hbox.pack_end(self.sep_status, False, False, 0)
        self.menubox.pack_start(self.menubar, False, False, 0)
        self.vbox.pack_start(self.menubox, False, False, 0)
        self.vbox.pack_start(self.display_widget, True, True, 0)
        self.vbox.pack_end(self.hbox, False, False, 0)
        self.label_coord.set_width_chars(12)
        self.add(self.vbox)

        # Displaying GUI
        self.platine_warning() # warning dialog for platine initialization
        self.statusbar.push(self.context_id, 'Welcome fellow hyphaddict!  ｡^‿^｡')
        self.set_default_size(1920, 1200) # 960, 600
        self.set_position(Gtk.WindowPosition.CENTER)
        self.show_all()
        self.progressbar.hide() # hiding progress bar while unused
        self.display_coord_timer(500)

        ## Set up

        # Setting the video stream
        src = self.pipeline.get_by_name('src')
        src.set_state(Gst.State.READY)
        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect('message::eos', self.on_eos)
        self.start_pipeline()

        # Creating temp directory for calibration
        if not os.path.isdir('temp/'):
            os.mkdir('temp/')


    ## Callbacks

    def handle_panoramas(self, widget):
        """
        Callback for the 'Panoramas' item in 'Capture' menu.
        Opens a dialog so that the user can fill in the parameters and starts the capture.
        """

        ## Dialog GUI

        dialog = Gtk.MessageDialog(parent=self,
                                   modal=True,
                                   buttons=Gtk.ButtonsType.OK_CANCEL,
                                   title='Panorama settings')
        message_id = self.statusbar.push(self.context_id, 'Please enter your panorama settings °u°')
        dialog.set_icon_from_file('Champix/champix8.png')

        # Labels
        label_lx = Gtk.Label()
        label_lx.set_markup('Lx (<i>mm</i>):')

        label_ly = Gtk.Label()
        label_ly.set_markup('Ly (<i>mm</i>):')

        label_ovl = Gtk.Label()
        label_ovl.set_markup('Overlap (<i>%</i>):')

        label_img = Gtk.Label()
        label_img.set_markup('Pause between images (<i>s</i>):')

        label_pano = Gtk.Label()
        label_pano.set_markup('Pause between panoramas (<i>s</i>):')

        # Corresponding input text fields
        entry_lx = Gtk.Entry()
        entry_lx.set_max_length(4)
        entry_lx.set_width_chars(4)
        entry_lx.set_text(str(self.d_lx))

        entry_ly = Gtk.Entry()
        entry_ly.set_max_length(4)
        entry_ly.set_width_chars(4)
        entry_ly.set_text(str(self.d_ly))

        entry_ovl = Gtk.Entry()
        entry_ovl.set_max_length(3)
        entry_ovl.set_width_chars(3)
        entry_ovl.set_text(str(self.d_ovl))

        entry_img = Gtk.Entry()
        entry_img.set_max_length(5)
        entry_img.set_width_chars(5)
        entry_img.set_text(str(self.d_pause_img))

        entry_pano = Gtk.Entry()
        entry_pano.set_max_length(5)
        entry_pano.set_width_chars(5)
        entry_pano.set_text(str(self.d_pause_pano))

        entry_nb = Gtk.Entry()
        entry_nb.set_max_length(5)
        entry_nb.set_width_chars(5)
        entry_nb.set_text(str(self.d_nb_pano))

        # Attaching labels and entries to Hbox
        hbox1 = Gtk.HBox()
        hbox1.pack_start(label_lx, False, 5, 5)
        hbox1.pack_start(entry_lx, False, False, 5)
        hbox1.pack_end(entry_ly, False, False, 5)
        hbox1.pack_end(label_ly, False, 5, 5)

        hbox2 = Gtk.HBox()
        hbox2.pack_start(label_ovl, False, 5, 5)
        hbox2.pack_start(entry_ovl, False, False, 0)

        hbox3 = Gtk.HBox()
        hbox3.pack_start(label_img, False, 5, 5)
        hbox3.pack_start(entry_img, False, False, 0)

        hbox4 = Gtk.HBox()
        hbox4.pack_start(label_pano, False, 5, 5)
        hbox4.pack_start(entry_pano, False, False, 0)

        hbox5 = Gtk.HBox()
        hbox5.pack_start(Gtk.Label.new('Number of panoramas:'), False, 5, 5)
        hbox5.pack_start(entry_nb, False, False, 0)

        hbox0 = Gtk.HBox()
        check_previous = Gtk.CheckButton.new_with_label('Load previous settings')
        hbox0.set_center_widget(check_previous)

        # Attaching to dialog window and displaying
        dialog.vbox.pack_start(hbox0, True, True, 0)
        dialog.vbox.pack_start(hbox1, True, True, 0)
        dialog.vbox.pack_start(hbox2, True, True, 0)
        dialog.vbox.pack_start(hbox3, True, True, 0)
        dialog.vbox.pack_start(hbox4, True, True, 0)
        dialog.vbox.pack_start(hbox5, True, True, 0)
        dialog.show_all()
        self.progressbar.hide() # hiding progress bar while unused

        # Handling the check button
        labels = (entry_lx, entry_ly, entry_ovl, entry_img, entry_pano, entry_nb)
        check_previous.connect("toggled", self.on_checked, labels)

        ## Handling the response

        response = dialog.run()
        if response in (Gtk.ResponseType.CANCEL, Gtk.ResponseType.DELETE_EVENT):
            self.statusbar.pop(self.context_id)
            dialog.destroy()

        else: # Gtk.ResponseType.OK
            lx = int(entry_lx.get_text())
            ly = int(entry_ly.get_text())
            ovl = float(entry_ovl.get_text())
            pause_img = float(entry_img.get_text())
            pause_pano = float(entry_pano.get_text())
            nb_pano = int(entry_nb.get_text())
            self.end_capture = False
            self.statusbar.pop(self.context_id)
            dialog.destroy()

            ## File explorer

            file_dialog = Gtk.FileChooserDialog(parent=self,
                                                title='File explorer',
                                                action=Gtk.FileChooserAction.SELECT_FOLDER)
            file_dialog.add_button(Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
            file_dialog.set_position(Gtk.WindowPosition.CENTER)
            file_dialog.set_icon_from_file('Champix/champix8.png')
            text = 'And now choose or create the folder in which to save the panoramas.'
            message_id = self.statusbar.push(self.context_id, text)

            response = file_dialog.run()

            if response in (Gtk.ResponseType.CANCEL, Gtk.ResponseType.DELETE_EVENT):
                self.statusbar.pop(self.context_id)
                file_dialog.destroy()

            else: # Gtk.ResponseType.OK

                # Saving the settings for later use
                self.lx = lx
                self.ly = ly
                self.ovl = ovl
                self.pause_img = pause_img
                self.pause_pano = pause_pano
                self.nb_pano = nb_pano

                directory = os.path.abspath(file_dialog.get_filename())
                self.statusbar.pop(self.context_id)
                file_dialog.destroy()

                # Computing the coordinates of each tile of a pano
                tiles_x, tiles_y, out_of_range = self.compute_panorama()

                # Saving the tiles coordinates to another file
                coord_path = os.path.join(directory, 'tiles_coord.txt')
                with open(coord_path, 'w') as file:
                    file.write('x\t\ty\n')
                    for x in tiles_x:
                        for y in tiles_y:
                            file.write('{}\t{}\n'.format(self.x_rangemax - x, y))

                if out_of_range: # the panorama exceeds the platine's range
                    error_dialog = Gtk.MessageDialog(parent=self,
                                                     modal=True,
                                                     message_type=Gtk.MessageType.ERROR,
                                                     buttons=Gtk.ButtonsType.OK,
                                                     title='Error',
                                                     text='Some tiles will be out of the platine\'s range.')
                    error_dialog.set_icon_from_file('Champix/champix3.png')
                    self.statusbar.pop(self.context_id)
                    self.statusbar.push(self.context_id, 'I can\'t do this panorama... ⌣_⌣')
                    error_dialog.format_secondary_text(out_of_range)
                    error_dialog.show_all()
                    error_dialog.run()
                    error_dialog.destroy()

                else: # the coordinates are valid

                    self.statusbar.pop(self.context_id)
                    self.statusbar.push(self.context_id, 'I\'m working on a capture! ^▽^')
                    t = threading.Thread(target=self.panoramas, args=[directory, tiles_x, tiles_y])
                    t.start()

    def handle_pictures(self, widget):
        """
        Callback for the 'Pictures' item in 'Capture' menu.
        Opens a dialog so that the user can fill in the parameters and starts the capture.
        """

        ## Dialog GUI

        dialog = Gtk.MessageDialog(parent=self,
                                   modal=True,
                                   buttons=Gtk.ButtonsType.OK_CANCEL,
                                   title='Pictures settings')
        dialog.set_icon_from_file('Champix/champix10.png')
        text = 'Please enter your pictures settings °u°'
        self.statusbar.push(self.context_id, text)

        # Entries and matching labels
        entry_img = Gtk.Entry()
        entry_img.set_max_length(5)
        entry_img.set_width_chars(5)
        entry_img.set_text('60')
        label_img = Gtk.Label()
        label_img.set_markup('Pause between pictures (<i>s</i>):')

        entry_nb = Gtk.Entry()
        entry_nb.set_max_length(5)
        entry_nb.set_width_chars(5)
        entry_nb.set_text('60')
        label_nb = Gtk.Label.new('Number of pictures:')

        # Attaching and displaying
        hbox_img = Gtk.HBox()
        hbox_img.pack_start(label_img, False, 5, 5)
        hbox_img.pack_end(entry_img, True, True, 0)

        hbox_nb = Gtk.HBox()
        hbox_nb.pack_start(label_nb, False, 5, 5)
        hbox_nb.pack_end(entry_nb, True, True, 0)

        dialog.vbox.pack_start(hbox_img, True, True, 0)
        dialog.vbox.pack_start(hbox_nb, True, True, 0)
        dialog.show_all()
        self.progressbar.hide() # hiding progress bar while unused

        ## Handling the response

        response = dialog.run()

        if response in (Gtk.ResponseType.CANCEL, Gtk.ResponseType.DELETE_EVENT):
            self.statusbar.pop(self.context_id)
            dialog.destroy()

        else: # Gtk.ResponseType.OK
            pause_img = int(entry_img.get_text())
            nb_img = int(entry_nb.get_text())
            self.end_capture = False
            self.statusbar.pop(self.context_id)
            dialog.destroy()

            ## File explorer

            file_dialog = Gtk.FileChooserDialog(parent=self,
                                                title='File explorer',
                                                action=Gtk.FileChooserAction.SELECT_FOLDER)
            file_dialog.add_button('Cancel', Gtk.ResponseType.CANCEL)
            file_dialog.add_button('Choose', Gtk.ResponseType.OK)
            file_dialog.set_position(Gtk.WindowPosition.CENTER)
            file_dialog.set_icon_from_file('Champix/champix10.png')
            text = 'Please choose or create the folder in which to save the pictures.'
            self.statusbar.push(self.context_id, text)

            response = file_dialog.run()

            if response in (Gtk.ResponseType.CANCEL, Gtk.ResponseType.DELETE_EVENT):
                self.statusbar.pop(self.context_id)
                file_dialog.destroy()

            else: # Gtk.ResponseType.OK
                self.progressbar.show()
                self.progressbar.set_fraction(0.5)
                self.progressbar.set_show_text(True)
                directory = os.path.abspath(file_dialog.get_filename())
                self.statusbar.pop(self.context_id)
                file_dialog.destroy()

                self.statusbar.pop(self.context_id)
                self.statusbar.push(self.context_id, 'I\'m working on a capture! ^▽^')
                t = threading.Thread(target=self.pictures, args=[pause_img, directory, nb_img])
                t.start()

    def handle_end(self, widget):
        """
        Callback for the 'End Capture' item in 'Capture' menu.
        Opens a confirmation dialog and then ends the capture.
        """

        ## Dialog GUI

        dialog = Gtk.MessageDialog(parent=self,
                                   modal=True,
                                   buttons=Gtk.ButtonsType.OK_CANCEL,
                                   title='')
        dialog.set_icon_from_file('Champix/champix3.png')

        sec_text = 'Are you sure you want to abort the capture?\nThe capture will stop at the end of the current panorama.'
        dialog.format_secondary_text(sec_text)
        
        text = 'Can\'t even work in peace >_<'
        self.statusbar.push(self.context_id, text)
        
        ## Handling the response

        response = dialog.run()

        if response == Gtk.ResponseType.CANCEL:
            self.statusbar.pop(self.context_id)
            dialog.destroy()

        else: # Gtk.ResponseType.OK
            self.end_capture = True
            self.statusbar.pop(self.context_id)
            self.statusbar.push(self.context_id, 'Just let me finish this one.')
            dialog.destroy()

    def handle_autoMove(self, widget):
        """
        Callback for the 'Auto' item in 'Motion' menu.
        Opens a dialog, and automaticaly moves the platine to the coordinates specified
        by the user.
        """

        ## Dialog GUI

        dialog = Gtk.MessageDialog(parent=self,
                                   modal=True,
                                   buttons=Gtk.ButtonsType.OK_CANCEL,
                                   title='Platine auto motion',
                                   text='Enter coordinates to go to:')
        dialog.set_icon_from_file('Champix/champix4.png')
        self.statusbar.push(self.context_id, '♪ I like to move it move it ♫')

        # Input fields, packed into a HBox to be centered
        entry_x = Gtk.Entry()
        entry_x.set_max_length(5)
        entry_x.set_width_chars(5)
        entry_x.set_placeholder_text('x')
        entry_y = Gtk.Entry()
        entry_y.set_max_length(5)
        entry_y.set_width_chars(5)
        entry_y.set_placeholder_text('y')

        coordbox = Gtk.HBox()
        coordbox.pack_start(Gtk.Label.new('('), False, False, 5)
        coordbox.pack_start(entry_x, False, False, 0)
        coordbox.pack_start(Gtk.Label.new(', '), False, False, 5)
        coordbox.pack_start(entry_y, False, False, 0)
        coordbox.pack_start(Gtk.Label.new(')'), False, False, 5)

        # Complementary text
        text = ('Range X axis: {} ‒ {}\nRange Y axis: {} ‒ {}'
                '\nAvoid full range motion, proceed in two steps.'
            .format(self.x_rangemin, self.x_rangemax, self.y_rangemin, self.y_rangemax))
        label = Gtk.Label(label=text)
        label.set_justify(Gtk.Justification.CENTER)

        # Attaching and displaying
        hbox = Gtk.HBox()
        hbox.set_center_widget(coordbox)
        dialog.vbox.pack_start(hbox, True, True, 0)
        dialog.vbox.pack_start(label, True, True, 0)
        dialog.show_all()
        self.progressbar.hide() # hiding progress bar while unused

        ## Handling the response

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            new_x = float(entry_x.get_text()) 
            new_x = self.x_rangemax - new_x # because X axis is inverted
            new_y = float(entry_y.get_text())

            # Calibrating, if not already done
            if self.x_step == 0 or self.y_step == 0:
                self.handle_calibration(widget, False)

            # Moving on X axis                
            if new_x > self.x_rangemax:
                gcs_x.MOV(1, self.x_rangemax)
            elif new_x < self.x_rangemin:
                gcs_x.MOV(1, self.x_rangemin)
            else:
                gcs_x.MOV(1, new_x)

            # Moving on Y axis
            if new_y > self.y_rangemax:
                gcs_y.MOV(1, self.y_rangemax)
            elif new_y < self.y_rangemin:
                gcs_y.MOV(1, self.y_rangemin)
            else:
                gcs_y.MOV(1, new_y)

        dialog.destroy()

        # Computing motion time
        x_distance = abs(new_x - gcs_x.qPOS()['1'])
        y_distance = abs(new_y - gcs_y.qPOS()['1'])
        print('x_distance :', x_distance)
        print('y_distance :', y_distance)
        if max(x_distance, y_distance) < 10:
            sleep_duration = 1
        else:
            sleep_duration = max(x_distance, y_distance) / 10
        print(sleep_duration)
        pause.seconds(sleep_duration)
        self.statusbar.pop(self.context_id)

    def handle_manualMove(self, widget):
        """
        Callback for the 'Manual' item in 'Motion' menu.
        Allows the user to move the platine by using key arrows.
        """

        ## Dialog GUI

        dialog = Gtk.Dialog(parent=self,
                            modal=False,
                            title='Manual Motion Mode')
        dialog.set_icon_from_file('Champix/champix9.png')
        self.statusbar.push(self.context_id, '♪ I like to move it move it ♫')

        # Content area
        box = dialog.get_content_area()

        main_text = "<span size='large' weight='bold'>Move the platine with arrow keys.</span>"
        main_label = Gtk.Label()
        main_label.set_markup(main_text)

        sec_text = ('You need to focus the camera window to move the platine.\n'
                    'Keep the <i>Ctrl</i> key pressed to move the platine with larger steps.\n\n'
                    'The menu is inactive while in manual motion mode.\n Click on <b>Cancel</b> '
                    'to exit this mode and go back to the position the platine had when this '
                    'mode was activated.\n Click on <b>Reset position</b> to go back to the '
                    'position the platine had when this mode was activated.\n Click '
                    'on <b>Exit</b> to exit this mode and stay at the current position.')
        sec_label = Gtk.Label()
        sec_label.set_markup(sec_text)
        sec_label.set_line_wrap(True)
        sec_label.set_justify(Gtk.Justification.CENTER)

        # Action area
        cancel_button = dialog.add_button('Cancel', 1)
        reset_button = dialog.add_button('Reset position', 2)
        exit_button = dialog.add_button('Exit', 3)

        # Attaching and displaying
        box.pack_start(main_label, True, True, 0)
        box.pack_start(sec_label, True, True, 5)
        dialog.set_default_size(400, 200)
        dialog.show_all()
        print('Manual motion mode activated.')
        self.progressbar.hide() # hiding progress bar while unused

        # Deactivating the menu and saving initial platine position
        self.activate_menu(dialog, False)
        x_old_coord = gcs_x.qPOS()['1']
        y_old_coord = gcs_y.qPOS()['1']

        ## Handling the response

        def handle_response(widget, do_reset, do_exit):
            """
            Callback for the manual motion mode buttons.

            :param bool do_reset: if True, reset the platine to it's previous position
            :param bool do_exit: if True, reactivate the menu bar and destroy the dialog
            """

            if do_reset:
                gcs_x.MOV(1, x_old_coord)
                gcs_y.MOV(1, y_old_coord)
                
            if do_exit:
                self.activate_menu(widget, True)
                self.disconnect(handler_id) # not watching for arrow keys input anymore
                print('Manual motion mode deactivated.')
                dialog.destroy()
            
            self.statusbar.pop(self.context_id) # clear the status bar message

        # Buttons
        dialog.connect('destroy', self.activate_menu, True)
        cancel_button.connect('clicked', handle_response, True, True)
        reset_button.connect('clicked', handle_response, True, False)
        exit_button.connect('clicked', handle_response, False, True)

        # Arrow keys
        handler_id = self.connect('key_release_event', self.on_key_press_event) # moving the platine

    def handle_moveToOrigin(self, widget):
        """
        Callback for the 'Go to Origin' item in 'Motion' menu.
        Moves the platine to the origin.
        """
        # TODO: vérifier si on ne doit pas inverser pr l'axe x ?
        gcs_x.MOV(1, self.x_rangemin)
        gcs_y.MOV(1, self.y_rangemin)
        print('The platine is now at the origin.')

    def handle_moveToCenter(self, widget):
        """
        Callback for the 'Go to Center' item in 'Motion' menu.
        Moves the platine to the origin.
        """

        center_x = (self.x_rangemax - self.x_rangemin) / 2
        center_y = (self.y_rangemax - self.y_rangemin) / 2

        gcs_x.MOV(1, center_x)
        gcs_y.MOV(1, center_y)
        print('The platine is now centered.')

    def handle_calibration(self, widget, from_menu):
        """
        Callback for the 'Platine Calibration' item in 'Settings' menu.
        Is also called before moving the platine if the platine has not already been calibrated.

        Calibrates the platine movements i.e.

        :param bool from_menu: True if the method is called when clicking on 'Platine Calibration'
            in the menu, False if it is called before moving the platine if no calibration
            has been done
        """

        # Informing the user that the platine is being calibrated
        # This is not displayed because of thread concurrency
        if from_menu:
            text = 'I\'m calibrating the platine.'
        else:
            text = 'Wait! I need to calibrate first.'
        message_id = self.statusbar.push(self.context_id, text)

        # Running calibration
        step = 0.2
        t = threading.Thread(target=self.calibration, args=[step])
        t.start()
        t.join() # waiting for the calibration end to continue

        # Checking calibration
        lower_bound = 1050
        upper_bound = 1500
        x_step_ok = (self.x_step > lower_bound and self.x_step < upper_bound)
        y_step_ok = (self.y_step > lower_bound and self.y_step < upper_bound)

        if x_step_ok and y_step_ok:
            print('Calibration successful: {}, {}'.format(str(self.x_step), str(self.y_step)))
            success_dialog = Gtk.MessageDialog(parent=self,
                                            modal=True,
                                            message_type=Gtk.MessageType.INFO,
                                            buttons=Gtk.ButtonsType.OK,
                                            title='Calibration',
                                            text='The calibration was successful.')
            success_dialog.set_icon_from_file('Champix/champix5.png')
            self.statusbar.pop(self.context_id)
            self.statusbar.push(self.context_id, 'We\'re all good!')

            cal_result = 'Results (x, y): ({}, {})'.format(self.x_step, self.y_step)
            success_dialog.format_secondary_text(cal_result)

            success_dialog.show_all()
            self.progressbar.hide() # hiding progress bar while unused
            success_dialog.run()
            self.statusbar.pop(self.context_id)
            success_dialog.destroy()
            self.statusbar.push(self.context_id, 'Time to shine!')

        else:
            error_dialog = Gtk.MessageDialog(parent=self,
                                            modal=True,
                                            message_type=Gtk.MessageType.ERROR,
                                            buttons=Gtk.ButtonsType.OK,
                                            title='Error',
                                            text='Incorrect result during calibration.')
            error_dialog.set_icon_from_file('Champix/champix3.png')
            self.statusbar.pop(self.context_id)
            self.statusbar.push(self.context_id, 'Something went wrong...  ⋋_⋌')

            cal_result = 'Results (x, y): ({}, {})'.format(self.x_step, self.y_step)
            error_dialog.format_secondary_text(cal_result)

            sec_txt = Gtk.Label()
            sec_txt.set_markup('Please check that there\'s no red lights on the PI controllers'
                                '\nand that the axis have not been inverted.\nAlso check that '
                                'the USB ports are matching those in the code.\nAs a last '
                                'resort, bring some chocolate to Eric, it <i>might</i> help.')
            sec_txt.set_line_wrap(True)
            sec_txt.set_justify(Gtk.Justification.CENTER)

            error_dialog.vbox.pack_start(sec_txt, True, True, 0)
            error_dialog.set_default_size(450, 200)
            error_dialog.show_all()
            self.progressbar.hide() # hiding progress bar while unused
            error_dialog.run()
            error_dialog.destroy()

    def handle_properties(self, widget):
        """
        Callback for the 'Camera Properties' item in 'Settings' menu.
        Opens a multi-page dialog that permits to adjust the camera properties.
        """

        src = self.pipeline.get_by_name('src')
        window = PropertyDialog(src)
        window.set_icon_from_file('Champix/champix11.png')
        window.set_default_size(600, -1)
        window.show_all()


    ## Pipeline

    def create_pipeline(self):
        """
        Builds the video capture and displays pipeline.
        """

        # Here the video capture pipeline gets created. Elements that are
        # referenced in other places in the application are given a name, so
        # that they could later be retrieved.
        #
        # The pipeline consists of the following elements:
        #
        # tcambin: This is the main capture element that handles all basic
        #   operations needed to capture video images from The Imaging Source
        #   cameras.
        #
        # queue: The queue is a FIFO buffer element. It is set to a capacity of
        #   2 buffers at maximum to prevent it from filling up indifinitely
        #   should the camera produce video frames faster than the host computer
        #   can handle. The creates a new thread on the downstream side of the
        #   pipeline so that all elements coming after the queue operate in
        #   separate thread.
        #
        # videoconvert: This element converts the videoformat coming from the
        #   camera to match the specification given by the "capsfilter" element
        #   that comes next in the pipeline
        #
        # capsfilter: This element specifies the video format. This example just
        #   specifies a BGRx pixel format which means that we just want a color
        #   image format without any preferences on width, height or framerate.
        #   The tcambin will automatically select the biggest image size
        #   supported by the device and sets the maximum frame rate allowed for
        #   this format. If the camera only supports monochrome formats they get
        #   converted to BGRx by the preceeding 'videoconvert' element.
        #
        # videoconvert: The second videoconvert element in the pipeline converts
        #   the BGRx format to a format understood by the video display element.
        #   Since the gtksink should natively support BGRx, the videoconvert
        #   element will just pass the buffers through without touching them.
        # elf.pipeline = Gst.parse_launch(('tcambin '
        #                                   + '! video/{},width={},height={},framerate={}'
        #                                   + '! videoconvert '
        #                                   + '! ximagesink').format(format, width, height, framerate))
        # gtksink: This element displays the incoming video buffers. It also
        #   stores a reference to the last buffer at any time so it could be
        #   saved as a still image

        pipeline = Gst.parse_launch(
            'tcambin name=src ! queue max_size_buffers=2 ! videoconvert ! capsfilter caps="video/x-raw,format=GRAY8" ! videoconvert ! gtksink name=sink')

        # Enable the "last-sample" support in the sink. This way the last buffer
        # seen by the display element could be retrieved when saving a still
        # image is requested
        sink = pipeline.get_by_name('sink')
        sink.set_property('enable-last-sample', True)

        return pipeline

    def start_pipeline(self):
        """
        Starts the video capture and display pipeline.
        """

        self.pipeline.set_state(Gst.State.PLAYING)
        src = self.pipeline.get_by_name('src')

        # Error dialog
        if self.pipeline.get_state(10 * Gst.SECOND)[0] != Gst.StateChangeReturn.SUCCESS:
            serial = src.get_property('serial')
            dialog = Gtk.MessageDialog(parent=self,
                                       modal=True,
                                       message_type=Gtk.MessageType.ERROR,
                                       buttons=Gtk.ButtonsType.CANCEL,
                                       title='Error',
                                       text='Failed to start the video stream.')
            dialog.set_icon_from_file('Champix/champix3.png')
            self.statusbar.push(self.context_id, 'Something went wrong...  ⋋_⋌')

            label = Gtk.Label.new('Please check that the camera is connected.')
            label.set_justify(Gtk.Justification.CENTER)
            dialog.vbox.add(label)
            dialog.show_all()
            self.progressbar.hide() # hiding progress bar while unused

            if not serial:
                dialog.format_secondary_text('No video capture device was found.')
            dialog.run()
            dialog.destroy()
            self.statusbar.push(self.context_id, 'Don\'t forget to restart me! ⊙﹏⊙')

        else: # displaying camera info at the end of the menu bar
            serial = src.get_property('serial')
            device_txt = 'Camera: {} ({})'.format(src.get_device_info(serial)[1], serial)
            self.menubox.pack_end(Gtk.Label.new(device_txt), False, False, 5)
            self.show_all()
            self.progressbar.hide() # hiding progress bar while unused

        return False

    def on_eos(self, bus, msg):
        """
        Opens a dialog to inform the user that the video capture device has been disconnected.
        """

        dialog = Gtk.MessageDialog(self, 0, Gtk.MessageType.INFO, Gtk.ButtonsType.OK,
                                   'Video stream has ended')
        dialog.format_secondary_text(
            'The video capture device got disconnected')
        dialog.run()
        self.close()


    ## Other methods

    def on_key_press_event(self, widget, event):
        """
        Callback for releasing a key arrow while in manual motion mode.
        """

        # Calibrating the platine if not already done
        if self.x_step == 0 and self.y_step == 0:
            self.handle_calibration(widget, False)

        # Defining steps size
        ctrl = (event.state & Gdk.ModifierType.CONTROL_MASK)
        if ctrl:
            step = 1
        else:
            step = 0.2

        # Keys
        if event.keyval == 65362: # up
            if gcs_y.qPOS()['1'] + step > self.y_rangemax:
                gcs_y.MOV(1, self.y_rangemax)
                text = 'I can\'t move further, I\'ve reached the top edge ´･_･`'
                self.statusbar.push(self.context_id, text)
            else:
                gcs_y.MVR(1, step)

        elif event.keyval == 65363: # right
            if gcs_x.qPOS()['1'] - step < self.x_rangemin:
                gcs_x.MOV(1, self.x_rangemin)
                text = 'I can\'t move further, I\'ve reached the right edge ´･_･`'
                self.statusbar.push(self.context_id, text)
            else:
                gcs_x.MVR(1, -step)

        elif event.keyval == 65364: # down
            if gcs_y.qPOS()['1'] - step < self.y_rangemin:
                gcs_y.MOV(1, self.y_rangemin)
                text = 'I can\'t move further, I\'ve reached the bottom edge ´･_･`'
                self.statusbar.push(self.context_id, text)
            else:
                gcs_y.MVR(1, -step)

        elif event.keyval == 65361: # left
            if gcs_x.qPOS()['1'] + step > self.x_rangemax:
                gcs_x.MOV(1, self.x_rangemax)
                text = 'I can\'t move further, I\'ve reached the left edge ´･_･`'
                self.statusbar.push(self.context_id, text)
            else:
                gcs_x.MVR(1, step)

    def activate_menu(self, widget, activate):
        """
        Changes the state of the menu bar.
        When activated, the menu bar is clickable, when deactivated it is not.
        This does not work on the machine linked to the platine (Ubuntu 18.04), 
        but it works on Debian 9 and 10, I couldn't find why.

        :param bool activate: if True activate the menu bar, if False deactivate it
        """

        menu_items = self.menubar.get_children()
        for item in menu_items:
            item.set_sensitive(bool)

    def platine_warning(self):
        """
        Invokes a message dialog when launching the application to ask the user
        for platine initialization, then handles the answer accordingly.
        """

        # Creating the message dialog
        warning_dialog = Gtk.MessageDialog(parent=self,
                                           modal=True,
                                           message_type=Gtk.MessageType.WARNING,
                                           buttons=Gtk.ButtonsType.YES_NO,
                                           title='Platine initialization',
                                           text='Do you want to use the platine?')
        sub_txt = ('If you press NO and change your mind, do not forget to restart the program '
                   'and press yes or you will damage the platine.\n'
                   'If you press YES, be sure that the platine is on.')
        warning_dialog.format_secondary_text(sub_txt)
        warning_dialog.set_icon_from_file('Champix/champix7.png')

        # Handling the response
        response = warning_dialog.run()
        if response == Gtk.ResponseType.YES:
            reset_ser()
        warning_dialog.destroy()

    def display_coord_timer(self, interval):
        """
        Updates regularly the bottom right label of the GUI with the current
        platine coordinates.

        :param int interval: the time between the updates, in milliseconds
        """

        def display_coordinates():

            # The X axis is inverted:
            #   x+10 => platine goes left for the observer
            x_coord = self.x_rangemax - gcs_x.qPOS()['1'] 
            y_coord = gcs_y.qPOS()['1']

            # Observer coordinates
            self.label_coord.set_text('({:.2f}, {:.2f})'.format(x_coord, y_coord))

            # Platine internal coordinates
            #self.label_coord.set_text('({:.2f}, {:.2f})'
            #                           .format(gcs_x.qPOS()['1'], gcs_y.qPOS()['1']))

            return True

        GLib.timeout_add(interval, display_coordinates)

    def calibration(self, step):
        """
        Calibrates the platine movements, i.e. determines how many pixels a platine step
        represents, on X and Y axis.
        Moving the platine 1mm in any direction should represent a shift of 1050—1500 pixels.

        :param float step: how much the platine must move for the calibration
        """

        print('Calibration')

        for axis in ('x', 'y'):

            # Saving calibration first image
            if axis == 'x':
                path = 'temp/calibrationX_0.png'
            elif axis == 'y':
                path = 'temp/calibrationY_0.png'
            self.unique_image(path)
            print('  moving')
            if axis == 'x':
                gcs_x.MVR(1, step)
                gcs_y.MVR(1, 0)
            elif axis == 'y':
                gcs_x.MVR(1, 0)
                gcs_y.MVR(1, step)
            print('  moving done')
            pause.seconds(1)

            # Saving calibration second image
            if axis == 'x':
                path = 'temp/calibrationX_1.png'
            elif axis == 'y':
                path = 'temp/calibrationY_1.png'
            self.unique_image(path)
            print('  moving')
            if axis == 'x':
                gcs_x.MVR(1, -step)
                gcs_y.MVR(1, 0)
            elif axis == 'y':
                gcs_x.MVR(1, 0)
                gcs_y.MVR(1, -step)
            print('  moving done')
            pause.seconds(1)

            if axis == 'x':
                x_disp = displacement('temp/calibrationX_0.png', 'temp/calibrationX_1.png')[0]
            elif axis == 'y':
                y_disp = displacement('temp/calibrationY_0.png', 'temp/calibrationY_1.png')[1]

        print('  displacement in pixels (x, y): ({}, {})'.format(x_disp, y_disp))
        self.x_step = x_disp / step
        self.y_step = y_disp / step
        print('  1mm on X axis = {} pixels'.format(self.x_step))
        print('  1mm on Y axis = {} pixels'.format(self.y_step))

    def unique_image(self, path):
        """
        Saves a unique image of what the camera is currently seeing.

        :param str path: path (and name) of where to save the image
        """

        sink = self.pipeline.get_by_name('sink')
        sample = sink.get_property('last-sample')
        buffer = sample.get_buffer()
        parse_str = 'appsrc name=src ! videoconvert ! pngenc ! filesink location={}'.format(path)
        pipeline = Gst.parse_launch(parse_str)
        src = pipeline.get_by_name('src')
        src.set_property('caps', sample.get_caps())
        pipeline.set_state(Gst.State.PLAYING)
        src.emit('push-buffer', buffer)
        src.emit('end-of-stream')
        pipeline.get_state(Gst.CLOCK_TIME_NONE)
        pause.seconds(0.1)
        pipeline.set_state(Gst.State.NULL)
        pipeline.get_state(Gst.CLOCK_TIME_NONE)

    def panoramas(self, directory, tiles_x, tiles_y):
        """
        Callback for the 'OK' button of the panorama settings window.

        To save an image file, this function first gets the last video buffer
        from the display sink element. The element needs to have the
        "enable-last-buffer" set to "true" to make this functionality work.

        Then a new GStreamer pipeline is created that encodes the buffer to png
        format and saves the result to a new file.

        :param str directory: path of the directory where to save the images and log files
        :param tiles_x: list of X coordinates
        :type tiles_x: list(float)
        :param tiles_y: list of Y coordinates
        :type tiles_y: list(float)
        """
        
        # Pipeline creation
        sink = self.pipeline.get_by_name('sink')
        sample = sink.get_property('last-sample')

        tiles_folder = os.path.join(directory, 'tiles')
        if not os.path.exists(tiles_folder):
            os.mkdir(tiles_folder)
        path = os.path.join(tiles_folder, 'tile%d.png')
        log_path = os.path.join(directory, 'log.txt')

        pipeline = Gst.parse_launch('appsrc name=src  ! videoconvert ! pngenc ! multifilesink '
                                    'post-messages=true max-files=30000 location={}'.format(path))
        src = pipeline.get_by_name('src')
        src.set_property('caps', sample.get_caps())
        pipeline.set_state(Gst.State.PLAYING)

        # Creating a queue to proccess the stitching while taking pictures of the next panorama
        q = Queue()
        t = threading.Thread(target=self.worker_stitch, args=(q,))
        t.start()

        # Taking pictures of all the tiles, column by column with a snake path
        print('Panoramas capture')
        nb_tiles = len(tiles_x) * len(tiles_y)
        current_pano = 0

        for pano in range(self.nb_pano):
            
            # Checking if a capture termination has been requested
            if self.end_capture:
                self.statusbar.pop(self.context_id)
                self.statusbar.push(self.context_id, 'OK, I\'m done.')
                print('Capture termination requested by the user : finishing the current panorama.')
                break

            # Writing information about current pano
            if current_pano == 0:
            
                # Saving the parameters to a log file
                with open(log_path, 'w') as file:
                    file.write('### Parameters ###\n')
                    file.write('lx = {}\n'.format(self.lx))
                    file.write('ly = {}\n'.format(self.lx))
                    file.write('overlay = {}\n'.format(self.ovl))
                    file.write('x_number_of_tiles = {}\n'.format(len(tiles_x)))
                    file.write('y_number_of_tiles = {}\n'.format(len(tiles_y)))
                    file.write('pause_img = {}\n'.format(self.pause_img))
                    file.write('pause_pano = {}\n'.format(self.pause_pano))
                    file.write('nb_pano = {}\n'.format(self.nb_pano))
                    file.write('x_step = {}\n'.format(self.x_step))
                    file.write('y_step = {}\n'.format(self.y_step))
                    file.write('\n### Time stamps ###\n')
                    file.write('pano\ttime\n')
                    file.write('{}\t{}\n'.format(current_pano, datetime.datetime.now()))

            else:
                with open(log_path, 'a') as file:
                    file.write('{}\t{}\n'.format(current_pano, datetime.datetime.now()))

            print('Panorama {} ({} / {})'.format(current_pano, current_pano+1, self.nb_pano))
            current_tile = 0

            # Tiles processing
            for i, x in enumerate(tiles_x):
                if i % 2 == 0: # for the snake path
                    for y in tiles_y:

                        print('  tile {} ({} / {})'.format(current_tile, current_tile+1, nb_tiles))

                        # Moving the platine to the next tile
                        print('    moving...')
                        gcs_x.MOV(1, x)
                        gcs_y.MOV(1, y)
                        current_tile += 1
                        time.sleep(self.pause_img)
                        print('    ...done')

                        # Taking a picture
                        sample = sink.get_property('last-sample')
                        buffer = sample.get_buffer()
                        src.emit('push-buffer', buffer)
                        print('    picture taken')
                else:
                    for y in reversed(tiles_y):

                        print('  tile {} ({} / {})'.format(current_tile, current_tile+1, nb_tiles))

                        # Moving the platine to the next tile
                        print('    moving...')
                        gcs_x.MOV(1, x)
                        gcs_y.MOV(1, y)
                        current_tile += 1
                        time.sleep(self.pause_img)
                        print('    ...done')

                        # Taking a picture
                        sample = sink.get_property('last-sample')
                        buffer = sample.get_buffer()
                        src.emit('push-buffer', buffer)
                        print('    picture taken')

            # Going to the center between panoramas
            gcs_x.MOV(1, np.mean(tiles_x))
            gcs_y.MOV(1, np.mean(tiles_y))
            print('INTER PANO PAUSE: the platine is centered')

            # Creating a folder that will hold the stitched panorama
            pano_folder = os.path.join(directory, 'pano' +  str(current_pano))
            if not os.path.exists(pano_folder):
                os.makedirs(pano_folder)

            new_pano_start_index = current_pano * nb_tiles
            q.put((tiles_folder, 'tile', pano_folder, new_pano_start_index, tiles_x, tiles_y))
            time.sleep(self.pause_pano)

            current_pano += 1
            
        # Closing pipeline
        src.emit('end-of-stream')
        pipeline.set_state(Gst.State.NULL)
        q.put('stop')

    def compute_panorama(self):
        """
        Computes the coordinates of the tiles that make a panorama.

        :return: 2 lists of tiles coordinates (x ones and y ones), and a message to show the user
        :rtype: (list(float), list(float), str)
        """

        # How much the platine must move to cover the overlay distance
        x_ovl_step = round((self.size_x * self.ovl) / (self.x_step * 100), 2)
        y_ovl_step = round((self.size_y * self.ovl) / (self.y_step * 100), 2)
        print('x_ovl_step: {}'.format(x_ovl_step))
        print('y_ovl_step: {}'.format(y_ovl_step))

        # How much the platine must move for the camera to display a new area
        x_screen_step = round(self.size_x / self.x_step, 2)
        y_screen_step = round(self.size_y / self.y_step, 2)
        print('x_screen_step: {}'.format(x_screen_step))
        print('y_screen_step: {}'.format(y_screen_step))

        print('\nComputing tiles X')

        # Computing the x-coordinates of the tiles
        x = 0
        tiles_x = [x]
        while x < self.lx:
            # 'x_screen_step - x_ovl_step' is a step: the x-distance between 2 tiles
            x += x_screen_step - x_ovl_step
            tiles_x.append(round(x, 2))

        # If there's an even number of tiles on x_axis, the center tile will be
        # the currently displayed area shifted by half a step
        if len(tiles_x) % 2 == 0:
            shift = (x_screen_step - x_ovl_step) / 2 # half a step
            x_middle_value = tiles_x[len(tiles_x)//2]
            tiles_x = [round(i - x_middle_value + shift + gcs_x.qPOS()['1'], 2) for i in tiles_x]

        # If there's an odd number of tiles on X axis, the center tile will be
        # the currently displayed area
        else:
            x_middle_value = tiles_x[len(tiles_x)//2]
            tiles_x = [round(i - x_middle_value + gcs_x.qPOS()['1'], 2) for i in tiles_x]

        # Checking there's no out of range x-coordinates
        x_min_oor = False
        x_max_oor = False
        for x in tiles_x:
            if x < self.x_rangemin:
                x_min_oor = True
            if x > self.x_rangemax:
                x_max_oor = True

        print('Computing tiles Y')

        # Same with Y axis
        y = 0
        tiles_y = [y]
        while y < self.ly:
            y += y_screen_step - y_ovl_step
            tiles_y.append(round(y, 2))

        if len(tiles_y) % 2 == 0:
            shift = (y_screen_step - y_ovl_step) / 2
            y_middle_value = tiles_y[len(tiles_y)//2]
            tiles_y = [round(i - y_middle_value + shift + gcs_y.qPOS()['1'], 2) for i in tiles_y]
        else:
            y_middle_value = tiles_y[len(tiles_y)//2]
            tiles_y = [round(i - y_middle_value + gcs_y.qPOS()['1'], 2) for i in tiles_y]

        y_min_oor = False
        y_max_oor = False
        for y in tiles_y:
            if y < self.y_rangemin:
                y_min_oor = True
            if y > self.y_rangemax:
                y_max_oor = True

        # Callback to warn the user that there are out of range tiles coordinates
        if x_min_oor or x_max_oor or y_min_oor or y_max_oor:
            print('x_min_oor: ', x_min_oor)
            print('x_max_oor: ', x_max_oor)
            print('y_min_oor: ', y_min_oor)
            print('y_max_oor: ', y_max_oor)
            out_of_range = self.pano_out_of_range(x_min_oor, x_max_oor, y_min_oor, y_max_oor)
        else:
            out_of_range = ''

        return tiles_x, tiles_y, out_of_range

    def pano_out_of_range(self, x_min_oor, x_max_oor, y_min_oor, y_max_oor):
        """
        Determines the error message to show to the user, indicating how to move the petri dish
        in order to stay into the platine's range.

        :param bool x_min_oor: True if the panorama exceeds the platine right bound
        :param bool x_max_oor: True if the panorama exceeds the platine left bound
        :param bool y_min_oor: True if the panorama exceeds the platine bottom bound
        :param bool y_max_oor: True if the panorama exceeds the platine upper bound

        :return: the message to show to the user
        :rtype: str
        """

        # Determining where the panorama exceeds the platine's range
        oor_sum = x_min_oor + x_max_oor + y_min_oor + y_max_oor

        if oor_sum == 4: # out of range on 4 borders
            # It means that the panorama exceeds the platine's range on X and Y axis.
            sub_txt = ('The panorama is too big and can\'t fit into the platine\'s range. '
                       'You have to change your settings: reduce the size on X and Y axis. ')

        elif x_min_oor + x_max_oor == 2: # the panorama exceeds the platine's range on X axis
            sub_txt = ('The panorama is too big and can\'t fit into the platine\'s range. '
                       'You have to change your settings: reduce the size on X axis. ')

            if y_min_oor == 1:
                sub_txt += 'You also need to move the petri dish to the back of the chamber.'
            elif y_max_oor == 1:
                sub_txt += 'You also need to move the petri dish to the front of the chamber.'

        elif y_min_oor + y_max_oor == 2: # the panorama exceeds the platine's range on Y axis
            sub_txt = ('The panorama is too big and can\'t fit into the platine\'s range. '
                       'You have to change your settings: reduce the size on Y axis. ')

            # Don't forget that the X axis is inverted for the user
            if x_min_oor == 1: 
                sub_txt += 'You also need to move the petri dish to the left of the chamber.'
            elif y_max_oor == 1:
                sub_txt += 'You also need to move the petri dish to the right of the chamber.'

        elif oor_sum == 2: # out of range on 1 corner
            if x_min_oor:
                x_txt = 'left'
            elif x_max_oor:
                x_txt = 'right'

            if y_min_oor:
                y_txt = 'back'
            elif y_max_oor:
                y_txt = 'front'

            sub_txt = ('You need to move the petri dish to the {} and the {} of the chamber.'
                       .format(y_txt, x_txt))

        elif oor_sum == 1: # out of range on 1 border
            if x_min_oor:
                txt = 'left'
            elif x_max_oor:
                txt = 'right'
            elif y_min_oor:
                txt = 'back'
            elif y_max_oor:
                txt = 'front'
            sub_txt = ('You need to move the petri dish to the {} of the chamber.'.format(txt))

        return sub_txt

    def worker_stitch(self, q):
        """
        Worker for stiching tiles into a panorama.
        """

        while True:
            item = q.get()
            if item == 'stop':
                break
            directory, filename, output, index, tiles_x, tiles_y = item
            self.stitching(directory, filename, output, index, tiles_x, tiles_y)

            q.task_done()

    def stitching(self, directory, filename, output, index, tiles_x, tiles_y):
        """
        Reduces the size of some tiles and creates a panorama from those.

        :param str directory: the path of the directory where the tiles are saved
        :param str filename: the name of the panorama
        :param str output: the path of the directory where to save the panorama
        :param int index: the start index of the tiles to reduce and stitch
        :param tiles_x: list of X coordinates
        :type tiles_x: list(float)
        :param tiles_y: list of Y coordinates
        :type tiles_y: list(float)
        """

        step_x = abs(round(self.size_x * (100 - self.ovl) / (100 * self.x_step), 2))
        print('STITCHING step_x: ', step_x)
        step_y = abs(round(self.size_y * (100 - self.ovl) / (100 * self.y_step), 2))
        print('STITCHING step_y: ', step_y)
        nb_images = len(tiles_x) * len(tiles_y)
        print('STITCHING nb_images: ', nb_images)
        self.reduce_images(directory, index, nb_images) # divides the image resolution by 2

        # For better reconstruction, use the script 'stitching_script.ijm' 
        # (but it will take more time)
        # f_script = 'stitching_script.ijm'
        f_script = 'stitching_script_nocomputeoverlap.ijm'

        # Getting the data template
        with open(f_script, 'r') as f:
            filedata = f.read()

        # Creating the data file needed by imageJ script from the data template
        newdata = filedata.replace('%%x_size%%', str(len(tiles_x)))
        newdata = newdata.replace('%%y_size%%', str(len(tiles_y)))
        newdata = newdata.replace('%%overlap%%', str(int(self.ovl)))
        newdata = newdata.replace('%%directory%%', directory)
        newdata = newdata.replace('%%filename%%', filename)
        newdata = newdata.replace('%%output%%', output)
        newdata = newdata.replace('%%findex%%', str(index))

        script_path = os.path.join(output, f_script)
        with open(script_path, 'w') as f:
            f.write(newdata)

        # Calling the script
        subprocess.call(['/home/dyco/Bureau/Fiji.app/ImageJ-linux64',
                         '--headless', '-macro', script_path])

    def reduce_images(self, folder, index, nb_img):
        """
        Reduces and compresses the PNG tiles of a panorama.

        Scans the directory 'folder' for PNG files, sorts them by name and then
        reduces the images comprised in 'index' and 'index' + 'nb_img'.

        :param str folder: path of the folder to scan for PNG images
        :param int index: start index of the images to reduce
        :param int nb_img: number of images to reduce
        pas de decimation = ne pas appeler reduce_image
        """

        pause.seconds(5) # gives time for the last image(s) to be written to disk
        images = []
        try:
            with os.scandir(folder) as dirIt:
                for entry in dirIt:
                    file_format = os.path.splitext(entry)[1]
                    if file_format == '.png':
                        images.append(entry.path)
            images = natsorted(images) # sorting the list by file name
        except IOError as e:
            print('IOError when scanning folder {}: {}'.format(folder, e))

        # decimation fx=0.5 demi-taille en x
        for img in images[index:index+nb_img]:
            im1 = cv2.imread(img, cv2.IMREAD_GRAYSCALE)
            small = cv2.resize(im1, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_CUBIC)
            cv2.imwrite(img, small, [int(cv2.IMWRITE_PNG_COMPRESSION), 6])

    def pictures(self, sleep, directory, nb_pictures):
        """
        Callback for clicking on the 'Open' button when in the file explorer
        of 'Pictures settings'.
        To save an image file, this function first gets the last video buffer
        from the display sink element. The element needs to have the
        'enable-last-buffer' set to 'true' to make this functionality work.
        Then a new GStreamer pipeline is created that encodes the buffer to png
        format and saves the result to a new file.

        :param int sleep: time between two images
        :param str directory: path of the directory where to save the images and log files
        :param int nb_pictures: number of images to save
        """

        sink = self.pipeline.get_by_name('sink')
        sample = sink.get_property('last-sample')
        buffer = sample.get_buffer()

        if not os.path.exists(directory):
            os.makedirs(directory)

        path = os.path.join(directory, 'image%d.png')
        pipeline = Gst.parse_launch('appsrc name=src  ! videoconvert ! pngenc ! multifilesink '
                                    'post-messages=true max-files=30000 location={}'.format(path))
        src = pipeline.get_by_name('src')
        src.set_property('caps', sample.get_caps())
        pipeline.set_state(Gst.State.PLAYING)

        print('Pictures capture')

        j = 0
        while j < nb_pictures:

            # Checking if a capture termination has been requested
            if self.end_capture: 
                self.statusbar.pop(self.context_id)
                self.statusbar.push(self.context_id, 'OK, I\'m done.')
                print('Capture termination requested by the user : end of pictures capture.')
                break
            
            print('... picture {} ({} / {})'.format(j, j+1, nb_pictures))

            sample = sink.get_property('last-sample')
            buffer = sample.get_buffer()
            src.emit('push-buffer', buffer)
            time.sleep(sleep)
            j += 1

        src.emit('end-of-stream')
        pipeline.set_state(Gst.State.NULL)
        print('Taking {} pictures DONE'.format(nb_pictures))

    def on_checked(self, widget, data):
        """
        Callback for when checking/unchecking the 'Load previous settings' checkbox.
        """

        state = widget.get_active()

        if state: # loads the previous settings
            data[0].set_text(str(self.lx))
            data[1].set_text(str(self.ly))
            data[2].set_text(str(self.ovl))
            data[3].set_text(str(self.pause_img))
            data[4].set_text(str(self.pause_pano))
            data[5].set_text(str(self.nb_pano))

        else: # turns back to the default settings
            data[0].set_text('10')
            data[1].set_text('10')
            data[2].set_text('20')
            data[3].set_text('4')
            data[4].set_text('600')
            data[5].set_text('250')


def phase(img1, img2):
    """
    Function extracted from Tracker.py
    """

    (dY, dX) = img1.shape

    f1 = np.fft.fft2(img1)
    f2 = np.fft.fft2(img2)
    f1 = f1 / np.abs(f1)
    f2 = f2 / np.abs(f2)
    corr = f1 * np.conj(f2)

    image_back = np.abs(np.fft.ifft2(corr))

    return np.unravel_index(image_back.argmax(), image_back.shape)

def cut_and_compare(img1, img2, disx, disy):
    """
    Function extracted from Tracker.py
    """

    (Y, X) = img1.shape
    cut1 = img1[max(-disy, 0):min(Y, Y- disy), max(-disx, 0):min(X, X - disx)]
    cut2 = img2[max(disy, 0):min(Y, Y + disy), max(disx, 0):min(X, X + disx)]
    (dY, dX) = cut1.shape
    a, b = phase(cut1, cut2)
    a = abs(dY/2 - ((a + dY/2) % dY))
    b = abs(dX/2 - ((b + dX/2) % dX))
    return a, b

def displacement(image1, image2, *args, **kwargs):
    """
    Function extracted from Tracker.py
    """

    detector = kwargs.get('detector', None)
    x_val = kwargs.get('x_guess', None)
    y_val = kwargs.get('y_guess', None)

    img1 = cv2.imread(image1, 0) # queryImage
    img2 = cv2.imread(image2, 0) # trainImage

    # Initiating SIFT detector
    orb = cv2.ORB_create(nfeatures=1000, WTA_K=4, patchSize=60, edgeThreshold=0)
    if detector == 'BRISK':
        orb = cv2.BRISK_create()

    # Finding the keypoints and descriptors with SIFT
    kp1, des1 = orb.detectAndCompute(img1, None)
    kp2, des2 = orb.detectAndCompute(img2, None)

    # Creating BFMatcher object
    bf = cv2.BFMatcher(cv2.NORM_HAMMING2, crossCheck=True)

    # Matching descriptors
    matches = bf.match(des1, des2)

    # Sorting them in the order of their distance
    matches = sorted(matches, key = lambda x:x.distance)
    l = len(matches)

    x_list = np.asarray([kp1[matches[i].queryIdx].pt[0] for i in range(l)])
    y_list = np.asarray([kp1[matches[i].queryIdx].pt[1] for i in range(l)])
    x_list_2 = np.asarray([kp2[matches[i].trainIdx].pt[0] for i in range(l)])
    y_list_2 = np.asarray([kp2[matches[i].trainIdx].pt[1] for i in range(l)])
    x_l = x_list_2 - x_list
    y_l = y_list_2 - y_list

    if detector == 'Fourier':
        i = -1
        a = 300
        b = 300
        while abs(a) > 2 or abs(b) > 2:
            i += 1
            a, b = cut_and_compare(img1, img2, int(x_l[i]), int(y_l[i]))
            print('a=' + str(a) + ' b=' + str(b))
    else:
        a = []
        for i in range(5):
            a.append(np.where((np.abs(x_l - x_l[i]) < 5) * (np.abs(y_l - y_l[i]) < 5))[0].shape[0])
            i = np.argmax(a)

    x_l_3 = x_l[np.where((np.abs(x_l - x_l[i]) < 5) * (np.abs(y_l - y_l[i]) < 5))[0]]
    y_l_3 = y_l[np.where((np.abs(x_l - x_l[i]) < 5) * (np.abs(y_l - y_l[i]) < 5))[0]]

    # Draw first 10 matches.
    #img3 = cv2.drawMatches(img1,kp1,img2,kp2,matches[:5],None, flags=2)

    #plt.imshow(img3),plt.show()

    displacement_x = int(round(np.mean(x_l_3)))
    displacement_y = int(round(np.mean(y_l_3)))

    if x_val != None and y_val != None and detector != 'BRISK':
        cond1 = abs(abs(displacement_x) - abs(x_val)) > 10
        cond2 = abs(abs(displacement_y) - abs(y_val)) > 10
        if cond1 and cond2:
            print('having a doubt, verifying with BRISK')
            displacement_x, displacement_y = displacement(image1, image2, detector='BRISK')

    return displacement_x, displacement_y

def reset_ser():
    """
    Initializes the platine.
    """

    # Set servo-control "on" or "off" (closed-loop/open-loop mode)
    gcs_x.SVO(1, 1)
    gcs_y.SVO(1, 1)
    pause.seconds(1)

    # Start a reference move to the positive limit switch (needed on an old version)
    #gcs_x.FPL(1)
    #gcs_y.FPL(1)
    #pause.seconds(10)

    # Set the acceleration to use during moves of 'axes'
    gcs_x.ACC(1, 5)
    gcs_y.ACC(1, 5)
    pause.seconds(1)

    # Move 'axes' to specified absolute positions (we always use the '1' axis)
    # This is optional, but it helps not being out of range when creating panoramas
    gcs_x.MOV(1, 25)
    gcs_y.MOV(1, 25)
    pause.seconds(10)


class Application(Gtk.Application):

    def __init__(self):
        super(Application, self).__init__()
        self.windows = {}

    def do_startup(self):
        Gtk.Application.do_startup(self)
        Gst.init(sys.argv)

    def do_activate(self):
        self.tis_win = TisCameraWindow(self)

    def on_quit(self, action, param):
        self.quit()


if __name__ == '__main__':

    ## Identifying controllers
    # 16HU1CI! and 16HU1CH are the serial number of the controllers,
    # as given by the module pyserial

    # X axis
    controller_x = serial.tools.list_ports.grep('16HU1CH!')
    for item in controller_x:
        gcs_x = GCSDevice('C-663.11')
        gcs_x.ConnectRS232(item.device, baudrate=115200)
        print('X controller connected to {}'.format(item.device))

    # Y axis
    controller_y = serial.tools.list_ports.grep('16HU1CI!')
    for item in controller_y:
        gcs_y = GCSDevice('C-663.11')
        gcs_y.ConnectRS232(item.device, baudrate=115200)
        print('Y controller connected to {}'.format(item.device))


    app = Application()
    app.run(sys.argv)
    print('Panoramyphes has been closed.')
