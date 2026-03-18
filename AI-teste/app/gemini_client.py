import base64
import glob
import json
import os
import re
from datetime import datetime

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:
    raise ImportError(
        "google-genai is not installed. Run: pip install google-genai"
    )

# ---------------------------------------------------------------------------
# Load block definitions from individual JSON files in the blocks/ directory.
# Each file is named <interfaceFunctionName>.json  (e.g. CLOCK_c.json).
# Files are cached per block name after first load.
# ---------------------------------------------------------------------------
_BLOCKS_DIR: str = os.path.join(os.path.dirname(os.path.dirname(__file__)), "blocks")
_BLOCK_CACHE: dict[str, dict] = {}


def get_xcos_block_info(block_name: str) -> str:
    """
    Retrieves the complete structured JSON definition for an Xcos block from
    the blocks/ directory.  Always call this tool before using any block in
    the diagram — never generate block XML from memory.

    Args:
        block_name: The interfaceFunctionName of the block
                    (e.g. 'CLOCK_c', 'CSCOPE', 'GAIN_f', 'scifunc_block_m').

    Returns:
        A JSON string containing the block's tag, geometry, parameters, and
        ports arrays, or an error string if the block is not in the catalogue.
    """
    if block_name in _BLOCK_CACHE:
        return json.dumps(_BLOCK_CACHE[block_name], indent=2)

    block_path = os.path.join(_BLOCKS_DIR, f"{block_name}.json")

    if not os.path.exists(block_path):
        # Build a helpful hint from the available filenames
        available = sorted(
            os.path.splitext(os.path.basename(p))[0]
            for p in glob.glob(os.path.join(_BLOCKS_DIR, "*.json"))
            if not os.path.basename(p).startswith("_")
        )
        hint = ", ".join(available[:20])
        return (
            f"Error: Block '{block_name}' is not in the block catalogue.\n"
            f"Available blocks (first 20): {hint}...\n"
            f"Please ask the user to clarify the block name or try a similar alternative."
        )

    with open(block_path, "r", encoding="utf-8") as f:
        block_info = json.load(f)

    _BLOCK_CACHE[block_name] = block_info
    return json.dumps(block_info, indent=2)

