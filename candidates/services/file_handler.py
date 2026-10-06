import os
import fitz  # PyMuPDF
from docx import Document


def extract_text(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    if ext == '.pdf':
        return _extract_pdf(file_path)
    elif ext in ('.docx', '.doc'):
        return _extract_docx(file_path)
    else:
        raise ValueError(f"Unsupported file type: {ext}")


def _extract_pdf(file_path: str) -> str:
    text_parts = []
    with fitz.open(file_path) as doc:
        for page in doc:
            text_parts.append(page.get_text())
    return '\n'.join(text_parts)


def _extract_docx(file_path: str) -> str:
    doc = Document(file_path)
    return '\n'.join(para.text for para in doc.paragraphs)
