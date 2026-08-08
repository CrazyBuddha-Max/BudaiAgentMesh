"""协同层 Pydantic 契约."""
import datetime as dt

from pydantic import BaseModel, ConfigDict, Field


class AgentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: str | None = None
    llm_provider_id: int | None = None  # M7: 绑定模型提供方, 空 = 默认
    capabilities: list[str] = ["data_access", "knowledge_retrieval"]
    tools: list[str] = []  # 空 = 全部


class AgentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    llm_provider_id: int | None = None
    llm_provider_name: str | None = None  # 冗余展示字段 (API 层填充)
    capabilities: list[str] = []
    tools: list[str] = []
    status: str
    created_at: dt.datetime


class LLMProviderCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    provider_type: str = "openai"
    api_base: str = Field(..., description="OpenAI 兼容地址, 如 https://api.openai.com/v1")
    api_key: str | None = None
    model: str = Field(..., description="对话模型, 如 gpt-4o-mini / deepseek-chat")
    embedding_model: str | None = None
    temperature: float = 0.2
    max_tokens: int = 2048
    is_default: bool = False


class LLMProviderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    provider_type: str
    api_base: str
    model: str
    embedding_model: str | None = None
    temperature: float
    max_tokens: int
    enabled: bool
    is_default: bool
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
