"""
Integration tests for the RFP Intelligence Platform API endpoints and routes.
Verifies system health, bid discovery, hybrid search, 20-field extraction retrieval,
cited Q&A, bid comparison matrix, and observability trace handling.
"""

import pytest
from fastapi import HTTPException
from api.routes import (
    health_check,
    list_bids,
    get_bid_manifest,
    hybrid_search,
    get_extracted_bid,
    ask_question,
    compare_bids,
    get_run_trace,
    list_run_traces,
    upload_bid_documents,
    AskRequest,
    HealthResponse,
    RunTraceSummary,
    UploadResponse
)
from schemas.extraction import BidExtractionOutput
from schemas.search import SearchResult
from schemas.documents import BidManifest


def test_health_endpoint():
    """Verify system health, vector backend, and index statistics."""
    res = health_check()
    assert isinstance(res, HealthResponse)
    assert res.status == "ok"
    assert res.version == "1.0.0"
    assert "MiniLM" in res.embedding_model
    assert res.total_indexed_chunks > 0


def test_list_bids_endpoint():
    """Verify dynamic bid package discovery endpoint."""
    bids = list_bids()
    assert len(bids) >= 2
    bid_ids = [b.bid_id for b in bids]
    assert "Bid1" in bid_ids
    assert "Bid2" in bid_ids


def test_get_bid_manifest_endpoint():
    """Verify bid document manifest inspection endpoint."""
    manifest = get_bid_manifest("Bid1")
    assert isinstance(manifest, BidManifest)
    assert manifest.bid_id == "Bid1"
    assert manifest.total_documents >= 3
    assert manifest.total_pages > 0
    assert len(manifest.documents) >= 3


def test_hybrid_search_endpoint():
    """Verify hybrid search endpoint with query and bid filtering."""
    res = hybrid_search(q="bid bond requirement", bid_id="Bid1", top_k=3)
    assert isinstance(res, SearchResult)
    assert len(res.evidence) > 0
    top_hit = res.evidence[0]
    assert top_hit.file_name != ""
    assert top_hit.page_number > 0
    assert top_hit.score > 0
    assert "bond" in top_hit.text.lower() or "bid" in top_hit.text.lower()


def test_get_extracted_bid_endpoint():
    """Verify retrieval of structured 20-field extraction output."""
    output = get_extracted_bid("Bid1")
    assert isinstance(output, BidExtractionOutput)
    assert output.bid_id == "Bid1"
    assert len(output.fields) == 20
    assert "Bid Number" in output.fields
    assert "Due Date" in output.fields
    assert output.fields["Due Date"].value == "2024-07-09 14:00 CST"
    assert len(output.addendum_changes) >= 1
    assert output.validation.passed >= 18


def test_ask_question_endpoint():
    """Verify cited Q&A endpoint with traceable citations."""
    req = AskRequest(
        question="What is the final submission deadline for Bid1 after all addendums?",
        bid_id="Bid1"
    )
    res = ask_question(req)
    assert "July 9, 2024" in res.answer or "2024-07-09" in res.answer
    assert len(res.citations) > 0
    assert res.run_id is not None


def test_compare_endpoint():
    """Verify side-by-side bid comparison report endpoint."""
    res = compare_bids()
    assert len(res["bids"]) == 2
    assert len(res["dimensions"]) >= 10
    assert len(res["key_differences"]) >= 3


def test_invalid_run_trace_404():
    """Verify proper 404 HTTPException for non-existent execution trace."""
    with pytest.raises(HTTPException) as excinfo:
        get_run_trace("non-existent-run-id-99999")
    assert excinfo.value.status_code == 404


def test_list_runs_endpoint():
    """Verify listing of observability execution telemetry runs."""
    traces = list_run_traces()
    assert isinstance(traces, list)
    if traces:
        assert isinstance(traces[0], RunTraceSummary)
        assert traces[0].run_id != ""


def test_upload_bid_document_endpoint():
    """Verify uploading new documents to a bid folder via REST API."""
    import io
    from fastapi import UploadFile

    dummy_content = b"Mock Bid Document for testing upload"
    file_obj = io.BytesIO(dummy_content)
    upload_file = UploadFile(filename="mock_specs.pdf", file=file_obj)

    res = upload_bid_documents(bid_id="MockBidTest", files=[upload_file])
    assert isinstance(res, UploadResponse)
    assert res.bid_id == "MockBidTest"
    assert "mock_specs.pdf" in res.uploaded_files

    # Cleanup temporary test folder created in raw_bids
    from config.settings import settings
    test_folder = settings.RAW_BIDS_DIR / "MockBidTest"
    if test_folder.exists():
        import shutil
        shutil.rmtree(test_folder)
