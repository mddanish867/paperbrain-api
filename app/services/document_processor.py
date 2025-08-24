import PyPDF2
from typing import List, Dict
import uuid
import re
import os

# OCR libs (optional, fail gracefully)
try:
    from pdf2image import convert_from_path
    import pytesseract
    from PIL import Image
    OCR_AVAILABLE = True
except Exception:
    OCR_AVAILABLE = False

class DocumentProcessor:
    def __init__(self):
        self.chunk_size = 1000
        self.chunk_overlap = 200
        # Poppler path (if needed for Windows); read from env to avoid hardcoding
        self.poppler_path = os.getenv("POPPLER_PATH", None)
        # Optional Tesseract cmd path (Windows)
        tesseract_cmd = os.getenv("TESSERACT_CMD", None)
        if tesseract_cmd:
            try:
                pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
            except Exception:
                pass

    def process_pdf(self, file_path: str, filename: str) -> List[Dict]:
        try:
            text = self._extract_text_from_pdf(file_path)

            # If text looks empty/too small, try OCR fallback
            if len(text.strip()) < 50:
                if OCR_AVAILABLE:
                    ocr_text = self._ocr_pdf(file_path)
                    text = ocr_text if ocr_text.strip() else text
                else:
                    # Leave as-is if OCR unavailable; caller handles
                    pass

            if not text.strip():
                raise ValueError("No readable text found in PDF")

            cleaned_text = self._clean_text(text)
            chunks = self._split_text_into_chunks(cleaned_text)

            processed_chunks = []
            for i, chunk in enumerate(chunks):
                processed_chunks.append({
                    "id": str(uuid.uuid4()),
                    "text": chunk,
                    "chunk_index": i,
                    "source": filename,
                    "metadata": {
                        "filename": filename,
                        "chunk_size": len(chunk),
                        "total_chunks": len(chunks)
                    }
                })
            return processed_chunks

        except Exception as e:
            raise Exception(f"Failed to process PDF: {str(e)}")

    def _extract_text_from_pdf(self, file_path: str) -> str:
        text = ""
        with open(file_path, 'rb') as f:
            pdf_reader = PyPDF2.PdfReader(f)
            for page_num, page in enumerate(pdf_reader.pages):
                try:
                    page_text = page.extract_text() or ""
                    if page_text.strip():
                        text += f"\n[Page {page_num + 1}]\n{page_text}\n"
                except Exception:
                    continue
        return text

    def _ocr_pdf(self, file_path: str) -> str:
        """
        Convert pages to images, then OCR with Tesseract.
        Requires: poppler (for pdf2image) and tesseract.
        """
        if not OCR_AVAILABLE:
            return ""
        try:
            pages = convert_from_path(file_path, fmt="png", poppler_path=self.poppler_path)
            ocr_text = []
            for idx, img in enumerate(pages, start=1):
                txt = pytesseract.image_to_string(img)
                if txt.strip():
                    ocr_text.append(f"\n[Page {idx} - OCR]\n{txt}\n")
            return "".join(ocr_text)
        except Exception:
            return ""

    def _clean_text(self, text: str) -> str:
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'[^\w\s.,!?;:()\-"\']', ' ', text)
        text = re.sub(r' +', ' ', text)
        return text.strip()

    def _split_text_into_chunks(self, text: str) -> List[str]:
        if len(text) <= self.chunk_size:
            return [text]
        chunks, start = [], 0
        while start < len(text):
            end = start + self.chunk_size
            if end < len(text):
                sentence_end = max(text.rfind('.', start, end), text.rfind('!', start, end), text.rfind('?', start, end))
                if sentence_end != -1 and sentence_end > start + self.chunk_size // 2:
                    end = sentence_end + 1
                else:
                    word_boundary = text.rfind(' ', start, end)
                    if word_boundary != -1 and word_boundary > start + self.chunk_size // 2:
                        end = word_boundary
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            start = end - self.chunk_overlap
            if start >= len(text):
                break
        return chunks
