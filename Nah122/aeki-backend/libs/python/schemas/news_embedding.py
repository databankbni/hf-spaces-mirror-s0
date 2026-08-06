from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

class NewsEmbedding(BaseModel):
    """
    Standardized schema for news embeddings (Dense + Sparse) produced by the Embedding Service.
    Output Topic: news.embeddings
    """
    # Identification
    doc_id: str = Field(..., description="Original document ID from source")
    chunk_id: str = Field(..., description="Unique deterministic ID for this chunk (hash of doc_id + index)")
    chunk_index: int = Field(..., description="Sequence number of the chunk (0-indexed)")
    
    # Content
    text_chunk: str = Field(..., description="The actual text content of the chunk")
    text_hash: str = Field(..., description="Hash of the text content for deduplication/verification")
    
    # Embeddings
    embedding_dense: str = Field(..., description="Base64 encoded float32 dense vector (1024 dim)")
    embedding_sparse: Optional[Dict[str, float]] = Field(None, description="Sparse vector (token weights), optional")
    
    # Metadata (Passthrough for convenience)
    language: str = Field("unknown", description="Language code")
    url: Optional[str] = Field(None, description="Source URL")
    published_at: Optional[datetime] = Field(None, description="Original publication timestamp")
    source: Optional[str] = Field(None, description="Source name")
    
    # System Metadata
    processed_at: datetime = Field(default_factory=datetime.utcnow, description="UTC timestamp when embedding was generated")
    model_name: str = Field("BAAI/bge-m3", description="Model used for embedding")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() + "Z"
        }
