"""
Pydantic schemas for the 20 RFP extraction fields, addendum reconciliation, and validation.
"""

from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field


class Citation(BaseModel):
    file: str = Field(..., description="Source document file name")
    page: int = Field(..., description="1-indexed source page number")
    chunk_id: Optional[str] = Field(None, description="Identifier of the cited chunk")
    quote: Optional[str] = Field(None, description="Exact supporting text excerpt")


class ExtractedField(BaseModel):
    value: Optional[str] = Field(None, description="Extracted canonical value or null if not found")
    sources: List[Citation] = Field(default_factory=list, description="List of source citations backing this value")
    confidence: float = Field(..., description="Confidence score from 0.0 to 1.0")
    notes: str = Field(..., description="Explanation of value, addendum impact, or reason for null")


class AddendumChange(BaseModel):
    field_name: str = Field(..., description="Name of the affected field")
    change_type: Literal["replaced", "clarified", "added", "conflicting"] = Field(
        ..., description="Nature of the change introduced by the addendum"
    )
    original_value: Optional[str] = Field(None, description="Original value from base RFP or portal")
    new_value: Optional[str] = Field(None, description="Updated value established by the addendum")
    original_source: Optional[Citation] = Field(None, description="Citation for original clause")
    new_source: Optional[Citation] = Field(None, description="Citation for addendum clause")
    notes: str = Field(..., description="Detailed explanation of the amendment modification")


class ValidationSummary(BaseModel):
    passed: int = Field(0, description="Count of successfully validated fields")
    failed: int = Field(0, description="Count of fields that failed verification")
    not_found: int = Field(0, description="Count of non-applicable / not found null fields")
    details: List[str] = Field(default_factory=list, description="Audit log of validation rules applied")


class BidExtractionOutput(BaseModel):
    bid_id: str = Field(..., description="Bid package identifier (e.g. Bid1, Bid2)")
    fields: Dict[str, ExtractedField] = Field(..., description="Dictionary of all 20 required extracted fields")
    addendum_changes: List[AddendumChange] = Field(default_factory=list, description="Chronological log of addendum amendments")
    validation: ValidationSummary = Field(..., description="Automated validation summary statistics")


# The exact 20 field names defined in Section 8 of the assignment
REQUIRED_FIELDS = [
    "Bid Number",
    "Title",
    "Due Date",
    "Bid Submission Type",
    "Term of Bid",
    "Pre Bid Meeting",
    "Installation",
    "Bid Bond Requirement",
    "Delivery Date",
    "Payment Terms",
    "Any Additional Documentation Required",
    "MFG for Registration",
    "Contract or Cooperative to use",
    "Model_no",
    "Part_no",
    "Product",
    "contact_info",
    "company_name",
    "Bid Summary",
    "Product Specification"
]
