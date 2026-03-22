"""Document text extraction — supports TXT, MD, PDF, DOCX."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class UnsupportedFormatError(Exception):
    """Raised when a file format is not supported."""

    def __init__(self, extension: str) -> None:
        self.extension = extension
        super().__init__(
            f"Unsupported file format: '{extension}'. "
            f"Supported: .txt, .md, .pdf, .docx"
        )


def parse_document(filename: str, content: bytes) -> str:
    """Extract text content from a document file.

    Args:
        filename: Original filename (used to detect format).
        content: Raw file bytes.

    Returns:
        Extracted text content.

    Raises:
        UnsupportedFormatError: If the file format is not supported.
    """
    ext = Path(filename).suffix.lower()

    if ext in (".txt", ".md", ".markdown"):
        return _parse_text(content)
    elif ext == ".pdf":
        return _parse_pdf(content)
    elif ext == ".docx":
        return _parse_docx(content)
    else:
        raise UnsupportedFormatError(ext)


def _parse_text(content: bytes) -> str:
    """Decode text/markdown files."""
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def _parse_pdf(content: bytes) -> str:
    """Extract text from PDF using pdfplumber."""
    import io

    import pdfplumber

    text_parts = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)

    return "\n\n".join(text_parts)


def _parse_docx(content: bytes) -> str:
    """Extract text from DOCX using python-docx."""
    import io

    import docx

    doc = docx.Document(io.BytesIO(content))
    text_parts = []
    for para in doc.paragraphs:
        if para.text.strip():
            text_parts.append(para.text)

    return "\n\n".join(text_parts)
