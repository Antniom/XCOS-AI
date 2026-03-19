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
Your first response MUST be tool calls following the FOUR-TOOL WORKFLOW below.
Only after reading all tool results may you generate XML.

╔═══════════════════════════════════════════════════════════════════════╗
║  MASTER RULE: FOUR-TOOL WORKFLOW FOR EVERY BLOCK  ← HIGHEST PRIORITY ║
╚═══════════════════════════════════════════════════════════════════════╝

For EVERY block in the diagram, call ALL applicable tools before generating XML:

  STEP 0 → get_xcos_block_example("BLOCK_NAME")   ← CALL THIS FIRST
    Returns the complete, working .xcos XML for this block as saved by
    Scilab 2026.0.1. This is the PRIMARY reference — use it as a template.
    Copy the block's XML element verbatim, then only change:
      • id, parent, and geometry (x, y, width, height)
      • exprs values that the user explicitly requests to change
    DO NOT invent or change any other parameters. If this tool returns XML,
    that XML is correct by definition — trust it completely.
    If the returned .xcos contains a <SuperBlockDiagram>, you MUST reproduce
    it EXACTLY (same internal blocks, same link topology, same port types).

  STEP 1 → get_xcos_block_source("BLOCK_NAME")
    Reads the raw Scilab .sci interface macro. Use it to:
      • Understand which exprs fields are user-editable (shown in 'set' case)
      • Confirm port counts, blockType, simulationFunctionName
    Only deviate from the Step 0 example for parameters the 'set' case exposes.

  STEP 2 → get_xcos_block_info("BLOCK_NAME")
    Returns criticalRules, anomalies, commonUses annotation JSON.
    Apply on top of the Step 0 example. If says "No info found", no special rules.

  STEP 3 → get_xcos_block_help("BLOCK_NAME")
    Returns official parameter descriptions and constraints (type, size, range).
    Use this to validate your parameter values match the documented types.

MANDATORY: Call ALL FOUR tools for EVERY block before generating any XML.
NEVER invent parameter values from memory — always derive from tool results.

╔═══════════════════════════════════════════════════════════════════════╗
║  SUPERBLOCK RULE  ←  CRITICAL, READ BEFORE USING CLOCK_c / CLOCK_f   ║
╚═══════════════════════════════════════════════════════════════════════╝

If get_xcos_block_example returns a file containing <SuperBlockDiagram>:
  • You MUST reproduce that SuperBlockDiagram EXACTLY in your output.
  • NEVER flatten it into a plain BasicBlock with scalar parameters.
  • ALL top-level params (exprs, realParameters, integerParameters) MUST
    be empty ScilabDouble 0×0 — actual params live inside internal blocks.
  • The SuperBlockDiagram MUST come AFTER <mxGeometry>.
  • The SuperBlockDiagram MUST start with <Array as="context" scilabClass="String[]"></Array>.
  • The SuperBlockDiagram MUST end with <mxCell as="defaultParent" .../>.

CLOCK_c: blockType="h", simulationFunctionName="csuper", simulationFunctionType="DEFAULT"
  Internal: CLKOUT_f + EVTDLY_c + CLKSPLIT_f + 3 CommandControlLinks (feedback loop).
CLOCK_f: blockType="h", simulationFunctionName="csuper", simulationFunctionType="DEFAULT"
  Internal: CLKOUT_f + EVTDLY_f + CLKSPLIT_f + 3 CommandControlLinks (feedback loop).
  (Uses EVTDLY_f instead of EVTDLY_c — different sim function: "evtdly"/C_OR_FORTRAN)

╔═══════════════════════════════════════════════════════════════════════╗
║  MANDATORY BLOCK LIST ENFORCEMENT  ←  HIGHEST PRIORITY RULE          ║
╚═══════════════════════════════════════════════════════════════════════╝

