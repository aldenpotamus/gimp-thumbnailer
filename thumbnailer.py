#!/usr/bin/env python3

#Batch move commands &"<path_to_gimp>\bin\gimp-2.99.exe" -i -b '(gimp-xcf-load 1 \"<path_to_template>\")' -b '(plug-in-thumbnailer-python 1 (car (gimp-get-images)))' -b '(gimp-quit TRUE)'

import gi
gi.require_version('Gimp', '3.0')
from gi.repository import Gimp
gi.require_version('GimpUi', '3.0')
from gi.repository import GimpUi
gi.require_version('Gegl', '0.4')
from gi.repository import Gegl
from gi.repository import GObject
from gi.repository import GLib
from gi.repository import Gio

import gettext
import os
import sys
import random
import re
import json

import pygsheets
import configparser

sys.stderr = open('C:/temp/python-fu-output.txt','a')
sys.stdout=sys.stderr # So that they both go to the same file

# Set-up localization for your plug-in with your own text domain.
# This is complementary to the gimp_plug_in_set_translation_domain()
# which is only useful for the menu entries inside GIMP interface,
# whereas the below calls are used for localization within the plug-in.
textdomain = 'gimp30-thumbnailer'
# gettext.bind_textdomain_codeset(textdomain, 'UTF-8')
gettext.textdomain(textdomain)
_ = gettext.gettext
def N_(message): return message

