import json
import glob
import os

files = glob.glob('c:/Users/anton/Desktop/AI xcos module/xcosgen/server/logs/iterations/*.json')
files.sort(key=os.path.getctime)
latest = files[-1]
print('Newest file is:', latest)
with open(latest, 'r', encoding='utf-8') as f:
    data = json.load(f)
    print('Scilab Error:', data.get('scilab_error'))
    xml = data.get('extracted_xml', '')
    with open('c:/Users/anton/Desktop/AI xcos module/xcosgen/server/newest_generated2.xml', 'w', encoding='utf-8') as out:
        out.write(xml)
