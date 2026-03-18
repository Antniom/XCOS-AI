# XCOS Block Catalogue Analysis Task

## Your Mission
Add more XCOS block files to the `blocks/` directory. Each block is now its own JSON file for easy AI agent context management.

## Current Status
- Individual block files in `blocks/` (73 blocks catalogued so far)
- Index file `blocks/_index.json` tracks all existing blocks
- Reference XCOS files in `Reference blocks/` (150+ remaining)

## Files to Process
1. List all .xcos files in `Reference blocks\`
2. Compare with `blocks/_index.json` to find unprocessed blocks
3. Pick the next 70 UNPROCESSED files
4. Create individual JSON files for each
5. **DELETE the processed .xcos files from `Reference blocks\` to track progress**

## Individual Block File Structure
Create files like `blocks/MYBLOCK.json`:
```json
{
  "name": "MYBLOCK",
  "description": "Human-readable description",
  "category": "Category",
  "blockType": "c|d|h|x",
  "tag": "BasicBlock|RoundBlock|Product|...",
  "interfaceFunctionName": "MYBLOCK",
  "simulationFunctionName": "func",
  "simulationFunctionType": "C_OR_FORTRAN|SCILAB|TYPE_2|...",
  "dependsOnU": 0|1,
  "dependsOnT": 0|1,
  "geometry": { "width": 40, "height": 40 },
  "parameters": { "exprs": {...}, "realParameters": {...}, ... },
  "ports": { "explicitInputs": [...], "explicitOutputs": [...], ... },
  "xmlExample": "<BasicBlock ...>...</BasicBlock>",
  "anomalies": [...],
  "criticalRules": [...],
  "commonUses": [...],
  "relatedBlocks": [...]
}
```

## Step 1: Parse Each XCOS File
Extract:
- Core attributes (tag, blockType, simulationFunctionType, etc.)
- Geometry (width/height - note non-standard sizes)
- Parameters (exprs, realParameters, integerParameters, state, dState, nbZerosCrossing, nmode)
- Ports (explicitInputs/Outputs, controls, commands with exact styles)

## Step 2: Create Block File
For each block:
- Filename: `blocks/BLOCK_NAME.json`
- Include complete structure, XML example, anomalies, critical rules
- Document any special patterns discovered

## Step 3: Update Index
Add entry to `blocks/_index.json`:
```json
{ "name": "MYBLOCK", "file": "MYBLOCK.json", "category": "...", "description": "...", "complexity": "simple|medium|high" }
```

## Common Anomalies to Document
| Pattern | Example | Note |
|---------|---------|------|
| Special tag | "Product", "BigSom" | Not BasicBlock |
| blockType="h" | CLOCK_c, ANDBLK | SuperBlock with internal diagram |
| blockType="x" | DERIV | Special differentiation |
| ControlPort | CSCOPE, AFFICH_m | Event refresh, not clock |
| CommandPort | CLOCK_c, AUTOMAT | Event output |
| dataLines=-1 | ABS_VALUE | Variable-size |
| initialState=-1.0 | Command ports | Event port default |
| nbZerosCrossing=2 | BACKLASH | Gap detection |
| Width=60,80,100 | BIGSOM_f, BITCLEAR | Non-standard |
| Height=60 | BIGSOM_f, PRODUCT | Tall blocks |
| Empty exprs | SINBLK_f | height=0,width=0 |
| INT32_MATRIX | BITCLEAR, BITSET | Integer data |
| dataLines=-2 | MUX | Auto-dimension second input |

## Port Style Reference
```
ExplicitInput:  "ExplicitInputPort;align=left;verticalAlign=middle;spacing=10.0"
ExplicitOutput: "ExplicitOutputPort;align=right;verticalAlign=middle;spacing=10.0"
ControlPort:    "ControlPort;align=center;verticalAlign=top;spacing=10.0"
CommandPort:    "CommandPort;align=center;verticalAlign=bottom;spacing=10.0"
```

## Critical Reminders
- NEVER use spacingLeft - use spacing=10.0
- Preserve exact port styles from reference
- Copy parameter structures exactly (ScilabString height, data lines)
- Note any block with unique requirements
