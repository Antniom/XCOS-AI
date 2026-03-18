import xml.etree.ElementTree as ET

def analyze_file(filename, label):
    print(f"\n{'='*60}")
    print(f"Analyzing: {label}")
    print(f"{'='*60}")
    
    tree = ET.parse(filename)
    root = tree.getroot()
    
    # Check Array as="context"
    ctx = root.find('.//Array[@as="context"]')
    print(f"\n1. Array as='context': {'PRESENT' if ctx is not None else 'MISSING'}")
    
    # Check root element
    relem = root.find('.//root')
    print(f"\n2. Root element children: {len(list(relem)) if relem is not None else 'N/A'}")
    
    if relem:
        # List first 10 children
        for i, elem in enumerate(list(relem)[:10]):
            tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
            print(f"   [{i}] {tag}: id={elem.get('id', 'N/A')[:30]}, parent={elem.get('parent', 'N/A')}")
    
    # Check parent values for blocks
    blocks = root.findall('.//BasicBlock') + root.findall('.//RoundBlock') + root.findall('.//SplitBlock')
    parents = set(b.get('parent', '') for b in blocks)
    print(f"\n3. Block parent values: {parents}")
    
    # Check for mxCell elements
    mxcells = root.findall('.//mxCell')
    print(f"\n4. mxCell elements: {len(mxcells)}")
    for m in mxcells:
        print(f"   id={m.get('id')}, parent={m.get('parent')}")
    
    # PROD_f specific analysis
    print(f"\n5. PROD_f Analysis:")
    prod = None
    for rb in root.findall('.//RoundBlock'):
        if rb.get('interfaceFunctionName') == 'PROD_f':
            prod = rb
            break
    if prod:
        prod_id = prod.get('id')
        print(f"   Found PROD_f: id={prod_id}")
        # Find its input ports
        xpath = ".//ExplicitInputPort[@parent='" + prod_id + "']"
        inputs = root.findall(xpath)
        print(f"   Input ports: {len(inputs)}")
        for inp in inputs:
            style = inp.get('style', '')
            ordering = inp.get('ordering', '')
            print(f"     order={ordering}: {style}")
    
    # RAMP block analysis
    print(f"\n6. RAMP Block exprs:")
    for bb in root.findall('.//BasicBlock'):
        if bb.get('interfaceFunctionName') == 'RAMP':
            exprs = bb.find('.//ScilabString[@as="exprs"]')
            if exprs:
                datas = exprs.findall('data')
                print(f"   RAMP {bb.get('id')}: {len(datas)} exprs")
                for d in datas:
                    print(f"     line={d.get('line')}: {d.get('value')}")
            # realParameters
            rp = bb.find('.//ScilabDouble[@as="realParameters"]')
            if rp:
                datas = rp.findall('data')
                print(f"   realParameters: {len(datas)} values")
                for d in datas:
                    print(f"     {d.get('realPart')}")
    
    # MUX block analysis
    print(f"\n7. MUX Block:")
    for bb in root.findall('.//BasicBlock'):
        if bb.get('interfaceFunctionName') == 'MUX':
            exprs = bb.find('.//ScilabString[@as="exprs"]')
            if exprs:
                datas = exprs.findall('data')
                print(f"   exprs: {[d.get('value') for d in datas]}")
            intp = bb.find('.//ScilabInteger[@as="integerParameters"]')
            if intp:
                datas = intp.findall('data')
                print(f"   integerParameters: {[d.get('value') for d in datas]}")
    
    # scifunc_block_m analysis
    print(f"\n8. scifunc_block_m:")
    for bb in root.findall('.//BasicBlock'):
        if bb.get('interfaceFunctionName') == 'scifunc_block_m':
            value = bb.get('value', 'N/A')
            print(f"   value attribute: {value}")
            exprs = bb.find('.//Array[@as="exprs"]')
            if exprs:
                strs = exprs.findall('.//ScilabString')
                print(f"   Nested ScilabString count: {len(strs)}")
                for i, s in enumerate(strs[:3]):
                    datas = s.findall('data')
                    print(f"   String {i}: {[d.get('value') for d in datas[:2]]}")

if __name__ == "__main__":
    analyze_file(r'C:\Users\anton\Desktop\Mec apl PLs\teste7.xcos', 'teste7.xcos (generated)')
    analyze_file(r'C:\Users\anton\Desktop\Mec apl PLs\teste7_correct.xcos', 'teste7_correct.xcos (reference)')
