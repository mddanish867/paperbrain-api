import PyPDF2
from typing import List, Dict
import uuid
import re
import os
from app.utils.logger import logger

# Try to import OCR libraries (optional)
try:
    from pdf2image import convert_from_path
    import pytesseract
    from PIL import Image
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False
    logger.warning("OCR libraries not available. PDF text extraction will be limited to native PDF text.")

class DocumentProcessor:
    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        
        # OCR configuration
        self.poppler_path = os.getenv("POPPLER_PATH", None)
        tesseract_cmd = os.getenv("TESSERACT_CMD", None)
        if tesseract_cmd and OCR_AVAILABLE:
            try:
                pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
            except Exception as e:
                logger.warning(f"Failed to set tesseract command: {e}")

    def process_pdf(self, file_path: str, filename: str) -> List[Dict]:
        """Process a PDF file and return chunks of text with metadata"""
        try:
            logger.info(f"Processing PDF: {filename}")
            
            # Extract text from PDF
            text = self._extract_text_from_pdf(file_path)
            
            # If text extraction yields little content, try OCR as fallback
            if len(text.strip()) < 100 and OCR_AVAILABLE:  # Threshold for OCR fallback
                logger.info(f"Low text content, attempting OCR for: {filename}")
                ocr_text = self._ocr_pdf(file_path)
                if ocr_text and len(ocr_text.strip()) > len(text.strip()):
                    text = ocr_text
                    logger.info(f"OCR extracted additional text: {len(text)} characters")
            
            if not text.strip():
                raise ValueError("No readable text found in PDF")
            
            # Clean and chunk the text
            cleaned_text = self._clean_text(text)
            chunks = self._split_text_into_chunks(cleaned_text)
            
            # Prepare chunks with metadata
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
            
            logger.info(f"Processed {filename} into {len(chunks)} chunks")
            return processed_chunks
            
        except Exception as e:
            logger.error(f"Failed to process PDF {filename}: {str(e)}")
            raise Exception(f"Failed to process PDF: {str(e)}")

    def _extract_text_from_pdf(self, file_path: str) -> str:
        """Extract text from PDF using PyPDF2"""
        text = ""
        try:
            with open(file_path, 'rb') as f:
                pdf_reader = PyPDF2.PdfReader(f)
                
                for page_num, page in enumerate(pdf_reader.pages):
                    try:
                        page_text = page.extract_text() or ""
                        if page_text.strip():
                            text += f"\n[Page {page_num + 1}]\n{page_text}\n"
                    except Exception as e:
                        logger.warning(f"Error extracting text from page {page_num + 1}: {e}")
                        continue
        except Exception as e:
            logger.error(f"Error reading PDF file: {e}")
            raise
        
        return text

    def _ocr_pdf(self, file_path: str) -> str:
        """Extract text from PDF using OCR (fallback for scanned PDFs)"""
        if not OCR_AVAILABLE:
            return ""
        
        try:
            logger.info(f"Performing OCR on: {file_path}")
            pages = convert_from_path(file_path, fmt="png", poppler_path=self.poppler_path)
            ocr_text = []
            
            for idx, img in enumerate(pages, start=1):
                try:
                    txt = pytesseract.image_to_string(img)
                    if txt.strip():
                        ocr_text.append(f"\n[Page {idx} - OCR]\n{txt}\n")
                except Exception as e:
                    logger.warning(f"OCR failed for page {idx}: {e}")
                    continue
            
            return "".join(ocr_text)
        except Exception as e:
            logger.error(f"OCR processing failed: {e}")
            return ""

    def _clean_text(self, text: str) -> str:
        """Clean and normalize extracted text"""
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Remove non-printable characters (keep letters, numbers, punctuation, and basic symbols)
        text = re.sub(r'[^\w\s.,!?;:()\-"\'\n]', ' ', text)
        
        # Normalize whitespace again
        text = re.sub(r' +', ' ', text)
        
        return text.strip()

    def _split_text_into_chunks(self, text: str) -> List[str]:
        """Split text into overlapping chunks with semantic boundaries"""
        if len(text) <= self.chunk_size:
            return [text]
        
        chunks = []
        start = 0
        
        while start < len(text):
            # Determine chunk end position
            end = start + self.chunk_size
            
            if end >= len(text):
                # Reached end of text
                chunk = text[start:].strip()
                if chunk:
                    chunks.append(chunk)
                break
            
            # Try to find a good breaking point (sentence end)
            sentence_end = max(
                text.rfind('.', start, end),
                text.rfind('!', start, end),
                text.rfind('?', start, end),
                text.rfind('\n', start, end)
            )
            
            if sentence_end != -1 and sentence_end > start + (self.chunk_size // 2):
                # Break at sentence end
                end = sentence_end + 1
            else:
                # Break at word boundary
                word_boundary = text.rfind(' ', start, end)
                if word_boundary != -1 and word_boundary > start + (self.chunk_size // 2):
                    end = word_boundary
            
            # Extract chunk
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            
            # Move start position, considering overlap
            start = end - self.chunk_overlap
            if start < 0:
                start = 0
        
        return chunks

    def get_document_stats(self, file_path: str) -> Dict:
        """Get statistics about a document without full processing"""
        try:
            with open(file_path, 'rb') as f:
                pdf_reader = PyPDF2.PdfReader(f)
                page_count = len(pdf_reader.pages)
                
                # Extract a sample of text to estimate content
                sample_text = ""
                for i in range(min(3, page_count)):
                    try:
                        page_text = pdf_reader.pages[i].extract_text() or ""
                        sample_text += page_text + " "
                    except:
                        pass
                
                return {
                    "page_count": page_count,
                    "has_text": len(sample_text.strip()) > 0,
                    "sample_text_preview": sample_text[:200] + "..." if sample_text else ""
                }
        except Exception as e:
            logger.error(f"Error getting document stats: {e}")
            return {"error": str(e)}