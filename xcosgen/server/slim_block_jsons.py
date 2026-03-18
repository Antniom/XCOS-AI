"""
slim_block_jsons.py
-------------------
Migration script: strips all xcosgen block JSON files down to annotation-only.

Fields KEPT  : name, description, sourceFile, criticalRules, anomalies,
               commonUses, relatedBlocks
Fields REMOVED: blockType, tag, interfaceFunctionName, simulationFunctionName,
                simulationFunctionType, dependsOnU, dependsOnT, geometry,
                parameters, ports, xmlExample, category, and any other data
                field not in the keep-list.

Also:
  - Locates the matching .sci source file in SCILAB_MACROS_DIR and writes a
    relative 'sourceFile' path into each slim JSON.
  - Backs up originals to blocks/_backup/ before any modification.

Usage:
  python slim_block_jsons.py             # real run
  python slim_block_jsons.py --dry-run   # preview diffs, no writes
  python slim_block_jsons.py --block CSCOPE  # process one block only
"""

import json
import os
import sys
import shutil
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BLOCKS_DIR = Path(__file__).parent / "blocks"
BACKUP_DIR = BLOCKS_DIR / "_backup"

# Path to the Scilab 2026 source macros folder.
# Adjust if your scilab folder is in a different location.
_THIS_DIR = Path(__file__).parent          # xcosgen/server/
_PROJECT_DIR = _THIS_DIR.parent.parent     # AI xcos module/
SCILAB_MACROS_DIR = (
    _PROJECT_DIR
    / "scilab-2026.0.1"
    / "scilab-2026.0.1"
    / "scilab"
    / "modules"
    / "scicos_blocks"
    / "macros"
)

# Fields to preserve in the slim JSON (all others are removed).
KEEP_FIELDS = {
    "name",
    "description",
    "sourceFile",
    "criticalRules",
    "anomalies",
    "commonUses",
    "relatedBlocks",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def find_sci_file(block_name: str) -> Path | None:
    """Search SCILAB_MACROS_DIR recursively for <block_name>.sci"""
    if not SCILAB_MACROS_DIR.exists():
        return None
    for candidate in SCILAB_MACROS_DIR.rglob(f"{block_name}.sci"):
        return candidate
    return None


def relative_sci_path(sci_path: Path) -> str:
    """Return a relative path from the project root for human readability."""
    try:
        return str(sci_path.relative_to(_PROJECT_DIR)).replace("\\", "/")
    except ValueError:
        return str(sci_path).replace("\\", "/")


def slim_json(data: dict, block_name: str) -> dict:
    """Return the slim version of a block JSON dict."""
    slim: dict[str, object] = {}

    # Carry forward only allowed fields
    for field in KEEP_FIELDS:
        if field in data:
            slim[field] = data[field]

    # Ensure name is always present
    if "name" not in slim:
        slim["name"] = block_name

    # Fill in empty annotation lists if missing
    for list_field in ("criticalRules", "anomalies", "commonUses", "relatedBlocks"):
        if list_field not in slim:
            slim[list_field] = []

    # Locate and attach sourceFile
    sci = find_sci_file(block_name)
    if sci:
        slim["sourceFile"] = relative_sci_path(sci)
    elif "sourceFile" not in slim:
        slim["sourceFile"] = ""   # empty string = not found, flag for manual attention

    return slim


def diff_summary(original: dict, slimmed: dict) -> list[str]:
    """Return a human-readable list of removed keys."""
    removed = sorted(set(original.keys()) - set(slimmed.keys()))
    added   = sorted(set(slimmed.keys()) - set(original.keys()))
    lines = []
    if removed:
        lines.append(f"  REMOVED : {', '.join(removed)}")
    if added:
        lines.append(f"  ADDED   : {', '.join(added)}")
    return lines


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    dry_run  = "--dry-run" in sys.argv
    single   = None
    for i, arg in enumerate(sys.argv):
        if arg == "--block" and i + 1 < len(sys.argv):
            single = sys.argv[i + 1]

    if dry_run:
        print("[slim_block_jsons] DRY-RUN mode — no files will be modified.\n")

    if not BLOCKS_DIR.exists():
        print(f"ERROR: blocks/ directory not found: {BLOCKS_DIR}")
        sys.exit(1)

    if not SCILAB_MACROS_DIR.exists():
        print(
            f"WARNING: Scilab macros directory not found:\n  {SCILAB_MACROS_DIR}\n"
            "sourceFile fields will be set to null."
        )

    # Collect JSON files to process
    if single:
        json_files = [BLOCKS_DIR / f"{single}.json"]
        json_files = [f for f in json_files if f.exists()]
        if not json_files:
            print(f"ERROR: {single}.json not found in {BLOCKS_DIR}")
            sys.exit(1)
    else:
        json_files = sorted(
            f for f in BLOCKS_DIR.glob("*.json")
            if not f.name.startswith("_")
        )

    # Create backup directory (skip in dry-run)
    if not dry_run:
        BACKUP_DIR.mkdir(exist_ok=True)

    no_source = []
    processed = 0

    for json_path in json_files:
        block_name = json_path.stem

        with open(json_path, "r", encoding="utf-8") as f:
            original = json.load(f)

        slimmed = slim_json(original, block_name)

        if not slimmed.get("sourceFile"):
            no_source.append(block_name)

        diffs = diff_summary(original, slimmed)
        if diffs or dry_run:
            print(f"[{block_name}]")
            for d in diffs:
                print(d)
            if slimmed.get("sourceFile"):
                print(f"  SOURCE  : {slimmed['sourceFile']}")
            else:
                print("  SOURCE  : *** NOT FOUND — needs manual sourceFile ***")
            print()

        if not dry_run:
            # Backup original
            shutil.copy2(json_path, BACKUP_DIR / json_path.name)
            # Write slim version
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(slimmed, f, indent=2, ensure_ascii=False)

        processed += 1

    print(f"\n{'[DRY RUN] Would process' if dry_run else 'Processed'} {processed} block(s).")

    if no_source:
        print(
            f"\nWARNING: {len(no_source)} block(s) have no matching .sci source file:\n"
            + "\n".join(f"  - {b}" for b in no_source)
            + "\nThese blocks keep sourceFile=null — review manually."
        )

    if not dry_run:
        print(f"\nBackups saved to: {BACKUP_DIR}")
        print("Done.")


if __name__ == "__main__":
    main()
