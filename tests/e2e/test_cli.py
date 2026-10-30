"""
End-to-end tests for the RFP Intelligence Platform CLI (main.py).
Verifies that all primary user command-line workflows execute cleanly and produce expected outputs.
"""

import subprocess
import sys
import json
from pathlib import Path

PYTHON_EXE = sys.executable
MAIN_SCRIPT = str(Path(__file__).resolve().parent.parent.parent / "main.py")


def test_cli_search():
    """Verify CLI search mode outputs ranked citations and scores."""
    cmd = [PYTHON_EXE, MAIN_SCRIPT, "--search", "bid bond requirement", "--bid", "Bid1", "--top-k", "3"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0
    assert "Search Query:" in result.stdout
    assert "Rank 1:" in result.stdout
    assert "JA-207652" in result.stdout or "bond" in result.stdout.lower()


def test_cli_ask():
    """Verify CLI Q&A mode outputs cited answer and trace file."""
    cmd = [
        PYTHON_EXE, MAIN_SCRIPT,
        "--ask", "What is the final submission deadline for Bid1 after all addendums?",
        "--bid", "Bid1"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0
    assert "ANSWER:" in result.stdout
    assert "July 9, 2024" in result.stdout or "2024-07-09" in result.stdout
    assert "CITATIONS:" in result.stdout
    assert "Trace log saved to:" in result.stdout


def test_cli_compare():
    """Verify CLI side-by-side comparison mode outputs markdown table."""
    cmd = [PYTHON_EXE, MAIN_SCRIPT, "--compare"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0
    assert "BID COMPARISON REPORT" in result.stdout
    assert "Dallas Independent School District" in result.stdout
    assert "State of Maryland" in result.stdout
    assert "Key Differences" in result.stdout
