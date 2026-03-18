import json
import glob
import os

files = glob.glob('c:/Users/anton/Desktop/AI xcos module/xcosgen/server/logs/iterations/*.json')
files.sort(key=os.path.getctime)
if len(files) > 0:
    latest = files[-1]
    print('Processing', latest)
    with open(latest, 'r', encoding='utf-8') as f:
        data = json.load(f)
        xml = data.get('extracted_xml', '')
        with open('latest_generated_error2.xcos', 'w', encoding='utf-8') as out:
            out.write(xml)
