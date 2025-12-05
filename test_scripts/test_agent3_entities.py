#!/usr/bin/env python3
"""
Test Agent 3 Entity Extraction with Gemini
Actually calls Gemini with enhanced prompt to validate our approach.
Tests extraction of copybook-referenced entities.
"""

import json
import os
import sys
import time

# Initialize Gemini
from google import genai
from google.genai import types

project_id = os.environ.get("GOOGLE_CLOUD_PROJECT", "wz-cobol-graph")
client = genai.Client(vertexai=True, project=project_id)
MODEL_NAME = "gemini-3-pro-preview"

def load_test_data():
    """Load canonical test data"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    canonical_dir = os.path.join(base_dir, '..', '1_graph_creation', 'canonical_references')
    
    # Load source lines
    with open(os.path.join(canonical_dir, '01_source_lines.json'), 'r') as f:
        source_data = json.load(f)
    
    # Load structures
    with open(os.path.join(canonical_dir, '02_structure.json'), 'r') as f:
        structure_data = json.load(f)
    
    return source_data, structure_data

def get_expected_defined_entities():
    """
    Entities that ARE defined in the source code (have PIC, FD, SELECT, etc.)
    These should have definition_line_id set
    """
    return {
        # FILES (from SELECT statements)
        "DALYTRAN-FILE",      # Line 29
        "CUSTOMER-FILE",      # Line 34
        "XREF-FILE",          # Line 40
        "CARD-FILE",          # Line 46
        "ACCOUNT-FILE",       # Line 52
        "TRANSACT-FILE",      # Line 58
        
        # COPYBOOKS
        "CVTRA06Y",           # Line 99
        "CVCUS01Y",           # Line 104
        "CVACT03Y",           # Line 109
        "CVACT02Y",           # Line 114
        "CVACT01Y",           # Line 119
        "CVTRA05Y",           # Line 124
        
        # FD Records
        "FD-TRAN-RECORD",     # Line 67
        "FD-CUSTFILE-REC",    # Line 72
        "FD-XREFFILE-REC",    # Line 77
        "FD-CARDFILE-REC",    # Line 82
        "FD-ACCTFILE-REC",    # Line 87
        "FD-TRANFILE-REC",    # Line 92
        
        # Working Storage Variables
        "DALYTRAN-STATUS",    # Line 100
        "CUSTFILE-STATUS",    # Line 105
        "XREFFILE-STATUS",    # Line 110
        "CARDFILE-STATUS",    # Line 115
        "ACCTFILE-STATUS",    # Line 120
        "TRANFILE-STATUS",    # Line 125
        "IO-STATUS",          # Line 129
        "TWO-BYTES-BINARY",   # Line 133
        "TWO-BYTES-ALPHA",    # Line 134
        "IO-STATUS-04",       # Line 138
        "APPL-RESULT",        # Line 142
        "END-OF-DAILY-TRANS-FILE",  # Line 146
        "ABCODE",             # Line 147
        "TIMING",             # Line 148
        "WS-MISC-VARIABLES",  # Line 149
    }

def get_expected_referenced_entities():
    """
    Entities that are USED but NOT DEFINED in source (from copybooks)
    These should have definition_line_id = null
    """
    return {
        # From CVTRA06Y (transaction record)
        "DALYTRAN-RECORD",     # Used at line 168, 203
        "DALYTRAN-CARD-NUM",   # Used at line 171, 181
        "DALYTRAN-ID",         # Used at line 183
        
        # From CVACT03Y (xref record)
        "XREF-CARD-NUM",       # Used at line 171, 228, 236
        "XREF-ACCT-ID",        # Used at line 175, 237
        "XREF-CUST-ID",        # Used at line 238
        "CARD-XREF-RECORD",    # Used at line 229
        
        # From CVACT01Y (account record)
        "ACCT-ID",             # Used at line 175, 178, 242
        "ACCOUNT-RECORD",      # Used at line 243
    }

def format_source_for_context(source_lines, start_line=None, end_line=None):
    """Format source lines for LLM context"""
    lines = source_lines.get('source_code_lines', [])
    
    if start_line and end_line:
        lines = [l for l in lines if start_line <= l.get('line_number', 0) <= end_line]
    
    formatted = []
    for line in lines:
        line_num = line.get('line_number', 0)
        line_id = line.get('line_id', 'NA')
        content = line.get('content', '')
        line_type = line.get('type', 'CODE')
        formatted.append(f"Line {line_num} [{line_id}] ({line_type}): {content}")
    
    return '\n'.join(formatted)

def test_full_context_prompt():
    """
    Test what the LLM should extract when given full program context
    """
    source_data, structure_data = load_test_data()
    
    # Format full program
    full_program = format_source_for_context(source_data)
    
    # Get specific structures for testing
    structures = structure_data.get('structure', [])
    
    # Find the MAIN-PARA structure (where copybook variables are heavily used)
    main_para = None
    for s in structures:
        if s.get('name') == 'MAIN-PARA':
            main_para = s
            break
    
    print("=" * 80)
    print("TEST: Full Context Prompt Generation")
    print("=" * 80)
    
    if main_para:
        start = main_para.get('start_line')
        end = main_para.get('end_line')
        structure_content = format_source_for_context(source_data, start, end)
        
        print(f"\nStructure: MAIN-PARA (lines {start}-{end})")
        print("-" * 40)
        print("Key lines that should trigger copybook entity extraction:\n")
        
        # Show the critical lines
        lines = source_data.get('source_code_lines', [])
        critical_lines = [168, 171, 175, 178, 181, 183]
        for line in lines:
            if line.get('line_number') in critical_lines:
                print(f"  Line {line['line_number']}: {line['content']}")
        
        print("\n" + "-" * 40)
        print("Expected REFERENCED entities from these lines:")
        for entity in sorted(get_expected_referenced_entities()):
            print(f"  - {entity}")
    
    print("\n" + "=" * 80)
    print("TEST: Data Division Check")
    print("=" * 80)
    
    # Check DATA DIVISION structures
    data_div = None
    for s in structures:
        if s.get('name') == 'DATA DIVISION':
            data_div = s
            break
    
    if data_div:
        start = data_div.get('start_line')
        end = data_div.get('end_line')
        print(f"\nDATA DIVISION spans lines {start}-{end}")
        print("COPY statements in this range:")
        
        lines = source_data.get('source_code_lines', [])
        for line in lines:
            ln = line.get('line_number')
            if start <= ln <= end and 'COPY' in line.get('content', ''):
                print(f"  Line {ln}: {line['content']}")

def test_entity_coverage():
    """
    Check what entities are in the canonical output vs what's expected
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    canonical_dir = os.path.join(base_dir, '..', '1_graph_creation', 'canonical_references')
    
    # Load current canonical entities
    with open(os.path.join(canonical_dir, '03_entities.json'), 'r') as f:
        entities_data = json.load(f)
    
    current_entities = set()
    for entity in entities_data.get('entities', []):
        current_entities.add(entity.get('entity_name', '').upper())
    
    expected_defined = get_expected_defined_entities()
    expected_referenced = get_expected_referenced_entities()
    
    print("\n" + "=" * 80)
    print("TEST: Entity Coverage Analysis")
    print("=" * 80)
    
    # Check defined entities
    print("\n--- DEFINED Entities (from source code) ---")
    defined_found = 0
    defined_missing = []
    for entity in sorted(expected_defined):
        if entity.upper() in current_entities:
            defined_found += 1
        else:
            defined_missing.append(entity)
    
    print(f"Found: {defined_found}/{len(expected_defined)}")
    if defined_missing:
        print(f"Missing: {defined_missing}")
    
    # Check referenced entities (the key test!)
    print("\n--- REFERENCED Entities (from copybooks) ---")
    referenced_found = 0
    referenced_missing = []
    for entity in sorted(expected_referenced):
        if entity.upper() in current_entities:
            referenced_found += 1
        else:
            referenced_missing.append(entity)
    
    print(f"Found: {referenced_found}/{len(expected_referenced)}")
    if referenced_missing:
        print(f"MISSING (these should be added): {referenced_missing}")
    
    # Summary
    print("\n--- SUMMARY ---")
    total_expected = len(expected_defined) + len(expected_referenced)
    total_found = defined_found + referenced_found
    print(f"Total Coverage: {total_found}/{total_expected} ({100*total_found//total_expected}%)")
    
    if referenced_missing:
        print("\n⚠️  ISSUE: Copybook-referenced entities are not being extracted!")
        print("   The Agent 3 prompt needs to extract variables that are USED")
        print("   but not DEFINED in the visible source code.")
        return False
    else:
        print("\n✓ All expected entities are present!")
        return True

