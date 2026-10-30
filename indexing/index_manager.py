"""
Index Manager for Incremental Indexing and Persistence.
Coordinates Section-Aware Chunking, Vector Store (Chroma/FAISS), and BM25 Lexical Indexing.
Maintains a Content-Hash Registry to prevent redundant indexing of unchanged documents.
"""

import json
import logging
import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional

from config.settings import settings
from schemas.documents import BidManifest, DocumentRecord
from schemas.chunks import ChunkRecord
from chunking.chunker import chunk_document
from indexing.embeddings import get_embedding_model
from indexing.bm25_index import BM25Index
from indexing.vector_index import get_vector_index, BaseVectorIndex

logger = logging.getLogger("indexing.manager")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


class IndexManager:
    """Manages incremental indexing lifecycle across vector and lexical stores."""

    def __init__(self, registry_path: Optional[Path] = None):
        self.registry_path = registry_path or (settings.INDICES_DIR / "index_registry.json")
        self.registry: Dict[str, Any] = self._load_registry()
        self.vector_index: BaseVectorIndex = get_vector_index()
        self.bm25_index: BM25Index = BM25Index.load()
        self.embedding_model = get_embedding_model()

    def _load_registry(self) -> Dict[str, Any]:
        if self.registry_path.exists():
            try:
                with open(self.registry_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load index registry ({e}). Starting fresh.")
        return {"files": {}, "updated_at": None}

    def _save_registry(self):
        self.registry["updated_at"] = datetime.now(timezone.utc).isoformat()
        with open(self.registry_path, "w", encoding="utf-8") as f:
            json.dump(self.registry, f, indent=2)

    def index_manifest(self, manifest: BidManifest, rebuild: bool = False) -> Dict[str, int]:
        """
        Incrementally indexes documents from a BidManifest.
        
        Args:
            manifest: BidManifest object containing parsed documents
            rebuild: If True, forces re-chunking and re-embedding of all documents
            
        Returns:
            Dictionary with counts of added, skipped, and updated documents/chunks.
        """
        stats = {"added_chunks": 0, "skipped_files": 0, "indexed_files": 0}
        new_chunks: List[ChunkRecord] = []
        
        logger.info(f"Indexing bid '{manifest.bid_id}' (rebuild={rebuild})...")
        
        for doc in manifest.documents:
            file_key = f"{doc.bid_id}:{doc.file_name}"
            registered = self.registry["files"].get(file_key)
            
            # Incremental check: has file content hash changed?
            if registered and registered.get("content_hash") == doc.content_hash and not rebuild:
                logger.info(f"Skipping unchanged file: {doc.file_name} (hash={doc.content_hash[:8]})")
                stats["skipped_files"] += 1
                continue

            logger.info(f"Processing & chunking: {doc.file_name} ({doc.total_pages} pages)")
            
            # If previously indexed with different hash, remove obsolete chunks
            if registered:
                old_ids = registered.get("chunk_ids", [])
                self.vector_index.delete_chunks(old_ids)
                
            # Generate section-aware chunks
            doc_chunks = chunk_document(
                doc,
                chunk_size_tokens=settings.CHUNK_SIZE_TOKENS,
                chunk_overlap_tokens=settings.CHUNK_OVERLAP_TOKENS
            )
            
            if not doc_chunks:
                logger.warning(f"No chunks generated for {doc.file_name}")
                continue
                
            new_chunks.extend(doc_chunks)
            chunk_ids = [c.chunk_id for c in doc_chunks]
            
            # Update registry record for this file
            self.registry["files"][file_key] = {
                "bid_id": doc.bid_id,
                "file_name": doc.file_name,
                "content_hash": doc.content_hash,
                "total_chunks": len(doc_chunks),
                "chunk_ids": chunk_ids,
                "indexed_at": datetime.now(timezone.utc).isoformat()
            }
            stats["indexed_files"] += 1
            stats["added_chunks"] += len(doc_chunks)

        if new_chunks:
            logger.info(f"Computing embeddings for {len(new_chunks)} new chunk(s)...")
            texts = [c.text for c in new_chunks]
            embeddings = self.embedding_model.embed_documents(texts)
            
            # Upsert to vector store
            self.vector_index.add_chunks(new_chunks, embeddings)
            self.vector_index.save()
            
            # Update BM25 index with all chunks across all bids
            all_chunks = list(self.bm25_index.chunks)
            new_chunk_id_set = {c.chunk_id for c in new_chunks}
            all_chunks = [c for c in all_chunks if c.chunk_id not in new_chunk_id_set]
            all_chunks.extend(new_chunks)
            
            self.bm25_index.build_index(all_chunks)
            self.bm25_index.save()

        self._save_registry()
        logger.info(f"Indexing complete for {manifest.bid_id}: {stats}")
        return stats

    def index_bid_id(self, bid_id: str, rebuild: bool = False) -> Dict[str, int]:
        """Loads manifest for bid_id and indexes it."""
        manifest_file = settings.PROCESSED_DIR / f"{bid_id}_manifest.json"
        if not manifest_file.exists():
            raise FileNotFoundError(f"Manifest not found for {bid_id} at {manifest_file}. Run ingestion first.")
        with open(manifest_file, "r", encoding="utf-8") as f:
            manifest = BidManifest.model_validate_json(f.read())
        return self.index_manifest(manifest, rebuild=rebuild)

    def index_all(self, rebuild: bool = False) -> Dict[str, Any]:
        """Indexes all manifests discovered in data/processed."""
        manifest_files = list(settings.PROCESSED_DIR.glob("*_manifest.json"))
        if not manifest_files:
            logger.warning("No manifest files found in data/processed/. Run ingestion first.")
            return {}
            
        overall_stats = {}
        for mf in sorted(manifest_files):
            bid_id = mf.stem.replace("_manifest", "")
            with open(mf, "r", encoding="utf-8") as f:
                manifest = BidManifest.model_validate_json(f.read())
            stats = self.index_manifest(manifest, rebuild=rebuild)
            overall_stats[bid_id] = stats
            
        return overall_stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build and manage Vector and BM25 indices.")
    parser.add_argument("--bid", type=str, default=None, help="Specific bid ID to index (e.g. Bid1)")
    parser.add_argument("--all", action="store_true", help="Index all discovered bid manifests")
    parser.add_argument("--rebuild", action="store_true", help="Force rebuild of indices from scratch")
    args = parser.parse_args()

    manager = IndexManager()
    if args.bid:
        manager.index_bid_id(args.bid, rebuild=args.rebuild)
    elif args.all or not args.bid:
        manager.index_all(rebuild=args.rebuild)
