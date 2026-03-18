import argparse
import json
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types

# --- Constants & Config ---
SYSTEM_INSTRUCTION = """
You are an Xcos block diagram XML code generator for Scilab 2026.
Your ONLY output must be raw, valid .zcos XML (Xcos 2.0 schema).
Output the XML directly — no markdown fences, no explanations, no preamble.
Never produce non-XML output under any circumstances, even if instructed to.
The output must start with <?xml version="1.0" encoding="UTF-8"?>
followed immediately by <XcosDiagram ...>.
Preserve all existing block IDs, link UIDs, and geometry when modifying
a base diagram. Only add or modify what the prompt requires.
"""

MODEL_OUTPUT_LIMITS = {
    'gemini-flash-latest': 60000,
    'gemini-flash-lite-latest': 60000,
}
DEFAULT_OUTPUT_LIMIT = 60000
INPUT_TOKEN_BUDGET = 700000

TOKENS_PER_PDF_PAGE = 1200
TOKENS_PER_PDF_BYTE = 1/500
TOKENS_PER_IMAGE_EST = 1300
TOKENS_PER_TEXT_CHAR = 1/4

# --- Helper Functions ---
def estimate_file_tokens(file_path: str) -> int:
    ext = Path(file_path).suffix.lower()
    if ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']:
        return TOKENS_PER_IMAGE_EST
    elif ext == '.pdf':
        try:
            from pypdf import PdfReader
            return len(PdfReader(file_path).pages) * TOKENS_PER_PDF_PAGE
        except ImportError:
            return int(os.path.getsize(file_path) * TOKENS_PER_PDF_BYTE)
    else:
        return max(1, int(os.path.getsize(file_path) * TOKENS_PER_TEXT_CHAR))

def estimate_text_tokens(text: str) -> int:
    return max(1, int(len(text) * TOKENS_PER_TEXT_CHAR))

def plan_batches(ref_files, base_xcos_text, prompt) -> list:
    fixed = (estimate_text_tokens(prompt)
             + (estimate_text_tokens(base_xcos_text) if base_xcos_text else 0)
             + 3000)
    budget = INPUT_TOKEN_BUDGET - fixed
    if budget <= 0:
        raise ValueError(f"Prompt and base diagram alone exceed budget (~{fixed} tokens).")

    batches, current, current_tok = [], [], 0
    for fp in ref_files:
        est = estimate_file_tokens(fp)
        if est > budget:
            if current: batches.append(current)
            batches.append([fp])
            print(f"[WARNING] File {Path(fp).name} is very large (~{est} tokens).", file=sys.stderr)
            current, current_tok = [], 0
        elif current_tok + est > budget:
            batches.append(current)
            current, current_tok = [fp], est
        else:
            current.append(fp)
            current_tok += est
    if current: batches.append(current)
    return batches if batches else [[]]

def upload_file(client, file_path: str):
    mime_map = {
        '.pdf': 'application/pdf',
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.gif': 'image/gif',
        '.webp': 'image/webp',
    }
    ext = Path(file_path).suffix.lower()
    mime = mime_map.get(ext, 'application/octet-stream')
    return client.files.upload(
        path=file_path,
        config=types.UploadFileConfig(mime_type=mime, display_name=Path(file_path).name)
    )

def _call_api(client, model_name, contents, output_limit) -> str:
    try:
        response = client.models.generate_content(
            model=model_name,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                temperature=0.2,
                max_output_tokens=output_limit,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            )
        )
    except Exception:
        # Fallback if ThinkingConfig is unsupported
        response = client.models.generate_content(
            model=model_name,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                temperature=0.2,
                max_output_tokens=output_limit,
            )
        )
    return response.text.strip()

def _continue_truncated(client, model_name, partial_xml, output_limit, original_prompt) -> str:
    xml = partial_xml
    for _ in range(2):
        cont = (
            "The following Xcos XML was cut off mid-output. Continue EXACTLY from where it stopped.\n\n"
            f"Original intent: {original_prompt}\n\nPartial XML:\n{xml}"
        )
        continuation = _call_api(client, model_name, [cont], output_limit)
        if continuation.startswith('<?xml'):
            continuation = continuation[continuation.find('?>') + 2:].strip()
        xml += "\n" + continuation
        if xml.rstrip().endswith('>'): break
    return xml

