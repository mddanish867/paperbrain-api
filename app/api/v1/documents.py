from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from fastapi.responses import JSONResponse
from typing import List
import tempfile
import os
from app.services.vector_store import get_vector_store
from app.services.chat import chat_service
from app.services.document_processor import DocumentProcessor
from app.db.models.documents import DocumentUploadResponse, DocumentListResponse, DocumentDeleteResponse



router = APIRouter(prefix="/documents", tags=["documents"])
@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(file: UploadFile = File(...)):
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    
    # Create temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
        content = await file.read()
        temp_file.write(content)
        temp_file_path = temp_file.name
    
    try:
        # Process the document
        processor = DocumentProcessor()
        chunks = processor.process_pdf(temp_file_path, file.filename)
        
        # Store in vector database
        vector_store = get_vector_store()
        doc_id = await vector_store.store_document(chunks, file.filename)
        
        # ✅ CREATE A NEW SESSION FOR THIS DOCUMENT
        session_id = await chat_service.create_document_session(doc_id, file.filename)
        
        return DocumentUploadResponse(
            id=doc_id,
            filename=file.filename,
            chunk_count=len(chunks),
            session_id=session_id  # ✅ Include the session_id in response
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process document: {str(e)}")
    finally:
        # Clean up temporary file
        if os.path.exists(temp_file_path):
            os.unlink(temp_file_path)

@router.get("/", response_model=List[DocumentListResponse])
async def list_documents():
    vector_store = get_vector_store()
    documents = await vector_store.list_documents()
    return documents

@router.delete("/{doc_id}", response_model=DocumentDeleteResponse)
async def delete_document(doc_id: str):
    try:
        vector_store = get_vector_store()
        await vector_store.delete_document(doc_id)
        return DocumentDeleteResponse(
            success=True,
            message=f"Document {doc_id} deleted successfully"
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete document: {str(e)}")