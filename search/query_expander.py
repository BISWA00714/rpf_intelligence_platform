"""
Procurement domain query expander and normalizer.
Expands RFP terminology while strictly preserving exact technical identifiers, SKUs, and dates.
"""

import re
from typing import Tuple, List

# Common RFP procurement domain synonyms
PROCUREMENT_SYNONYMS = {
    "deadline": "due date submission deadline closing date proposal due",
    "due date": "deadline submission deadline closing date proposal due date and time",
    "bond": "bid bond proposal bond bid security surety bonding requirement",
    "affidavit": "affidavit certification disclosure compliance form legal document",
    "warranty": "extended warranty manufacturer warranty hardware warranty service agreement repair replacement",
    "specs": "product specifications technical requirements cpu ram storage memory processor",
    "specification": "technical requirements product specifications cpu ram storage display",
    "contact": "procurement contact buyer officer email phone point of contact poc",
    "cooperative": "cooperative contract vehicle piggyback state contract purchasing alliance",
    "installation": "installation deployment imaging white glove setup configuration",
    "submission": "submission instructions electronic portal e-procurement sealed bid delivery",
    "payment": "payment terms net 30 invoicing billing prompt payment"
}

TECHNICAL_CODE_PATTERN = re.compile(
    r'\b(?:[A-Za-z0-9]+(?:[-_/.#][A-Za-z0-9]+)+|[A-Za-z]+[0-9]+[A-Za-z0-9]*|[0-9]+[A-Za-z]+[A-Za-z0-9]*)\b'
)


def extract_exact_identifiers(query: str) -> List[str]:
    """Finds exact alphanumeric technical codes (e.g. JA-207652, 210-BLYZ, WD22TB4, #E20P4600040)."""
    return TECHNICAL_CODE_PATTERN.findall(query)


def expand_query(query: str, enable_expansion: bool = True) -> Tuple[str, str]:
    """
    Normalizes and expands a procurement query.
    
    Returns:
        (dense_query, bm25_expanded_query)
    """
    clean_query = query.strip()
    if not enable_expansion:
        return clean_query, clean_query

    exact_ids = extract_exact_identifiers(clean_query)
    q_lower = clean_query.lower()
    
    synonyms_to_add = []
    for trigger, expansion in PROCUREMENT_SYNONYMS.items():
        if trigger in q_lower:
            synonyms_to_add.append(expansion)

    # For BM25, boost exact IDs by repeating them and append domain synonyms
    bm25_parts = [clean_query]
    if exact_ids:
        # Prepend exact identifiers to maximize lexical term frequency
        bm25_parts.insert(0, " ".join(exact_ids))
    if synonyms_to_add:
        bm25_parts.append(" ".join(synonyms_to_add))

    bm25_query = " ".join(bm25_parts)
    dense_query = clean_query  # Keep dense query focused for semantic embedding

    return dense_query, bm25_query
