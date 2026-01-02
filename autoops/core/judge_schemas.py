from typing import List
from pydantic import BaseModel, Field

class JudgeReport(BaseModel):
    run_id: str
    judge_model: str
    overall: float = Field(ge=0.0, le=1.0)
    correctness: float = Field(ge=0.0, le=1.0)
    completeness: float = Field(ge=0.0, le=1.0)
    concision: float = Field(ge=0.0, le=1.0)
    clarity: float = Field(ge=0.0, le=1.0)
    safety: float = Field(ge=0.0, le=1.0)
    reasons: List[str] = Field(min_length=1)