If the user's prompt or any attached image/file specifies a list of
blocks — possibly with counts (e.g., "2 X RAMP", "1 X PROD_f") — you
MUST follow these rules WITHOUT ANY EXCEPTION:

  ⛔ RULE 1 — USE ONLY THE LISTED BLOCKS.
     Do NOT add any top-level functional block that is not in the specified list.
     (CRITICAL EXCEPTION: You MUST include all internal blocks inside SuperBlockDiagrams
     exactly as shown in get_xcos_block_example. Do NOT omit them — they are mandatory!)

  ⛔ RULE 2 — USE EXACTLY THE SPECIFIED COUNT FOR EACH TOP-LEVEL BLOCK.
     Count applies to top-level blocks with parent="0:2:0".
     "2 X RAMP"   → instantiate EXACTLY 2 top-level RAMP blocks.
     "1 X PROD_f" → instantiate EXACTLY 1 top-level PROD_f block.
     Never omit a listed block. Never add an unlisted top-level block.

  ⛔ RULE 3 — CALL ALL FOUR tools FOR EVERY LISTED BLOCK FIRST.
     Before generating any XML, call the tools for each block in the list.

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
    - `<EventOutBlock>` for `CLKOUTV_f`, `CLKOUT_f`.
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
  • mxGeometry goes LAST among the block's children (exception: SuperBlocks have
    SuperBlockDiagram AFTER mxGeometry).

╔═══════════════════════════════════════════════════════════════════════╗
║  C.  PARAMETERS                                                       ║
╚═══════════════════════════════════════════════════════════════════════╗

  Always emit ALL 10 parameters in order: exprs, realParameters, integerParameters,
  objectsParameters, nbZerosCrossing, nmode, state, dState, oDState, equations.

  MANDATORY TYPE MAPPING:
  • non-empty integerParameters, nbZerosCrossing, nmode:
    MUST use `<ScilabInteger as="..." height="..." width="..." intPrecision="sci_int32">` with `value="..."` attribute.
  • COMPLETELY EMPTY parameters (integerParameters, realParameters, state, etc.):
    MUST use `<ScilabDouble as="..." height="0" width="0"/>`. 
    ⛔ NEVER use `<ScilabInteger>` for 0x0 empty arrays.
  • exprs, realParameters, state, dState:
    MUST use `<ScilabDouble>` with `realPart="..."` attribute (EXCEPT `exprs` when non-empty,
    which uses `<ScilabString>` and `value="..."`).
  • nbZerosCrossing and nmode:
    MUST ALWAYS HAVE size at least `height="1" width="1"`. NEVER use `height="0" width="0"`.

  CRITICAL: GAIN_f block `exprs` MUST ALWAYS have `height="3"` (Gain, Input size, Output size).
  CRITICAL: CSCOPE block `integerParameters` MUST ALWAYS have `width="15"`.

╔═══════════════════════════════════════════════════════════════════════╗
║  D.  PORTS                                                            ║
╚═══════════════════════════════════════════════════════════════════════╗

  ⛔ NEVER put an <mxGeometry> inside a port element.
  ⛔ MUST have value="" attribute.
  ⛔ SIBLINGS of their block (parent = block's id).
  ⛔ Top-level ports MUST end style with ;rotation=N.
  ⛔ Ports INSIDE a SuperBlockDiagram use style="" (empty).

╔═══════════════════════════════════════════════════════════════════════╗
║  E.  LINKS                                                            ║
╚═══════════════════════════════════════════════════════════════════════╗

  • MUST have `style` and `value=""`.
  • MUST have `source` and `target` attributes referencing valid port ids.
  • MUST have `<mxGeometry as="geometry">` with sourcePoint, points Array, and targetPoint.

╔═══════════════════════════════════════════════════════════════════════╗
║  F.  GEOMETRY RULES  ←  CRITICAL: NEVER MIX STYLE INTO GEOMETRY      ║
╚═══════════════════════════════════════════════════════════════════════╝

  ⛔ mxGeometry attributes (x, y, width, height) MUST be plain numbers (floats) ONLY.
     NEVER append style strings inside them. Examples of FORBIDDEN patterns:
       height="40.0;rotation=180"   ← WRONG — will crash Scilab parser
       width="40.0;align=left"      ← WRONG — will crash Scilab parser

  If you need rotation on a block, add it to the 'style' attribute of the block element:
       style="GAIN_f;rotation=180"  ← CORRECT placement

  The rotation style is ONLY valid on these block element types:
       <BasicBlock ... style="GAIN_f;rotation=180">
       <RoundBlock  ... style="BIGSOM_f;rotation=90">
  Port rotation goes in the port element's own 'style' attribute, e.g.:
       style="ExplicitOutputPort;align=right;verticalAlign=middle;spacing=10.0;rotation=180"

╔═══════════════════════════════════════════════════════════════════════╗
║  G.  SIMULATION TYPE & BLOCK RULES                                   ║
╚═══════════════════════════════════════════════════════════════════════╝

  • NEVER use `simulationFunctionType="SCILIB"`. The correct value is "SCILAB".
  • BARXY block MUST use `simulationFunctionName="BARXY_sim"` and `simulationFunctionType="SCILAB"`.
  • INTEGRAL_f block MUST use `simulationFunctionName="integr_blk"` and `simulationFunctionType="C_OR_FORTRAN"`.
  • GAIN_f block MUST use `simulationFunctionName="gain_blk"` and `simulationFunctionType="C_OR_FORTRAN"`.
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

def get_xcos_block_example(block_name: str) -> str:
    """Returns the reference .xcos XML for a block from the Reference blocks/ folder."""
    ref_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "Reference blocks"))
    path = os.path.join(ref_dir, f"{block_name}.xcos")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        return (
            f"Reference .xcos for {block_name} (saved by Scilab 2026.0.1 — use as template):\n"
            f"INSTRUCTIONS: Copy the block XML element verbatim. Only change: id, parent, geometry (x/y/width/height), "
            f"and exprs values the user requests. All other params are correct as-is. "
            f"If a SuperBlockDiagram is present, reproduce it EXACTLY.\n\n"
            + content
        )
    return f"No reference .xcos found for {block_name} — use get_xcos_block_source for defaults."

