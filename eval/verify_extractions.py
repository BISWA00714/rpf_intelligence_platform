"""
Verification script for generated Bid1 and Bid2 JSON extraction artifacts.
"""

import json
from pathlib import Path

for bid in ["Bid1", "Bid2"]:
    p = Path("data") / f"{bid}_extracted.json"
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"\n================ {bid} EXTRACTION SUMMARY ================")
    print(f"Bid ID: {data['bid_id']}")
    print(f"Total Fields Extracted: {len(data['fields'])}")
    print(f"Due Date: {data['fields']['Due Date']['value']}")
    print(f"Due Date Sources: {[s['file'] + ' P' + str(s['page']) for s in data['fields']['Due Date']['sources']]}")
    print(f"Bid Bond: {data['fields']['Bid Bond Requirement']['value']}")
    print(f"Pre Bid Meeting: {data['fields']['Pre Bid Meeting']['value']}")
    print(f"Contract Vehicle: {data['fields']['Contract or Cooperative to use']['value']}")
    print(f"Addendum Changes: {len(data['addendum_changes'])}")
    for chg in data["addendum_changes"]:
        print(f"   -> [{chg['change_type'].upper()}] {chg['field_name']}: {chg['notes']}")
    print(f"Validation: {data['validation']}")
