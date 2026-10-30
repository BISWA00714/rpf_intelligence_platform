"""
Hybrid RAG Search Engine.
Combines Dense Semantic Search (Qdrant / Chroma) and Lexical BM25 Search
via Reciprocal Rank Fusion (RRF), Query Expansion, and Cross-Encoder Reranking.
"""

import time
import logging
import argparse
from typing import Optional, Dict, Any, Union

from config.settings import settings
from schemas.search import SearchQuery, SearchResult, EvidenceItem
from indexing.embeddings import get_embedding_model, BaseEmbeddingModel
from indexing.vector_index import get_vector_index, BaseVectorIndex
from indexing.bm25_index import BM25Index
from search.query_expander import expand_query
from search.rrf import reciprocal_rank_fusion
from search.reranker import get_reranker, BaseReranker

logger = logging.getLogger("search.engine")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


class RAGSearchEngine:
    """Production-oriented Hybrid RAG Search Engine."""

    def __init__(
        self,
        vector_index: Optional[BaseVectorIndex] = None,
        bm25_index: Optional[BM25Index] = None,
        embedding_model: Optional[BaseEmbeddingModel] = None,
        reranker: Optional[BaseReranker] = None
    ):
        self.embedding_model = embedding_model or get_embedding_model()
        self.vector_index = vector_index or get_vector_index()
        self.bm25_index = bm25_index or BM25Index.load()
        self.reranker = reranker or get_reranker()

    def search(
        self,
        query_input: Union[SearchQuery, str],
        bid_id: Optional[str] = None,
        doc_type: Optional[str] = None,
        addendum_number: Optional[int] = None,
        page_number: Optional[int] = None,
        top_k: int = 5,
        use_reranker: bool = False,
        enable_query_expansion: bool = True
    ) -> SearchResult:
        """
        Executes hybrid retrieval over indexed bid documents.
        
        Args:
            query_input: SearchQuery object or raw question string
            bid_id: Filter by bid ID (e.g. 'Bid1')
            doc_type: Filter by document role ('rfp', 'addendum', 'specs', 'affidavit')
            addendum_number: Filter by addendum number (e.g. 1 or 2)
            page_number: Filter by specific page number
            top_k: Number of ranked evidence passages to return
            use_reranker: Enable cross-encoder neural reranking
            enable_query_expansion: Enable domain synonym expansion
            
        Returns:
            SearchResult with ranked EvidenceItem objects containing source citations.
        """
        t0 = time.time()
        
        # Normalize input to SearchQuery model
        if isinstance(query_input, str):
            sq = SearchQuery(
                query=query_input,
                bid_id=bid_id,
                doc_type=doc_type,
                addendum_number=addendum_number,
                page_number=page_number,
                top_k=top_k,
                use_reranker=use_reranker,
                enable_query_expansion=enable_query_expansion
            )
        else:
            sq = query_input

        clean_query = sq.query.strip()
        if not clean_query:
            return SearchResult(
                query=sq.query,
                total_candidates=0,
                evidence=[],
                is_empty=True,
                execution_time_ms=0.0
            )

        # 1. Query Normalization & Expansion
        dense_q, bm25_q = expand_query(clean_query, enable_expansion=sq.enable_query_expansion)

        # 2. Build Structured Filters
        filters = {}
        if sq.bid_id:
            filters["bid_id"] = sq.bid_id
        if sq.doc_type:
            filters["doc_type"] = sq.doc_type
        if sq.addendum_number is not None:
            filters["addendum_number"] = sq.addendum_number
        if sq.page_number is not None:
            filters["page_number"] = sq.page_number

        # 3. Dense Semantic Vector Search
        candidate_multiplier = 3
        fetch_k = max(sq.top_k * candidate_multiplier, 10)
        
        dense_results = []
        try:
            q_emb = self.embedding_model.embed_query(dense_q)
            dense_results = self.vector_index.search(q_emb, top_k=fetch_k, filters=filters)
        except Exception as e:
            logger.error(f"Dense vector retrieval failed: {e}")

        # 4. Lexical BM25 Keyword Search
        bm25_results = []
        try:
            bm25_results = self.bm25_index.search(bm25_q, top_k=fetch_k, filters=filters)
        except Exception as e:
            logger.error(f"BM25 lexical retrieval failed: {e}")

        total_candidates = len(set([c[0].chunk_id for c in dense_results] + [c[0].chunk_id for c in bm25_results]))

        # 5. Reciprocal Rank Fusion (RRF)
        fused_evidence = reciprocal_rank_fusion(
            dense_results=dense_results,
            bm25_results=bm25_results,
            k=settings.RRF_K,
            dense_weight=settings.HYBRID_DENSE_WEIGHT,
            bm25_weight=settings.HYBRID_BM25_WEIGHT,
            top_k=fetch_k
        )

        # 6. Optional Cross-Encoder Reranking
        if sq.use_reranker:
            reranker_engine = get_reranker(enable_reranker=True)
            final_evidence = reranker_engine.rerank(clean_query, fused_evidence, top_k=sq.top_k)
        else:
            final_evidence = fused_evidence[:sq.top_k]

        # 7. Quality Gate: check if evidence meets minimum relevance threshold
        is_empty = False
        if not final_evidence or (final_evidence and final_evidence[0].score < 0.05):
            is_empty = True

        elapsed_ms = round((time.time() - t0) * 1000.0, 2)

        return SearchResult(
            query=clean_query,
            expanded_query=bm25_q if sq.enable_query_expansion else None,
            total_candidates=total_candidates,
            evidence=final_evidence,
            is_empty=is_empty,
            execution_time_ms=elapsed_ms
        )