# ---------------------------------------------------------------------------
# System prompt — instructs Gemini to generate a .xcos XML file directly.
# The .xcos format is the legacy plain-XML format that Scilab 2026 still opens.
# No Scilab execution is needed; Python writes the XML straight to disk.
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """\
You are an expert Scilab Xcos diagram builder.
Your ONLY task is to output a complete, valid .xcos XML file that Scilab 2026
Xcos can open directly from disk.

╔═══════════════════════════════════════════════════════════════╗
║  SCILAB 2026 CLI COMPATIBILITY (IMPORTANT)                   ║
╟───────────────────────────────────────────────────────────────╢
║ If asked to generate a Scilab script (.sce), ALWAYS use:      ║
║   loadScicos();                                               ║
║   loadXcosLibs();                                             ║
║ Failure to call loadScicos() first results in Undefined error.║
╚═══════════════════════════════════════════════════════════════╝

╔═══════════════════════════════════════════════════════════════╗
║  MASTER RULE: USE THE BLOCK CATALOGUE TOOL FOR ALL BLOCKS    ║
╚═══════════════════════════════════════════════════════════════╝

You have access to a tool called `get_xcos_block_info`.
Call it for EVERY block before generating any XML — never invent XML from memory.
The tool returns JSON with: tag, interfaceFunctionName, blockType,
simulationFunctionName, simulationFunctionType, dependsOnU, dependsOnT,
geometry, parameters, ports, xmlExample.

Use the `xmlExample` field as the PRIMARY reference for that block's XML.

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
</XcosDiagram>

╔═══════════════════════════════════════════════════════════════════════╗
║  B.  BLOCK ELEMENT                                                    ║
╚═══════════════════════════════════════════════════════════════════════╝

  • XML tag   = block["tag"]  (BasicBlock, RoundBlock, SplitBlock, …)
  • id        = short sequential id: b1, b2, b3, …
  • parent    = ALWAYS "0:2:0"
  • style     = block["interfaceFunctionName"]
  • All other attributes (blockType, simulationFunctionName, etc.) from JSON.
  • mxGeometry goes LAST among the block's children (after all parameters).
    CLOCK_c EXCEPTION: SuperBlockDiagram goes AFTER mxGeometry.

╔═══════════════════════════════════════════════════════════════════════╗
║  C.  PARAMETERS                                                       ║
╚═══════════════════════════════════════════════════════════════════════╝

  Always emit ALL of: exprs, realParameters, integerParameters,
  objectsParameters, nbZerosCrossing, nmode, state, dState, oDState, equations.

  ScilabDouble: use attribute `realPart` (NOT `value`) for data elements.
  Empty ScilabDouble:  <ScilabDouble as="realParameters" height="0" width="0"/>
  Empty lists:
    <Array as="objectsParameters" scilabClass="ScilabList"/>
    <Array as="oDState" scilabClass="ScilabList"/>
    <Array as="equations" scilabClass="ScilabList"/>

╔═══════════════════════════════════════════════════════════════════════╗
║  D.  PORTS  ← MOST CRITICAL SECTION                                  ║
╚═══════════════════════════════════════════════════════════════════════╝

  ⛔ NEVER put an <mxGeometry> inside a port element.
  ⛔ NEVER omit the value="" attribute from a port element.
  ⛔ NEVER add any child elements to a port — ports are self-closing.

  Port elements are SIBLINGS of their block (parent = block's id).
    <ExplicitInputPort id="b1_in_1" parent="b1" ordering="1"
        dataType="REAL_MATRIX" dataColumns="1" dataLines="-1"
        initialState="0.0"
        style="ExplicitInputPort;align=left;verticalAlign=middle;spacing=10.0;rotation=0"
        value=""/>

  Port id:  {blockId}_{portRole}_{ordering}
    portRole: in → ExplicitInputPort, out → ExplicitOutputPort,
              ctrl → ControlPort, cmd → CommandPort

  MANDATORY ;rotation=N suffix on ALL port styles:
    ExplicitInputPort  → ;rotation=0
    ExplicitOutputPort → ;rotation=0
    ControlPort        → ;rotation=90
    CommandPort        → ;rotation=90

  Copy dataType, dataColumns, dataLines, initialState from the block JSON.

╔═══════════════════════════════════════════════════════════════════════╗
║  E.  LINKS                                                            ║
╚═══════════════════════════════════════════════════════════════════════╗

  <ExplicitLink id="l1" parent="0:2:0" source="b1_out_1" target="b2_in_1"
      style="ExplicitLink" value="">
    <mxGeometry as="geometry">
      <mxPoint as="sourcePoint" x="…" y="…"/>
      <Array as="points"></Array>
      <mxPoint as="targetPoint" x="…" y="…"/>
    </mxGeometry>
  </ExplicitLink>

  <CommandControlLink id="l2" parent="0:2:0" source="b1_cmd_1"
      target="b2_ctrl_1" style="CommandControlLink" value="">
    <mxGeometry as="geometry">
      <mxPoint as="sourcePoint" x="…" y="…"/>
      <Array as="points"></Array>
      <mxPoint as="targetPoint" x="…" y="…"/>
    </mxGeometry>
  </CommandControlLink>

╔═══════════════════════════════════════════════════════════════════════╗
║  F.  BLOCK-SPECIFIC RULES ← READ ALL                                 ║
╚═══════════════════════════════════════════════════════════════════════╗

  GAIN_f ─ exprs height="3" (to match ground truth):
    <ScilabString as="exprs" height="3" width="1">
      <data line="0" column="0" value="1"/>
      <data line="1" column="0" value=" "/>
      <data line="2" column="0" value=" "/>
    </ScilabString>

  MUX ─ must include ALL standard parameter blocks.

  scifunc_block_m ─ CRITICAL:
  • objectsParameters MUST BE POPULATED with the SAME ScilabStrings as the
    function body Array. It is NOT an empty Array.
  • Second body string = "xd=[]" (not a space). Last has TWO lines.
  • Use y1=%e^(u1) for exponential (NOT y1=exp(u1)).
  objectsParameters example for y1=%e^(u1):
    <Array as="objectsParameters" scilabClass="ScilabList">
      <ScilabString height="1" width="1"><data line="0" column="0" value="y1=%e^(u1)"/></ScilabString>
      <ScilabString height="1" width="1"><data line="0" column="0" value="xd=[]"/></ScilabString>
      <ScilabString height="1" width="1"><data line="0" column="0" value=" "/></ScilabString>
      <ScilabString height="1" width="1"><data line="0" column="0" value=" "/></ScilabString>
      <ScilabString height="1" width="1"><data line="0" column="0" value=" "/></ScilabString>
      <ScilabString height="1" width="1"><data line="0" column="0" value=" "/></ScilabString>
      <ScilabString height="2" width="1">
        <data line="0" column="0" value=" "/>
        <data line="1" column="0" value="y1=[]"/>
      </ScilabString>
    </Array>

  CLINDUMMY_f ─ state height="1" width="1":
    <ScilabDouble as="state" height="1" width="1">
      <data line="0" column="0" realPart="0.0"/>
    </ScilabDouble>

  CLOCK_c ─ CRITICAL INTERNAL STRUCTURE. SuperBlockDiagram AFTER mxGeometry:
  • SuperBlockDiagram attrs: background="-1" gridEnabled="1" title=""
  • First child: <Array as="context" scilabClass="String[]"></Array>
  • Internal blocks: EVTDLY_c + CLKSPLIT_f (SplitBlock) + CLKOUTV_f (EventOutBlock)
    ⛔ Use CLKOUTV_f NOT CLKOUT_f
  • 3 CommandControlLinks: EVTDLY_c.cmd→CLKSPLIT_f.ctrl,
    CLKSPLIT_f.cmd1→CLKOUTV_f.ctrl, CLKSPLIT_f.cmd2→EVTDLY_c.ctrl
  • Trailing: <mxCell as="defaultParent" id="inner_root_2" parent="inner_root_1"/>
  • Port styles inside SuperBlockDiagram use style="" (empty)

FINAL RULES:
• Output ONLY raw XML. No markdown fences, no commentary.
• realPart (not value) for all ScilabDouble data elements.
• Ports: no mxGeometry, must have value="", must end style with ;rotation=N.
• GAIN_f exprs: height="3" (not 1).
• scifunc_block_m: objectsParameters MUST be populated (Scilab 2026 requirement).
• mxGeometry: goes LAST among a block's children.
• CLOCK_c: use CLKOUTV_f (not CLKOUT_f) inside SuperBlockDiagram.
• NEVER stop early — complete file must end with </XcosDiagram>.
"""