class Thumbnailer (Gimp.PlugIn):
    def __init__(self, repeatAllowance=10, faceDefault='Faces', usedFaces=[]):
        print('Parsing config file...')
        self.CONFIG = configparser.ConfigParser()
        self.CONFIG.read('thumbnailer.ini')

        print('Connecting to gSheets...')
        gc = pygsheets.authorize(service_file=self.CONFIG['AUTHENTICATION']['serviceToken'])
        self.SHEET = gc.open_by_key(self.CONFIG['SHEET']['id'])

        self.MAIN_WORKSHEET = self.SHEET.worksheet_by_title(self.CONFIG['SHEET']['main'])
        self.THUMB_WORKSHEET = self.SHEET.worksheet_by_title(self.CONFIG['SHEET']['thumbnails'])

        print('Initializing Thumbnail Builder')

        self.__numErrors = -1
        self.__numWarnings = -1

        self.__requiredFields = ['title',
                                 'fg_color',
                                 'bg_color',
                                 'font_data']
        self.__priorityEdits = ['episode_number']
        self.usedFaces = usedFaces

        self.__repeatAllowance = repeatAllowance

        self.__layers = { 'border':                 { 'generated': True,  'layer': None },
                          'head_border':            { 'generated': True,  'layer': None },
                          'episode_number':         { 'generated': True,  'layer': None },
                          'episode_number_outline': { 'generated': True,  'layer': None },
                          'sub_text':               { 'generated': True,  'layer': None },
                          'sub_text_outline':       { 'generated': True,  'layer': None },
                          'Games':                  { 'generated': False, 'layer': None },
                          faceDefault:              { 'generated': False, 'layer': None } }

        self.__strokeBrush = '2. Hardness 100'

    ## GimpPlugIn virtual methods ##
    def do_query_procedures(self):
        return [ "plug-in-thumbnailer-python" ]

    def generateThumbnails(self, thumbs):
        self.__numErrors = 0
        self.__numWarnings = 0

        for episode in thumbs:
            # image prep
            print('Processing for '+episode['filename'])

            # Set defaults for non-required fields
            episodeParams = { 'fill_size': 2 }
            episodeParams.update(episode)
            episodeParams['episode_num_pretty'] = str(episodeParams['episode_number']).zfill(int(episodeParams['fill_size']))

            # Clear everything to write new
            self._resetThumbnail()

            # Check Required Fields
            if None in [episodeParams[x] for x in self.__requiredFields]:
                print('Missing required field: '+str([(x, getattr(self, x)) for x in self.__requiredFields if not getattr(self, x)])+'\n')
                self.__numErrors += 1
                continue

            # Parse Complex Fields
            episodeParams['font'] = episodeParams['font_data'].split(',')[0]
            episodeParams['font_color'] = episodeParams['font_data'].split(',')[1]
            episodeParams['font_size'] = int(episodeParams['font_data'].split(',')[2])
            episodeParams['font_x_offset'] = int(episodeParams['font_data'].split(',')[3])
            episodeParams['font_y_offset'] = int(episodeParams['font_data'].split(',')[4])

            episodeParams['sub_font'] = episodeParams['sub_font_data'].split(',')[0]
            episodeParams['sub_font_color'] = episodeParams['sub_font_data'].split(',')[1]
            episodeParams['sub_font_size'] = int(episodeParams['sub_font_data'].split(',')[2])
            episodeParams['sub_x_offset'] = int(episodeParams['sub_font_data'].split(',')[3])
            episodeParams['sub_y_offset'] = int(episodeParams['sub_font_data'].split(',')[4])

            # Priority Functions
            print('Processing Priority Edits')
            for functionName in [key for key in episode.keys() if key in self.__priorityEdits]:
                if '_'+functionName in dir(self):
                    getattr(self, '_'+functionName)(episodeParams)
                elif functionName not in self.__requiredFields:
                     print('\t[Skip] '+functionName+' assumed data variable.')

            # Remaining Functions
            print('Processing Remaining Edits')
            for functionName in [key for key in episode.keys() if key not in self.__priorityEdits]:
                if '_'+functionName in dir(self):
                    retVal = getattr(self, '_'+functionName)(episodeParams)
                    if retVal:  #recording any metadata from functions that have randomness
                        episodeParams['!'+functionName] = retVal
                elif functionName not in self.__requiredFields:
                    print('\t[Skip] '+functionName+' assumed data variable.')

            print('Gathering overwrites, to record in sheet...')
            overrides = { item[0]: item[1] for item in episodeParams.items() if (item[0].startswith('!') and item[1] != '') }
            if episodeParams['use_raw'] == 'TRUE':
                overrides['use_raw'] = 'TRUE'
                overrides['raw_sub_text'] = episodeParams['sub_text']

            print('Updating core fields on main worksheet...')
            self.MAIN_WORKSHEET.update_values('A'+str(episodeParams['local_row'])+':P'+str(episodeParams['local_row']),
                                [[
                                    None, None, None, None, #Handling Checkboxes
                                    None, #Date
                                    None, #Time
                                    episodeParams['game'] if 'game' in episodeParams.keys() else '', 
                                    episodeParams['title'] if 'title' in episodeParams.keys() else '',
                                    episodeParams['episode_number'] if 'episode_number' in episodeParams.keys() else '',
                                    episodeParams['sub_text_raw'] if 'sub_text_raw' in episodeParams.keys() else '',
                                    episodeParams['reaction'] if 'reaction' in episodeParams.keys() else '',
                                    None, None, None, None,
                                    json.dumps(overrides)
                                ]])

            # finalize thumbnail to layer
            print('[Done] Finalizing Thumbnail\n')
            Gimp.displays_flush()
            self._exportImage(episodeParams)

        print('Used Faces\n'+str(self.usedFaces)+'\n')

        print('Done processing request, completed with [Errors:'+str(self.__numErrors)+' Warnings:'+str(self.__numWarnings)+']')
        Gimp.displays_flush()

    # Utility Functions
    def getDataFromSheet(self):
        print('Pulling thumbs from sheet...')

        headers = self.THUMB_WORKSHEET.get_values(start='A3', end='AL3', returnas='matrix')[0]
        thumbRows = self.THUMB_WORKSHEET.get_values(start='A5', end='AL50', returnas='matrix')

        thumbsToBuild = []
        for row in thumbRows:
            if row[0] != '' and row[0] != 'Filename':
                thumbsToBuild.append({ x.lower(): y for (x,y) in zip(headers, row) if y != ''})

        return thumbsToBuild

    @staticmethod
    def _cleanValue(value):
        iVal = None
        fVal = None

        try:
            iVal = int(value)
        except ValueError:
            pass

        try:
            fVal = float(value)
        except ValueError:
            pass

        if iVal and iVal == fVal:
            return iVal

        if fVal and fVal != iVal:
            return fVal

        return str(value)

    # tb._randomizeFace("happy", "Faces")
    def _randomizeFace(self, faceLayerName, repeat=[]):
        faceLayer = self.__image.get_layer_by_name(faceLayerName)

        if not faceLayer and not self.__layers['faces_default']['layer']:
            print("No face layers found: ["+str(self.__layers['faces_default']['layer'])+"]")
            self.__numErrors += 1
            return
        elif not faceLayer:
            print("Could not find requested reaction: ["+str(faceLayerName)+"]")
            faceLayer = self.__layers['faces_default']['layer']
            self.__numWarnings += 1

        numChildren, faceLayers = Thumbnailer._allChildren(faceLayer)
        numChildren, clearLayers = Thumbnailer._allChildren(self.__layers['faces_default']['layer'])

        for layer in clearLayers:
            if layer.is_group():
                 layer.set_visible(True)
            else:
                 layer.set_visible(False)

        validIds = [layer for layer in faceLayers if id not in repeat]
        if len(validIds) == 0:
            print("Not enough faces to satisfy request... take more photos.")
            self.__numWarnings += 1

        toUse = random.choice(Thumbnailer._layersOnly(validIds))
        toUse.set_visible(True)

        return toUse

    def _specificFace(self, specificFaceName):
        specificLayer = self.__image.get_layer_by_name(specificFaceName)

        numChildren, clearLayers = Thumbnailer._allChildren(self.__layers['faces_default']['layer'])

        for layer in clearLayers:
            if layer.is_group():
                 layer.set_visible(True)
            else:
                 layer.set_visible(False)

        specificLayer.set_visible(True)

        return specificLayer

    def _exportImage(self, params):
        new_image = self.__image.duplicate()
        layer = new_image.merge_visible_layers(Gimp.MergeType.CLIP_TO_IMAGE)
        
        # scale image => INTERPOLATION-NOHALO (3)
        Gimp.context_set_interpolation(3)
        new_image.scale(1280, 720)

        outputPath = self.CONFIG['GENERAL']['outputDir']+params['filename']+'.png'    
        file = Gio.File.new_for_path(outputPath)
        Gimp.file_save(Gimp.RunMode.NONINTERACTIVE, new_image, [layer], file)
        new_image.delete()

    def _resetThumbnail(self):
        #Reset Selection
        self.__image.get_selection().none(self.__image)

        for layerName in self.__layers.keys():
            if self.__layers[layerName]['generated']:
                print('\tClearing: '+layerName)
                self.__layers[layerName]['layer'].edit_clear()

    # Adders
    def _game(self, params):
        print('\t[Edit] Setting game background to: '+params['game'])
        gameBackground = params['!bg'] if '!bg' in params.keys() else params['game']

        backgroundExists = False
        children = self.__layers['Games']['layer'].list_children()

        for layer in children:
            if layer.get_name() == gameBackground:
                layer.set_visible(True)
                backgroundExists = True
            else:
                layer.set_visible(False)

        if not backgroundExists:
            print("No layer found that matches the game: "+str(gameBackground))
            self.__numErrors += 1

    def _episode_number(self, params):
        print('\t[Edit] Episode Number: '+str(params['episode_number']))

        Gimp.context_set_antialias(True)
        Gimp.context_set_sample_merged(False)
        Gimp.context_set_sample_transparent(True)
        Gimp.context_set_foreground(Thumbnailer._parseHex(params['font_color']))
        Gimp.context_set_background(Thumbnailer._parseHex(params['bg_color']))

        textLayer = Gimp.text_fontname(self.__image,
                                       self.__layers['episode_number']['layer'],
                                       params['font_x_offset'],
                                       params['font_y_offset'],
                                       params['episode_num_pretty'] ,
                                       0,
                                       True,
                                       params['font_size'], 0,
                                       params['font'])


        Gimp.context_set_sample_threshold(0.7)
        Gimp.context_set_sample_criterion(10) #SELECT-CRITERION-ALPHA

        Gimp.context_set_foreground(Thumbnailer._parseHex(params['fg_color']))
        Gimp.floating_sel_anchor(textLayer)
        Gimp.context_set_feather(True)
        Gimp.context_set_feather_radius(2, 2)
        self.__image.select_contiguous_color(2, self.__layers['episode_number']['layer'], 10, 10)
        self.__image.get_selection().invert(self.__image)
        self.__image.get_selection().grow(self.__image, 10)
        
        Gimp.context_set_sample_threshold(0)
        Gimp.context_set_sample_criterion(0) #SELECT-CRITERION-COMPOSITE

        self.__layers['episode_number_outline']['layer'].edit_fill(Gimp.FillType.FOREGROUND)

        Gimp.get_pdb().run_procedure('plug-in-threshold-alpha', [ Gimp.RunMode.INTERACTIVE, 
                                                                  self.__image, self.__layers['episode_number_outline']['layer'],
                                                                  0])

        Gimp.get_pdb().run_procedure('plug-in-gauss', [ Gimp.RunMode.INTERACTIVE,
                                                        self.__image,
                                                        self.__layers['episode_number_outline']['layer'],
                                                        2.0,
                                                        2.0,
                                                        0])

    def _sub_text(self, params):
        print('\t[Edit] Sub Number: '+str(params['sub_text']))

        Gimp.context_set_antialias(True)
        Gimp.context_set_sample_merged(False)
        Gimp.context_set_sample_transparent(True)

        Gimp.context_set_foreground(Thumbnailer._parseHex(params['font_color']))
        Gimp.context_set_background(Thumbnailer._parseHex(params['bg_color']))

        # Place subtext down and right of main episode
        self.__image.select_contiguous_color(2, self.__layers['episode_number']['layer'], 10, 10)
        self.__image.get_selection().invert(self.__image)
        thing, non_empty, x1, y1, x2, y2 = self.__image.get_selection().bounds(self.__image)

        fontSize = params['sub_font_size']
        bufferSize = 30

        Gimp.context_set_foreground(Thumbnailer._parseHex(params['sub_font_color']))
        textLayer = Gimp.text_fontname(self.__image,
                                       self.__layers['sub_text']['layer'],
                                       x2 + bufferSize + params['sub_x_offset'],
                                       params['sub_y_offset'],
                                       params['sub_text'],
                                       0,
                                       True,
                                       params['sub_font_size'], 0,
                                       params['sub_font'])
        Gimp.floating_sel_anchor(textLayer)
  
        Gimp.context_set_sample_threshold(0.7)
        Gimp.context_set_sample_criterion(10) #SELECT-CRITERION-ALPHA
        
        Gimp.context_set_foreground(Thumbnailer._parseHex(params['fg_color']))
        Gimp.context_set_feather(True)
        Gimp.context_set_feather_radius(2, 2)
        self.__image.select_contiguous_color(2, self.__layers['sub_text']['layer'], 10, 10)
        self.__image.get_selection().invert(self.__image)
        self.__image.get_selection().grow(self.__image, 10)
        
        Gimp.context_set_sample_threshold(0)
        Gimp.context_set_sample_criterion(0) #SELECT-CRITERION-COMPOSITE
        
        self.__layers['sub_text_outline']['layer'].edit_fill(Gimp.FillType.FOREGROUND)

        Gimp.get_pdb().run_procedure('plug-in-threshold-alpha', [ Gimp.RunMode.INTERACTIVE, 
                                                                  self.__image, self.__layers['sub_text_outline']['layer'],
                                                                  0])

        Gimp.get_pdb().run_procedure('plug-in-gauss', [ Gimp.RunMode.INTERACTIVE,
                                                        self.__image,
                                                        self.__layers['sub_text_outline']['layer'],
                                                        2.0,
                                                        2.0,
                                                        0])


    def _reaction(self, params):
        print('\t[Edit] Face Type: '+str(params['reaction']))

        if '!reaction' not in params.keys():
            print('\t\tChoosing random face from: '+str(params['reaction']))
            faceUsed = self._randomizeFace(params['reaction'], repeat=self.usedFaces[-self.__repeatAllowance:])
        else:
            print('\t\tSpecific face requested, using: '+str(params['!reaction']))
            faceUsed = self._specificFace(params['!reaction'])
        self.usedFaces += [faceUsed]

        # Dynamic based on user input
        Gimp.context_set_foreground(Thumbnailer._parseHex(params['fg_color']))  
        Gimp.context_set_background(Thumbnailer._parseHex(params['bg_color']))
        
        Gimp.context_set_antialias(True)
        Gimp.context_set_feather(True)
        Gimp.context_set_feather_radius(2, 2)
        Gimp.context_set_sample_merged(False)
        Gimp.context_set_sample_transparent(True)

        #Face Outline
        Gimp.context_set_brush_size(10.0)
        Gimp.context_set_brush_hardness(1.0)
        Gimp.context_set_brush_force(1.0)
        Gimp.context_set_sample_threshold(0.7)
        Gimp.context_set_sample_criterion(10) #SELECT-CRITERION-ALPHA
        
        color = Gimp.RGB()
        color.set(0.0, 0.0, 0.0)
        color.set_alpha(1.0)

        self.__image.select_color(2, self.__layers['faces_default']['layer'], color)
        self.__image.get_selection().invert(self.__image)
        self.__image.get_selection().grow(self.__image, 2)
        # Gimp.context_swap_colors()
        
        Gimp.context_set_foreground(Thumbnailer._parseHex("#FFFFFF"))  
        
        Gimp.context_set_line_width(100)
        self.__layers['head_border']['layer'].edit_stroke_selection()
        Gimp.get_pdb().run_procedure('plug-in-gauss', [ Gimp.RunMode.INTERACTIVE,
                                                        self.__image,
                                                        self.__layers['head_border']['layer'],
                                                        4.0,
                                                        4.0,
                                                        0])
       
        Gimp.context_set_foreground(Thumbnailer._parseHex(params['fg_color']))  
        # Gimp.context_swap_colors()

        Gimp.context_set_sample_threshold(0)
        Gimp.context_set_sample_criterion(0) #SELECT-CRITERION-COMPOSITE

        #Frame Outline
        self.__image.get_selection().all(self.__image)
        self.__image.get_selection().shrink(self.__image, 25)
        self.__image.get_selection().invert(self.__image)
        self.__layers['border']['layer'].edit_fill(Gimp.FillType.BACKGROUND)

        Gimp.get_pdb().run_procedure('plug-in-gauss', [ Gimp.RunMode.INTERACTIVE,
                                                self.__image,
                                                self.__layers['border']['layer'],
                                                16.0,
                                                16.0,
                                                0])

        self.__image.get_selection().none(self.__image)

        return faceUsed.get_name()

    @staticmethod
    def _allChildren(parent):
        result = Thumbnailer._allChildrenHelper(parent)
        
        return (len(result), result)
    
    @staticmethod
    def _allChildrenHelper(parent):
        result = []
        
        children = parent.list_children()
        for child in children:
            if child.is_group():
                result += Thumbnailer._allChildrenHelper(child)
            else:
                result += [child]
                
        return result
    
    @staticmethod
    def _layersOnly(children):
      return [child for child in children if not child.is_group()]
    
    @staticmethod
    def _safeListGet (l, idx, default):
      try:
        return l[idx]
      except IndexError:
        return default

    @staticmethod
    def _parseHex(hex):
        color = Gimp.RGB()
        rgb = tuple(int(hex.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
        color.set(float(rgb[0])/255.0, float(rgb[1])/255.0, float(rgb[2])/255.0)
        # print('Color: ('+str(color.r)+','+str(color.g)+','+str(color.b)+')')
        return color

    def do_create_procedure(self, name):
        procedure = Gimp.ImageProcedure.new(self, name,
                                            Gimp.PDBProcType.PLUGIN,
                                            self.run, None)

        procedure.set_image_types("*")
        procedure.set_sensitivity_mask (Gimp.ProcedureSensitivityMask.DRAWABLE)

        procedure.set_menu_label(N_("Generate Thumbnails"))
        procedure.set_icon_name(GimpUi.ICON_GEGL)
        procedure.add_menu_path('<Image>/Filters/Development/Thumbnailer/')

        procedure.set_documentation(N_("Thumbnailer: Template + Google sheet = Thumbnail"),
                                    N_("Thumbnailer: Template + Google sheet = Thumbnail"),
                                    name)
        procedure.set_attribution("Alden Roberts", "Alden Roberts", "2022")

        return procedure

    def run(self, procedure, run_mode, image, n_drawables, drawables, args, run_data):
        self.__image = image

        print('Collecting layer references...')
        for layerName in self.__layers.keys():
            self.__layers[layerName]['layer'] = self.__image.get_layer_by_name(layerName)
            print(self.__layers[layerName]['layer'])
        self.__layers['faces_default'] = { 'generated': False,
                                           'layer':  self.__image.get_layer_by_name(self.CONFIG['IMAGE']['facesLayer']) }

        if None in self.__layers:
            print('Missing required layers: '+str([(x, self.__layers[x]['layer']) for x in self.__layers.keys() if not self.__layers[x]['layer']])+'\n')

        thumbs = self.getDataFromSheet()
        self.generateThumbnails(thumbs)

        return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, GLib.Error())

Gimp.main(Thumbnailer.__gtype__, sys.argv)
