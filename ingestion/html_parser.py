"""
HTML parser for RFP web portal pages (e.g., BidNet Direct dumps).
Extracts metadata key-value pairs, dates, contact details, and any embedded tables.
"""

import hashlib
from pathlib import Path
from typing import Dict, Any, List
from bs4 import BeautifulSoup

from schemas.documents import DocumentRecord, PageRecord, TableData, DocumentType
from ingestion.normalizer import normalize_whitespace


def extract_html_metadata(soup: BeautifulSoup) -> Dict[str, Any]:
    """Extracts structured key-value metadata from standard procurement portal HTML layouts."""
    metadata = {}
    
    # Check for dl/dt/dd structures
    for dt in soup.find_all('dt'):
        dd = dt.find_next_sibling('dd')
        if dd:
            key = dt.get_text(strip=True).rstrip(':')
            val = dd.get_text(strip=True)
            if key and val:
                metadata[key] = val
                
    # Check for typical label-value div pairs
    for label_elem in soup.find_all(class_=lambda c: c and any(k in str(c).lower() for k in ['label', 'key', 'title'])):
        val_elem = label_elem.find_next_sibling(class_=lambda c: c and any(v in str(c).lower() for v in ['value', 'val', 'desc', 'data']))
        if val_elem:
            key = label_elem.get_text(strip=True).rstrip(':')
            val = val_elem.get_text(strip=True)
            if key and val and key not in metadata:
                metadata[key] = val

    # Search for common procurement fields in text if not found yet
    full_text = soup.get_text(separator='\n', strip=True)
    keywords = [
        ("Reference Number", r"Reference Number[:\s]+([0-9A-Za-z_-]+)"),
        ("Solicitation Number", r"Solicitation Number[:\s]+([0-9A-Za-z_-]+)"),
        ("Issuing Organization", r"Issuing Organization[:\s]+([^\n\r]+)"),
        ("Closing Date", r"Closing Date[:\s]+([^\n\r]+)"),
        ("Prebid Conference", r"Prebid Conference[:\s]+([^\n\r]+)"),
        ("Title", r"Title[:\s]+([^\n\r]+)")
    ]
    import re
    for key, pattern in keywords:
        if key not in metadata:
            match = re.search(pattern, full_text, re.IGNORECASE)
            if match:
                metadata[key] = match.group(1).strip()
                
    return metadata


def parse_html_document(file_path: str, bid_id: str) -> DocumentRecord:
    """
    Parses an HTML bid portal file into a standardized DocumentRecord.
    
    Args:
        file_path: Path to the HTML file
        bid_id: Target bid identifier
        
    Returns:
        DocumentRecord containing normalized page content, extracted tables, and metadata.
    """
    path = Path(file_path)
    content_bytes = path.read_bytes()
    content_hash = hashlib.sha256(content_bytes).hexdigest()
    
    html_text = content_bytes.decode('utf-8', errors='ignore')
    soup = BeautifulSoup(html_text, 'html.parser')
    
    # Remove script and style elements
    for s in soup(['script', 'style', 'noscript', 'header', 'footer']):
        s.decompose()
        
    extracted_metadata = extract_html_metadata(soup)
    
    # Extract any HTML tables
    tables: List[TableData] = []
    for idx, table_tag in enumerate(soup.find_all('table')):
        rows_data = []
        headers = []
        
        # Extract headers
        th_tags = table_tag.find_all('th')
        if th_tags:
            headers = [th.get_text(strip=True) for th in th_tags]
            
        # Extract rows
        for tr in table_tag.find_all('tr'):
            td_tags = tr.find_all('td')
            if td_tags:
                row = [td.get_text(separator=' ', strip=True) for td in td_tags]
                rows_data.append(row)
                
        if rows_data or headers:
            # Generate markdown table
            all_cols = max(len(headers), max([len(r) for r in rows_data], default=0))
            if not headers:
                headers = [f"Col {i+1}" for i in range(all_cols)]
            while len(headers) < all_cols:
                headers.append(f"Col {len(headers)+1}")
                
            md_lines = [
                "| " + " | ".join(headers) + " |",
                "| " + " | ".join(["---"] * all_cols) + " |"
            ]
            for row in rows_data:
                padded = row + [""] * (all_cols - len(row))
                md_lines.append("| " + " | ".join(padded) + " |")
                
            tables.append(TableData(
                table_id=f"html_table_{idx+1}",
                page_number=1,
                headers=headers,
                rows=rows_data,
                caption=f"Portal Table {idx+1}",
                markdown="\n".join(md_lines)
            ))
            
    # Clean text content
    clean_text = soup.get_text(separator='\n', strip=True)
    clean_text = normalize_whitespace(clean_text)
    
    # Prepend formatted metadata if present
    if extracted_metadata:
        meta_lines = ["--- PORTAL BID METADATA ---"]
        for k, v in extracted_metadata.items():
            meta_lines.append(f"{k}: {v}")
        meta_lines.append("----------------------------\n")
        clean_text = "\n".join(meta_lines) + "\n" + clean_text
        
    page = PageRecord(
        page_number=1,
        text=clean_text,
        tables=tables,
        is_scanned=False,
        has_images=False,
        char_count=len(clean_text)
    )
    
    doc_date = extracted_metadata.get("Publication") or extracted_metadata.get("Date")
    
    return DocumentRecord(
        bid_id=bid_id,
        file_name=path.name,
        file_path=str(path.resolve()),
        file_type="html",
        doc_type=DocumentType.BID_PAGE,
        addendum_number=None,
        doc_date=doc_date,
        content_hash=content_hash,
        total_pages=1,
        pages=[page],
        parsing_errors=[],
        raw_metadata=extracted_metadata
    )
