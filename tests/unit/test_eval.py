"""
Unit test for retrieval evaluation dataset schema and benchmark pipeline.
"""

import json
from pathlib import Path
from config.settings import settings


def test_evaluation_dataset_completeness():
    dataset_file = settings.BASE_DIR / "eval" / "evaluation_dataset.json"
    assert dataset_file.exists()
    
    with open(dataset_file, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    assert "cases" in data
    cases = data["cases"]
    assert len(cases) >= 15  # Requirement: at least 15 cases
    
    # Check coverage of both bids
    bid_ids = {c["bid_id"] for c in cases}
    assert "Bid1" in bid_ids
    assert "Bid2" in bid_ids
    
    # Check schema of each case
    for case in cases:
        assert "case_id" in case
        assert "question" in case
        assert "category" in case
        assert "expected_chunk_ids" in case
        assert "expected_keywords" in case
        assert "relevance_notes" in case


def test_benchmark_results_exist_and_valid():
    results_file = settings.DATA_DIR / "evaluation_results.json"
    assert results_file.exists()
    
    with open(results_file, "r", encoding="utf-8") as f:
        res = json.load(f)
        
    assert "summary" in res
    summary = res["summary"]
    assert "dense_only" in summary
    assert "bm25_only" in summary
    assert "hybrid_rrf" in summary
    assert summary["hybrid_rrf"]["Recall@5"] >= 0.90
