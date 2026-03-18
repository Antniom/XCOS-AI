import asyncio
import os
import json
from intelligence import AutonomousLoop

class DummyBridge:
    async def verify(self, xml):
        return True, ''

async def run_test():
    loop = AutonomousLoop()
    
    async def on_update(data):
        step = data.get('step', '')
        if step == 'Generating':
            print('--', data.get('message', ''))
        elif step == 'Success':
            xml = data.get('xml', '')
            print('\nSUCCESS! Checking for simulationFunctionType=4 vs C_OR_FORTRAN:')
            print('Count of \"4\":', xml.count('simulationFunctionType=\"4\"'))
            print('Count of \"C_OR_FORTRAN\":', xml.count('simulationFunctionType=\"C_OR_FORTRAN\"'))
            print('\nDone.')
            
            with open('test_output.xml', 'w') as f:
                f.write(xml)
        elif step == 'Error':
            print('\nERROR:', data)
            
    print('Starting Generation...')
    await loop.run(
        prompt='Connect a RAMP block to a CSCOPE block. The RAMP should go from 0 to 10. The CSCOPE should display it.',
        model='gemini-2.5-flash',
        scilab_bridge=DummyBridge(),
        update_callback=on_update
    )

if __name__ == '__main__':
    asyncio.run(run_test())
