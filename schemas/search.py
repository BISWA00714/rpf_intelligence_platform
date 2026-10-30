"""
Search schemas and typed evidence data models for the Hybrid RAG Search Engine.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class SearchQuery(BaseModel):
    query: str = Field(..., description="User query or agent retrieval question")
    bid_id: Optional[str] = Field(None, description="Optional target bid filter (e.g. 'Bid1')")
    doc_type: Optional[str] = Field(None, description="Optional document type filter (e.g. 'addendum', 'specs')")
    addendum_number: Optional[int] = Field(None, description="Optional addendum sequence number filter")
    page_number: Optional[int] = Field(None, description="Optional page number filter")
    top_k: int = Field(5, description="Number of top ranked evidence passages to return")
    use_reranker: bool = Field(False, description="Whether to apply cross-encoder neural reranking")
    enable_query_expansion: bool = Field(True, description="Whether to expand procurement synonyms")


class EvidenceItem(BaseModel):
    chunk_id: str = Field(..., description="Unique deterministic identifier of the cited chunk")
    bid_id: str = Field(..., description="Bid package identifier")
    file_name: str = Field(..., description="Source document filename")
    page_number: int = Field(..., description="Source page number (1-indexed)")
    doc_type: str = Field(..., description="Document type role")
    addendum_number: Optional[int] = Field(None, description="Addendum number if applicable")
    section_title: Optional[str] = Field(None, description="Section heading context")
    text: str = Field(..., description="Full text passage of the cited evidence chunk")
    score: float = Field(..., description="Normalized relevance score (0.0 to 1.0)")
    dense_rank: Optional[int] = Field(None, description="Rank from dense semantic search")
    bm25_rank: Optional[int] = Field(None, description="Rank from lexical BM25 search")
    citation: str = Field(..., description="Formatted citation label (e.g. '[Addendum 2, Page 1]')")


class SearchResult(BaseModel):
    query: str = Field(..., description="Original input query")
    expanded_query: Optional[str] = Field(None, description="Expanded query used for retrieval")
    total_candidates: int = Field(0, description="Total candidate passages retrieved before cut-off")
    evidence: List[EvidenceItem] = Field(default_factory=list, description="Top ranked evidence items with citations")
    is_empty: bool = Field(False, description="True if no relevant evidence passed threshold")
    execution_time_ms: float = Field(0.0, description="End-to-end search latency in milliseconds")
