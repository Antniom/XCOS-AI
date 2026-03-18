import os
import base64
from google import genai
from google.genai import types as genai_types

# PROVIDED TEST API KEY
API_KEY = "AIzaSyCpAE8hr-oBIEKpZvxH5debYS3qHPHHaZs"
client = genai.Client(api_key=API_KEY)

def test_multipart_payload():
    print("Testing multi-part (text + image) payload...")
    # Variation 1: Content object (likely breaks)
    try:
        pixel_data = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=")
        parts = [
            genai_types.Part(text="Identify this image."),
            genai_types.Part(inline_data=genai_types.Blob(data=pixel_data, mime_type="image/png"))
        ]
        message = genai_types.Content(parts=parts)
        print("  - Trying with genai_types.Content...")
        client.interactions.create(
            model="gemini-3-flash-preview",
            input=message,
            system_instruction="You are a helpful assistant."
        )
        print("    Success!")
    except Exception as e:
        print(f"    Failed: {e}")

    # Variation 2: List of dicts (likely works)
    try:
        pixel_data = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=")
        input_data = [
            {"type": "text", "text": "Identify this image."},
            {"type": "image", "data": base64.b64encode(pixel_data).decode("utf-8"), "mime_type": "image/png"}
        ]
        print("  - Trying with list of dicts...")
        client.interactions.create(
            model="gemini-3-flash-preview",
            input=input_data,
            system_instruction="You are a helpful assistant."
        )
        print("    Success!")
    except Exception as e:
        print(f"    Failed: {e}")

def test_tool_result_payload():
    print("\nTesting tool result payload...")
    try:
        # First interaction
        tool_decl = {
            "name": "get_time",
            "description": "Returns current time",
            "parameters": {"type": "OBJECT", "properties": {}}
        }
        interaction1 = client.interactions.create(
            model="gemini-3-flash-preview",
            input="What is the time?",
            tools=[genai_types.Tool(function_declarations=[tool_decl])]
        )
        
        call_id = None
        for output in interaction1.outputs:
            if output.type == "function_call":
                call_id = output.id
                break
        
        if not call_id:
            print("  - No function call returned. Skipping.")
            return

        # Variation 1: Content object (likely breaks)
        try:
            tool_results = [genai_types.Part(
                function_response=genai_types.FunctionResponse(
                    name="get_time",
                    response={"result": "12:00 PM"}
                )
            )]
            print("  - Trying tool result with genai_types.Content...")
            client.interactions.create(
                model="gemini-3-flash-preview",
                input=genai_types.Content(parts=tool_results),
                previous_interaction_id=interaction1.id
            )
            print("    Success!")
        except Exception as e:
            print(f"    Failed: {e}")

        # Variation 2: List of dicts (likely works)
        try:
            input_data = [{
                "type": "function_result",
                "call_id": call_id,
                "name": "get_time",
                "result": {"result": "12:00 PM"}
            }]
            print("  - Trying tool result with list of dicts...")
            client.interactions.create(
                model="gemini-3-flash-preview",
                input=input_data,
                previous_interaction_id=interaction1.id
            )
            print("    Success!")
        except Exception as e:
            print(f"    Failed: {e}")

    except Exception as e:
        print(f"Global failed: {e}")

if __name__ == "__main__":
    test_multipart_payload()
    test_tool_result_payload()
