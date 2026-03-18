import asyncio
from intelligence import AutonomousLoop

class DummyBridge:
    async def verify(self, xml):
        with open('debug_latest.xml', 'w') as f: f.write(xml)
        return True, ''

async def cb(x):
    print(x.get('step', ''), x.get('message', ''), x.get('error', ''))

async def run():
    loop = AutonomousLoop()
    res = await loop.run('Connect a RAMP block to a CSCOPE block.', 'gemini-3.1-flash-lite', DummyBridge(), cb)
    print("Final result keys:", getattr(res, 'keys', lambda: [])())

asyncio.run(run())
