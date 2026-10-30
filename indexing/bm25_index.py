"""
BM25 Lexical Keyword Index.
Implements exact term matching for technical SKUs, model numbers, part IDs, dates, and names.
Includes self-contained BM25Okapi implementation to guarantee zero external dependency failures.
"""

import re
import math
import pickle
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from collections import Counter

from schemas.chunks import ChunkRecord
from config.settings import settings

logger = logging.getLogger(__name__)


def tokenize_text(text: str) -> List[str]:
    """
    Procurement-specific tokenizer.
    Preserves exact technical identifiers (e.g. JA-207652, 210-BLYZ, WD22TB4, 07/09/2024, #E20P4600040)
    while normalizing standard words.
    """
    if not text:
        return []
    tokens = re.findall(r'[a-zA-Z0-9]+(?:[-_/.#][a-zA-Z0-9]+)*', text.lower())
    return tokens


class BM25OkapiEngine:
    """
    Self-contained, optimized implementation of BM25Okapi.
    Implements standard Okapi BM25 formula with idf smoothing:
    IDF = ln((N - n + 0.5) / (n + 0.5) + 1)
    """

    def __init__(self, corpus: List[List[str]], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.corpus_size = len(corpus)
        self.avgdl = sum(len(doc) for doc in corpus) / max(1, self.corpus_size)
        self.doc_freqs: Dict[str, int] = Counter()
        self.doc_len: List[int] = []
        self.doc_term_freqs: List[Dict[str, int]] = []
        self.idf: Dict[str, float] = {}

        for doc in corpus:
            self.doc_len.append(len(doc))
            frequencies = Counter(doc)
            self.doc_term_freqs.append(frequencies)
            for word in frequencies.keys():
                self.doc_freqs[word] += 1

        for word, freq in self.doc_freqs.items():
            # Okapi BM25 IDF formulation
            self.idf[word] = math.log((self.corpus_size - freq + 0.5) / (freq + 0.5) + 1.0)

    def get_scores(self, query: List[str]) -> List[float]:
        """Calculates BM25 scores for all documents in the corpus for the query tokens."""
        scores = [0.0] * self.corpus_size
        doc_len = self.doc_len
        avgdl = self.avgdl
        k1 = self.k1
        b = self.b

        for q in query:
            if q not in self.idf:
                continue
            q_idf = self.idf[q]
            for doc_idx, freqs in enumerate(self.doc_term_freqs):
                tf = freqs.get(q, 0)
                if tf > 0:
                    numerator = tf * (k1 + 1.0)
                    denominator = tf + k1 * (1.0 - b + b * (doc_len[doc_idx] / avgdl))
                    scores[doc_idx] += q_idf * (numerator / denominator)

        return scores


class BM25Index:
    """Persistent BM25 lexical index with metadata filtering."""

    def __init__(self):
        self.chunks: List[ChunkRecord] = []
        self.chunk_ids: List[str] = []
        self.tokenized_corpus: List[List[str]] = []
        self.engine: Optional[BM25OkapiEngine] = None

    def build_index(self, chunks: List[ChunkRecord]):
        """Builds index from list of chunks."""
        self.chunks = list(chunks)
        self.chunk_ids = [c.chunk_id for c in self.chunks]
        self.tokenized_corpus = [tokenize_text(c.text) for c in self.chunks]
        if self.tokenized_corpus:
            self.engine = BM25OkapiEngine(self.tokenized_corpus)
        else:
            self.engine = None
        logger.info(f"Built BM25 index with {len(self.chunks)} chunks.")

    def search(
        self,
        query: str,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Tuple[ChunkRecord, float]]:
        """
        Executes BM25 keyword search with metadata pre-filtering.
        
        Args:
            query: Query string
            top_k: Number of candidates to return
            filters: Dict of metadata filters (e.g. {"bid_id": "Bid1", "doc_type": "addendum"})
            
        Returns:
            List of (ChunkRecord, bm25_score) tuples sorted descending.
        """
        if not self.engine or not self.chunks:
            return []

        tokenized_query = tokenize_text(query)
        if not tokenized_query:
            return []

        raw_scores = self.engine.get_scores(tokenized_query)
        
        candidates: List[Tuple[ChunkRecord, float]] = []
        for idx, score in enumerate(raw_scores):
            if score <= 0.0:
                continue
            chunk = self.chunks[idx]
            
            # Apply metadata filters
            if filters:
                match = True
                for k, v in filters.items():
                    if v is None:
                        continue
                    if k == "bid_id" and chunk.bid_id != v:
                        match = False
                        break
                    elif k == "doc_type" and chunk.doc_type != v:
                        match = False
                        break
                    elif k == "addendum_number" and chunk.addendum_number != v:
                        match = False
                        break
                    elif k == "page_number" and chunk.page_number != v:
                        match = False
                        break
                if not match:
                    continue
                    
            candidates.append((chunk, float(score)))

        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[:top_k]

    def save(self, filepath: Optional[Path] = None):
        """Persists BM25 index to disk."""
        path = filepath or (settings.INDICES_DIR / "bm25_index.pkl")
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump({
                "chunks": [c.model_dump() for c in self.chunks],
                "chunk_ids": self.chunk_ids,
                "tokenized_corpus": self.tokenized_corpus
            }, f)
        logger.info(f"Persisted BM25 index to {path}")

    @classmethod
    def load(cls, filepath: Optional[Path] = None) -> "BM25Index":
        """Loads BM25 index from disk."""
        path = filepath or (settings.INDICES_DIR / "bm25_index.pkl")
        if not path.exists():
            logger.warning(f"No existing BM25 index found at {path}")
            return cls()
            
        with open(path, "rb") as f:
            data = pickle.load(f)
            
        index = cls()
        index.chunks = [ChunkRecord.model_validate(c) for c in data["chunks"]]
        index.chunk_ids = data["chunk_ids"]
        index.tokenized_corpus = data["tokenized_corpus"]
        if index.tokenized_corpus:
            index.engine = BM25OkapiEngine(index.tokenized_corpus)
        logger.info(f"Loaded BM25 index with {len(index.chunks)} chunks from {path}")
        return index
