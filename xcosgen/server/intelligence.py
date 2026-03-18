import base64
import glob
import json
import os
import re
import asyncio
import time
from datetime import datetime
from typing import List, Optional, Dict, Any, Callable
from google import genai
from google.genai import types as genai_types

# The .xcos format is the legacy plain-XML format that Scilab 2026 still opens.
# No Scilab execution is needed; Python writes the XML directly.

SYSTEM_PROMPT = """\
You are an expert Scilab Xcos diagram builder.
Your ONLY task is to output a complete, valid .xcos XML file that Scilab 2026
Xcos can open directly from disk.

⛔ CRITICAL: DO NOT OUTPUT ANY XML IN YOUR VERY FIRST RESPONSE.
Your first response MUST be function calls to get_xcos_block_source and get_xcos_block_info.
Only after reading those results may you generate XML.

╔═══════════════════════════════════════════════════════════════╗
║  SCILAB 2026 CLI COMPATIBILITY (IMPORTANT)                   ║
╟───────────────────────────────────────────────────────────────╢
║ If asked to generate a Scilab script (.sce), ALWAYS use:      ║
║   loadScicos();                                               ║
║   loadXcosLibs();                                             ║
║ Failure to call loadScicos() first results in Undefined error.║
╚═══════════════════════════════════════════════════════════════╝

╔═══════════════════════════════════════════════════════════════════════╗
║  MASTER RULE: TWO-TOOL WORKFLOW FOR EVERY BLOCK  ←  HIGHEST PRIORITY ║
╚═══════════════════════════════════════════════════════════════════════╝

You have TWO tools for block information. Use BOTH for every block:

  STEP 1 → get_xcos_block_source("BLOCK_NAME")
    Reads the raw Scilab .sci interface macro directly from the Scilab 2026
    source code. This is the SINGLE SOURCE OF TRUTH for:
      • Default parameter values (ipar, rpar, exprs)
      • Port counts and sizes (in, in2, out, evtin, evtout)
      • Simulation function name and blocktype
      • What a block looks like when first placed on the canvas
    Read the 'define' case carefully. Use those exact defaults.
    Only deviate from defaults for parameters the Xcos GUI dialog
    explicitly allows a user to change (shown in the 'set' case).

  STEP 2 → get_xcos_block_info("BLOCK_NAME")
    Returns the annotation JSON: criticalRules, anomalies, commonUses.
    Apply these ON TOP of the source defaults from Step 1.
    If no annotation JSON exists, that block has no special rules —
    just use the .sci source defaults.

MANDATORY: Call BOTH tools for EVERY block before generating any XML.
NEVER invent parameter values from memory — always derive from .sci source.

╔═══════════════════════════════════════════════════════════════════════╗
║  MANDATORY BLOCK LIST ENFORCEMENT  ←  HIGHEST PRIORITY RULE          ║
╚═══════════════════════════════════════════════════════════════════════╝

If the user's prompt or any attached image/file specifies a list of
blocks — possibly with counts (e.g., "2 X RAMP", "1 X PROD_f") — you
MUST follow these rules WITHOUT ANY EXCEPTION:

  ⛔ RULE 1 — USE ONLY THE LISTED BLOCKS.
     Do NOT add any top-level functional block that is not in the specified list.
     (CRITICAL EXCEPTION: You MUST include all internal blocks inside SuperBlockDiagrams exactly as shown in their get_xcos_block_info tool xmlExample. Do NOT omit them, they are mandatory!).

  ⛔ RULE 2 — USE EXACTLY THE SPECIFIED COUNT FOR EACH TOP-LEVEL BLOCK.
     Count applies to top-level blocks with parent="0:2:0".
     "2 X RAMP"   → instantiate EXACTLY 2 top-level RAMP blocks.
     "1 X PROD_f" → instantiate EXACTLY 1 top-level PROD_f block.
     Never omit a listed block. Never add an unlisted top-level block.

  ⛔ RULE 3 — CALL get_xcos_block_info() FOR EVERY LISTED BLOCK FIRST.
     Before generating any XML, call the tool for each block in the list.

  ⛔ RULE 4 — SELF-VERIFY BEFORE FINALISING.
     After assembling the XML, count each block type and confirm it matches
     the specification. If any count is wrong, fix it before outputting.

VIOLATION OF THESE RULES IS A CRITICAL ERROR that will cause the
diagram to be rejected regardless of XML correctness.

╔═══════════════════════════════════════════════════════════════════════╗
║  A.  FILE SKELETON                                                    ║
╚═══════════════════════════════════════════════════════════════════════╝

The root XcosDiagram MUST include <Array as="context"> directly after the
opening tag, before <mxGraphModel>. Also note attribute order:

<?xml version="1.0" ?>
<XcosDiagram debugLevel="0" finalIntegrationTime="30.0"
    integratorAbsoluteTolerance="1.0E-6" integratorRelativeTolerance="1.0E-6"
    toleranceOnTime="1.0E-10" maxIntegrationTimeInterval="100001.0"
    maximumStepSize="0.0" realTimeScaling="0.0" solver="1.0"
    background="-1" gridEnabled="1" title="Diagram">
  <Array as="context" scilabClass="String[]"></Array>
  <mxGraphModel as="model">
    <root>
      <mxCell id="0:1:0"/>
      <mxCell id="0:2:0" parent="0:1:0"/>
      <!-- ALL BLOCKS, PORTS, AND LINKS GO HERE -->
    </root>
  </mxGraphModel>
  <mxCell as="defaultParent" id="0:2:0" parent="0:1:0"/>
</XcosDiagram>

╔═══════════════════════════════════════════════════════════════════════╗
║  B.  BLOCK ELEMENT                                                    ║
╚═══════════════════════════════════════════════════════════════════════╗

  • XML tag   = MUST be `<BasicBlock>` for standard blocks EXCEPT:
    - `<RoundBlock>` for `PROD_f`, `SUMMATION`, `PRODUCT`, `BIGSOM_f`, `PROD`.
    - `<SplitBlock>` for `CLKSPLIT_f`, `SPLIT_f`.
    - `<EventOutBlock>` for `CLKOUTV_f`.
  • Attributes (MANDATORY):
    - id = short sequential id: b1, b2, b3, …
    - parent = ALWAYS "0:2:0" for top-level.
    - interfaceFunctionName = FROM .sci (e.g. 'RAMP', 'CSCOPE').
    - blockType = FROM .sci (e.g. 'c', 'h', 'd').
    - dependsOnU = MUST BE "1" if block depends on input, "0" otherwise. (FROM .sci `model.dep_ut`)
    - dependsOnT = MUST BE "1" if block depends on time, "0" otherwise. (FROM .sci `model.dep_ut`)
    - style = interfaceFunctionName.
    - simulationFunctionName = Verbatim from .sci (e.g. 'ramp', 'cscope').
    - simulationFunctionType = Exact String Enum mapping from .sci integer:
        0         → 'DEFAULT'
        1         → 'TYPE_1'
        2         → 'TYPE_2'
        3         → 'TYPE_3'
        4         → 'C_OR_FORTRAN'
        5         → 'MSCILIB'
        -1        → 'LUA'
        10001     → 'SCILIB'
        (Example: If .sci says `model.sim=list('ramp',4)`, use `simulationFunctionType="C_OR_FORTRAN"`)
  • mxGeometry goes LAST among the block's children.

╔═══════════════════════════════════════════════════════════════════════╗
║  C.  PARAMETERS                                                       ║
╚═══════════════════════════════════════════════════════════════════════╗

  Always emit ALL 10 parameters in order: exprs, realParameters, integerParameters,
  objectsParameters, nbZerosCrossing, nmode, state, dState, oDState, equations.

  MANDATORY TYPE MAPPING:
  • non-empty integerParameters, nbZerosCrossing, nmode:
    MUST use `<ScilabInteger as="..." height="..." width="..." intPrecision="sci_int32">` with `value="..."` attribute.
    Example: `<ScilabInteger as="integerParameters" height="2" width="1" intPrecision="sci_int32"><data column="0" line="0" value="1"/><data column="0" line="1" value="2"/></ScilabInteger>`
    DO NOT use `<ScilabDouble>` with `realPart` for `integerParameters` unless it is completely empty (`height="0" width="0"`).
  • exprs, realParameters, state, dState:
    MUST use `<ScilabDouble>` with `realPart="..."` attribute (EXCEPT `exprs` when non-empty, which uses `<ScilabString>` and `value="..."`).

  CRITICAL: If .sci says `model.nzcross=1` or `model.nmode=1`, you MUST output a `<ScilabInteger>` with `value="1"`. DO NOT USE `0.0`.

╔═══════════════════════════════════════════════════════════════════════╗
║  D.  PORTS                                                            ║
╚═══════════════════════════════════════════════════════════════════════╗

  ⛔ NEVER put an <mxGeometry> inside a port element.
  ⛔ MUST have value="" attribute.
  ⛔ SIBLINGS of their block (parent = block's id).
  ⛔ MUST end style with ;rotation=N.

╔═══════════════════════════════════════════════════════════════════════╗
║  E.  LINKS                                                            ║
╚═══════════════════════════════════════════════════════════════════════╗

  • MUST have `style` (e.g. "ExplicitLink") and `value=""`.
  • MUST have `<mxGeometry as="geometry">` with source/target points.
"""

