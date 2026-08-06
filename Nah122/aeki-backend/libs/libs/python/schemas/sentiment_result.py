from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

class SentimentResult(BaseModel):
    """
    Standardized schema for sentiment analysis results.
    """
    doc_id: str = Field(..., description="Unique system ID of the article")
    url: str = Field(..., description="Original article URL")
    language: str = Field(..., description="Article language")
    source: str = Field(..., description="Source name")
    published_at: Optional[datetime] = Field(None, description="UTC publication date")
    
    # Sentiment Fields
    sentiment_label: str = Field(..., description="Label: POSITIVE, NEUTRAL, or NEGATIVE")
    sentiment_score: float = Field(..., description="Model confidence score")
    sentiment_score_normalized: float = Field(..., description="Normalized score: POSITIVE=+1, NEUTRAL=0, NEGATIVE=-1")
    
    # Metadata
    model_name: str = Field("xlm-roberta-sentiment", description="Name of the model used")
    processed_at: datetime = Field(default_factory=datetime.utcnow, description="UTC timestamp of processing")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() + "Z"
        }
