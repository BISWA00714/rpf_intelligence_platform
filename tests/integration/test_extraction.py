"""
Integration tests for Phase 6: End-to-End Bid Extraction and Reconciliation.
Verifies schemas, non-null field completeness, citation grounding,
and addendum reconciliation on generated JSON artifacts.
"""

import json
import pytest
from pathlib import Path
from config.settings import settings
from schemas.extraction import REQUIRED_FIELDS, BidExtractionOutput, ExtractedField


def load_extracted_json(bid_id: str) -> BidExtractionOutput:
    json_path = settings.DATA_DIR / f"{bid_id}_extracted.json"
    assert json_path.exists(), f"Extraction artifact {json_path} does not exist."
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return BidExtractionOutput.model_validate(data)


def test_bid1_extraction_schema_and_completeness():
    """Verify Bid1 (Dallas ISD) extraction schema and completeness."""
    record = load_extracted_json("Bid1")
    assert record.bid_id == "Bid1"
    assert len(record.fields) == 20
    
    # Check all 20 required fields exist
    for field_name in REQUIRED_FIELDS:
        assert field_name in record.fields, f"Missing field {field_name} in Bid1"
        field_obj = record.fields[field_name]
        assert isinstance(field_obj, ExtractedField)
        assert field_obj.confidence >= 0.0
        assert field_obj.notes != ""

    # Check Addendum 2 reconciliation on Due Date
    due_date = record.fields["Due Date"]
    assert "2024-07-09" in due_date.value
    assert len(record.addendum_changes) >= 1
    assert any(ch.field_name == "Due Date" for ch in record.addendum_changes)
    
    # Check citations exist for non-null fields
    for fname, fobj in record.fields.items():
        if fobj.value is not None and fobj.value.lower() not in ["none", "not found"]:
            assert len(fobj.sources) > 0, f"Field {fname} has value but no citations."
            for s in fobj.sources:
                assert s.file != ""
                assert s.page > 0


def test_bid2_extraction_schema_and_completeness():
    """Verify Bid2 (State of Maryland) extraction schema and completeness."""
    record = load_extracted_json("Bid2")
    assert record.bid_id == "Bid2"
    assert len(record.fields) == 20

    for field_name in REQUIRED_FIELDS:
        assert field_name in record.fields, f"Missing field {field_name} in Bid2"
        field_obj = record.fields[field_name]
        assert isinstance(field_obj, ExtractedField)

    # Check key hardware specifications
    assert "210-BLYZ" in record.fields["Part_no"].value
    assert "5550" in record.fields["Model_no"].value
    assert "Ultra 5" in record.fields["Product Specification"].value

    # Check Pre-Bid Meeting is correctly verified as None
    pre_bid = record.fields["Pre Bid Meeting"]
    assert pre_bid.value is None or "None" in str(pre_bid.value)

    # Validation summary
    assert record.validation.passed >= 18
    assert record.validation.failed == 0
