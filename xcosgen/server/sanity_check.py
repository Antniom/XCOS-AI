import asyncio
import os
import sys

# Add current dir to path
sys.path.append(os.getcwd())

async def test():
    try:
        from intelligence import AutonomousLoop
        print("Import successful")
        loop = AutonomousLoop()
        
        async def mock_callback(data):
            print(f"Update: {data}")
            
        # We don't actually run it because we don't want to hit the API yet
        print("AutonomousLoop initialized")
        
        # Test GeminiClient init
        from intelligence import GeminiClient
        try:
            client = GeminiClient(api_key="mock")
            print("GeminiClient initialized with mock key")
        except Exception as e:
            print(f"GeminiClient init error (expected if key missing): {e}")
            
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())