def get_xcos_block_source(block_name: str) -> str:
    macros_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "scilab-2026.0.1", "scilab-2026.0.1", "scilab", "modules", "scicos_blocks", "macros"))
    target_file = f"{block_name}.sci"
    for root, dirs, files in os.walk(macros_dir):
        if target_file in files:
            path = os.path.join(root, target_file)
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
    return f"Source for {block_name} not found."

def get_xcos_block_info(block_name: str) -> str:
    path = os.path.join(os.path.dirname(__file__), "blocks", f"{block_name}.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return f"No info found for {block_name}."

class GeminiClient:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not found.")
        self.client = genai.Client(api_key=self.api_key)

    def _clean_xml(self, raw_text: str) -> str:
        # Strip UTF-8 BOM if present
        if raw_text.startswith('\ufeff'):
            raw_text = raw_text[1:]
            
        # The AI might enclose the XML in ```xml fences, or it might just
        # include other randomly fenced code blocks in its reasoning (which breaks regex).
        # We simply find where the XML starts and where it ends.
        
        start_idx = raw_text.find('<?xml')
        if start_idx == -1:
            start_idx = raw_text.find('<XcosDiagram')
            
        if start_idx == -1:
            raise ValueError("No XML tags found in your response. You MUST generate valid Xcos XML enclosed in <?xml ...?> tags.")
            
        end_idx = raw_text.rfind('</XcosDiagram>')
        if end_idx != -1:
            # include the length of the closing tag
            end_idx += len('</XcosDiagram>')
            raw_text = raw_text[start_idx:end_idx]
        else:
            raw_text = raw_text[start_idx:]
            
        return raw_text.strip()

    async def _sync_generate_3phase(self, prompt: str, model: str, scilab_bridge: Any, update_callback: Callable, initial_xml: Optional[str] = None, attachments: Optional[List[Any]] = None):
        iteration = 1
        
        # Build initial input
        input_data = []
        if attachments:
            for att in attachments:
                input_data.append({
                    "type": "image",
                    "data": att.data,  # Base64
                    "mime_type": att.type
                })
        input_data.append({"type": "text", "text": prompt})

        # Define tools using the flat ToolParam format required by the Interactions API.
        # Each entry is a dict with type="function", name, description, and parameters.
        tools = [
            {
                "type": "function",
                "name": "get_xcos_block_source",
                "description": "Reads the raw Scilab .sci interface macro directly from the source code.",
                "parameters": {
                    "type": "object",
                    "properties": {"block_name": {"type": "string"}},
                    "required": ["block_name"]
                }
            },
            {
                "type": "function",
                "name": "get_xcos_block_info",
                "description": "Returns the annotation JSON for an Xcos block: criticalRules, anomalies, commonUses.",
                "parameters": {
                    "type": "object",
                    "properties": {"block_name": {"type": "string"}},
                    "required": ["block_name"]
                }
            }
        ]

        async def send_update(data):
            if asyncio.iscoroutinefunction(update_callback):
                await update_callback(data)
            else:
                update_callback(data)

        # Phase 1: Call tools and generate
        await send_update({"step": "Generating", "iteration": iteration, "message": "Analyzing prompt and calling tools..."})
        
        try:
            interaction = self.client.interactions.create(
                model=model,
                input=input_data,
                system_instruction=SYSTEM_PROMPT,
                tools=tools
            )
            
            # Handle tool calls
            while True:
                tool_calls = [o for o in interaction.outputs if getattr(o, "type", None) == "function_call" or (hasattr(o, "name") and hasattr(o, "arguments"))]
                
                if not tool_calls:
                    if iteration == 1 and not any("function_result" in str(getattr(o, "type", "")) for o in interaction.outputs):
                        # Force tool usage if the model tried to answer directly on the first attempt
                        await send_update({"step": "Fixing", "iteration": iteration, "message": "Enforcing tool usage: no tools called."})
                        input_data.append({"role": "model", "parts": [o for o in interaction.outputs]})
                        input_data.append({"role": "user", "parts": [{"text": "⛔ CRITICAL ERROR: You failed to call the info tools. You MUST call get_xcos_block_source and get_xcos_block_info FIRST to learn the block parameters. Do NOT output XML without calling tools."}]})
                        
                        interaction = self.client.interactions.create(
                            model=model,
                            input=[{"role": "user", "parts": [{"text": "⛔ CRITICAL ERROR: You MUST call the tools now."}]}],
                            previous_interaction_id=interaction.id,
                            tools=tools
                        )
                        continue
                    else:
                        break
                
                results = []
                for call in tool_calls:
                    fname = call.name
                    args = call.arguments
                    bname = args.get("block_name", "")
                    
                    await send_update({"step": "Generating", "iteration": iteration, "message": f"Tool call: {fname}({bname})"})
                    
                    if fname == "get_xcos_block_source":
                        res = get_xcos_block_source(bname)
                    else:
                        res = get_xcos_block_info(bname)
                    
                    results.append({
                        "type": "function_result",
                        "call_id": getattr(call, "id", None) or call.name,
                        "name": fname,
                        "result": {"result": res}
                    })
                
                interaction = self.client.interactions.create(
                    model=model,
                    input=results,
                    previous_interaction_id=interaction.id
                )
            
            # Extract XML
            response_text = ""
            for o in interaction.outputs:
                if o.type == "text":
                    response_text += o.text
            
            # Phase 3: Validation and review
            max_fix_iterations = 5
            while iteration <= max_fix_iterations:
                await send_update({"step": "Verifying", "iteration": iteration, "message": "Verifying with Scilab..."})
                
                # Log iteration detail
                self.log_iteration(iteration, model, input_data, response_text)

                try:
                    xml = self._clean_xml(response_text)
                    success, error = await scilab_bridge.verify(xml)
                except ValueError as ve:
                    success, error = False, str(ve)
                    xml = ""

                if success:
                    await send_update({"step": "Success", "xml": xml})
                    return xml
                
                await send_update({"step": "Fixing", "iteration": iteration, "error": error})
                
                # Feedback to AI
                iteration += 1
                if "No XML tags found" in error:
                    feedback = f"You failed to generate valid XML. You MUST output ONLY raw XML starting with <?xml...\nError details: {error}"
                else:
                    feedback = f"That XML failed Scilab validation with this error:\n{error}\nStudy the error carefully. Then output the COMPLETE corrected XML."
                    
                input_data = [{"type": "text", "text": feedback}]
                
                interaction = self.client.interactions.create(
                    model=model,
                    input=input_data,
                    previous_interaction_id=interaction.id
                )
                
                response_text = ""
                for o in interaction.outputs:
                    if o.type == "text":
                        response_text += o.text

            await send_update({"step": "Error", "error": "Maximum fix iterations reached. Final XML still has errors."})
            return xml

        except Exception as e:
            await send_update({"step": "Error", "error": str(e)})
            return None

    def log_iteration(self, iter_val, model, prompt, response):
        log_dir = os.path.join(os.path.dirname(__file__), "logs", "iterations")
        os.makedirs(log_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = os.path.join(log_dir, f"iter_{iter_val}_{timestamp}.json")
        try:
            with open(log_path, "w", encoding="utf-8") as f:
                json.dump({
                    "iteration": iter_val,
                    "model": model,
                    "timestamp": datetime.now().isoformat(),
                    "prompt_sent": str(prompt),
                    "ai_response_raw": response
                }, f, indent=2)
        except Exception as e:
            print(f"Failed to log iteration details: {e}")

class AutonomousLoop:
    def __init__(self):
        # GeminiClient is lazy-initialized in run() so the server can start
        # without GEMINI_API_KEY being set at import time.
        self._client: Optional[GeminiClient] = None

    def _get_client(self) -> GeminiClient:
        api_key = os.getenv("GEMINI_API_KEY", "")
        if self._client is None or (self._client is not None and self._client.api_key != api_key):
            self._client = GeminiClient(api_key=api_key)
        return self._client  # type: ignore[return-value]

    async def run(self, prompt, model, scilab_bridge, update_callback, initial_xml=None, attachments=None, max_iterations=5):
        client = self._get_client()
        return await client._sync_generate_3phase(prompt, model, scilab_bridge, update_callback, initial_xml, attachments)

    def get_system_prompt(self):
        return SYSTEM_PROMPT

    def get_reference_blocks(self):
        blocks_dir = os.path.join(os.path.dirname(__file__), "blocks")
        if not os.path.exists(blocks_dir):
            return []
        files = glob.glob(os.path.join(blocks_dir, "*.json"))
        return [os.path.basename(f).replace(".json", "") for f in files]
