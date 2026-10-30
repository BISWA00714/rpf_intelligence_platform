"""
High-precision PDF parser for RFP documents and addenda.
Uses PyMuPDF (fitz) for text and structural table extraction, with OCR fallback for scanned pages.
"""

import re
import hashlib
import logging
from pathlib import Path
from typing import Optional, List, Tuple
import fitz  # PyMuPDF

from schemas.documents import DocumentRecord, PageRecord, TableData, DocumentType
from ingestion.normalizer import normalize_page_text
from ingestion.ocr_engine import ocr_page_pixmap
from config.settings import settings

logger = logging.getLogger(__name__)


def classify_document(file_name: str, sample_text: str) -> Tuple[DocumentType, Optional[int]]:
    """
    Classifies the role of a document based on its file name and first page text.
    Returns (DocumentType, addendum_number).
    """
    fn_lower = file_name.lower()
    text_lower = sample_text[:1500].lower()
    
    # Check for Addendum
    addendum_match = re.search(r'addendum\s*(?:no\.?|#)?\s*(\d+)', fn_lower + " " + text_lower)
    if addendum_match:
        add_num = int(addendum_match.group(1))
        return DocumentType.ADDENDUM, add_num
    elif "addendum" in fn_lower or "addendum" in text_lower:
        return DocumentType.ADDENDUM, None

    # Check for Affidavit
    if "affidavit" in fn_lower or "affidavit" in text_lower:
        return DocumentType.AFFIDAVIT, None
        
    # Check for Specs
    if "specs" in fn_lower or "specification" in fn_lower:
        return DocumentType.SPECS, None
        
    # Check for core RFP / PORFP
    if any(k in fn_lower for k in ["rfp", "porfp", "final", "solicitation", "contract"]):
        return DocumentType.RFP, None
        
    return DocumentType.UNKNOWN, None


