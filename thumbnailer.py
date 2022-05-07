# TODO: Write back face used to the spreadsheet row and read it to avoid repeats
# Fix bug where sometimes the number outline fails (all white screen)

from __future__ import print_function

import configparser
import os.path
import random
import re
import sys

from gimpfu import *
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

sys.stderr = open('C:/temp/python-fu-output.txt','a')
sys.stdout=sys.stderr # So that they both go to the same file

class ThumbnailBuilder:
    __SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
    __SAMPLE_SPREADSHEET_ID = None
    __SAMPLE_RANGE_NAME = None

    def __init__(self, image, repeatAllowance=5, faceDefault='Faces', usedFaces=[]):
        global CONFIG
        print('Parsing config file...')
        CONFIG = configparser.ConfigParser()
        CONFIG.read('thumbnailer.ini')

        print(os.getcwd())

        self.__SAMPLE_SPREADSHEET_ID = CONFIG['GENERAL']['spreadsheetId']
        self.__SAMPLE_RANGE_NAME = CONFIG['GENERAL']['dataSheet']

        print('Initializing Thumbnail Builder')
        
        self.__image = image

        self.__numErrors = -1
        self.__numWarnings = -1
        
        self.__requiredFields = ['episode_name',
                                 'date',
                                 'fg_color',
                                 'bg_color',
                                 'font_data']
        self.__priorityEdits = ['episode_number']
        self.usedFaces = usedFaces
        
        self.__repeatAllowance = repeatAllowance

        self.__layers = { 'border':                 { 'generated': True,  'layer': None },
                          'episode_number':         { 'generated': True,  'layer': None },
                          'episode_number_outline': { 'generated': True,  'layer': None },
                          'sub_text':               { 'generated': True,  'layer': None },
                          'sub_text_outline':       { 'generated': True,  'layer': None },
                          'Games':                  { 'generated': False, 'layer': None },
                          faceDefault:              { 'generated': False, 'layer': None } }
        
        for layerName in self.__layers.keys():
            self.__layers[layerName]['layer'] = pdb.gimp_image_get_layer_by_name(self.__image, layerName)
        self.__layers['faces_default'] = { 'generated': FALSE,
                                           'layer': pdb.gimp_image_get_layer_by_name(self.__image, faceDefault) }
        
        if None in self.__layers:
            print('Missing required layers: '+str([(x, self.__layers[x]['layer']) for x in self.__layers.keys() if not self.__layers[x]['layer']])+'\n')

    def generateThumbnails(self):
        self.__numErrors = 0
        self.__numWarnings = 0
        
        print('Pulling data from google sheet')
        json = self._getDataFromSheet()
        # using poor mans dateparser to avoid dependencies
        sortedJSON = sorted(json, key = lambda i: i['date'].split('/')[2]+
                                                  i['date'].split('/')[0]+
                                                  i['date'].split('/')[1])
        
        for episode in sortedJSON:
            # image prep
            print('Processing for '+episode['episode_name'])
            
            # Set defaults for non-required fields
            episodeParams = { 'fill_size': 2 }
            episodeParams.update(episode)
            episodeParams['episode_num_pretty'] = str(episodeParams['episode_number']).zfill(episodeParams['fill_size'])
            
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
                    getattr(self, '_'+functionName)(episodeParams)
                elif functionName not in self.__requiredFields:
                     print('\t[Skip] '+functionName+' assumed data variable.')
            
            # finalize thumbnail to layer
            print('[Done] Finalizing Thumbnail\n')
            self._exportImage(episodeParams)
        
        print('Used Faces\n'+str(self.usedFaces)+'\n')
        
        print('Done processing request, completed with [Errors:'+str(self.__numErrors)+' Warnings:'+str(self.__numWarnings)+']')
    
    # Adders
    def _game(self, params):
        print('\t[Edit] Setting game background to: '+params['game'])
        
        backgroundExists = False
        children = pdb.gimp_item_get_children(self.__layers['Games']['layer'])[1]
        
        for child in children:
            layer = gimp.Item.from_id(child)
            if layer.name == params['game']:
                pdb.gimp_item_set_visible(layer, True)
                backgroundExists = True
            else:
                pdb.gimp_item_set_visible(layer, False)
        
        if not backgroundExists:
            print("No layer found that matches the game: "+str(params['game']))
            self.__numErrors += 1
    
    def _episode_number(self, params):
        print('\t[Edit] Episode Number: '+str(params['episode_number']))

        pdb.gimp_context_set_antialias(True)
        pdb.gimp_context_set_sample_merged(False)
        pdb.gimp_context_set_sample_transparent(True)

        pdb.gimp_context_set_foreground(params['font_color'])
        pdb.gimp_context_set_background(params['bg_color'])
        
        textLayer = pdb.gimp_text_fontname(self.__image,
                                           self.__layers['episode_number']['layer'],
                                           params['font_x_offset'],
                                           params['font_y_offset'],
                                           params['episode_num_pretty'] ,
                                           0,
                                           True,
                                           params['font_size'], 0,
                                           params['font'])
        pdb.gimp_context_set_foreground(params['fg_color'])
        pdb.gimp_floating_sel_anchor(textLayer)

        pdb.gimp_context_set_feather(True)
        pdb.gimp_context_set_feather_radius(2, 2)
        pdb.gimp_image_select_contiguous_color(self.__image, 2, self.__layers['episode_number']['layer'], 10, 10)
        pdb.gimp_selection_invert(self.__image)
        pdb.gimp_selection_grow(self.__image, 10)

        pdb.gimp_drawable_edit_fill(self.__layers['episode_number_outline']['layer'], 1)
    
    def _sub_text(self, params):
        print('\t[Edit] Sub Number: '+str(params['sub_text']))
        
        pdb.gimp_context_set_antialias(True)
        pdb.gimp_context_set_sample_merged(False)
        pdb.gimp_context_set_sample_transparent(True)

        pdb.gimp_context_set_foreground(params['font_color'])
        pdb.gimp_context_set_background(params['bg_color'])
        
        # Place subtext down and right of main episode
        pdb.gimp_image_select_contiguous_color(self.__image, 2, self.__layers['episode_number']['layer'], 10, 10)
        pdb.gimp_selection_invert(self.__image)
        non_empty, x1, y1, x2, y2 = pdb.gimp_selection_bounds(gimp.image_list()[0])
        
        fontSize = params['sub_font_size']
        bufferSize = 30
        
        pdb.gimp_context_set_foreground(params['sub_font_color'])
        textLayer = pdb.gimp_text_fontname(self.__image,
                                           self.__layers['sub_text']['layer'],
                                           x2 + bufferSize + params['sub_x_offset'],
                                           params['sub_y_offset'],
                                           params['sub_text'],
                                           0,
                                           True,
                                           params['sub_font_size'], 0,
                                           params['font'])
        pdb.gimp_floating_sel_anchor(textLayer)
        pdb.gimp_context_set_foreground(params['fg_color'])
        
        pdb.gimp_context_set_feather(True)
        pdb.gimp_context_set_feather_radius(2, 2)
        pdb.gimp_image_select_contiguous_color(self.__image, 2, self.__layers['sub_text']['layer'], 10, 10)
        pdb.gimp_selection_invert(self.__image)
        pdb.gimp_selection_grow(self.__image, 10)
        pdb.gimp_drawable_edit_fill(self.__layers['sub_text_outline']['layer'], 1)
        
        
    def _reaction(self, params):
        print('\t[Edit] Face Type: '+str(params['reaction']))
        
        self.usedFaces += [ self._randomizeFace(params['reaction'],
                                                repeat=self.usedFaces[-self.__repeatAllowance:]) ]
        
        # Dynamic based on user input
        pdb.gimp_context_set_foreground(params['fg_color'])
        pdb.gimp_context_set_background(params['bg_color'])
        pdb.gimp_context_set_antialias(True)
        pdb.gimp_context_set_feather(True)
        pdb.gimp_context_set_feather_radius(2, 2)
        pdb.gimp_context_set_sample_merged(False)
        pdb.gimp_context_set_sample_transparent(True)
        
        #Face Outline
        pdb.gimp_image_select_contiguous_color(self.__image, 2, self.__layers['faces_default']['layer'], 10, 10)
        pdb.gimp_selection_grow(self.__image, 10)
        pdb.gimp_selection_border(self.__image, 20)
        pdb.gimp_drawable_edit_fill(self.__layers['border']['layer'], 0)
        
        #Frame Outline
        pdb.gimp_selection_all(self.__image)
        pdb.gimp_selection_shrink(self.__image, 25)
        pdb.gimp_selection_invert(self.__image)
        pdb.gimp_drawable_edit_fill(self.__layers['border']['layer'], 0)
        
        pdb.gimp_selection_none(self.__image)
        
    # Utility Functions
    def _getDataFromSheet(self):
        creds = None
        # The file token.json stores the user's access and refresh tokens, and is
        # created automatically when the authorization flow completes for the first
        # time.
        if os.path.exists('token.json'):
            creds = Credentials.from_authorized_user_file('token.json', self.__SCOPES)
        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    CONFIG['AUTHENTICATION']['tokenPath'], self.__SCOPES)
                creds = flow.run_local_server(port=0)
            # Save the credentials for the next run
            with open('token.json', 'w') as token:
                token.write(creds.to_json())
        
        service = build('sheets', 'v4', credentials=creds)
        
        # Call the Sheets API
        sheet = service.spreadsheets()
        result = sheet.values().get(spreadsheetId=self.__SAMPLE_SPREADSHEET_ID,
                                    range=self.__SAMPLE_RANGE_NAME).execute()
        values = result.get('values', [])
        
        if not values:
            print('No data found.')
        else:
            regex = re.compile('[^a-zA-Z ]')
            
            header = [str(regex.sub('', v)).lower().replace(' ', '_') for v in values[0]]
            result = []
            skipped = []
            for row in enumerate(values[1:]):
                obj = dict([cell for cell in zip(header[1:], [ThumbnailBuilder._cleanValue(str(v)) for v in row[1][1:]]) if cell[1] is not ''])
                
                print(row[1][0])
                if str(row[1][0]) == 'FALSE':
                    result.append(obj)
                else:
                    skipped.append(row[0])
            
            print('Ingest complete, ignored rows: '+str(skipped)+'\n')
            
            return result
    
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
        faceLayer = pdb.gimp_image_get_layer_by_name(self.__image, faceLayerName)
        
        if not faceLayer and not self.__layers['faces_default']['layer']:
            print("No face layers found: ["+str(self.__layers['faces_default']['layer'])+"]")
            self.__numErrors += 1
            return
        elif not faceLayer:
            print("Could not find requested reaction: ["+str(faceLayerName)+"]")
            faceLayer = self.__layers['faces_default']['layer']
            self.__numWarnings += 1
        
        numChildren, faceIds = ThumbnailBuilder._allChildren(faceLayer)
        numChildren, clearIds = ThumbnailBuilder._allChildren(self.__layers['faces_default']['layer'])
        
        for id in clearIds:
            if pdb.gimp_item_is_group(gimp.Item.from_id(id)):
                pdb.gimp_item_set_visible(gimp.Item.from_id(id), True)
            else:
                pdb.gimp_item_set_visible(gimp.Item.from_id(id), False)
        
        validIds = [id for id in faceIds if id not in repeat]
        if len(validIds) == 0:
            print("Not enough faces to satisfy request... take more photos.")
            self.__numWarnings += 1
        
            validIds = faceIds
        
        toUse = random.choice(ThumbnailBuilder._layersOnly(validIds))
        pdb.gimp_item_set_visible(gimp.Item.from_id(toUse), True)
        
        return toUse
    
    def _exportImage(self, params):
        new_image = pdb.gimp_image_duplicate(self.__image)
        layer = pdb.gimp_image_merge_visible_layers(new_image, CLIP_TO_IMAGE)
        
        pdb.gimp_file_save(new_image, layer, CONFIG['GENERAL']['outputDir']+
                                             re.sub(r'[><:"/|?*]', '', params['filename'])+
                                             '.png', '?')
        pdb.gimp_image_delete(new_image)
    
    def _resetThumbnail(self):
        #Reset Selection
        pdb.gimp_selection_none(self.__image)
        
        for layerName in self.__layers.keys():
            if self.__layers[layerName]['generated']:
                print('\tClearing: '+layerName)
                pdb.gimp_drawable_edit_clear(self.__layers[layerName]['layer'])
    
    # ThumbnailBuilder._allChildren(pdb.gimp_image_get_layer_by_name(image, "Faces"))
    @staticmethod
    def _allChildren(parent):
        result = ThumbnailBuilder._allChildrenHelper(parent)
        
        return (len(result), result)
    
    @staticmethod
    def _allChildrenHelper(parent):
        result = []
        
        num, children = pdb.gimp_item_get_children(parent)
        for child in children:
            c = gimp.Item.from_id(child)
            if pdb.gimp_item_is_group(c):
                result += ThumbnailBuilder._allChildrenHelper(c)
            else:
                result += [child]
        
        return result
    
    @staticmethod
    def _layersOnly(child_ids):
      return [id for id in child_ids if not pdb.gimp_item_is_group(gimp.Item.from_id(id))]
    
    @staticmethod
    def _safeListGet (l, idx, default):
      try:
        return l[idx]
      except IndexError:
        return default

def thumbnailerRun(timg):
    tb = ThumbnailBuilder(timg)
    tb.generateThumbnails()
    pdb.gimp_message('done!')

register(
    "python-thumbnailer",
    "Generate thumbnails from template files & Google Sheets.",
    "Generate thumbnails from template files & Google Sheets.",
    "Alden Roberts", "Alden Roberts", "2022",
    "Thumbnailer",
    "*", # type of image it works on (*, RGB, RGB*, RGBA, GRAY etc...)
    [
        (PF_IMAGE, "image", "takes current image", None)
    ],
    [],
    thumbnailerRun, menu="<Image>/Filters")  # second item is menu location

main()
