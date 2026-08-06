from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field

class NewsProcessed(BaseModel):
    """
    Standardized schema for processed news articles, ready for AI services.
    """
    doc_id: str = Field(..., description="Unique system ID (hash of URL)")
    url: str = Field(..., description="Original article URL")
    title: str = Field(..., description="Cleaned title")
    content: str = Field(..., description="Cleaned and normalized text content")
    source: str = Field(..., description="Source name")
    published_at: Optional[datetime] = Field(None, description="Standardized UTC publication date")
    scraped_at: datetime = Field(..., description="UTC timestamp when originally scraped")
    processed_at: datetime = Field(default_factory=datetime.utcnow, description="UTC timestamp when processed")
    language: str = Field(..., description="Verified language code (e.g., 'en', 'am')")
    language_confidence: float = Field(1.0, description="Verification confidence level")
    
    # Enrichment
    word_count: int = Field(0, description="Total word count of content")
    char_count: int = Field(0, description="Total character count of content")
    
    # Flexible metadata for source-specific fields
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() + "Z"
        }
