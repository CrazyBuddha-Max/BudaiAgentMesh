"""多租户管理 (M6): 租户实体 + 账号归属.

隔离模型: 数据接入层 (数据源/目录/采集) 按 tenant_id 硬隔离, 越权访问视为不存在;
JWT 携带 tenant 声明, 内置账号格式扩展为 username:password:role:tenant (缺省归 default).
"""
import datetime as dt

from sqlalchemy import String, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.exceptions import BizError, NotFoundError

DEFAULT_TENANT = "default"


class Tenant(Base):
    """租户: 资源隔离维度 (演示: 字符串标识; 生产可扩展配额/加密密钥等)."""

    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16), default="active")  # active/disabled
    created_at: Mapped[dt.datetime] = mapped_column(server_default=func.now())


async def list_tenants(session: AsyncSession) -> list[Tenant]:
    result = await session.execute(select(Tenant).order_by(Tenant.code))
    return list(result.scalars().all())


async def get_tenant(session: AsyncSession, code: str) -> Tenant:
    tenant = (
        await session.execute(select(Tenant).where(Tenant.code == code))
    ).scalar_one_or_none()
    if tenant is None:
        raise NotFoundError(f"租户不存在: {code}")
    return tenant


async def create_tenant(session: AsyncSession, code: str, name: str) -> Tenant:
    if not code or not name:
        raise BizError("租户编码与名称不能为空")
    existing = (await session.execute(select(Tenant).where(Tenant.code == code))).scalar_one_or_none()
    if existing is not None:
        raise BizError(f"租户已存在: {code}")
    tenant = Tenant(code=code, name=name)
    session.add(tenant)
    await session.commit()
    await session.refresh(tenant)
    return tenant


async def set_tenant_status(session: AsyncSession, code: str, status: str) -> Tenant:
    tenant = await get_tenant(session, code)
    if status not in ("active", "disabled"):
        raise BizError("状态仅支持 active/disabled")
    tenant.status = status
    await session.commit()
    await session.refresh(tenant)
    return tenant