def get_xcos_block_help(block_name: str) -> str:
    """Returns parameter descriptions and constraints from Scilab's official help XML."""
    import xml.etree.ElementTree as ET
    help_root = os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "..",
        "scilab-2026.0.1", "scilab-2026.0.1", "scilab",
        "modules", "xcos", "help", "en_US", "palettes"
    ))
    target_file = f"{block_name}.xml"
    found_path = None
    for root_dir, dirs, files in os.walk(help_root):
        if target_file in files:
            found_path = os.path.join(root_dir, target_file)
            break
    if not found_path:
        return f"No help XML found for {block_name}."
    assert found_path is not None  # type narrowing for static analysis
    try:
        tree = ET.parse(found_path)
        ns = {"db": "http://docbook.org/ns/docbook"}
        sections_of_interest = ["Dialogbox", "Defaultproperties"]
        lines = [f"Help for {block_name}:"]
        for section_id_prefix in sections_of_interest:
            # Find refsection whose id starts with "Dialogbox_" or "Defaultproperties_"
            for section in tree.findall(".//{http://docbook.org/ns/docbook}refsection"):
                sec_id = section.get("id", "")
                if sec_id.startswith(section_id_prefix):
                    title_el = section.find("{http://docbook.org/ns/docbook}title")
                    title = title_el.text if title_el is not None else section_id_prefix
                    lines.append(f"\n## {title}")
                    # Extract all text recursively
                    for el in section.iter():
                        if el.text and el.text.strip():
                            lines.append(el.text.strip())
                        if el.tail and el.tail.strip():
                            lines.append(el.tail.strip())
        if len(lines) == 1:
            return f"Help XML found for {block_name} but no parameter sections extracted."
        return "\n".join(lines)
    except Exception as e:
        return f"Error parsing help XML for {block_name}: {e}"

