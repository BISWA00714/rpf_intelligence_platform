"""
Vector Store Index implementations.
Provides Chroma, Qdrant, and FAISS persistent vector indexes with metadata filtering.
"""

import abc
import uuid
import pickle
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import numpy as np

from schemas.chunks import ChunkRecord
from config.settings import settings

logger = logging.getLogger(__name__)


class BaseVectorIndex(abc.ABC):
    """Abstract interface for dense vector indices."""

    @abc.abstractmethod
    def add_chunks(self, chunks: List[ChunkRecord], embeddings: List[List[float]]):
        """Adds chunks and their embedding vectors to index."""
        pass

    @abc.abstractmethod
    def search(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Tuple[ChunkRecord, float]]:
        """Searches vector index with metadata filtering, returning (ChunkRecord, similarity_score)."""
        pass

    @abc.abstractmethod
    def delete_chunks(self, chunk_ids: List[str]):
        """Deletes chunks by their IDs."""
        pass

    @abc.abstractmethod
    def save(self):
        """Persists index to disk."""
        pass


class QdrantVectorIndex(BaseVectorIndex):
    """
    Qdrant Vector Index supporting 100% Free Local Embedded Storage on Disk
    or Remote Qdrant Cloud Cluster.
    """
    _CLIENT_CACHE: Dict[str, Any] = {}

    def __init__(
        self,
        collection_name: str = "rfp_chunks",
        dimension: int = 384,
        persist_dir: Optional[Path] = None
    ):
        from qdrant_client import QdrantClient
        from qdrant_client.http import models

        self.collection_name = collection_name
        self.dimension = dimension
        self.persist_dir = persist_dir or (settings.INDICES_DIR / "qdrant")

        cache_key = settings.QDRANT_URL if settings.QDRANT_URL else str(self.persist_dir.resolve())
        if cache_key in QdrantVectorIndex._CLIENT_CACHE:
            self.client = QdrantVectorIndex._CLIENT_CACHE[cache_key]
        else:
            if settings.QDRANT_URL:
                logger.info(f"Connecting to remote Qdrant at {settings.QDRANT_URL}...")
                self.client = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY)
            else:
                self.persist_dir.mkdir(parents=True, exist_ok=True)
                logger.info(f"Initializing local embedded Qdrant (disk: {self.persist_dir})...")
                self.client = QdrantClient(path=str(self.persist_dir))
            QdrantVectorIndex._CLIENT_CACHE[cache_key] = self.client

        # Ensure collection exists with cosine metric
        collections = [c.name for c in self.client.get_collections().collections]
        if self.collection_name not in collections:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(
                    size=self.dimension,
                    distance=models.Distance.COSINE
                )
            )
            logger.info(f"Created Qdrant collection '{self.collection_name}' (size={self.dimension}, metric=COSINE).")

    def _chunk_id_to_uuid(self, chunk_id: str) -> str:
        """Deterministically maps any string chunk_id to a valid UUID format required by Qdrant."""
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk_id))

    def add_chunks(self, chunks: List[ChunkRecord], embeddings: List[List[float]]):
        if not chunks or not embeddings:
            return

        from qdrant_client.http import models
        points = []
        for chunk, vector in zip(chunks, embeddings):
            pt_id = self._chunk_id_to_uuid(chunk.chunk_id)
            payload = chunk.model_dump()
            points.append(models.PointStruct(id=pt_id, vector=vector, payload=payload))

        self.client.upsert(
            collection_name=self.collection_name,
            points=points
        )
        logger.info(f"Upserted {len(chunks)} chunks into Qdrant collection '{self.collection_name}'.")

    def search(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Tuple[ChunkRecord, float]]:
        from qdrant_client.http import models

        query_filter = None
        if filters:
            conditions = []
            for k, v in filters.items():
                if v is not None:
                    conditions.append(
                        models.FieldCondition(
                            key=k,
                            match=models.MatchValue(value=v)
                        )
                    )
            if conditions:
                query_filter = models.Filter(must=conditions)

        # Execute vector search via query_points (qdrant-client 1.20+)
        response = self.client.query_points(
            collection_name=self.collection_name,
            query=query_embedding,
            limit=top_k,
            query_filter=query_filter
        )

        candidates: List[Tuple[ChunkRecord, float]] = []
        for hit in response.points:
            chunk = ChunkRecord.model_validate(hit.payload)
            candidates.append((chunk, float(hit.score)))

        return candidates

    def delete_chunks(self, chunk_ids: List[str]):
        if not chunk_ids:
            return
        from qdrant_client.http import models
        point_ids = [self._chunk_id_to_uuid(cid) for cid in chunk_ids]
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=models.PointIdsList(points=point_ids)
        )

    def save(self):
        # Qdrant client handles automatic disk flush
        pass


