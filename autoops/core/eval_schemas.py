from pydantic import BaseModel, Field
from typing import List


class EvalReport(BaseModel):
    run_id: str

    quality_score: float = Field(ge=0.0, le=1.0)
    structure_score: float = Field(ge=0.0, le=1.0)
    cost_score: float = Field(ge=0.0, le=1.0)
    stability_score: float = Field(ge=0.0, le=1.0)

    reasons: List[str] = Field(default_factory=list)