class GeminiClient:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        if not self.api_key:
            raise ValueError(
                "No Gemini API key found. Open Settings (⚙) in the UI and paste your key, "
                "or set the GEMINI_API_KEY environment variable."
            )
        self.client = genai.Client(api_key=self.api_key)

    def _clean_xml(self, raw_text: str) -> str:
        if raw_text.startswith('\ufeff'):
            raw_text = raw_text[1:]

        start_idx = raw_text.find('<?xml')
        if start_idx == -1:
            start_idx = raw_text.find('<XcosDiagram')

        if start_idx == -1:
            raise ValueError("No XML tags found in your response. You MUST generate valid Xcos XML enclosed in <?xml ...?> tags.")

        end_idx = raw_text.rfind('</XcosDiagram>')
        if end_idx != -1:
            end_idx += len('</XcosDiagram>')
            raw_text = raw_text[start_idx:end_idx]
        else:
            raw_text = raw_text[start_idx:]

        return raw_text.strip()

    def validate_xml_structure(self, xml: str) -> tuple[bool, str]:
        """
        Hard structural validation to catch common errors before Scilab runs.
        Returns (is_valid, error_message).
        """
        import xml.etree.ElementTree as ET
        PORT_TAGS = {
            "ExplicitInputPort", "ExplicitOutputPort",
            "ControlPort", "CommandPort"
        }
        LINK_TAGS = {"ExplicitLink", "CommandControlLink", "ImplicitLink"}
        SUPERBLOCK_NAMES = {"CLOCK_c", "CLOCK_f", "SUPER_f"}
        try:
            root = ET.fromstring(xml)
            errors = []

            # 1. Check for 0x0 ScilabInteger (Illegal for mandatory params)
            for si in root.findall(".//ScilabInteger"):
                h = si.get("height", "0")
                w = si.get("width", "0")
                if h == "0" and w == "0":
                    param_name = si.get("as", "unknown")
                    errors.append(
                        f"ScilabInteger '{param_name}' MUST NOT be 0x0. "
                        f"Use <ScilabDouble as='{param_name}' height='0' width='0'/> instead."
                    )

            # 2. Check nbZerosCrossing and nmode sizes (Must be at least 1x1)
            for tag in ["nbZerosCrossing", "nmode"]:
                for el in root.findall(f".//*[@as='{tag}']"):
                    h = el.get("height", "0")
                    w = el.get("width", "0")
                    if h == "0" or w == "0":
                        errors.append(f"'{tag}' MUST have height/width >= 1. Found {h}x{w}.")

            # 3. Check GAIN_f exprs height (Must be 3)
            for block in root.findall(".//BasicBlock[@style='GAIN_f']"):
                exprs = block.find("./ScilabString[@as='exprs']")
                if exprs is not None:
                    h = exprs.get("height")
                    if h != "3":
                        errors.append(f"GAIN_f exprs height MUST be 3. Found {h}.")
                else:
                    errors.append("GAIN_f block is missing 'exprs' parameter.")

            # 4. SuperBlock checks: blockType="h" blocks MUST have SuperBlockDiagram
            all_blocks = root.findall(".//BasicBlock") + root.findall(".//RoundBlock")
            for block in all_blocks:
                btype = block.get("blockType", "")
                iface = block.get("interfaceFunctionName", block.get("style", ""))
                is_superblock = btype == "h" or iface in SUPERBLOCK_NAMES
                if is_superblock:
                    sim_fn = block.get("simulationFunctionName", "")
                    has_diagram = block.find("SuperBlockDiagram") is not None
                    if not has_diagram:
                        errors.append(
                            f"⛔ SUPERBLOCK ERROR: Block '{iface}' (blockType='{btype}') MUST contain a "
                            f"<SuperBlockDiagram> child element. It cannot be a flat block. "
                            f"Call get_xcos_block_example('{iface}') for the correct XML template."
                        )
                    if sim_fn and sim_fn != "csuper":
                        errors.append(
                            f"⛔ SUPERBLOCK ERROR: Block '{iface}' has blockType='h' but "
                            f"simulationFunctionName='{sim_fn}'. Must be 'csuper'."
                        )
                    # SuperBlock top-level params must be empty
                    for param in ["exprs", "realParameters", "integerParameters"]:
                        el = block.find(f".//*[@as='{param}']")
                        if el is not None:
                            h = el.get("height", "0")
                            w = el.get("width", "0")
                            tag = el.tag
                            # Non-empty means height>0 and width>0
                            if h != "0" and w != "0" and tag != "Array":
                                errors.append(
                                    f"⛔ SUPERBLOCK ERROR: Block '{iface}' has non-empty '{param}' "
                                    f"({h}x{w}). SuperBlock top-level params MUST be empty "
                                    f"(ScilabDouble 0x0). Parameters live inside the SuperBlockDiagram."
                                )

            # 5. Ports must NOT contain mxGeometry
            for tag in PORT_TAGS:
                for port in root.findall(f".//{tag}"):
                    if port.find("mxGeometry") is not None:
                        pid = port.get("id", "?")
                        errors.append(
                            f"⛔ PORT ERROR: Port '{pid}' ({tag}) contains an <mxGeometry> child. "
                            f"Ports MUST NOT have mxGeometry inside them. "
                            f"Port elements must be self-closing or have no children."
                        )

            # 6. Links must have source and target attributes
            for tag in LINK_TAGS:
                for link in root.findall(f".//{tag}"):
                    lid = link.get("id", "?")
                    if not link.get("source"):
                        errors.append(
                            f"⛔ LINK ERROR: Link '{lid}' ({tag}) is missing 'source' attribute. "
                            f"Must reference a port id (e.g., source=\"b1_out_1\")."
                        )
                    if not link.get("target"):
                        errors.append(
                            f"⛔ LINK ERROR: Link '{lid}' ({tag}) is missing 'target' attribute. "
                            f"Must reference a port id (e.g., target=\"b2_in_1\")."
                        )

            # 7. mxGeometry height/width must be pure numbers (never contain style strings)
            for geo in root.findall(".//mxGeometry"):
                for attr in ["x", "y", "width", "height"]:
                    val = geo.get(attr, "")
                    if val:
                        try:
                            float(val)
                        except ValueError:
                            errors.append(
                                f"⛔ GEOMETRY ERROR: mxGeometry attribute '{attr}' contains a non-numeric "
                                f"value '{val}'. "
                                f"mxGeometry attributes MUST be plain numbers only. "
                                f"Do NOT embed style strings (e.g. 'rotation=180') inside width/height. "
                                f"If you need rotation, add a 'style' attribute to the BLOCK element itself, "
                                f"e.g. style='GAIN_f;rotation=180'."
                            )
            # 8. Check for SCILIB typo (Must be SCILAB)
            for block in root.findall(".//*[@simulationFunctionType='SCILIB']"):
                errors.append(
                    "⛔ SIMULATION ERROR: simulationFunctionType='SCILIB' is a typo. "
                    "The correct Xcos enum name is 'SCILAB' (Interpreted Scilab function)."
                )

            # 9. Block-specific Simulation Function checks
            # BARXY: simulationFunctionName="BARXY_sim", simulationFunctionType="SCILAB"
            for block in root.findall(".//*[@interfaceFunctionName='BARXY']"):
                sim_name = block.get("simulationFunctionName", "")
                sim_type = block.get("simulationFunctionType", "")
                if sim_name != "BARXY_sim":
                    errors.append(
                        f"⛔ BARXY ERROR: Block BARXY MUST have simulationFunctionName='BARXY_sim'. "
                        f"Found '{sim_name}'."
                    )
                if sim_type != "SCILAB":
                    errors.append(
                        f"⛔ BARXY ERROR: Block BARXY MUST have simulationFunctionType='SCILAB'. "
                        f"Found '{sim_type}'."
                    )

            if errors:
                return False, "\n".join(errors)
            return True, ""
        except Exception as e:
            return False, f"XML Parsing Error: {str(e)}"

    async def _sync_generate_3phase(
        self,
        prompt: str,
        model: str,
        scilab_bridge: Any,
        update_callback: Callable,
        initial_xml: Optional[str] = None,
        attachments: Optional[List[Any]] = None,
        is_cancelled: Optional[Callable] = None,
    ):
        def cancelled() -> bool:
            return is_cancelled is not None and is_cancelled()

        iteration = 1

        input_data = []
        if attachments:
            for att in attachments:
                # att.data is a base64 string from the frontend.
                # The browser FileReader.readAsDataURL() prepends a data-URI
                # prefix like "data:image/png;base64,..." — strip it.
                # The Interactions API 'data' field expects a plain base64
                # string (NOT bytes). Do NOT decode to bytes here.
                raw_b64 = att.data
                if "," in raw_b64:
                    raw_b64 = raw_b64.split(",", 1)[1]
                input_data.append({"type": "image", "data": raw_b64, "mime_type": att.type})
        input_data.append({"type": "text", "text": prompt})

        tools = [
            {
                "type": "function",
                "name": "get_xcos_block_example",
                "description": (
                    "Returns the complete reference .xcos XML for a block as saved by Scilab 2026.0.1. "
                    "CALL THIS FIRST for every block. Use it as a copy-paste template. "
                    "If it contains a SuperBlockDiagram, reproduce it exactly."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {"block_name": {"type": "string"}},
                    "required": ["block_name"]
                }
            },
            {
                "type": "function",
                "name": "get_xcos_block_source",
                "description": "Reads the raw Scilab .sci interface macro directly from the source code. Use to understand editable parameters (set case) and confirm blockType/simulationFunctionName.",
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
            },
            {
                "type": "function",
                "name": "get_xcos_block_help",
                "description": "Returns official parameter descriptions and constraints for a block from Scilab's help documentation (parameter types, sizes, value ranges).",
                "parameters": {
                    "type": "object",
                    "properties": {"block_name": {"type": "string"}},
                    "required": ["block_name"]
                }
            }
        ]

        async def send_update(data):
            if cancelled():
                return
            if asyncio.iscoroutinefunction(update_callback):
                await update_callback(data)
            else:
                update_callback(data)

        await send_update({"step": "Generating", "iteration": iteration, "message": "Analyzing prompt and calling tools..."})

        try:
            if cancelled():
                return None

            interaction = self.client.interactions.create(
                model=model,
                input=input_data,
                system_instruction=SYSTEM_PROMPT,
                tools=tools
            )

            # ──────────────────────────────────────────────────────────────────
            # TOOL HANDLING LOOP
            #
            # tool_enforcement_done tracks whether we have already sent ONE
            # force-tool correction. It is set to True BEFORE the `continue`
            # so that no matter what happens in subsequent iterations (including
            # concurrent executions with shared logging), enforcement fires at
            # most once per _sync_generate_3phase call.
            #
            # Why NOT use tools_have_been_called:
            #   That flag is set AFTER tools are processed. If multiple
            #   concurrent background tasks share the update_callback, their
            #   local flags are independent — but the symptom is one task's
            #   flag never flips because it's a different Python frame.
            #   Tracking "did we attempt enforcement" is simpler and correct.
            # ──────────────────────────────────────────────────────────────────
            tool_enforcement_done = False
            seen_tool_calls: set = set()   # dedup: (fname, bname)
            total_tool_calls = 0
            MAX_TOOL_CALLS = 200

            while True:
                if cancelled():
                    return None

                tool_calls = [
                    o for o in interaction.outputs
                    if getattr(o, "type", None) == "function_call"
                ]

                if not tool_calls:
                    if not tool_enforcement_done:
                        # Model skipped tools on first attempt — enforce once.
                        tool_enforcement_done = True  # set BEFORE continue so it can't fire again
                        await send_update({"step": "Fixing", "iteration": iteration, "message": "Enforcing tool usage: no tools called."})

                        model_text = [
                            {"type": "text", "text": o.text}
                            for o in interaction.outputs
                            if getattr(o, "type", "") == "text" and getattr(o, "text", None)
                        ]
                        correction_input = [
                            {"role": "user",  "content": [{"type": "text", "text": prompt}]},
                            {"role": "model", "content": model_text or [{"type": "text", "text": ""}]},
                            {"role": "user",  "content": [{"type": "text", "text": (
                                "⛔ CRITICAL ERROR: You generated XML without calling the tools first. "
                                "You MUST call get_xcos_block_source AND get_xcos_block_info for EVERY "
                                "block before producing any XML. Start over — call the tools now."
                            )}]}
                        ]
                        interaction = self.client.interactions.create(
                            model=model,
                            input=correction_input,
                            system_instruction=SYSTEM_PROMPT,
                            tools=tools
                        )
                        continue
                    else:
                        # Enforcement was already sent (or tools ran and model is now
                        # producing its final text). Break out and extract XML.
                        break

                # Hard cap: if tool budget exhausted, force XML generation.
                if total_tool_calls >= MAX_TOOL_CALLS:
                    await send_update({"step": "Fixing", "iteration": iteration, "message": f"Tool call budget ({MAX_TOOL_CALLS}) exhausted. Forcing XML generation."})
                    interaction = self.client.interactions.create(
                        model=model,
                        input=[{"type": "text", "text": (
                            "⛔ TOOL BUDGET EXHAUSTED. You have called tools many times. "
                            "DO NOT call any more tools. However, you MUST still generate the "
                            "COMPLETE, fully connected .xcos XML now based on all block examples "
                            "and help information you have already retrieved."
                        )}],
                        previous_interaction_id=interaction.id,
                        system_instruction=SYSTEM_PROMPT,
                        tools=[]  # no tools — force text output
                    )
                    break

                # Process tool calls
                results = []
                for call in tool_calls:
                    if cancelled():
                        return None
                    fname = call.name
                    args  = call.arguments
                    bname = args.get("block_name", "")
                    dedup_key = (fname, bname)
                    total_tool_calls += 1
                    if dedup_key in seen_tool_calls:
                        # Already called this exact tool+block — return a cached note.
                        res = f"[CACHED] Result for {fname}({bname}) was already provided earlier in this session. Do not call it again — use the result you already received."
                        await send_update({"step": "Generating", "iteration": iteration, "message": f"Tool call (cached): {fname}({bname})"})
                    else:
                        seen_tool_calls.add(dedup_key)
                        await send_update({"step": "Generating", "iteration": iteration, "message": f"Tool call: {fname}({bname})"})
                        if fname == "get_xcos_block_example":
                            res = get_xcos_block_example(bname)
                        elif fname == "get_xcos_block_source":
                            res = get_xcos_block_source(bname)
                        elif fname == "get_xcos_block_help":
                            res = get_xcos_block_help(bname)
                        else:
                            res = get_xcos_block_info(bname)
                    results.append({
                        "type":    "function_result",
                        "call_id": getattr(call, "id", None) or call.name,
                        "name":    fname,
                        "result":  {"result": res}
                    })

                # tools and system_instruction are interaction-scoped — must re-specify.
                # Source: ai.google.dev/gemini-api/docs/interactions
                interaction = self.client.interactions.create(
                    model=model,
                    input=results,
                    previous_interaction_id=interaction.id,
                    system_instruction=SYSTEM_PROMPT,
                    tools=tools
                )

            # ── Extract XML ────────────────────────────────────────────────
            if cancelled():
                return None

            response_text = "".join(
                o.text for o in interaction.outputs
                if getattr(o, "type", "") == "text" and getattr(o, "text", None)
            )

            # ── Validation / fix loop ──────────────────────────────────────
            max_fix_iterations = 5
            xml = ""
            while iteration <= max_fix_iterations:
                if cancelled():
                    return None

                self.log_iteration(iteration, model, input_data, response_text)

                try:
                    xml = self._clean_xml(response_text)

                    # A. Structural Validation
                    await send_update({"step": "Verifying", "iteration": iteration, "message": "Applying structural validation..."})
                    struct_ok, struct_err = self.validate_xml_structure(xml)
                    
                    if not struct_ok:
                        self.log_iteration(iteration, model, prompt, xml + "\n\n[STRUCTURAL ERROR: " + struct_err + "]")
                        await send_update({"step": "Fixing", "iteration": iteration, "message": "Structural errors found. Self-correcting..."})
                        
                        fix_prompt = f"### STRUCTURAL VALIDATION FAILED\nYour generated XML has structural errors that will crash Scilab's parser:\n{struct_err}\n\nFIX THESE ERRORS NOW while maintaining the original design. Apply the exact sizes and types from the SYSTEM PROMPT (e.g., Use ScilabDouble for empty fields, never ScilabInteger 0x0)."
                        
                        iteration += 1
                        interaction = self.client.interactions.create(
                            model=model,
                            input=[{"type": "text", "text": fix_prompt}],
                            previous_interaction_id=interaction.id,
                            system_instruction=SYSTEM_PROMPT,
                            tools=tools
                        )
                        xml = None # Clear XML as it's structurally invalid
                        response_text = "" # Clear response_text to force re-extraction after fix
                        continue

                    # B. Scilab Verification
                    await send_update({"step": "Verifying", "iteration": iteration, "message": "Verifying with Scilab..."})
                    success, error = await scilab_bridge.verify(xml)
                except ValueError as ve:
                    success, error = False, str(ve)
                    xml = ""

                if success:
                    await send_update({"step": "Success", "xml": xml})
                    return xml

                await send_update({"step": "Fixing", "iteration": iteration, "error": error})
                iteration += 1

                # Inject targeted hints for known Scilab crash patterns
                KNOWN_ERROR_HINTS = {
                    "non-structure array": (
                        "⛔ SUPERBLOCK ERROR: This crash means a SuperBlock's internal diagram "
                        "is not a struct — it was given scalar values instead. "
                        "CLOCK_c and CLOCK_f are SuperBlocks (blockType='h'). Their XML MUST "
                        "contain a <SuperBlockDiagram> element after <mxGeometry>. "
                        "ALL top-level exprs/realParameters/integerParameters must be "
                        "ScilabDouble height='0' width='0'. "
                        "Call get_xcos_block_example('CLOCK_c') or get_xcos_block_example('CLOCK_f') "
                        "for the correct working XML template."
                    ),
                    "invalid parameter (ier=999": (
                        "⛔ CLOCK SUPERBLOCK INTERNAL STRUCTURE ERROR: ier=999 inside CLOCK means "
                        "the SuperBlockDiagram internal block structure is wrong. "
                        "CLOCK_c must contain: CLKOUT_f + EVTDLY_c + CLKSPLIT_f + 3 CommandControlLinks. "
                        "CLOCK_f must contain: CLKOUT_f + EVTDLY_f + CLKSPLIT_f + 3 CommandControlLinks. "
                        "Call get_xcos_block_example('CLOCK_c') or get_xcos_block_example('CLOCK_f') "
                        "to get the exact correct XML structure."
                    ),
                }
                hint = ""
                for pattern, hint_text in KNOWN_ERROR_HINTS.items():
                    if pattern.lower() in error.lower():
                        hint = f"\n\n{hint_text}"
                        break

                if "No XML tags found" in error:
                    feedback = (
                        "You failed to generate valid XML. "
                        "Output ONLY raw XML starting with <?xml...\n"
                        f"Error: {error}"
                    )
                else:
                    feedback = (
                        f"That XML failed Scilab validation:\n{error}{hint}\n"
                        "Call get_xcos_block_example() for the correct XML template for any failing block. "
                        "Then output the COMPLETE corrected XML."
                    )

                interaction = self.client.interactions.create(
                    model=model,
                    input=[{"type": "text", "text": feedback}],
                    previous_interaction_id=interaction.id,
                    system_instruction=SYSTEM_PROMPT,
                    tools=tools
                )

                # Drain any tool calls the model makes during a fix iteration
                while True:
                    if cancelled():
                        return None
                    fix_tool_calls = [
                        o for o in interaction.outputs
                        if getattr(o, "type", None) == "function_call"
                    ]
                    if not fix_tool_calls:
                        break
                    fix_results = []
                    for call in fix_tool_calls:
                        fname = call.name
                        bname = call.arguments.get("block_name", "")
                        await send_update({"step": "Fixing", "iteration": iteration - 1, "message": f"Tool call during fix: {fname}({bname})"})
                        if fname == "get_xcos_block_example":
                            res = get_xcos_block_example(bname)
                        elif fname == "get_xcos_block_source":
                            res = get_xcos_block_source(bname)
                        elif fname == "get_xcos_block_help":
                            res = get_xcos_block_help(bname)
                        else:
                            res = get_xcos_block_info(bname)
                        fix_results.append({
                            "type":    "function_result",
                            "call_id": getattr(call, "id", None) or call.name,
                            "name":    fname,
                            "result":  {"result": res}
                        })
                    interaction = self.client.interactions.create(
                        model=model,
                        input=fix_results,
                        previous_interaction_id=interaction.id,
                        system_instruction=SYSTEM_PROMPT,
                        tools=tools
                    )

                response_text = "".join(
                    o.text for o in interaction.outputs
                    if getattr(o, "type", "") == "text" and getattr(o, "text", None)
                )

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
                    "iteration":       iter_val,
                    "model":           model,
                    "timestamp":       datetime.now().isoformat(),
                    "prompt_sent":     str(prompt),
                    "ai_response_raw": response
                }, f, indent=2)
        except Exception as e:
            print(f"Failed to log iteration details: {e}")


