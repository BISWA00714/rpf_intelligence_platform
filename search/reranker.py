"""
Cross-Encoder Neural Reranker abstraction and implementations.
Scores query-evidence candidate pairs for high-precision semantic re-ordering.
"""

import abc
import logging
from typing import List
from schemas.search import EvidenceItem
from config.settings import settings

logger = logging.getLogger(__name__)


class BaseReranker(abc.ABC):
    """Abstract interface for candidate passage rerankers."""

    @abc.abstractmethod
    def rerank(self, query: str, items: List[EvidenceItem], top_k: int = 5) -> List[EvidenceItem]:
        pass


class NoOpReranker(BaseReranker):
    """Pass-through reranker when neural reranking is disabled."""

    def rerank(self, query: str, items: List[EvidenceItem], top_k: int = 5) -> List[EvidenceItem]:
        return items[:top_k]


class CrossEncoderReranker(BaseReranker):
    """Cross-encoder neural reranker using ms-marco-MiniLM-L-6-v2."""

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        self.model_name = model_name
        self._model = None

    def _get_model(self):
        if self._model is None:
            try:
                from sentence_transformers import CrossEncoder
                logger.info(f"Loading CrossEncoder reranker: {self.model_name}")
                self._model = CrossEncoder(self.model_name)
            except Exception as e:
                logger.warning(f"Could not initialize CrossEncoder ({e}). Falling back to NoOp.")
                self._model = False
        return self._model

    def rerank(self, query: str, items: List[EvidenceItem], top_k: int = 5) -> List[EvidenceItem]:
        if not items:
            return []

        model = self._get_model()
        if not model:
            return items[:top_k]

        pairs = [[query, it.text] for it in items]
        try:
            scores = model.predict(pairs)
            # Pair items with scores
            scored_items = []
            for item, score in zip(items, scores):
                # Sigmoid normalization: 1 / (1 + exp(-score))
                import math
                prob = 1.0 / (1.0 + math.exp(-float(score)))
                item_copy = item.model_copy()
                item_copy.score = round(prob, 4)
                scored_items.append(item_copy)

            scored_items.sort(key=lambda x: x.score, reverse=True)
            return scored_items[:top_k]
        except Exception as e:
            logger.error(f"Error during neural reranking: {e}")
            return items[:top_k]


def get_reranker(enable_reranker: bool = False) -> BaseReranker:
    """Factory returning configured reranker instance."""
    if enable_reranker or settings.RERANKER_ENABLED:
        return CrossEncoderReranker(model_name=settings.RERANKER_MODEL)
    return NoOpReranker()
