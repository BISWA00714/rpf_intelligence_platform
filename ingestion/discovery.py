"""
Dynamic bid discovery engine.
Automatically discovers bid packages and documents without hardcoded folder names.
Ensures seamless processing of arbitrary unseen bids (e.g. Bid3, NewRFP_2025).
"""

import os
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

from config.settings import settings

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".html", ".htm"}


class BidFolderInfo(BaseModel):
    bid_id: str
    folder_path: Path
    document_paths: List[Path]
    total_files: int


def get_supported_documents_in_dir(dir_path: Path) -> List[Path]:
    """Returns all supported document paths directly inside the directory."""
    if not dir_path.is_dir():
        return []
    return [
        p for p in sorted(dir_path.iterdir())
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS and not p.name.startswith(('.', '~', '$'))
    ]


def discover_bids(base_path: Optional[str] = None) -> List[BidFolderInfo]:
    """
    Discovers all bid folders under a base path dynamically.
    Defaults to settings.RAW_BIDS_DIR.
    
    1. Scans subdirectories: if any subdirectory contains supported documents,
       each such subdirectory is recognized as an independent bid package.
    2. If no subdirectories contain documents, checks if base_path itself directly
       contains supported documents (e.g. when pointing directly to a specific bid folder).
    """
    target = base_path if base_path is not None else str(settings.RAW_BIDS_DIR)
    root = Path(target)
    if not root.exists():
        logger.warning(f"Discovery root path does not exist: {base_path}")
        return []
        
    discovered: List[BidFolderInfo] = []
    
    # Check subdirectories first
    if root.is_dir():
        for item in sorted(root.iterdir()):
            if item.is_dir() and not item.name.startswith(('.', '_')):
                sub_docs = get_supported_documents_in_dir(item)
                if sub_docs:
                    discovered.append(BidFolderInfo(
                        bid_id=item.name,
                        folder_path=item.resolve(),
                        document_paths=sub_docs,
                        total_files=len(sub_docs)
                    ))
                    
    # If no child bid directories were found, check if root itself is a bid folder
    if not discovered and root.is_dir():
        root_docs = get_supported_documents_in_dir(root)
        if root_docs:
            discovered.append(BidFolderInfo(
                bid_id=root.name,
                folder_path=root.resolve(),
                document_paths=root_docs,
                total_files=len(root_docs)
            ))
            
    logger.info(f"Discovered {len(discovered)} bid folder(s) under {base_path}")
    return discovered
