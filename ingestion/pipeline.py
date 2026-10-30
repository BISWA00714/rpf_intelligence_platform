"""
End-to-end ingestion pipeline orchestrator.
Discovers documents, routes them to format parsers, normalizes text and tables,
and serializes document manifests for indexing and downstream agent use.
"""

import sys
import json
import logging
import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, List

from config.settings import settings
from schemas.documents import BidManifest, DocumentRecord
from ingestion.discovery import discover_bids, BidFolderInfo
from ingestion.pdf_parser import parse_pdf_document
from ingestion.html_parser import parse_html_document

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("ingestion.pipeline")


def ingest_bid_folder(bid_info: BidFolderInfo) -> BidManifest:
    """
    Ingests all documents in a discovered bid folder.
    
    Args:
        bid_info: BidFolderInfo descriptor
        
    Returns:
        Complete BidManifest with parsed document records.
    """
    logger.info(f"--- Starting Ingestion for Bid: {bid_info.bid_id} ({bid_info.total_files} files) ---")
    documents: List[DocumentRecord] = []
    total_pages = 0
    
    for doc_path in bid_info.document_paths:
        ext = doc_path.suffix.lower()
        logger.info(f"Parsing [{bid_info.bid_id}] {doc_path.name}...")
        
        try:
            if ext == ".pdf":
                record = parse_pdf_document(str(doc_path), bid_info.bid_id)
            elif ext in [".html", ".htm"]:
                record = parse_html_document(str(doc_path), bid_info.bid_id)
            else:
                logger.warning(f"Unsupported file format {ext} for {doc_path.name}")
                continue
                
            documents.append(record)
            total_pages += record.total_pages
            
            table_count = sum(len(p.tables) for p in record.pages)
            scanned_count = sum(1 for p in record.pages if p.is_scanned)
            logger.info(
                f"  -> Success: {record.file_name} | Type: {record.doc_type.value} | "
                f"Pages: {record.total_pages} | Tables: {table_count} | Scanned/OCR: {scanned_count}"
            )
            
        except Exception as e:
            logger.error(f"Failed to ingest {doc_path.name}: {e}", exc_info=True)
            
    manifest = BidManifest(
        bid_id=bid_info.bid_id,
        bid_folder=str(bid_info.folder_path),
        total_documents=len(documents),
        total_pages=total_pages,
        documents=documents,
        created_at=datetime.now(timezone.utc).isoformat()
    )
    
    # Save manifest to processed directory
    out_file = settings.PROCESSED_DIR / f"{bid_info.bid_id}_manifest.json"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(manifest.model_dump_json(indent=2))
        
    logger.info(f"Saved manifest to {out_file} (Total docs: {len(documents)}, Total pages: {total_pages})")
    return manifest


def run_ingestion_pipeline(raw_dir: Optional[str] = None, bid_path: Optional[str] = None) -> Dict[str, BidManifest]:
    """Runs ingestion across one or all discovered bids."""
    target_path = bid_path if bid_path else (raw_dir if raw_dir else str(settings.RAW_BIDS_DIR))
    bids = discover_bids(target_path)
    
    if not bids:
        logger.warning(f"No bid packages found in {target_path}")
        return {}
        
    manifests: Dict[str, BidManifest] = {}
    for b in bids:
        manifest = ingest_bid_folder(b)
        manifests[b.bid_id] = manifest
        
    logger.info(f"=== Completed Ingestion for {len(manifests)} Bid Package(s) ===")
    return manifests


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest RFP documents and generate manifests.")
    parser.add_argument("--bid", type=str, default=None, help="Path to a specific bid directory")
    parser.add_argument("--raw-dir", type=str, default=None, help="Root directory containing bid folders")
    args = parser.parse_args()
    
    run_ingestion_pipeline(raw_dir=args.raw_dir, bid_path=args.bid)
