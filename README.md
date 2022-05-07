# Thumbnailer

Gimp Plugin for generating thumbnails with reactions from a Google Sheet and a Gimp template file.

[Sample Sheet](https://docs.google.com/spreadsheets/d/1tWhWY_TxIuNjb46oULFhAzkVuWobK5syhosowStG9As)

## Instalation

Step 0
---
Make sure that pip is working with your Gimp install...

`PS C:\Program Files\GIMP 2\bin> ./python.exe -m pip install configparser`

Step 1
---
Copy thumbnailer.py to your plugins directory (you can find it in the Gimp preferences).

Might look something like this
`C:\Users\<user>\AppData\Roaming\GIMP\2.10\plug-ins`

Step 2
---
Copy [this spreadsheet](https://docs.google.com/spreadsheets/d/1tWhWY_TxIuNjb46oULFhAzkVuWobK5syhosowStG9As) and update it to your liking... more documentation to come on what everything in there does.

Step 3
---
Copy thumbnailer.ini to `C:\Users\<user>` and set ste the config file according to your needs.
Including changing the ini to reference your new spreadsheet from step 2.

```
[GENERAL]
dataSheet = Sheet1!A1:ZZ
spreadsheetId = 1tWhWY_TxIuNjb46oULFhAzkVuWobK5syhosowStG9As
outputDir = C:\<place_to_put_thumbs>\

[AUTHENTICATION]
tokenPath = <path_to>\credentials.json
```

Step 3
---
Restart gimp and thumbnailer should be available at the bottom of the Filters menu.

