"""
Document schemas and typed data models for ingestion, parsing, and chunking.
"""

from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class DocumentType(str, Enum):
    BID_PAGE = "bid_page"
    RFP = "rfp"
    ADDENDUM = "addendum"
    SPECS = "specs"
    AFFIDAVIT = "affidavit"
    UNKNOWN = "unknown"


class TableData(BaseModel):
    table_id: str = Field(..., description="Unique identifier for the table within the document/page")
    page_number: int = Field(..., description="Page number where the table was found (1-indexed)")
    headers: List[str] = Field(default_factory=list, description="Extracted header column names")
    rows: List[List[str]] = Field(default_factory=list, description="Extracted row values preserving grid structure")
    caption: Optional[str] = Field(None, description="Optional detected table title or preceding section heading")
    markdown: str = Field(..., description="Clean GitHub-flavored markdown representation of the table")


class PageRecord(BaseModel):
    page_number: int = Field(..., description="1-indexed page number")
    text: str = Field(..., description="Cleaned, normalized text content of the page")
    tables: List[TableData] = Field(default_factory=list, description="List of tables detected and extracted from page")
    is_scanned: bool = Field(False, description="True if text density was below threshold and OCR was triggered")
    has_images: bool = Field(False, description="True if page contains embedded raster/bitmap images")
    char_count: int = Field(0, description="Character count of cleaned text")


class DocumentRecord(BaseModel):
    bid_id: str = Field(..., description="Identifier of the bid package (e.g. Bid1, Bid2, or arbitrary unseen ID)")
    file_name: str = Field(..., description="Basename of the document file")
    file_path: str = Field(..., description="Absolute or normalized relative path to the source file")
    file_type: str = Field(..., description="File extension / format (pdf, html, etc.)")
    doc_type: DocumentType = Field(DocumentType.UNKNOWN, description="Classified semantic role of document")
    addendum_number: Optional[int] = Field(None, description="Detected addendum number if doc_type is ADDENDUM")
    doc_date: Optional[str] = Field(None, description="Extracted creation, publication, or issue date")
    content_hash: str = Field(..., description="SHA-256 hash of original file content for change detection & deduplication")
    total_pages: int = Field(0, description="Total number of pages (or 1 for HTML)")
    pages: List[PageRecord] = Field(default_factory=list, description="Page-by-page parsed records")
    parsing_errors: List[str] = Field(default_factory=list, description="Logged warnings, unreadable pages, or parse errors")
    raw_metadata: Dict[str, Any] = Field(default_factory=dict, description="Raw metadata extracted from portal or PDF dictionary")


class BidManifest(BaseModel):
    bid_id: str = Field(..., description="Identifier of the bid folder/package")
    bid_folder: str = Field(..., description="Path to the bid directory")
    total_documents: int = Field(0, description="Count of successfully parsed documents")
    total_pages: int = Field(0, description="Sum of pages across all parsed documents")
    documents: List[DocumentRecord] = Field(default_factory=list, description="List of all document records in the bid")
    created_at: str = Field(..., description="ISO 8601 timestamp of when the manifest was generated")
