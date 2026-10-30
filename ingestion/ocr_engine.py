"""
OCR Fallback Engine for scanned or image-only PDF pages.
Uses EasyOCR with lazy loading and graceful degradation.
"""

import logging
from typing import Optional
import numpy as np

logger = logging.getLogger(__name__)

_ocr_reader = None


def get_ocr_reader():
    """Lazy loader for EasyOCR reader to save memory and avoid startup delay."""
    global _ocr_reader
    if _ocr_reader is None:
        try:
            import easyocr
            logger.info("Initializing EasyOCR reader (CPU mode)...")
            _ocr_reader = easyocr.Reader(['en'], gpu=False, verbose=False)
        except Exception as e:
            logger.warning(f"EasyOCR reader could not be initialized: {e}")
            _ocr_reader = None
    return _ocr_reader


def ocr_page_pixmap(pixmap) -> str:
    """
    Extracts text from a PyMuPDF pixmap object.
    
    Args:
        pixmap: fitz.Pixmap
        
    Returns:
        Extracted text string from OCR.
    """
    reader = get_ocr_reader()
    if reader is None:
        logger.warning("OCR requested but reader is not available.")
        return ""
    
    try:
        # Convert fitz pixmap to numpy RGB image
        img_array = np.frombuffer(pixmap.samples, dtype=np.uint8)
        if pixmap.alpha:
            img_array = img_array.reshape((pixmap.height, pixmap.width, 4))
            img_array = img_array[:, :, :3]
        else:
            img_array = img_array.reshape((pixmap.height, pixmap.width, pixmap.n))
            
        # Run OCR
        results = reader.readtext(img_array)
        extracted_lines = [res[1] for res in results if res[1].strip()]
        return "\n".join(extracted_lines)
    except Exception as e:
        logger.error(f"Error executing OCR on page pixmap: {e}")
        return ""