def extract_doc_date(sample_text: str) -> Optional[str]:
    """Attempts to extract issue / publication date from cover pages."""
    patterns = [
        r'(?:Issue Date|Date|Advertisement Date)[:\s]+([0-9]{1,2}[-/][0-9]{1,2}[-/][0-9]{2,4})',
        r'([0-9]{1,2}-[A-Za-z]{3}-[0-9]{4})',
        r'(?:Date|Issued)[:\s]+([A-Za-z]+\s+\d{1,2},\s+\d{4})'
    ]
    for pat in patterns:
        match = re.search(pat, sample_text[:2000], re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def format_table_to_markdown(headers: List[str], rows: List[List[str]]) -> str:
    """Renders tabular data as a clean GitHub-flavored markdown table."""
    all_cols = max(len(headers), max([len(r) for r in rows], default=0))
    if all_cols == 0:
        return ""
    
    clean_headers = [re.sub(r'\s+', ' ', str(h)).strip() if h else f"Col {i+1}" for i, h in enumerate(headers)]
    while len(clean_headers) < all_cols:
        clean_headers.append(f"Col {len(clean_headers)+1}")
        
    md_lines = [
        "| " + " | ".join(clean_headers) + " |",
        "| " + " | ".join(["---"] * all_cols) + " |"
    ]
    
    for row in rows:
        clean_cells = []
        for cell in row:
            c = "" if cell is None else str(cell)
            c = re.sub(r'[\r\n]+', ' <br> ', c)
            c = re.sub(r'\s+', ' ', c).strip()
            c = c.replace('|', '\\|')
            clean_cells.append(c)
        while len(clean_cells) < all_cols:
            clean_cells.append("")
        md_lines.append("| " + " | ".join(clean_cells) + " |")
        
    return "\n".join(md_lines)


def parse_pdf_document(file_path: str, bid_id: str) -> DocumentRecord:
    """
    Parses a PDF document into a typed DocumentRecord with page-level text,
    tables, metadata, and optional OCR fallback.
    """
    path = Path(file_path)
    content_bytes = path.read_bytes()
    content_hash = hashlib.sha256(content_bytes).hexdigest()
    
    parsing_errors = []
    pages: List[PageRecord] = []
    
    try:
        doc = fitz.open(stream=content_bytes, filetype="pdf")
    except Exception as e:
        err_msg = f"Failed to open PDF {path.name}: {e}"
        logger.error(err_msg)
        return DocumentRecord(
            bid_id=bid_id,
            file_name=path.name,
            file_path=str(path.resolve()),
            file_type="pdf",
            doc_type=DocumentType.UNKNOWN,
            content_hash=content_hash,
            total_pages=0,
            pages=[],
            parsing_errors=[err_msg]
        )
        
    total_pages = len(doc)
    sample_text = doc[0].get_text() if total_pages > 0 else ""
    doc_type, addendum_num = classify_document(path.name, sample_text)
    doc_date = extract_doc_date(sample_text)
    
    for page_idx in range(total_pages):
        page_num = page_idx + 1
        page_obj = doc[page_idx]
        is_scanned = False
        tables: List[TableData] = []
        
        try:
            # 1. Extract digital text
            raw_text = page_obj.get_text()
            has_images = len(page_obj.get_images()) > 0
            
            # 2. Check for scanned page & OCR trigger
            if len(raw_text.strip()) < settings.OCR_MIN_CHARS_PER_PAGE and has_images:
                if settings.ENABLE_OCR:
                    logger.info(f"Triggering OCR for {path.name} page {page_num} (text len={len(raw_text.strip())})")
                    try:
                        pix = page_obj.get_pixmap(dpi=150)
                        ocr_text = ocr_page_pixmap(pix)
                        if len(ocr_text.strip()) > len(raw_text.strip()):
                            raw_text = ocr_text
                            is_scanned = True
                    except Exception as ocr_err:
                        logger.warning(f"OCR failed for {path.name} page {page_num}: {ocr_err}")
                        parsing_errors.append(f"Page {page_num} OCR failed: {ocr_err}")
            
            # 3. Extract tables
            try:
                table_finder = page_obj.find_tables()
                if table_finder and table_finder.tables:
                    for t_idx, table in enumerate(table_finder.tables):
                        extracted_table = table.extract()
                        if extracted_table and len(extracted_table) > 1:
                            raw_headers = extracted_table[0]
                            raw_rows = extracted_table[1:]
                            headers = [str(h) if h is not None else "" for h in raw_headers]
                            rows = [[str(c) if c is not None else "" for c in r] for r in raw_rows]
                            md = format_table_to_markdown(headers, rows)
                            
                            tables.append(TableData(
                                table_id=f"page_{page_num}_table_{t_idx+1}",
                                page_number=page_num,
                                headers=headers,
                                rows=rows,
                                caption=f"Table on page {page_num}",
                                markdown=md
                            ))
            except Exception as t_err:
                logger.debug(f"Table extraction notice on page {page_num}: {t_err}")

            # 4. Normalize text
            clean_text = normalize_page_text(raw_text, page_num, total_pages)
            
            # 5. Append formatted table markdown to page text for retrieval context
            if tables:
                table_blocks = []
                for t in tables:
                    table_blocks.append(f"\n[STRUCTURED TABLE on Page {page_num}]\n{t.markdown}\n[/STRUCTURED TABLE]\n")
                clean_text = clean_text + "\n" + "\n".join(table_blocks)
                
            pages.append(PageRecord(
                page_number=page_num,
                text=clean_text,
                tables=tables,
                is_scanned=is_scanned,
                has_images=has_images,
                char_count=len(clean_text)
            ))
            
        except Exception as p_err:
            err_str = f"Error parsing page {page_num} of {path.name}: {p_err}"
            logger.error(err_str)
            parsing_errors.append(err_str)
            pages.append(PageRecord(
                page_number=page_num,
                text="",
                tables=[],
                is_scanned=False,
                has_images=False,
                char_count=0
            ))
            
    doc.close()
    
    return DocumentRecord(
        bid_id=bid_id,
        file_name=path.name,
        file_path=str(path.resolve()),
        file_type="pdf",
        doc_type=doc_type,
        addendum_number=addendum_num,
        doc_date=doc_date,
        content_hash=content_hash,
        total_pages=total_pages,
        pages=pages,
        parsing_errors=parsing_errors,
        raw_metadata={"pdf_page_count": total_pages}
    )
