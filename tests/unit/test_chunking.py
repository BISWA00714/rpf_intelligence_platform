"""
Unit tests for Section-Aware and Table-Aware Document Chunking.
"""

import pytest
from schemas.documents import DocumentRecord, PageRecord, TableData, DocumentType
from schemas.chunks import ChunkRecord
from chunking.chunker import chunk_document, chunk_page_content, estimate_tokens


def test_heading_preservation_in_chunk():
    page = PageRecord(
        page_number=2,
        text="Section 1 - General Information\nThis section describes the procurement rules and deadlines.\n\n1.2 Terms\nThe term of this agreement shall be 3 years.",
        tables=[],
        is_scanned=False,
        char_count=130
    )
    doc = DocumentRecord(
        bid_id="Bid1",
        file_name="RFP_Final.pdf",
        file_path="/path/to/rfp.pdf",
        file_type="pdf",
        doc_type=DocumentType.RFP,
        content_hash="abc123hash",
        total_pages=1,
        pages=[page]
    )

    chunks = chunk_document(doc, chunk_size_tokens=100, chunk_overlap_tokens=20)
    assert len(chunks) >= 1
    # First chunk must contain section title
    assert "Section 1 - General Information" in chunks[0].text
    assert chunks[0].section_title is not None


def test_table_integrity_in_chunk():
    table_md = "| SKU | Description | Qty |\n| --- | --- | --- |\n| 210-BLYZ | Dell Latitude 5550 | 30 |"
    page = PageRecord(
        page_number=1,
        text=f"Please review the required hardware items below:\n\n[STRUCTURED TABLE on Page 1]\n{table_md}\n[/STRUCTURED TABLE]\n\nAll items must be new.",
        tables=[TableData(
            table_id="page_1_table_1",
            page_number=1,
            headers=["SKU", "Description", "Qty"],
            rows=[["210-BLYZ", "Dell Latitude 5550", "30"]],
            markdown=table_md
        )],
        is_scanned=False,
        char_count=200
    )
    doc = DocumentRecord(
        bid_id="Bid2",
        file_name="Specs.pdf",
        file_path="/path/to/specs.pdf",
        file_type="pdf",
        doc_type=DocumentType.SPECS,
        content_hash="specs123hash",
        total_pages=1,
        pages=[page]
    )

    chunks = chunk_document(doc, chunk_size_tokens=300, chunk_overlap_tokens=50)
    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.has_table is True
    assert "210-BLYZ" in chunk.text
    assert "Dell Latitude 5550" in chunk.text
    assert "[STRUCTURED TABLE" in chunk.text
    assert "[/STRUCTURED TABLE]" in chunk.text


def test_chunk_metadata_attachment():
    page = PageRecord(
        page_number=1,
        text="ADDENDUM No. 2\nThe new due date is July 9, 2024 at 2:00 PM CST.",
        tables=[],
        char_count=60
    )
    doc = DocumentRecord(
        bid_id="Bid1",
        file_name="Addendum_2.pdf",
        file_path="/path/to/add2.pdf",
        file_type="pdf",
        doc_type=DocumentType.ADDENDUM,
        addendum_number=2,
        content_hash="add2hash",
        total_pages=1,
        pages=[page]
    )

    chunks = chunk_document(doc, chunk_size_tokens=200, chunk_overlap_tokens=30)
    assert len(chunks) == 1
    c = chunks[0]
    assert c.bid_id == "Bid1"
    assert c.doc_type == "addendum"
    assert c.addendum_number == 2
    assert c.page_number == 1
    assert c.metadata["addendum_number"] == 2
