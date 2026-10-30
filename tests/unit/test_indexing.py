"""
Unit tests for BM25 Lexical Index, Vector Stores (Qdrant & Chroma), and Incremental Indexing.
"""

import pytest
from pathlib import Path
from schemas.chunks import ChunkRecord
from indexing.bm25_index import BM25Index, tokenize_text
from indexing.vector_index import ChromaVectorIndex, QdrantVectorIndex


def test_bm25_exact_tokenization_preserves_identifiers():
    text = "The model is SI# CC7802 Dell Latitude 5550 with SKU 210-BLYZ and WD22TB4."
    tokens = tokenize_text(text)
    assert "210-blyz" in tokens
    assert "wd22tb4" in tokens
    assert "cc7802" in tokens
    assert "5550" in tokens


def test_bm25_index_and_metadata_filtering():
    c1 = ChunkRecord(
        chunk_id="c1",
        bid_id="Bid1",
        file_name="Addendum_2.pdf",
        file_path="/p/a2.pdf",
        page_number=1,
        doc_type="addendum",
        addendum_number=2,
        text="The new due date for this RFP will be July 9, 2024 at 2:00 PM CST.",
        token_count=18,
        content_hash="h1",
        metadata={"bid_id": "Bid1", "doc_type": "addendum", "addendum_number": 2}
    )
    c2 = ChunkRecord(
        chunk_id="c2",
        bid_id="Bid1",
        file_name="RFP.pdf",
        file_path="/p/rfp.pdf",
        page_number=2,
        doc_type="rfp",
        text="Solicitation Due date is June 27, 2024.",
        token_count=10,
        content_hash="h2",
        metadata={"bid_id": "Bid1", "doc_type": "rfp"}
    )
    c3 = ChunkRecord(
        chunk_id="c3",
        bid_id="Bid2",
        file_name="Specs.pdf",
        file_path="/p/sp.pdf",
        page_number=1,
        doc_type="specs",
        text="Dell Latitude 5550 Core Ultra 5 125U 16GB RAM.",
        token_count=10,
        content_hash="h3",
        metadata={"bid_id": "Bid2", "doc_type": "specs"}
    )

    index = BM25Index()
    index.build_index([c1, c2, c3])

    # Search for July 9
    results = index.search("July 9 2024", top_k=2)
    assert len(results) > 0
    assert results[0][0].chunk_id == "c1"

    # Search with filter for doc_type == addendum
    addendum_results = index.search("date", top_k=5, filters={"doc_type": "addendum"})
    assert len(addendum_results) == 1
    assert addendum_results[0][0].chunk_id == "c1"

    # Search with filter for bid_id == Bid2
    bid2_results = index.search("Dell Latitude", top_k=5, filters={"bid_id": "Bid2"})
    assert len(bid2_results) == 1
    assert bid2_results[0][0].chunk_id == "c3"


def test_qdrant_vector_index(tmp_path):
    c1 = ChunkRecord(
        chunk_id="chunk_q1",
        bid_id="Bid1",
        file_name="doc.pdf",
        file_path="/path/doc.pdf",
        page_number=1,
        doc_type="rfp",
        text="Student and Staff Computing Devices RFP Dallas ISD",
        token_count=10,
        content_hash="hash1",
        metadata={"bid_id": "Bid1", "doc_type": "rfp"}
    )
    c2 = ChunkRecord(
        chunk_id="chunk_q2",
        bid_id="Bid2",
        file_name="specs.pdf",
        file_path="/path/specs.pdf",
        page_number=1,
        doc_type="specs",
        text="Dell laptops with 3-year extended warranty",
        token_count=8,
        content_hash="hash2",
        metadata={"bid_id": "Bid2", "doc_type": "specs"}
    )

    emb1 = [1.0, 0.0, 0.0, 0.0]
    emb2 = [0.0, 1.0, 0.0, 0.0]

    idx = QdrantVectorIndex(
        collection_name="test_qdrant",
        dimension=4,
        persist_dir=tmp_path / "qdrant_test"
    )
    idx.add_chunks([c1, c2], [emb1, emb2])

    q_emb = [0.95, 0.05, 0.0, 0.0]
    results = idx.search(q_emb, top_k=1)
    assert len(results) == 1
    assert results[0][0].chunk_id == "chunk_q1"
    assert results[0][1] > 0.9

    # Test metadata filter in Qdrant
    res_filtered = idx.search(q_emb, top_k=2, filters={"bid_id": "Bid2"})
    assert len(res_filtered) == 1
    assert res_filtered[0][0].chunk_id == "chunk_q2"


def test_chroma_vector_index(tmp_path):
    c1 = ChunkRecord(
        chunk_id="chunk_1",
        bid_id="Bid1",
        file_name="doc.pdf",
        file_path="/path/doc.pdf",
        page_number=1,
        doc_type="rfp",
        text="Student and Staff Computing Devices RFP Dallas ISD",
        token_count=10,
        content_hash="hash1",
        metadata={"bid_id": "Bid1"}
    )
    c2 = ChunkRecord(
        chunk_id="chunk_2",
        bid_id="Bid2",
        file_name="specs.pdf",
        file_path="/path/specs.pdf",
        page_number=1,
        doc_type="specs",
        text="Dell laptops with 3-year extended warranty",
        token_count=8,
        content_hash="hash2",
        metadata={"bid_id": "Bid2"}
    )
    
    emb1 = [1.0, 0.0, 0.0, 0.0]
    emb2 = [0.0, 1.0, 0.0, 0.0]
    
    idx = ChromaVectorIndex(persist_dir=tmp_path / "chroma_test", collection_name="test_coll")
    idx.add_chunks([c1, c2], [emb1, emb2])

    q_emb = [0.9, 0.1, 0.0, 0.0]
    results = idx.search(q_emb, top_k=1)
    assert len(results) == 1
    assert results[0][0].chunk_id == "chunk_1"
    assert results[0][1] > 0.8

    res_filtered = idx.search(q_emb, top_k=2, filters={"bid_id": "Bid2"})
    assert len(res_filtered) == 1
    assert res_filtered[0][0].chunk_id == "chunk_2"