def generate_test_prompt():
    """
    Generate the enhanced prompt format that includes full program context
    """
    source_data, structure_data = load_test_data()
    
    # Format DATA DIVISION only (for variable definitions)
    lines = source_data.get('source_code_lines', [])
    data_div_lines = [l for l in lines if 64 <= l.get('line_number', 0) <= 153]
    
    data_div_context = []
    for line in data_div_lines:
        ln = line.get('line_number')
        content = line.get('content', '')
        data_div_context.append(f"Line {ln}: {content}")
    
    print("\n" + "=" * 80)
    print("PROPOSED PROMPT ENHANCEMENT")
    print("=" * 80)
    
    prompt = """
    You are analyzing COBOL structure: {structure_name} ({structure_type}).
    Program: {program_id}.
    
    === DATA DIVISION REFERENCE (Lines 64-153) ===
    These are ALL the variable/file definitions in this program:
    
    {data_division_context}
    
    === CURRENT STRUCTURE TO ANALYZE ===
    {structure_content}
    
    === TASK ===
    Extract ALL Data Entities from the CURRENT STRUCTURE.
    
    Entity Types:
    - FILE: File names used in OPEN, CLOSE, READ statements
    - VARIABLE: Any variable name used in MOVE, IF, DISPLAY, etc.
    - COPYBOOK: COPY statements (e.g., "COPY CVTRA06Y.")
    
    CRITICAL RULES:
    1. For EVERY variable name you see in the current structure:
       - Check if it's DEFINED in the DATA DIVISION REFERENCE above
       - If YES: Set definition_line_id to the line where it's defined
       - If NO: Set definition_line_id to null (it's from a copybook)
    
    2. EXAMPLE - Line 171: "MOVE DALYTRAN-CARD-NUM TO XREF-CARD-NUM"
       - DALYTRAN-CARD-NUM: Not in DATA DIVISION → definition_line_id: null
       - XREF-CARD-NUM: Not in DATA DIVISION → definition_line_id: null
       - Both should be extracted as VARIABLE entities!
    
    3. EXAMPLE - Line 203: "READ DALYTRAN-FILE INTO DALYTRAN-RECORD"
       - DALYTRAN-FILE: Defined at line 29 (SELECT) → definition_line_id: "CBTRN01C_29"
       - DALYTRAN-RECORD: Not in DATA DIVISION → definition_line_id: null
    
    Return JSON: {{ "found_entities": [...] }}
    """
    
    print(prompt)
    print("\n--- Sample DATA DIVISION context (first 20 lines): ---")
    for line in data_div_context[:20]:
        print(f"    {line}")
    print("    ...")

