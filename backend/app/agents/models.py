"""协同层 ORM 模型: Agent / 任务 / 事件."""
import datetime as dt

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Agent(Base):
    """Agent 注册中心: 身份 / 能力声明 / 状态."""

    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    capabilities: Mapped[list] = mapped_column(JSON, default=list)  # 能力声明 (Capability Manifest)
    tools: Mapped[list] = mapped_column(JSON, default=list)  # 可调用工具名; 空 = 全部
    status: Mapped[str] = mapped_column(String(16), default="active")  # active/paused/offline
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())

    tasks: Mapped[list["AgentTask"]] = relationship(
        back_populates="agent", cascade="all, delete-orphan", lazy="selectin"
    )


class AgentTask(Base):
    """任务: 目标 -> 分解 -> 执行 -> 结果."""

    __tablename__ = "agent_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), index=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    objective: Mapped[str] = mapped_column(Text)
    collaborators: Mapped[list] = mapped_column(JSON, default=list)  # 协作 Agent ids (M3)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending/running/succeeded/failed
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)

    agent: Mapped[Agent] = relationship(back_populates="tasks")
    events: Mapped[list["AgentEvent"]] = relationship(
        back_populates="task", cascade="all, delete-orphan", lazy="selectin", order_by="AgentEvent.id"
    )


class AgentEvent(Base):
    """事件总线 (进程内): 任务执行全链路留痕, 供观测与审计."""

    __tablename__ = "agent_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("agent_tasks.id", ondelete="CASCADE"), index=True)
    agent_id: Mapped[int] = mapped_column(Integer, index=True)
    event_type: Mapped[str] = mapped_column(String(64))  # task_started/tool_call/retrieval/completion/error
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())

    task: Mapped[AgentTask] = relationship(back_populates="events")
