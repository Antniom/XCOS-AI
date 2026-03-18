import os
import json
import xml.etree.ElementTree as ET
import glob

ref_dir = r"c:\Users\anton\Desktop\Mec apl PLs\AI-teste\Reference blocks"
blocks_dir = r"c:\Users\anton\Desktop\Mec apl PLs\AI-teste\blocks"
index_path = os.path.join(blocks_dir, "_index.json")

# load index
with open(index_path, 'r', encoding='utf-8') as f:
    index_data = json.load(f)

processed_blocks = {b['name'] for b in index_data['block_files']}

xcos_files = glob.glob(os.path.join(ref_dir, "*.xcos"))

files_to_process = []
for f in xcos_files:
    basename = os.path.basename(f)
    block_name = os.path.splitext(basename)[0]
    if block_name not in processed_blocks:
        files_to_process.append(f)

# limit to 70
files_to_process = sorted(files_to_process)[:70]

print(f"Found {len(files_to_process)} files to process. Proceeding with top 70...")

def parse_xcos(filepath):
    tree = ET.parse(filepath)
    root = tree.getroot()
    mxGraphModel = root.find("mxGraphModel")
    if mxGraphModel is None:
        return None
    graph_root = mxGraphModel.find("root")
    main_block = None
    for child in graph_root:
        if child.tag.endswith("Block") or child.tag in ["SplitBlock", "ImplicitInBlock", "ImplicitOutBlock", "Summation"]:
            main_block = child
            break
            
    if main_block is None:
        return None
        
    block_name = main_block.get("interfaceFunctionName")
    if not block_name:
        block_name = os.path.splitext(os.path.basename(filepath))[0]
        
    block_data = {
        "name": block_name,
        "description": f"{block_name} block",
        "category": "Uncategorized",
        "blockType": main_block.get("blockType", ""),
        "tag": main_block.tag,
        "interfaceFunctionName": main_block.get("interfaceFunctionName", ""),
        "simulationFunctionName": main_block.get("simulationFunctionName", ""),
        "simulationFunctionType": main_block.get("simulationFunctionType", ""),
        "dependsOnU": int(main_block.get("dependsOnU", 0)) if main_block.get("dependsOnU") else 0,
        "dependsOnT": int(main_block.get("dependsOnT", 0)) if main_block.get("dependsOnT") else 0,
    }
    
    geom = main_block.find("mxGeometry")
    if geom is not None:
        block_data["geometry"] = {
            "width": float(geom.get("width", 0)),
            "height": float(geom.get("height", 0))
        }
    else:
        block_data["geometry"] = {"width": 0, "height": 0}
        
    params = {}
    for param_tag in ["exprs", "realParameters", "integerParameters", "nbZerosCrossing", "nmode", "state", "dState", "objectsParameters"]:
        node = main_block.find(f"*[@as='{param_tag}']")
        if node is not None:
            h = node.get("height", "0")
            w = node.get("width", "0")
            p_data = {"intPrecision": node.get("intPrecision")} if node.get("intPrecision") else {}
            p_data.update({"height": h, "width": w})
            data_nodes = node.findall("data")
            if data_nodes:
                p_data["data"] = []
                for d in data_nodes:
                    p_data["data"].append({
                        "line": d.get("line"),
                        "column": d.get("column"),
                        "value": d.get("value")
                    })
            params[param_tag] = p_data
    block_data["parameters"] = params
    
    ports = {"explicitInputs": [], "explicitOutputs": [], "implicitInputs": [], "implicitOutputs": [], "controlPorts": [], "commandPorts": []}
    
    port_tags = [c.tag for c in graph_root if c.tag.endswith("Port")]
    for child in graph_root:
        port_type = child.tag
        if port_type.endswith("Port"):
            port_data = {
                "dataType": child.get("dataType", ""),
                "dataColumns": int(child.get("dataColumns", 1)) if child.get("dataColumns") else 1,
                "dataLines": int(child.get("dataLines", 1)) if child.get("dataLines") else 1,
                "style": child.get("style", "")
            }
            if child.get("initialState"):
                port_data["initialState"] = child.get("initialState")
                
            if "ExplicitInput" in port_type:
                ports["explicitInputs"].append(port_data)
            elif "ExplicitOutput" in port_type:
                ports["explicitOutputs"].append(port_data)
            elif "ImplicitInput" in port_type:
                ports["implicitInputs"].append(port_data)
            elif "ImplicitOutput" in port_type:
                ports["implicitOutputs"].append(port_data)
            elif "Control" in port_type:
                ports["controlPorts"].append(port_data)
            elif "Command" in port_type:
                ports["commandPorts"].append(port_data)
                
    block_data["ports"] = {k: v for k, v in ports.items() if v}
    
    # clean xml example
    rough_string = ET.tostring(main_block, encoding='unicode')
    block_data["xmlExample"] = rough_string
    
    anomalies = []
    
    if main_block.tag not in ["BasicBlock"]:
        anomalies.append(f"Special tag: {main_block.tag}")
    if block_data["blockType"] == "h":
        anomalies.append("blockType='h' indicates SuperBlock with internal diagram")
    if block_data["blockType"] == "x":
        anomalies.append("blockType='x' special block type")
    if "ControlPort" in port_tags:
        anomalies.append("Contains ControlPort")
    if "CommandPort" in port_tags:
        anomalies.append("Contains CommandPort")
        
    for port_list in block_data["ports"].values():
        for p in port_list:
            if p.get("dataLines") == -1:
                anomalies.append("dataLines=-1 indicates variable-size")
            if p.get("dataLines") == -2:
                anomalies.append("dataLines=-2 indicates auto-dimension")
            if p.get("initialState") == "-1.0":
                anomalies.append("initialState=-1.0 for event port")
                
    if params.get("nbZerosCrossing", {}).get("data"):
        val = params["nbZerosCrossing"]["data"][0].get("value")
        if val not in ["0", None, 0]:
            anomalies.append(f"nbZerosCrossing={val}")
            
    width = block_data["geometry"]["width"]
    height = block_data["geometry"]["height"]
    if width not in [40.0] and width > 0:
        anomalies.append(f"Non-standard width: {width}")
    if height not in [40.0] and height > 0:
        anomalies.append(f"Non-standard height: {height}")
        
    has_int32 = any(p.get("dataType") == "INT32_MATRIX" for port_list in block_data["ports"].values() for p in port_list)
    if has_int32:
        anomalies.append("INT32_MATRIX integer data")
        
    if params.get("exprs", {}).get("height") == "0" and params.get("exprs", {}).get("width") == "0":
        anomalies.append("Empty exprs")
        
    block_data["anomalies"] = list(set(anomalies))
    
    block_data["criticalRules"] = [
        "NEVER use spacingLeft - use spacing=10.0",
        "Preserve exact port styles from reference",
        "Copy parameter structures exactly"
    ]
    block_data["commonUses"] = []
    block_data["relatedBlocks"] = []
    
    return block_data

for f in files_to_process:
    try:
        data = parse_xcos(f)
        if data:
            block_name = data["name"]
            out_path = os.path.join(blocks_dir, f"{block_name}.json")
            with open(out_path, 'w', encoding='utf-8') as outfile:
                json.dump(data, outfile, indent=2)
                
            index_data["block_files"].append({
                "name": block_name,
                "file": f"{block_name}.json",
                "category": "Uncategorized",
                "description": data["description"],
                "complexity": "medium"
            })
            
            os.remove(f)
            print(f"Processed and deleted: {block_name} from {os.path.basename(f)}")
        else:
            print(f"Failed to parse {f}")
    except Exception as e:
        print(f"Error processing {f}: {e}")

with open(index_path, 'w', encoding='utf-8') as f:
    json.dump(index_data, f, indent=2)
    
print("Updated index.")