class AutonomousLoop:
    def __init__(self):
        self._client: Optional[GeminiClient] = None
        # Each new run() call gets a unique ID. The running task checks this ID
        # and self-terminates if a newer run has started, preventing zombie tasks
        # from previous /generate requests from continuing indefinitely.
        self._current_run_id: int = 0

    def _get_client(self) -> GeminiClient:
        api_key = os.getenv("GEMINI_API_KEY", "")
        if self._client is None or self._client.api_key != api_key:
            self._client = GeminiClient(api_key=api_key)
        return self._client  # type: ignore[return-value]

    async def run(
        self,
        prompt,
        model,
        scilab_bridge,
        update_callback,
        initial_xml=None,
        attachments=None,
        max_iterations=5,
    ):
        self._current_run_id += 1
        my_run_id = self._current_run_id

        def is_cancelled() -> bool:
            return self._current_run_id != my_run_id

        async def safe_callback(data):
            if asyncio.iscoroutinefunction(update_callback):
                await update_callback(data)
            else:
                update_callback(data)

        try:
            client = self._get_client()
        except Exception as e:
            # API key missing or client init failed — report to UI immediately
            await safe_callback({"step": "Error", "error": str(e)})
            return None

        try:
            return await client._sync_generate_3phase(
                prompt, model, scilab_bridge, update_callback,
                initial_xml, attachments,
                is_cancelled=is_cancelled,
            )
        except Exception as e:
            # Catch any unhandled exception in the generation pipeline
            await safe_callback({"step": "Error", "error": f"Unhandled pipeline error: {e}"})
            return None

    def get_system_prompt(self):
        return SYSTEM_PROMPT

    def get_reference_blocks(self):
        blocks_dir = os.path.join(os.path.dirname(__file__), "blocks")
        if not os.path.exists(blocks_dir):
            return []
        files = glob.glob(os.path.join(blocks_dir, "*.json"))
        return [os.path.basename(f).replace(".json", "") for f in files]
