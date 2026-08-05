"""知识层 Pydantic 契约."""
import datetime as dt

from pydantic import BaseModel, ConfigDict


class KnowledgeDocOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    source_type: str
    file_name: str
    file_size: int
    chunk_count: int
    status: str
    error: str | None = None
    created_at: dt.datetime


class ChunkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    chunk_index: int
    content: str
    token_count: int
    meta: dict | None = None


class DocDetailOut(KnowledgeDocOut):
    chunks: list[ChunkOut] = []


class RetrieveRequest(BaseModel):
    query: str = ...
    top_k: int = 5


class RetrieveHitOut(BaseModel):
    chunk_id: int
    doc_id: int
    content: str
    score: float
    metadata: dict | None = None