class ChromaVectorIndex(BaseVectorIndex):
    """Persistent ChromaDB vector index."""

    def __init__(self, persist_dir: Optional[Path] = None, collection_name: str = "rfp_chunks"):
        import chromadb
        self.persist_dir = persist_dir or (settings.INDICES_DIR / "chroma")
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(self.persist_dir))
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"}
        )
        self._chunks_by_id: Dict[str, ChunkRecord] = {}

    def add_chunks(self, chunks: List[ChunkRecord], embeddings: List[List[float]]):
        if not chunks:
            return

        ids = [c.chunk_id for c in chunks]
        documents = [c.text for c in chunks]
        metadatas = []
        for c in chunks:
            meta = {
                "bid_id": str(c.bid_id),
                "file_name": str(c.file_name),
                "doc_type": str(c.doc_type),
                "page_number": int(c.page_number),
                "has_table": bool(c.has_table),
                "content_hash": str(c.content_hash)
            }
            if c.addendum_number is not None:
                meta["addendum_number"] = int(c.addendum_number)
            metadatas.append(meta)
            self._chunks_by_id[c.chunk_id] = c

        self.collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas
        )
        logger.info(f"Upserted {len(chunks)} chunks into Chroma collection '{self.collection.name}'.")

    def search(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Tuple[ChunkRecord, float]]:
        where_clause = None
        if filters:
            conditions = []
            for k, v in filters.items():
                if v is not None:
                    conditions.append({k: v})
            if len(conditions) == 1:
                where_clause = conditions[0]
            elif len(conditions) > 1:
                where_clause = {"$and": conditions}

        total_in_coll = self.collection.count()
        if total_in_coll == 0:
            return []

        n_results = min(top_k, total_in_coll)
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where_clause,
            include=["documents", "metadatas", "distances"]
        )

        candidates: List[Tuple[ChunkRecord, float]] = []
        if results and results["ids"] and len(results["ids"][0]) > 0:
            for idx, c_id in enumerate(results["ids"][0]):
                dist = results["distances"][0][idx] if results.get("distances") else 0.0
                sim_score = max(0.0, 1.0 - (dist / 2.0))
                
                chunk = self._chunks_by_id.get(c_id)
                if not chunk:
                    meta = results["metadatas"][0][idx]
                    doc_text = results["documents"][0][idx]
                    chunk = ChunkRecord(
                        chunk_id=c_id,
                        bid_id=meta.get("bid_id", "unknown"),
                        file_name=meta.get("file_name", "unknown"),
                        file_path="",
                        page_number=meta.get("page_number", 1),
                        doc_type=meta.get("doc_type", "unknown"),
                        addendum_number=meta.get("addendum_number"),
                        text=doc_text,
                        token_count=len(doc_text) // 4,
                        content_hash=meta.get("content_hash", ""),
                        has_table=meta.get("has_table", False),
                        metadata=meta
                    )
                candidates.append((chunk, float(sim_score)))

        return candidates

    def delete_chunks(self, chunk_ids: List[str]):
        if chunk_ids:
            self.collection.delete(ids=chunk_ids)
            for c_id in chunk_ids:
                self._chunks_by_id.pop(c_id, None)

    def save(self):
        pass


