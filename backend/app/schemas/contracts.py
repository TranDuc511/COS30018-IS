from typing import Literal

from pydantic import BaseModel, Field


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


class Pattern(BaseModel):
    description: str
    aspect: Literal[
        "food_quality",
        "staff_attitude",
        "pricing",
        "wait_time",
        "ambience",
        "cleanliness",
        "other",
    ]
    frequency: float = Field(ge=0, le=1)
    evidence_review_ids: list[str] = Field(default_factory=list)


class RootCause(BaseModel):
    pattern: str
    cause: str
    confidence: Literal["low", "medium", "high"]


class StrategicAgentInput(BaseModel):
    patterns: list[Pattern] = Field(default_factory=list)
    root_causes: list[RootCause] = Field(default_factory=list)


class Recommendation(BaseModel):
    priority: int = Field(ge=1)
    issue: str
    action: str
    category: str
    expected_impact: str


class StrategicAgentOutput(BaseModel):
    recommendations: list[Recommendation] = Field(default_factory=list)
    status: Literal["success", "error"]
    error_detail: str | None = None

