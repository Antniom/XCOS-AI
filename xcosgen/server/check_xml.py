import json
import glob
import os
import xml.etree.ElementTree as ET

files = glob.glob('c:/Users/anton/Desktop/AI xcos module/xcosgen/server/logs/iterations/*.json')
files = [f for f in files if '20260317' in f]
files.sort(key=os.path.getctime)
if len(files) > 0:
    latest = files[-1]
    with open(latest, 'r', encoding='utf-8') as f:
        data = json.load(f)
        xml = data.get('extracted_xml', '')
        print('Filename:', latest)
        with open('latest_generated_error2.xcos', 'w', encoding='utf-8') as out:
            out.write(xml)
        try:
            root = ET.fromstring(xml)
            for block in root.findall('.//*[@simulationFunctionType]'):
                print(block.tag, block.get('style'), block.get('simulationFunctionType'))
        except Exception as e:
            print(e)
