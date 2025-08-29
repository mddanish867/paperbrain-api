from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List
import tempfile
import os

from app.services.document_processor import DocumentProcessor
from app.services.vector_store import get_vector_store
from app.core.security import get_current_user
from app.utils.validators import validate_file_size, sanitize_filename
from app.utils.logger import logger
from app.db.session import get_db
from app.db.models.user import User

router = APIRouter(prefix="/documents", tags=["documents"])

class DocumentResponse(BaseModel):
    id: str
    filename: str
    chunk_count: int

class DocumentListResponse(BaseModel):
    documents: List[dict]
    count: int

@router.post("/upload", response_model=DocumentResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),    
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    safe_filename = sanitize_filename(file.filename or "uploaded.pdf")
    logger.info(f"Document upload from {current_user['sub']}: {safe_filename}")
    
    if not safe_filename.lower().endswith('.pdf'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are supported"
        )
    
    try:
        # Read and validate file
        content = await file.read()
        validate_file_size(len(content))
        
        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
            tmp_file.write(content)
            tmp_file_path = tmp_file.name
        
        # Process document in background
        def process_and_store_document():
            try:
                processor = DocumentProcessor()
                vector_store = get_vector_store()
                
                chunks = processor.process_pdf(tmp_file_path, safe_filename)
                doc_id = vector_store.store_document(chunks, safe_filename)
                
                logger.info(f"Document processed: {safe_filename} -> {len(chunks)} chunks")
                
                # Clean up temporary file
                os.unlink(tmp_file_path)
                
                return doc_id, len(chunks)
            except Exception as e:
                # Clean up on error
                if os.path.exists(tmp_file_path):
                    os.unlink(tmp_file_path)
                raise e
        
        # Process in background
        doc_id, chunk_count = await background_tasks.add_task(process_and_store_document)
        
        return DocumentResponse(
            id=doc_id,
            filename=safe_filename,
            chunk_count=chunk_count
        )
        
    except Exception as e:
        logger.error(f"Error processing document: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing document: {str(e)}"
        )

@router.get("", response_model=DocumentListResponse)
async def list_documents(
    current_user: dict = Depends(get_current_user),
    vector_store = Depends(get_vector_store)
):
    documents = await vector_store.list_documents()
    return DocumentListResponse(
        documents=documents,
        count=len(documents)
    )

@router.delete("/{doc_id}")
async def delete_document(
    doc_id: str,
    current_user: dict = Depends(get_current_user),
    vector_store = Depends(get_vector_store)
):
    try:
        await vector_store.delete_document(doc_id)
        logger.info(f"Document deleted by {current_user['sub']}: {doc_id}")
        return {"message": "Document deleted successfully", "document_id": doc_id}
    except Exception as e:
        logger.error(f"Error deleting document: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting document: {str(e)}"
        )