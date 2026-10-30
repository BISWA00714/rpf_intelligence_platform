"""
Chunk schemas and data models for section-aware and table-aware document partitioning.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class ChunkRecord(BaseModel):
    chunk_id: str = Field(..., description="Unique deterministic identifier for the chunk")
    bid_id: str = Field(..., description="Parent bid identifier")
    file_name: str = Field(..., description="Source file name")
    file_path: str = Field(..., description="Absolute path to the source document")
    page_number: int = Field(..., description="1-indexed page number where chunk originates")
    doc_type: str = Field(..., description="Document type (rfp, addendum, specs, affidavit, bid_page)")
    addendum_number: Optional[int] = Field(None, description="Addendum sequence number if applicable")
    section_title: Optional[str] = Field(None, description="Preceding section heading or clause title")
    text: str = Field(..., description="Normalized text payload of the chunk")
    token_count: int = Field(..., description="Estimated or exact token count")
    content_hash: str = Field(..., description="SHA-256 hash of chunk text for deduplication")
    has_table: bool = Field(False, description="True if chunk contains a structured table")
    table_ids: List[str] = Field(default_factory=list, description="IDs of any tables embedded in this chunk")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Custom metadata attributes for filtering")


class ChunkCollection(BaseModel):
    bid_id: str
    total_chunks: int
    chunks: List[ChunkRecord]
    created_at: str
