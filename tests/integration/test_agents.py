"""
Integration tests for the LangGraph Multi-Agent Orchestrator and specialist agents.
Tests end-to-end multi-agent workflow: Planner -> Retrieval -> Specialists ->
Addendum Reconciler -> Validator Critic -> Finalizer.
"""

import pytest
from agents.orchestrator import MultiAgentOrchestrator
from agents.addendum_agent import AddendumReconciliationAgent
from agents.validator_agent import ValidatorAgent
from schemas.extraction import REQUIRED_FIELDS, BidExtractionOutput, ExtractedField, Citation
from schemas.search import EvidenceItem


@pytest.fixture(scope="module")
def orchestrator():
    return MultiAgentOrchestrator()


def test_orchestrator_extract_bid1(orchestrator):
    """Verify full multi-agent extraction workflow on Bid1 (Dallas ISD)."""
    output = orchestrator.extract_bid("Bid1")
    assert isinstance(output, BidExtractionOutput)
    assert output.bid_id == "Bid1"
    
    # Check all 20 fields present
    for f in REQUIRED_FIELDS:
        assert f in output.fields
        field_obj = output.fields[f]
        assert isinstance(field_obj, ExtractedField)
        assert field_obj.confidence >= 0.0
        assert field_obj.notes != ""
        
    # Check Addendum 2 reconciled Due Date
    due_date = output.fields["Due Date"]
    assert "2024-07-09" in due_date.value
    assert len(output.addendum_changes) >= 1
    assert any(ch.field_name == "Due Date" for ch in output.addendum_changes)
    
    # Check validation results
    assert output.validation.passed >= 18
    assert output.validation.failed == 0


def test_orchestrator_extract_bid2(orchestrator):
    """Verify full multi-agent extraction workflow on Bid2 (State of Maryland)."""
    output = orchestrator.extract_bid("Bid2")
    assert isinstance(output, BidExtractionOutput)
    assert output.bid_id == "Bid2"
    
    # Check required fields
    assert "Bid Number" in output.fields
    assert "E20P4600040" in output.fields["Bid Number"].value or "BPM044557" in output.fields["Bid Number"].value
    assert output.fields["Term of Bid"].value is not None
    assert "Dell" in output.fields["company_name"].value or "Maryland" in output.fields["company_name"].value or "Treasurer" in output.fields["company_name"].value
    
    # Bid2 has no pre-bid meeting (null / not found)
    pre_bid = output.fields["Pre Bid Meeting"]
    assert pre_bid.value is None or "None" in str(pre_bid.value)
    
    # Validation
    assert output.validation.passed >= 18
    assert output.validation.failed == 0


def test_orchestrator_answer_question(orchestrator):
    """Verify cited procurement Q&A agent execution."""
    result = orchestrator.answer_question(
        question="What is the final submission deadline for Bid1 after all addendums?",
        bid_id="Bid1"
    )
    assert "query" in result
    assert "July 9, 2024" in result["answer"] or "2024-07-09" in result["answer"]
    assert len(result["citations"]) > 0
    assert result["run_id"] is not None


def test_addendum_reconciliation_logic():
    """Verify addendum priority override logic in isolation."""
    reconciler = AddendumReconciliationAgent()
    base_fields = {
        "Due Date": ExtractedField(
            value="2024-06-27 14:00 CST",
            sources=[Citation(file="base_rfp.pdf", page=2)],
            confidence=0.9,
            notes="Base RFP date"
        )
    }
    evidence = [
        EvidenceItem(
            chunk_id="chunk-add2-001",
            bid_id="Bid1",
            file_name="Addendum 2.pdf",
            page_number=1,
            doc_type="addendum",
            addendum_number=2,
            text="The proposal due date has been extended to July 9, 2024 at 2:00 PM CST.",
            score=0.95,
            citation="[Addendum 2, Page 1]"
        )
    ]
    reconciled, changes = reconciler.reconcile("Bid1", base_fields, evidence)
    assert reconciled["Due Date"].value == "2024-07-09 14:00 CST"
    assert len(changes) == 1
    assert changes[0].field_name == "Due Date"
    assert changes[0].change_type == "replaced"


def test_validator_critic_rules():
    """Verify deterministic validation critic rules in isolation."""
    validator = ValidatorAgent()
    sample_fields = {
        f: ExtractedField(
            value="Valid value",
            sources=[Citation(file="rfp.pdf", page=1, chunk_id="c1", quote="Sample quote")],
            confidence=0.95,
            notes="Extracted from source"
        )
        for f in REQUIRED_FIELDS
    }
    sample_fields["Due Date"] = ExtractedField(
        value="2024-07-09 14:00 CST",
        sources=[Citation(file="addendum2.pdf", page=1, chunk_id="c2", quote="Extended date")],
        confidence=0.99,
        notes="Amended by addendum"
    )
    sample_fields["Pre Bid Meeting"] = ExtractedField(
        value=None,
        sources=[],
        confidence=0.9,
        notes="No pre-bid meeting scheduled"
    )

    summary, failed_fields = validator.validate_fields("Bid1", sample_fields)
    assert summary.passed >= 18
    assert summary.not_found == 1
    assert summary.failed == 0
    assert len(failed_fields) == 0
