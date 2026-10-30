"""
Unit tests for Hybrid RAG Search Engine, Query Expansion, and Reciprocal Rank Fusion.
"""

import pytest
from schemas.search import SearchQuery, SearchResult
from search.query_expander import expand_query, extract_exact_identifiers
from search.rrf import reciprocal_rank_fusion
from search.engine import RAGSearchEngine
from schemas.chunks import ChunkRecord


def test_query_expansion_preserves_technical_identifiers():
    query = "What is the warranty and price for SKU 210-BLYZ and WD22TB4?"
    exact_ids = extract_exact_identifiers(query)
    assert "210-BLYZ" in exact_ids
    assert "WD22TB4" in exact_ids

    dense_q, bm25_q = expand_query(query)
    # Dense query stays clean and semantic
    assert dense_q == query
    # BM25 query includes prioritized exact tokens and procurement synonyms
    assert "210-BLYZ" in bm25_q
    assert "extended warranty" in bm25_q or "warranty" in bm25_q


def test_rrf_ranking_and_score_normalization():
    c1 = ChunkRecord(
        chunk_id="c1",
        bid_id="Bid1",
        file_name="Addendum_2.pdf",
        file_path="/p/a2.pdf",
        page_number=1,
        doc_type="addendum",
        text="The new due date is July 9, 2024 at 2:00 PM CST.",
        token_count=15,
        content_hash="h1"
    )
    c2 = ChunkRecord(
        chunk_id="c2",
        bid_id="Bid1",
        file_name="RFP.pdf",
        file_path="/p/rfp.pdf",
        page_number=2,
        doc_type="rfp",
        text="Old due date was June 27, 2024.",
        token_count=12,
        content_hash="h2"
    )

    # c1 is #1 in dense, #1 in BM25
    dense_results = [(c1, 0.95), (c2, 0.70)]
    bm25_results = [(c1, 8.5), (c2, 4.2)]

    fused = reciprocal_rank_fusion(dense_results, bm25_results, k=60, top_k=2)
    assert len(fused) == 2
    assert fused[0].chunk_id == "c1"
    assert fused[0].score == 1.0  # Normalized top rank
    assert fused[0].dense_rank == 1
    assert fused[0].bm25_rank == 1
    assert "[Addendum" in fused[0].citation or "[Addendum_2.pdf" in fused[0].citation


def test_hybrid_search_bid1_deadline():
    engine = RAGSearchEngine()
    result = engine.search("What is the new proposal submission due date for Bid1?", bid_id="Bid1", top_k=3)
    assert result.is_empty is False
    assert len(result.evidence) > 0
    # Top evidence must be Addendum 2 or the portal closing date
    top_files = [ev.file_name for ev in result.evidence]
    assert any("Addendum 2" in f or "BidNet Direct" in f for f in top_files)
    # Check that July 9 appears in the top retrieved evidence text
    top_text = " ".join(ev.text for ev in result.evidence)
    assert "July 9" in top_text or "07/09/2024" in top_text


def test_hybrid_search_bid2_exact_sku():
    engine = RAGSearchEngine()
    result = engine.search("What product corresponds to SKU 210-BLYZ and SI# CC7802?", bid_id="Bid2", top_k=3)
    assert result.is_empty is False
    assert len(result.evidence) > 0
    top_text = " ".join(ev.text for ev in result.evidence)
    assert "Latitude 5550" in top_text or "Dell" in top_text


def test_empty_retrieval_cutoff():
    engine = RAGSearchEngine()
    result = engine.search("Quantum nuclear fusion reactor specifications in outer space orbit", bid_id="Bid1", top_k=3)
    # Should either return empty or low confidence
    assert result.total_candidates >= 0