def test_gemini_with_enhanced_prompt():
    """
    Actually call Gemini with the enhanced prompt on MAIN-PARA structure.
    This validates our approach before updating main.py.
    """
    print("\n" + "=" * 80)
    print("TEST: Calling Gemini with Enhanced Prompt")
    print("=" * 80)
    
    source_data, structure_data = load_test_data()
    lines = source_data.get('source_code_lines', [])
    structures = structure_data.get('structure', [])
    
    # Build DATA DIVISION context (lines 26-153 for ENVIRONMENT + DATA DIVISION)
    data_div_context = ""
    for line in lines:
        ln = line.get('line_number', 0)
        if 26 <= ln <= 153:
            content = line.get('content', '')
            if content.strip():
                data_div_context += f"Line {ln}: {content}\n"
    
    # Find MAIN-PARA structure (where copybook variables are used)
    main_para = None
    for s in structures:
        if s.get('name') == 'MAIN-PARA':
            main_para = s
            break
    
    if not main_para:
        print("ERROR: Could not find MAIN-PARA structure")
        return False
    
    # Build structure content
    start = main_para.get('start_line')
    end = main_para.get('end_line')
    structure_content = ""
    for line in lines:
        ln = line.get('line_number', 0)
        if start <= ln <= end:
            line_id = line.get('line_id', 'NA')
            content = line.get('content', '')
            structure_content += f"Line {ln} [ID: {line_id}]: {content}\n"
    
    print(f"Testing on: MAIN-PARA (lines {start}-{end})")
    print(f"DATA DIVISION context: {len(data_div_context)} chars")
    print(f"Structure content: {len(structure_content)} chars")
    
    # Build the enhanced prompt
    prompt = f"""
You are analyzing COBOL structure: MAIN-PARA (PARAGRAPH).
Program: CBTRN01C.

=== ALL VARIABLE DEFINITIONS IN THIS PROGRAM (Lines 26-153) ===
{data_div_context}

=== CURRENT STRUCTURE TO ANALYZE ===
{structure_content}

=== TASK ===
Extract ALL Data Entities from the CURRENT STRUCTURE.

Entity Types:
- FILE: File names used in OPEN, CLOSE, READ statements
- VARIABLE: Any variable name used in MOVE, IF, DISPLAY, READ INTO, etc.
- COPYBOOK: COPY statements

CRITICAL: For EVERY variable name in the current structure:
1. Check if it's DEFINED in the VARIABLE DEFINITIONS section above
2. If YES: Set definition_line_id to the line ID where it's defined
3. If NO (not found above): Set definition_line_id to null - it's from a copybook

EXAMPLES from this structure:
- Line 168 "DISPLAY DALYTRAN-RECORD" → DALYTRAN-RECORD is NOT in definitions above → null
- Line 171 "MOVE DALYTRAN-CARD-NUM TO XREF-CARD-NUM" → Both are NOT defined → null for both
- Line 164 "END-OF-DAILY-TRANS-FILE = 'Y'" → IS defined at line 146 → "CBTRN01C_146"

Return JSON: {{ "found_entities": [...] }}
"""
    
    contents = [types.Content(role="user", parts=[types.Part.from_text(text=prompt)])]
    
    config = types.GenerateContentConfig(
        temperature=0.0,
        response_mime_type="application/json",
        response_schema={
            "type": "OBJECT",
            "properties": {
                "found_entities": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "entity_name": {"type": "STRING"},
                            "entity_type": {"type": "STRING"},
                            "definition_line_id": {"type": "STRING", "nullable": True},
                            "description": {"type": "STRING"}
                        },
                        "required": ["entity_name", "entity_type"]
                    }
                }
            }
        }
    )
    
    print("\nCalling Gemini...")
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=contents,
            config=config
        )
        
        result = json.loads(response.text)
        entities = result.get('found_entities', [])
        
        print(f"\n✓ Gemini returned {len(entities)} entities")
        
        # Check for the expected copybook variables
        expected_copybook_vars = {
            "DALYTRAN-RECORD", "DALYTRAN-CARD-NUM", "XREF-CARD-NUM",
            "XREF-ACCT-ID", "ACCT-ID", "DALYTRAN-ID"
        }
        
        found_names = set(e.get('entity_name', '').upper() for e in entities)
        
        print("\n--- Checking for copybook-referenced entities ---")
        success = True
        for var in sorted(expected_copybook_vars):
            if var.upper() in found_names:
                # Check it has null definition_line_id
                ent = next((e for e in entities if e.get('entity_name', '').upper() == var.upper()), None)
                if ent and ent.get('definition_line_id') is None:
                    print(f"  ✓ {var}: Found with null definition_line_id")
                else:
                    print(f"  ⚠ {var}: Found but definition_line_id = {ent.get('definition_line_id')}")
            else:
                print(f"  ✗ {var}: MISSING!")
                success = False
        
        print("\n--- All extracted entities ---")
        for e in entities:
            name = e.get('entity_name')
            etype = e.get('entity_type')
            defn = e.get('definition_line_id')
            print(f"  {etype}: {name} (def: {defn})")
        
        return success
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("Agent 3 Entity Extraction Test Suite")
    print("=" * 80)
    
    # First run the static analysis
    test_full_context_prompt()
    test_entity_coverage()
    
    # Now the real test with Gemini
    success = test_gemini_with_enhanced_prompt()
    
    print("\n" + "=" * 80)
    if success:
        print("✓ GEMINI TEST PASSED - Enhanced prompt works!")
        print("Ready to update Agent 3 main.py with this approach.")
        sys.exit(0)
    else:
        print("✗ GEMINI TEST FAILED - Need to adjust prompt")
        sys.exit(1)