def cli_main():
    """CLI runner for standalone hybrid retrieval queries."""
    parser = argparse.ArgumentParser(description="Standalone Hybrid RAG Search Engine.")
    parser.add_argument("--query", "-q", type=str, required=True, help="Question or search query")
    parser.add_argument("--bid", type=str, default=None, help="Target bid folder (e.g. Bid1, Bid2)")
    parser.add_argument("--doc-type", type=str, default=None, help="Document type filter (addendum, rfp, specs, affidavit)")
    parser.add_argument("--top-k", "-k", type=int, default=5, help="Number of evidence items to return")
    parser.add_argument("--rerank", action="store_true", help="Enable neural cross-encoder reranking")
    parser.add_argument("--no-expansion", action="store_true", help="Disable query expansion")
    args = parser.parse_args()

    engine = RAGSearchEngine()
    result = engine.search(
        query_input=args.query,
        bid_id=args.bid,
        doc_type=args.doc_type,
        top_k=args.top_k,
        use_reranker=args.rerank,
        enable_query_expansion=not args.no_expansion
    )

    print(f"\n==================== SEARCH RESULT ({result.execution_time_ms} ms) ====================")
    print(f"Query: {result.query}")
    if result.expanded_query:
        print(f"Expanded: {result.expanded_query}")
    print(f"Total Candidates: {result.total_candidates} | Top Results: {len(result.evidence)}")
    print("======================================================================\n")

    if result.is_empty or not result.evidence:
        print(">> No relevant evidence found matching the query.\n")
        return

    for idx, ev in enumerate(result.evidence, 1):
        print(f"[{idx}] Citation: {ev.citation} | Score: {ev.score} | Chunk: {ev.chunk_id}")
        if ev.section_title:
            print(f"    Section: {ev.section_title}")
        print(f"    Ranks: Dense={ev.dense_rank}, BM25={ev.bm25_rank}")
        lines = ev.text.splitlines()[:5]
        preview = "\n    ".join(lines)
        print(f"    Passage Preview:\n    {preview}\n")


if __name__ == "__main__":
    cli_main()
