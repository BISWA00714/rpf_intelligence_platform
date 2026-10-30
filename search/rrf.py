"""
Reciprocal Rank Fusion (RRF) algorithm for merging Dense and Lexical search results.
Formula: Score(d) = sum( weight_m / (k + rank_m(d)) )
Standard baseline: Cormack, Clarke & Buettcher (SIGIR 2009) with k=60.
"""

from typing import List, Tuple, Dict, Any, Optional
from schemas.chunks import ChunkRecord
from schemas.search import EvidenceItem
from config.settings import settings


def format_citation(chunk: ChunkRecord) -> str:
    """Formats standardized citation label for evidence tracking."""
    if chunk.doc_type == "addendum" and chunk.addendum_number:
        return f"[Addendum {chunk.addendum_number}, Page {chunk.page_number}]"
    return f"[{chunk.file_name}, Page {chunk.page_number}]"


def reciprocal_rank_fusion(
    dense_results: List[Tuple[ChunkRecord, float]],
    bm25_results: List[Tuple[ChunkRecord, float]],
    k: int = 60,
    dense_weight: float = 0.5,
    bm25_weight: float = 0.5,
    top_k: int = 5
) -> List[EvidenceItem]:
    """
    Fuses dense vector rankings and lexical BM25 rankings using Reciprocal Rank Fusion.
    
    Args:
        dense_results: List of (ChunkRecord, similarity_score) sorted descending
        bm25_results: List of (ChunkRecord, bm25_score) sorted descending
        k: Smoothing constant (default 60)
        dense_weight: Relative weight for dense rank contribution
        bm25_weight: Relative weight for BM25 rank contribution
        top_k: Maximum number of fused evidence items to return
        
    Returns:
        List of EvidenceItem objects sorted by fused score descending.
    """
    fused_scores: Dict[str, float] = {}
    chunk_store: Dict[str, ChunkRecord] = {}
    dense_ranks: Dict[str, int] = {}
    bm25_ranks: Dict[str, int] = {}

    # Track dense ranks (1-indexed)
    for rank, (chunk, _) in enumerate(dense_results, start=1):
        cid = chunk.chunk_id
        chunk_store[cid] = chunk
        dense_ranks[cid] = rank
        score = dense_weight / (k + rank)
        fused_scores[cid] = fused_scores.get(cid, 0.0) + score

    # Track BM25 ranks (1-indexed)
    for rank, (chunk, _) in enumerate(bm25_results, start=1):
        cid = chunk.chunk_id
        chunk_store[cid] = chunk
        bm25_ranks[cid] = rank
        score = bm25_weight / (k + rank)
        fused_scores[cid] = fused_scores.get(cid, 0.0) + score

    if not fused_scores:
        return []

    # Sort descending by fused score
    sorted_items = sorted(fused_scores.items(), key=lambda x: x[1], reverse=True)
    
    # Calculate max possible score for normalization
    # If a document was #1 in both lists: (w_dense + w_bm25) / (k + 1)
    max_theoretical_score = (dense_weight + bm25_weight) / (k + 1)

    evidence_list: List[EvidenceItem] = []
    for cid, raw_score in sorted_items[:top_k]:
        chunk = chunk_store[cid]
        norm_score = min(1.0, round(raw_score / max_theoretical_score, 4))
        
        evidence_list.append(EvidenceItem(
            chunk_id=chunk.chunk_id,
            bid_id=chunk.bid_id,
            file_name=chunk.file_name,
            page_number=chunk.page_number,
            doc_type=chunk.doc_type,
            addendum_number=chunk.addendum_number,
            section_title=chunk.section_title,
            text=chunk.text,
            score=norm_score,
            dense_rank=dense_ranks.get(cid),
            bm25_rank=bm25_ranks.get(cid),
            citation=format_citation(chunk)
        ))

    return evidence_list
