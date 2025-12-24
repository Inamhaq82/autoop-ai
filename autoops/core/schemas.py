from pydantic import BaseModel, Field
from typing import List


class TaskSummary(BaseModel):
    """
    Structured output schema for task summarization.
    """

    summary: str = Field(description="A concise summary of the task in plain English")

    key_points: List[str] = Field(description="Bullet-point style key takeaways")

    confidence: float = Field(
        ge=0.0, le=1.0, description="Model confidence between 0 and 1"
    )
