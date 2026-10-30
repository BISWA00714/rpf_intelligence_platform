"""
Main CLI entry point for RFP Intelligence Platform.
Supports:
1. Bid Extraction: Ingestion, Multi-Agent extraction, addendum reconciliation, and JSON export.
2. Natural-Language Q&A: Cited question-answering grounded in retrieved evidence.
3. Bid Comparison: Side-by-side comparative analysis of multiple bids.
4. Indexing: Re-indexing and index rebuilds.
5. Evaluation: Automated retrieval benchmark execution.
"""

import sys
import json
import argparse
import logging
from pathlib import Path

from config.settings import settings
from agents.orchestrator import MultiAgentOrchestrator
from eval.evaluate_retrieval import run_benchmark
from indexing.index_manager import IndexManager
from ingestion.pipeline import run_ingestion_pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("main")


def main():
    parser = argparse.ArgumentParser(description="RFP Intelligence Platform - Multi-Agent & RAG System.")
    parser.add_argument("--bid", type=str, default=None, help="Target bid identifier or directory path (e.g. Bid1, ./Bid1)")
    parser.add_argument("--all", action="store_true", help="Process and extract all bids in data/raw")
    parser.add_argument("--ask", type=str, default=None, help="Ask a natural-language question over the indexed bids")
    parser.add_argument("--search", type=str, default=None, help="Execute hybrid search (BM25 + Dense Qdrant)")
    parser.add_argument("--top-k", type=int, default=5, help="Number of search results to return")
    parser.add_argument("--compare", action="store_true", help="Generate side-by-side comparison report for Bid1 and Bid2")
    parser.add_argument("--index", action="store_true", help="Run ingestion and indexing pipeline")
    parser.add_argument("--rebuild", action="store_true", help="Force rebuild of indices from scratch")
    parser.add_argument("--benchmark", action="store_true", help="Run automated retrieval evaluation benchmark")
    args = parser.parse_args()

    # Mode 1: Benchmark Evaluation
    if args.benchmark:
        print("\n=== Running Retrieval Benchmark Evaluation ===")
        res = run_benchmark()
        print((settings.BASE_DIR / "eval" / "retrieval_benchmark.md").read_text(encoding="utf-8"))
        return

    # Mode 2: Ingestion & Indexing
    if args.index:
        print("\n=== Running Ingestion and Indexing ===")
        run_ingestion_pipeline()
        im = IndexManager()
        im.index_all(rebuild=args.rebuild)
        print("Indexing completed successfully.")
        return

    orchestrator = MultiAgentOrchestrator()

    # Mode 3: Hybrid Search
    if args.search:
        bid_filter = args.bid if args.bid in ["Bid1", "Bid2"] else None
        print(f"\n==================== HYBRID SEARCH ====================")
        print(f"Search Query: {args.search}")
        if bid_filter:
            print(f"Bid Filter: {bid_filter}")
        print("=======================================================\n")
        
        search_res = orchestrator.search_engine.search(
            query_input=args.search,
            bid_id=bid_filter,
            top_k=args.top_k
        )
        for idx, item in enumerate(search_res.evidence):
            print(f"Rank {idx+1}: {item.file_name} (Page {item.page_number}) | Score: {item.score:.4f}")
            print(f"  Excerpt: {item.text[:120]}...\n")
        return

    # Mode 4: Natural Language Q&A
    if args.ask:
        bid_filter = args.bid if args.bid in ["Bid1", "Bid2"] else None
        print(f"\n==================== CITED Q&A ====================")
        print(f"Question: {args.ask}")
        if bid_filter:
            print(f"Bid Filter: {bid_filter}")
        print("===================================================\n")
        
        qa_res = orchestrator.answer_question(args.ask, bid_id=bid_filter)
        print("ANSWER:")
        print(qa_res["answer"])
        print("\nCITATIONS:")
        for c in qa_res.get("citations", []):
            print(f"- {c}")
        print(f"\nTrace log saved to: {qa_res.get('trace_file')}")
        print(f"Trace ID: {qa_res['run_id']}")
        return

    # Mode 4: Bid Comparison
    if args.compare:
        print("\n==================== BID COMPARISON REPORT ====================")
        b1_file = settings.PROCESSED_DIR / "Bid1_extracted.json"
        b2_file = settings.PROCESSED_DIR / "Bid2_extracted.json"
        
        # Ensure extractions exist
        if not b1_file.exists():
            out1 = orchestrator.extract_bid("Bid1")
            with open(b1_file, "w", encoding="utf-8") as f:
                f.write(out1.model_dump_json(indent=2))
        if not b2_file.exists():
            out2 = orchestrator.extract_bid("Bid2")
            with open(b2_file, "w", encoding="utf-8") as f:
                f.write(out2.model_dump_json(indent=2))

        b1_data = json.loads(b1_file.read_text(encoding="utf-8"))
        b2_data = json.loads(b2_file.read_text(encoding="utf-8"))

        report = orchestrator.qa_agent.compare_bids(b1_data, b2_data)
        print(report)
        return

    # Mode 5: Structured Extraction (Single Bid or All)
    target_bids = []
    if args.bid:
        # Handle path like ./Bid1 or Bid1
        b_name = Path(args.bid).name
        target_bids.append(b_name)
    elif args.all or len(sys.argv) == 1:
        target_bids = ["Bid1", "Bid2"]

    for bid_id in target_bids:
        print(f"\n=======================================================")
        print(f"   STARTING MULTI-AGENT EXTRACTION FOR {bid_id}")
        print(f"=======================================================\n")
        
        output = orchestrator.extract_bid(bid_id)
        
        # Save output JSON file per bid
        out_path = settings.DATA_DIR / f"{bid_id}_extracted.json"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(output.model_dump_json(indent=2))
            
        print(f"\nExtraction complete for {bid_id}!")
        print(f"Saved JSON artifact to: {out_path}")
        print(f"Validation: Passed={output.validation.passed}, Failed={output.validation.failed}, Not Found={output.validation.not_found}")
        print(f"Addendum Changes Logged: {len(output.addendum_changes)}")


if __name__ == "__main__":
    main()
