"""
Unit tests for document ingestion, parsing, normalization, and discovery.
"""

import pytest
from pathlib import Path
from schemas.documents import DocumentType, DocumentRecord, BidManifest
from ingestion.discovery import discover_bids
from ingestion.html_parser import parse_html_document
from ingestion.pdf_parser import parse_pdf_document, classify_document
from ingestion.normalizer import normalize_whitespace, fix_broken_hyphenations, clean_pdf_headers_footers


def test_normalizer_rejoins_broken_hyphenations():
    text = "This agree-\n  ment is valid for five years."
    fixed = fix_broken_hyphenations(text)
    assert "agreement" in fixed
    
    # Must preserve exact technical SKUs
    sku_text = "SKU: JA-207652 and 210-BLYZ"
    fixed_sku = fix_broken_hyphenations(sku_text)
    assert "JA-207652" in fixed_sku
    assert "210-BLYZ" in fixed_sku


def test_normalizer_removes_headers_footers():
    raw = "Header text\nDallas ISD rev 2.0\nPage 2 of 40\nSubstantive content"
    cleaned = clean_pdf_headers_footers(raw, 2, 40)
    assert "Dallas ISD rev 2.0" not in cleaned
    assert "Page 2 of 40" not in cleaned
    assert "Substantive content" in cleaned


def test_classify_document():
    doc_type, num = classify_document("Addendum 1 RFP JA-207652.pdf", "Addendum No. 1")
    assert doc_type == DocumentType.ADDENDUM
    assert num == 1

    doc_type, num = classify_document("Addendum 2 RFP JA-207652.pdf", "Addendum No. 2")
    assert doc_type == DocumentType.ADDENDUM
    assert num == 2

    doc_type, _ = classify_document("Contract_Affidavit.pdf", "Affidavit")
    assert doc_type == DocumentType.AFFIDAVIT

    doc_type, _ = classify_document("Dell_Laptop_Specs.pdf", "Specifications")
    assert doc_type == DocumentType.SPECS

    doc_type, _ = classify_document("PORFP_-_Dell_Laptop_Final.pdf", "Purchase Order RFP")
    assert doc_type == DocumentType.RFP


def test_discovery_detects_all_bids():
    bids = discover_bids("data/raw")
    bid_ids = [b.bid_id for b in bids]
    assert "Bid1" in bid_ids
    assert "Bid2" in bid_ids
    
    bid1 = next(b for b in bids if b.bid_id == "Bid1")
    assert bid1.total_files == 4
    
    bid2 = next(b for b in bids if b.bid_id == "Bid2")
    assert bid2.total_files == 5


def test_html_parsing_bid1():
    html_path = "data/raw/Bid1/Student and Staff Computing Devices __SOURCING #168884__ - Bid Information - {3} _ BidNet Direct.html"
    if Path(html_path).exists():
        record = parse_html_document(html_path, "Bid1")
        assert record.bid_id == "Bid1"
        assert record.doc_type == DocumentType.BID_PAGE
        assert record.total_pages == 1
        assert "JA-207652" in record.pages[0].text
        assert len(record.content_hash) == 64


def test_pdf_parsing_bid2_porfp():
    pdf_path = "data/raw/Bid2/PORFP_-_Dell_Laptop_Final.pdf"
    if Path(pdf_path).exists():
        record = parse_pdf_document(pdf_path, "Bid2")
        assert record.bid_id == "Bid2"
        assert record.total_pages == 4
        assert record.doc_type == DocumentType.RFP
        assert len(record.pages) == 4
        # Verify tables extracted
        total_tables = sum(len(p.tables) for p in record.pages)
        assert total_tables > 0
        # Verify Dell Latitude appears in text
        all_text = " ".join(p.text for p in record.pages)
        assert "Dell" in all_text
        assert "E20P4600040" in all_text


def test_graceful_handling_corrupted_file(tmp_path):
    bad_pdf = tmp_path / "corrupt.pdf"
    bad_pdf.write_bytes(b"not a valid pdf data stream")
    record = parse_pdf_document(str(bad_pdf), "TestBid")
    assert record.total_pages == 0
    assert len(record.parsing_errors) > 0
