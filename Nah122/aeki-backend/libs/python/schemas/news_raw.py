from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

class NewsRaw(BaseModel):
    """
    Standardized schema for raw news events produced by any scraper.
    """
    id: str = Field(..., description="Unique ID for the news item (e.g., hash of URL/ArticleID)")
    title: str = Field(..., description="Original title of the news item")
    content: str = Field(..., description="Full raw content or snippet of the news")
    source: str = Field(..., description="Name of the source (e.g., 'Telegram_@channel', 'BBC')")
    url: Optional[str] = Field(None, description="Original URL of the article")
    published_at: Optional[datetime] = Field(None, description="Original publication timestamp if available")
    scraped_at: datetime = Field(default_factory=datetime.utcnow, description="Timestamp of when the data was scraped")
    language: str = Field(..., description="Language code (e.g., 'en', 'am', 'om')")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional source-specific metadata")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
