"""
Text normalization utilities for RFP and bid documents.
Cleans whitespace, broken line breaks, and repeated headers/footers while preserving technical IDs, SKUs, and dates.
"""

import re
from typing import List


def normalize_whitespace(text: str) -> str:
    """Normalizes excessive whitespace and tabs without crushing newline structure."""
    if not text:
        return ""
    # Standardize unicode quotes and hyphens
    text = text.replace('\u2018', "'").replace('\u2019', "'")
    text = text.replace('\u201c', '"').replace('\u201d', '"')
    text = text.replace('\u2013', '-').replace('\u2014', '-')
    text = text.replace('\ufffd', "'")  # Fix broken unicode apostrophe from PDFs
    
    # Replace non-breaking spaces
    text = text.replace('\xa0', ' ')
    
    # Replace multiple horizontal spaces/tabs with single space
    lines = text.splitlines()
    cleaned_lines = [re.sub(r'[ \t]+', ' ', line).strip() for line in lines]
    
    # Collapse 3+ consecutive newlines to 2 newlines
    result = '\n'.join(cleaned_lines)
    result = re.sub(r'\n{3,}', '\n\n', result)
    return result.strip()


def fix_broken_hyphenations(text: str) -> str:
    """
    Rejoins words split by line break hyphenation (e.g. 'solicita-\\ntion' -> 'solicitation').
    Preserves exact part numbers, model numbers, and technical identifiers (e.g. 'JA-207652', '210-BLYZ').
    """
    if not text:
        return ""
    # Only rejoin alphabetical words where hyphen is immediately followed by newline and next word
    # e.g., 'agree-\n  ment' -> 'agreement'
    pattern = re.compile(r'(\b[a-zA-Z]{2,})-\s*\n\s*([a-zA-Z]{2,}\b)')
    return pattern.sub(r'\1\2', text)


def clean_pdf_headers_footers(page_text: str, page_number: int, total_pages: int) -> str:
    """
    Removes common repeated running headers/footers such as 'Page X of Y' or 'Dallas ISD rev X.X'
    from the text stream without removing substantive clause text.
    """
    if not page_text:
        return ""
    
    lines = page_text.splitlines()
    filtered_lines = []
    
    header_footer_patterns = [
        re.compile(r'^Page\s+\d+\s+(?:of|\|)\s+\d+$', re.IGNORECASE),
        re.compile(r'^\d+\s+of\s+\d+$', re.IGNORECASE),
        re.compile(r'^Dallas ISD rev\s+\d+\.\d+$', re.IGNORECASE),
        re.compile(r'^Dell Marketing LP\. U\.S\. only\..*Round Rock, TX.*$', re.IGNORECASE)
    ]
    
    for line in lines:
        stripped = line.strip()
        if any(pat.match(stripped) for pat in header_footer_patterns):
            continue
        filtered_lines.append(line)
        
    return '\n'.join(filtered_lines)


def normalize_page_text(raw_text: str, page_number: int, total_pages: int) -> str:
    """Full normalization pipeline for a single extracted page."""
    text = clean_pdf_headers_footers(raw_text, page_number, total_pages)
    text = fix_broken_hyphenations(text)
    text = normalize_whitespace(text)
    return text
