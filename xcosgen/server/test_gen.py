import requests
import time
import sys

def main():
    try:
        resp = requests.post("http://127.0.0.1:8000/generate", json={
            "prompt": "Connect a RAMP block to a CSCOPE block.",
            "model": "gemini-3.1-flash-lite-preview"
        })
        resp.raise_for_status()
        print("Generated request:", resp.json())
        print("Now tailing the backend.log file to monitor progress (press Ctrl+C to stop)...")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
