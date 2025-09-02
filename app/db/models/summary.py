from pydantic import BaseModel
from typing import List, Dict

class SummaryRequest(BaseModel):
    doc_id: str
    session_id: str

class SummaryResponse(BaseModel):
    summary: str
    sources: List[Dict]
