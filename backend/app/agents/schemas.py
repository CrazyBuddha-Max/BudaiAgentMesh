"""协同层 Pydantic 契约."""
import datetime as dt

from pydantic import BaseModel, ConfigDict, Field


class AgentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: str | None = None
    capabilities: list[str] = ["data_access", "knowledge_retrieval"]
    tools: list[str] = []  # 空 = 全部


class AgentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    capabilities: list[str] = []
    tools: list[str] = []
    status: str
    created_at: dt.datetime


class TaskCreate(BaseModel):
    objective: str = Field(..., min_length=1, max_length=2000)
    title: str | None = None
    collaborators: list[int] = []  # 协作 Agent ids (M3)


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    agent_id: int
    event_type: str
    payload: dict | None = None
    created_at: dt.datetime


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    agent_id: int
    title: str | None = None
    objective: str
    collaborators: list[int] = []
    status: str
    result: str | None = None
    error: str | None = None
    created_at: dt.datetime
    finished_at: dt.datetime | None = None
    events: list[EventOut] = []


class ToolInfo(BaseModel):
    name: str
    description: str
    parameters: dict