class FAISSVectorIndex(BaseVectorIndex):
    """File-backed FAISS vector index using normalized inner product (cosine similarity)."""

    def __init__(self, dimension: int = 384, persist_dir: Optional[Path] = None):
        import faiss
        self.dimension = dimension
        self.persist_dir = persist_dir or (settings.INDICES_DIR / "faiss")
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.index = faiss.IndexFlatIP(dimension)
        self.chunks: List[ChunkRecord] = []
        self.chunk_ids: List[str] = []

    def add_chunks(self, chunks: List[ChunkRecord], embeddings: List[List[float]]):
        if not chunks or not embeddings:
            return
        vectors = np.array(embeddings, dtype=np.float32)
        import faiss
        faiss.normalize_L2(vectors)
        self.index.add(vectors)
        self.chunks.extend(chunks)
        self.chunk_ids.extend([c.chunk_id for c in chunks])

    def search(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Tuple[ChunkRecord, float]]:
        if self.index.ntotal == 0:
            return []

        q_vec = np.array([query_embedding], dtype=np.float32)
        import faiss
        faiss.normalize_L2(q_vec)

        search_k = min(self.index.ntotal, top_k * 4 if filters else top_k)
        scores, indices = self.index.search(q_vec, search_k)

        candidates: List[Tuple[ChunkRecord, float]] = []
        for idx_pos, idx in enumerate(indices[0]):
            if idx < 0 or idx >= len(self.chunks):
                continue
            chunk = self.chunks[idx]
            score = float(scores[0][idx_pos])

            if filters:
                match = True
                for k, v in filters.items():
                    if v is not None:
                        if getattr(chunk, k, None) != v and chunk.metadata.get(k) != v:
                            match = False
                            break
                if not match:
                    continue

            candidates.append((chunk, score))
            if len(candidates) >= top_k:
                break

        return candidates

    def delete_chunks(self, chunk_ids: List[str]):
        keep_indices = [i for i, c in enumerate(self.chunks) if c.chunk_id not in chunk_ids]
        if len(keep_indices) == len(self.chunks):
            return
        import faiss
        new_index = faiss.IndexFlatIP(self.dimension)
        if keep_indices:
            all_vecs = np.zeros((len(self.chunks), self.dimension), dtype=np.float32)
            for i in range(len(self.chunks)):
                self.index.reconstruct(i, all_vecs[i])
            keep_vecs = all_vecs[keep_indices]
            new_index.add(keep_vecs)
        self.index = new_index
        self.chunks = [self.chunks[i] for i in keep_indices]
        self.chunk_ids = [self.chunk_ids[i] for i in keep_indices]

    def save(self):
        import faiss
        index_file = self.persist_dir / "faiss.index"
        data_file = self.persist_dir / "faiss_meta.pkl"
        faiss.write_index(self.index, str(index_file))
        with open(data_file, "wb") as f:
            pickle.dump({"chunks": [c.model_dump() for c in self.chunks], "ids": self.chunk_ids}, f)

    @classmethod
    def load(cls, dimension: int = 384, persist_dir: Optional[Path] = None) -> "FAISSVectorIndex":
        import faiss
        pdir = persist_dir or (settings.INDICES_DIR / "faiss")
        index_file = pdir / "faiss.index"
        data_file = pdir / "faiss_meta.pkl"
        
        idx = cls(dimension=dimension, persist_dir=pdir)
        if index_file.exists() and data_file.exists():
            idx.index = faiss.read_index(str(index_file))
            with open(data_file, "rb") as f:
                data = pickle.load(f)
            idx.chunks = [ChunkRecord.model_validate(c) for c in data["chunks"]]
            idx.chunk_ids = data["ids"]
        return idx


def get_vector_index() -> BaseVectorIndex:
    """Factory returning configured vector store instance (qdrant, chroma, or faiss)."""
    if settings.VECTOR_STORE_TYPE == "qdrant":
        return QdrantVectorIndex(dimension=settings.EMBEDDING_DIMENSION)
    elif settings.VECTOR_STORE_TYPE == "faiss":
        return FAISSVectorIndex(dimension=settings.EMBEDDING_DIMENSION)
    else:
        return ChromaVectorIndex()
