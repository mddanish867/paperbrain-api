from fastapi import APIRouter, HTTPException
from app.services.summary import summary_service
from app.db.models.summary import SummaryRequest, SummaryResponse

router = APIRouter(prefix="/api/v1/summary", tags=["summary"])

@router.post("", response_model=SummaryResponse)
async def generate_summary(request: SummaryRequest):
    try:
        response = await summary_service.generate_summary(
            doc_id=request.doc_id,
            session_id=request.session_id
        )
        return SummaryResponse(**response)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Summary error: {str(e)}")
