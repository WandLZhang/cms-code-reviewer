import json
import os

def main():
    # Load the original data
    input_path = "1_graph_creation/cbtrn01c_data.json"
    with open(input_path, 'r') as f:
        data = json.load(f)

    output_dir = "1_graph_creation/canonical"
    os.makedirs(output_dir, exist_ok=True)

    # --- 1. Source Lines ---
    source_lines_data = {
        "program": data.get("program", {}),
        "source_code_lines": data.get("source_code_lines", [])
    }
    with open(f"{output_dir}/01_source_lines.json", 'w') as f:
        json.dump(source_lines_data, f, indent=2)
    print("Created 01_source_lines.json")

    # --- 2. Structure ---
    structure_data = {
        "structure": data.get("sections", [])
    }
    with open(f"{output_dir}/02_structure.json", 'w') as f:
        json.dump(structure_data, f, indent=2)
    print("Created 02_structure.json")

    # --- 3. Entities ---
    # Extracting distinct entities from the 'rules' links and known variables
    entities_map = {}
    
    # Helper to add entity
    def add_entity(name, type_):
        if name not in entities_map:
            entities_map[name] = {
                "entity_name": name,
                "entity_type": type_,
                "program_id": "CBTRN01C"
            }

    # Add known Files (from File Section context in source)
    files = ["DALYTRAN-FILE", "CUSTOMER-FILE", "XREF-FILE", "CARD-FILE", "ACCOUNT-FILE", "TRANSACT-FILE"]
    for f_name in files: add_entity(f_name, "FILE")

    # Add known Variables (from Working Storage context)
    vars_ = [
        "DALYTRAN-STATUS", "CUSTFILE-STATUS", "XREFFILE-STATUS", "CARDFILE-STATUS", "ACCTFILE-STATUS", "TRANFILE-STATUS",
        "IO-STATUS", "IO-STATUS-04", "APPL-RESULT", "APPL-AOK", "APPL-EOF", "END-OF-DAILY-TRANS-FILE", "ABCODE", "TIMING",
        "WS-XREF-READ-STATUS", "WS-ACCT-READ-STATUS",
        "FD-TRAN-RECORD", "FD-CUSTFILE-REC", "FD-XREFFILE-REC", "FD-CARDFILE-REC", "FD-ACCTFILE-REC", "FD-TRANFILE-REC",
        "FD-TRAN-ID", "FD-CUST-DATA", "FD-CUST-ID", "FD-XREF-CARD-NUM", "FD-XREF-DATA", "FD-CARD-NUM", "FD-CARD-DATA",
        "FD-ACCT-ID", "FD-ACCT-DATA", "FD-TRANS-ID"
    ]
    for v_name in vars_: add_entity(v_name, "VARIABLE")

    # Scan existing line_references for other entities
    for ref in data.get("line_references", []):
        # Basic heuristic: if it's not a file, it's likely a variable
        name = ref["target_entity_name"]
        if name not in entities_map:
            add_entity(name, "VARIABLE") # Default to variable

    entities_data = {
        "entities": list(entities_map.values())
    }
    with open(f"{output_dir}/03_entities.json", 'w') as f:
        json.dump(entities_data, f, indent=2)
    print("Created 03_entities.json")

    # --- 4. References & Flow ---
    existing_refs = data.get("line_references", [])
    
    # Generate Missing References
    new_refs = []
    
    def add_ref(line, entity, type_):
        new_refs.append({
            "reference_id": f"ref_CBTRN01C_{line}_{entity}",
            "source_line_id": f"CBTRN01C_{line}",
            "target_entity_name": entity,
            "usage_type": type_
        })

    # 0000-DALYTRAN-OPEN (252-268)
    add_ref(253, "APPL-RESULT", "UPDATES")
    add_ref(254, "DALYTRAN-FILE", "READS") 
    add_ref(255, "DALYTRAN-STATUS", "VALIDATES")
    add_ref(256, "APPL-RESULT", "UPDATES")
    add_ref(258, "APPL-RESULT", "UPDATES")
    add_ref(260, "APPL-AOK", "VALIDATES")
    add_ref(264, "DALYTRAN-STATUS", "READS")
    add_ref(264, "IO-STATUS", "UPDATES")

    # 0100-CUSTFILE-OPEN (271-287)
    add_ref(272, "APPL-RESULT", "UPDATES")
    add_ref(273, "CUSTOMER-FILE", "READS")
    add_ref(274, "CUSTFILE-STATUS", "VALIDATES")
    add_ref(275, "APPL-RESULT", "UPDATES")
    add_ref(277, "APPL-RESULT", "UPDATES")
    add_ref(279, "APPL-AOK", "VALIDATES")
    add_ref(283, "CUSTFILE-STATUS", "READS")
    add_ref(283, "IO-STATUS", "UPDATES")

    # 0200-XREFFILE-OPEN (289-305)
    add_ref(290, "APPL-RESULT", "UPDATES")
    add_ref(291, "XREF-FILE", "READS")
    add_ref(292, "XREFFILE-STATUS", "VALIDATES")
    add_ref(293, "APPL-RESULT", "UPDATES")
    add_ref(295, "APPL-RESULT", "UPDATES")
    add_ref(297, "APPL-AOK", "VALIDATES")
    add_ref(301, "XREFFILE-STATUS", "READS")
    add_ref(301, "IO-STATUS", "UPDATES")

    # 0300-CARDFILE-OPEN (307-323)
    add_ref(308, "APPL-RESULT", "UPDATES")
    add_ref(309, "CARD-FILE", "READS")
    add_ref(310, "CARDFILE-STATUS", "VALIDATES")
    add_ref(311, "APPL-RESULT", "UPDATES")
    add_ref(313, "APPL-RESULT", "UPDATES")
    add_ref(315, "APPL-AOK", "VALIDATES")
    add_ref(319, "CARDFILE-STATUS", "READS")
    add_ref(319, "IO-STATUS", "UPDATES")

    # 0400-ACCTFILE-OPEN (325-341)
    add_ref(326, "APPL-RESULT", "UPDATES")
    add_ref(327, "ACCOUNT-FILE", "READS")
    add_ref(328, "ACCTFILE-STATUS", "VALIDATES")
    add_ref(329, "APPL-RESULT", "UPDATES")
    add_ref(331, "APPL-RESULT", "UPDATES")
    add_ref(333, "APPL-AOK", "VALIDATES")
    add_ref(337, "ACCTFILE-STATUS", "READS")
    add_ref(337, "IO-STATUS", "UPDATES")

    # 0500-TRANFILE-OPEN (343-359)
    add_ref(344, "APPL-RESULT", "UPDATES")
    add_ref(345, "TRANSACT-FILE", "READS")
    add_ref(346, "TRANFILE-STATUS", "VALIDATES")
    add_ref(347, "APPL-RESULT", "UPDATES")
    add_ref(349, "APPL-RESULT", "UPDATES")
    add_ref(351, "APPL-AOK", "VALIDATES")
    add_ref(355, "TRANFILE-STATUS", "READS")
    add_ref(355, "IO-STATUS", "UPDATES")

    # 9000-DALYTRAN-CLOSE (361-377)
    add_ref(362, "APPL-RESULT", "UPDATES")
    add_ref(363, "DALYTRAN-FILE", "READS")
    add_ref(364, "DALYTRAN-STATUS", "VALIDATES")
    add_ref(365, "APPL-RESULT", "UPDATES")
    add_ref(367, "APPL-RESULT", "UPDATES")
    add_ref(369, "APPL-AOK", "VALIDATES")
    add_ref(373, "CUSTFILE-STATUS", "READS") # Bug in code? Uses CUSTFILE status for DALYTRAN close error?
    add_ref(373, "IO-STATUS", "UPDATES")

    # 9100-CUSTFILE-CLOSE (379-395)
    add_ref(380, "APPL-RESULT", "UPDATES")
    add_ref(381, "CUSTOMER-FILE", "READS")
    add_ref(382, "CUSTFILE-STATUS", "VALIDATES")
    add_ref(383, "APPL-RESULT", "UPDATES")
    add_ref(385, "APPL-RESULT", "UPDATES")
    add_ref(387, "APPL-AOK", "VALIDATES")
    add_ref(391, "CUSTFILE-STATUS", "READS")
    add_ref(391, "IO-STATUS", "UPDATES")

    # 9200-XREFFILE-CLOSE (397-413)
    add_ref(398, "APPL-RESULT", "UPDATES")
    add_ref(399, "XREF-FILE", "READS")
    add_ref(400, "XREFFILE-STATUS", "VALIDATES")
    add_ref(401, "APPL-RESULT", "UPDATES")
    add_ref(403, "APPL-RESULT", "UPDATES")
    add_ref(405, "APPL-AOK", "VALIDATES")
    add_ref(409, "XREFFILE-STATUS", "READS")
    add_ref(409, "IO-STATUS", "UPDATES")

    # 9300-CARDFILE-CLOSE (415-431)
    add_ref(416, "APPL-RESULT", "UPDATES")
    add_ref(417, "CARD-FILE", "READS")
    add_ref(418, "CARDFILE-STATUS", "VALIDATES")
    add_ref(419, "APPL-RESULT", "UPDATES")
    add_ref(421, "APPL-RESULT", "UPDATES")
    add_ref(423, "APPL-AOK", "VALIDATES")
    add_ref(427, "CARDFILE-STATUS", "READS")
    add_ref(427, "IO-STATUS", "UPDATES")

    # 9400-ACCTFILE-CLOSE (433-449)
    add_ref(434, "APPL-RESULT", "UPDATES")
    add_ref(435, "ACCOUNT-FILE", "READS")
    add_ref(436, "ACCTFILE-STATUS", "VALIDATES")
    add_ref(437, "APPL-RESULT", "UPDATES")
    add_ref(439, "APPL-RESULT", "UPDATES")
    add_ref(441, "APPL-AOK", "VALIDATES")
    add_ref(445, "ACCTFILE-STATUS", "READS")
    add_ref(445, "IO-STATUS", "UPDATES")

    # 9500-TRANFILE-CLOSE (451-467)
    add_ref(452, "APPL-RESULT", "UPDATES")
    add_ref(453, "TRANSACT-FILE", "READS")
    add_ref(454, "TRANFILE-STATUS", "VALIDATES")
    add_ref(455, "APPL-RESULT", "UPDATES")
    add_ref(457, "APPL-RESULT", "UPDATES")
    add_ref(459, "APPL-AOK", "VALIDATES")
    add_ref(463, "TRANFILE-STATUS", "READS")
    add_ref(463, "IO-STATUS", "UPDATES")

    # Z-ABEND-PROGRAM (469-475)
    add_ref(471, "TIMING", "UPDATES")
    add_ref(472, "ABCODE", "UPDATES")
    add_ref(473, "ABCODE", "READS")
    add_ref(473, "TIMING", "READS")

    # Z-DISPLAY-IO-STATUS (476-489)
    add_ref(477, "IO-STATUS", "VALIDATES")
    add_ref(478, "IO-STAT1", "VALIDATES")
    add_ref(479, "IO-STAT1", "READS")
    add_ref(479, "IO-STATUS-04", "UPDATES")
    add_ref(480, "TWO-BYTES-BINARY", "UPDATES")
    add_ref(481, "IO-STAT2", "READS")
    add_ref(481, "TWO-BYTES-RIGHT", "UPDATES")
    add_ref(482, "TWO-BYTES-BINARY", "READS")
    add_ref(482, "IO-STATUS-0403", "UPDATES")
    add_ref(483, "IO-STATUS-04", "READS")
    add_ref(485, "IO-STATUS-04", "UPDATES")
    add_ref(486, "IO-STATUS", "READS")
    add_ref(486, "IO-STATUS-04", "UPDATES")
    add_ref(487, "IO-STATUS-04", "READS")

    all_refs = existing_refs + new_refs

    flow_data = {
        "control_flow": data.get("control_flow", []),
        "line_references": all_refs
    }
    with open(f"{output_dir}/04_references_and_flow.json", 'w') as f:
        json.dump(flow_data, f, indent=2)
    print("Created 04_references_and_flow.json")

if __name__ == "__main__":
    main()
