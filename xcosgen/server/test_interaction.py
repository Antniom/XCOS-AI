import asyncio
import os
import sys

# Add current directory to path so it can find intelligence.py
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# PROVIDED TEST API KEY
os.environ["GEMINI_API_KEY"] = "AIzaSyCpAE8hr-oBIEKpZvxH5debYS3qHPHHaZs"

from intelligence import AutonomousLoop

async def run():
    loop = AutonomousLoop()
    class DummyBridge:
        async def verify(self, xml): 
            # Check if XML is complete for success sign
            if "</XcosDiagram>" in xml:
                return True, ""
            return False, "XML incomplete"
            
    async def cb(d): 
        print(f"CB: {d.get('step')} - {d.get('message', d.get('error', ''))}")
    
    print("Starting generation test using Interactions API...")
    res = await loop.run(
        'Generate a CONST_m block connected to CSCOPE. Use the tools to get block info first.', 
        'gemini-3.1-flash-lite-preview', 
        DummyBridge(), 
        cb, 
        max_iterations=1
    )
    
    print("\n" + "="*50)
    print("FINAL XML RESPONSE:")
    if res and isinstance(res, str):
        print(f"Generated {len(res)} bytes of XML.")
        if res.strip().endswith("</XcosDiagram>"):
            print("Status: SUCCESS (Complete diagram)")
        else:
            print("Status: PARTIAL (Incomplete diagram)")
    else:
        print("Status: FAILED (No response or invalid type)")
    print("="*50)

if __name__ == "__main__":
    asyncio.run(run())
