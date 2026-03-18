import json
import glob
import os

files = glob.glob('c:/Users/anton/Desktop/AI xcos module/xcosgen/server/logs/iterations/*.json')
files.sort(key=os.path.getctime)
for f in files[-5:]:
    with open(f, 'r', encoding='utf-8') as fh:
        data = json.load(fh)
        ts = data.get('timestamp')
        xml = data.get('extracted_xml', '')
        err = data.get('scilab_error', '')
        print('FILE:', f)
        print(' TIME:', ts)
        print(' ERROR:', err)
        print(' C_OR_FORTRAN count:', xml.count('C_OR_FORTRAN'), ' "4" count:', xml.count('simulationFunctionType="4"'))
