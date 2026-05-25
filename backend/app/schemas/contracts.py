from typing import Literal

from pydantic import BaseModel


class ReviewRecord(BaseModel):
    review_id: str
    business_id: str
    stars: int
    text: str
    date: str


class AgentError(BaseModel):
    status: Literal["error"] = "error"
    agent: str
    error_type: str
    error_detail: str
    retry_count: int
    recoverable: bool

