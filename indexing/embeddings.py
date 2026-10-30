"""
Embedding models abstraction and implementations.
Provides SentenceTransformer embedding with batching, offline-cache optimization,
and a deterministic Mock model for unit testing.
"""

import os
import abc
import hashlib
import logging
from typing import List
import numpy as np

# Enforce offline mode for cached models in sandboxed / production environments
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

from config.settings import settings

logger = logging.getLogger(__name__)


class BaseEmbeddingModel(abc.ABC):
    """Abstract base class for text embedding models."""

    @abc.abstractmethod
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embeds a list of document strings."""
        pass

    @abc.abstractmethod
    def embed_query(self, text: str) -> List[float]:
        """Embeds a single query string."""
        pass

    @property
    @abc.abstractmethod
    def dimension(self) -> int:
        """Returns embedding vector dimensionality."""
        pass


class SentenceTransformerEmbeddings(BaseEmbeddingModel):
    """Local SentenceTransformer embedding model with offline cache loading."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer
        logger.info(f"Loading SentenceTransformer: {model_name} (offline mode)")
        self.model = SentenceTransformer(model_name)
        self._dim = self.model.get_sentence_embedding_dimension()

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        embeddings = self.model.encode(texts, batch_size=32, show_progress_bar=False, normalize_embeddings=True)
        return embeddings.tolist()

    def embed_query(self, text: str) -> List[float]:
        embedding = self.model.encode(text, normalize_embeddings=True)
        return embedding.tolist()

    @property
    def dimension(self) -> int:
        return self._dim


class MockEmbeddingModel(BaseEmbeddingModel):
    """Deterministic mock embedding model for rapid testing without GPU/CPU heavy weights."""

    def __init__(self, dimension: int = 384):
        self._dim = dimension

    def _hash_vector(self, text: str) -> List[float]:
        h = hashlib.sha256(text.encode('utf-8')).digest()
        seed = int.from_bytes(h[:4], 'big')
        rng = np.random.RandomState(seed)
        vec = rng.randn(self._dim).astype(np.float32)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec.tolist()

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self._hash_vector(t) for t in texts]

    def embed_query(self, text: str) -> List[float]:
        return self._hash_vector(text)

    @property
    def dimension(self) -> int:
        return self._dim


_embedding_instance: BaseEmbeddingModel = None


def get_embedding_model(force_mock: bool = False) -> BaseEmbeddingModel:
    """Returns singleton configured embedding model."""
    global _embedding_instance
    if _embedding_instance is None or force_mock:
        if force_mock or settings.EMBEDDING_PROVIDER == "mock":
            _embedding_instance = MockEmbeddingModel(dimension=settings.EMBEDDING_DIMENSION)
        else:
            try:
                _embedding_instance = SentenceTransformerEmbeddings(model_name=settings.EMBEDDING_MODEL)
            except Exception as e:
                logger.warning(f"Could not load SentenceTransformer ({e}). Falling back to MockEmbeddingModel.")
                _embedding_instance = MockEmbeddingModel(dimension=settings.EMBEDDING_DIMENSION)
    return _embedding_instance