class GeminiClient:
    def __init__(self, api_key: str):
        self.client = genai.Client(api_key=api_key)

    def generate_xcos_xml(self, prompt: str, files: list, model_name: str = "gemini-flash-latest", log_push=None) -> str:
        """
        3-phase generation strategy:
          Phase 1: Generate XML (may be partial due to token limits)
          Phase 2: Continuation loop until </XcosDiagram> is present
          Phase 3: Validation review — Gemini self-reviews the assembled XML
                   against the block catalogue and fixes any issues.

        Returns the final validated raw .xcos XML string.
        """
        import time

        # Setup debug log directory
        debug_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "debug_logs")
        os.makedirs(debug_dir, exist_ok=True)
        session_ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        def save_debug_log(content: str, label: str):
            try:
                log_path = os.path.join(debug_dir, f"{session_ts}_{label}.txt")
                with open(log_path, "w", encoding="utf-8") as df:
                    df.write(content)
                if log_push:
                    log_push("info", f"Debug log saved: {session_ts}_{label}.txt")
            except Exception as de:
                if log_push:
                    log_push("warn", f"Could not save debug log: {de}")

        def clean_xml(raw_text: str) -> str:
            m = re.search(r'```(?:xml)?\s*(.*?)\s*```', raw_text, re.DOTALL)
            if m:
                return m.group(1).strip()
            return raw_text.strip()

        def send_with_retry(chat, message, phase_label: str):
            """Send a message, retrying on rate limit."""
            while True:
                try:
                    resp = chat.send_message(message)
                    return resp
                except Exception as e:
                    err = str(e)
                    if "429" in err or "RESOURCE_EXHAUSTED" in err:
                        if log_push:
                            log_push("warn", f"[{phase_label}] Rate limit hit. Waiting 35s...")
                        time.sleep(35)
                    else:
                        raise

        # --- Build initial message parts ---
        user_text = "USER REQUEST:\n" + prompt
        if files:
            user_text += "\n\nATTACHED CONTEXT FILES:\n"
        parts = [genai_types.Part(text=user_text)]

        for f in files:
            if f.get("type") == "binary":
                name_lower = f["name"].lower()
                if name_lower.endswith(".pdf"):
                    mime = "application/pdf"
                elif name_lower.endswith(".png"):
                    mime = "image/png"
                elif name_lower.endswith((".jpg", ".jpeg")):
                    mime = "image/jpeg"
                else:
                    mime = "application/octet-stream"
                try:
                    raw = base64.b64decode(f["content"])
                    if "mime" in f:
                        mime = f["mime"]
                    parts.append(genai_types.Part(
                        inline_data=genai_types.Blob(mime_type=mime, data=raw)
                    ))
                except Exception:
                    parts.append(genai_types.Part(
                        text=f"\n[Attached file: {f['name']} — could not decode]"
                    ))
            else:
                parts.append(genai_types.Part(
                    text=f"\n--- {f['name']} ---\n{f.get('content', '')}\n"
                ))

        config = genai_types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.2,
            max_output_tokens=65536,
            tools=[get_xcos_block_info],
            automatic_function_calling=genai_types.AutomaticFunctionCallingConfig(disable=False)
        )

        # ══════════════════════════════════════════════════════════════
        # PHASE 1: Initial generation
        # ══════════════════════════════════════════════════════════════
        if log_push:
            log_push("info", "Phase 1: Generating XML...")

        chat = self.client.chats.create(model=model_name, config=config)
        response = send_with_retry(chat, parts, "Phase1")
        xml = clean_xml(response.text)
        save_debug_log(xml, "phase1_initial")

        # ══════════════════════════════════════════════════════════════
        # PHASE 2: Continuation loop until XML is complete
        # ══════════════════════════════════════════════════════════════
        max_continuations = 5
        cont_count = 0
        while not xml.rstrip().endswith("</XcosDiagram>") and cont_count < max_continuations:
            cont_count += 1
            if log_push:
                log_push("warn", f"Phase 2: XML incomplete — continuation {cont_count}/{max_continuations}")
            cont_response = send_with_retry(
                chat,
                "Your output was truncated. Continue EXACTLY where you left off. "
                "Output ONLY raw XML — no markdown, no repeated content.",
                f"Phase2-cont{cont_count}"
            )
            xml += "\n" + clean_xml(cont_response.text)
            save_debug_log(xml, f"phase2_cont{cont_count}")

        if not xml.rstrip().endswith("</XcosDiagram>"):
            if log_push:
                log_push("error", "Phase 2: XML still incomplete after max continuations. Proceeding to validation anyway.")

        # ══════════════════════════════════════════════════════════════
        # PHASE 3: Validation review pass
        # ══════════════════════════════════════════════════════════════
        if log_push:
            log_push("info", "Phase 3: Running validation review pass...")

        review_prompt = (
            "Below is the assembled Xcos XML you generated. "
            "Review it thoroughly against the rules in your system prompt and the block catalogue (use the tool as needed). "
            "Check for:\n"
            "1. Missing <Array as=\"context\"> at root level and inside SuperBlockDiagram\n"
            "2. CLOCK_c: must use CLKOUTV_f (not CLKOUT_f), CLKSPLIT_f, EVTDLY_c with 3 links\n"
            "3. scifunc_block_m: objectsParameters must be populated (not empty)\n"
            "4. All 10 mandatory parameters present on every block\n"
            "5. Ports have value=\"\" and no mxGeometry\n"
            "6. GAIN_f exprs height=\"1\"\n"
            "7. XML starts with <?xml and ends with </XcosDiagram>\n\n"
            "If any issues are found, output the COMPLETE corrected XML. "
            "If the XML is already correct, output it unchanged. "
            "Output ONLY raw XML — no markdown, no commentary.\n\n"
            "XML TO REVIEW:\n" + xml
        )

        # Use a fresh chat so review prompt doesn't carry the full generation history token cost
        review_config = genai_types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.1,
            max_output_tokens=65536,
            tools=[get_xcos_block_info],
            automatic_function_calling=genai_types.AutomaticFunctionCallingConfig(disable=False)
        )
        review_chat = self.client.chats.create(model=model_name, config=review_config)

        try:
            review_response = send_with_retry(review_chat, review_prompt, "Phase3-review")
            reviewed_xml = clean_xml(review_response.text)

            # If the review returned XML, use it; otherwise keep what we had
            if "<XcosDiagram" in reviewed_xml:
                xml = reviewed_xml
                save_debug_log(xml, "phase3_reviewed")
                if log_push:
                    log_push("success", "Phase 3: Review complete. Using reviewed XML.")

                # Phase 3 continuation if review result also got truncated
                rev_continuations = 0
                while not xml.rstrip().endswith("</XcosDiagram>") and rev_continuations < 3:
                    rev_continuations += 1
                    if log_push:
                        log_push("warn", f"Phase 3: Reviewed XML incomplete — continuation {rev_continuations}")
                    rc = send_with_retry(
                        review_chat,
                        "Output was truncated. Continue EXACTLY where you left off. "
                        "Output ONLY raw XML.",
                        f"Phase3-cont{rev_continuations}"
                    )
                    xml += "\n" + clean_xml(rc.text)
                save_debug_log(xml, "phase3_final")
            else:
                if log_push:
                    log_push("warn", "Phase 3: Review response did not contain XML — keeping pre-review output.")

        except Exception as e:
            if log_push:
                log_push("warn", f"Phase 3 review failed ({e}). Using pre-review XML.")

        return xml