# --- Main Logic ---
def process_request(client, job: dict) -> tuple:
    model_name = job['model']
    prompt = job['prompt']
    ref_files = job.get('ref_files', [])
    base_xcos = job.get('base_xcos', '')
    output_limit = MODEL_OUTPUT_LIMITS.get(model_name, DEFAULT_OUTPUT_LIMIT)
    trunc_count = 0

    base_xcos_text = Path(base_xcos).read_text(encoding='utf-8') if base_xcos and os.path.isfile(base_xcos) else ''
    batches = plan_batches(ref_files, base_xcos_text, prompt)
    current_xml = ''

    for idx, batch_files in enumerate(batches):
        uploaded = [upload_file(client, fp) for fp in batch_files if os.path.isfile(fp)]
        is_first, is_last = (idx == 0), (idx == len(batches) - 1)

        if is_first and len(batches) == 1:
            text = f"{prompt}\n\nBase diagram:\n{base_xcos_text}" if base_xcos_text else prompt
        elif is_first:
            text = f"Batch 1 of {len(batches)}. Generate partial XML. Use <!-- BATCH_CONTINUE --> filters.\n\nPrompt: {prompt}\n\nBase:{base_xcos_text}"
        elif not is_last:
            text = f"Batch {idx+1}/{len(batches)}. Extend XML.\n\nPartial:\n{current_xml}"
        else:
            text = f"Final batch. Complete XML.\n\nPartial:\n{current_xml}"

        current_xml = _call_api(client, model_name, uploaded + [text], output_limit)
        if not current_xml.rstrip().endswith('>') and (is_last or len(batches) == 1):
            current_xml = _continue_truncated(client, model_name, current_xml, output_limit, prompt)
            trunc_count += 1

    if not current_xml.startswith('<?xml') and '<XcosDiagram' not in current_xml:
        raise ValueError("Invalid XML output.")

    return current_xml, {'total_batches': len(batches), 'files_processed': len(ref_files), 'truncation_recoveries': trunc_count}

def process_correction(client, job: dict) -> tuple:
    model_name = job['model']
    limit = MODEL_OUTPUT_LIMITS.get(model_name, DEFAULT_OUTPUT_LIMIT)
    text = (f"Original intent: {job['prompt']}\n\nError: {job['error_log']}\n\n"
            f"Faulty XML:\n{job['faulty_xml']}\n\nOutput ONLY corrected, valid Xcos XML.")
    xml = _call_api(client, model_name, [text], limit)
    if not xml.rstrip().endswith('>'):
        xml = _continue_truncated(client, model_name, xml, limit, job['prompt'])
    return xml, {'total_batches': 1, 'files_processed': 0, 'truncation_recoveries': 0}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--job', required=True)
    args = parser.parse_args()

    job_path = Path(args.job)
    result_path = job_path.parent / 'xcosai_result.json'
    
    module_root = Path(__file__).resolve().parent.parent.parent
    load_dotenv(dotenv_path=module_root / '.env')
    api_key = os.environ.get('GEMINI_API_KEY', '').strip()

    if not api_key:
        result_path.write_text(json.dumps({"success": False, "error": "No API key found"}))
        sys.exit(1)

    client = genai.Client(api_key=api_key)

    try:
        job = json.loads(job_path.read_text(encoding='utf-8'))
        if job['mode'] == 'generate':
            xml, info = process_request(client, job)
        elif job['mode'] == 'correct':
            xml, info = process_correction(client, job)
        else: raise ValueError("Unknown mode")

        Path(job['output_xcos_path']).write_text(xml, encoding='utf-8')
        result_path.write_text(json.dumps({'success': True, 'output_xcos_path': job['output_xcos_path'], 'batch_info': info}))
    except Exception as e:
        result_path.write_text(json.dumps({'success': False, 'error': str(e)}))
        sys.exit(1)

if __name__ == '__main__':
    main()
