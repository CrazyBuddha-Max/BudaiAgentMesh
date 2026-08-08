"""联邦接入 (M6): 跨实例目录/数据透传.

设计: BudaiAgentMesh 实例间联邦 —— 本机注册远端对等实例 (FederatedPeer),
通过其公开 API (Bearer token) 透传目录检索与数据查询, 实现"一处接入, 全局可查".
对远端的能力暴露复用既有 API (catalog/tables / access/sample), 无需远端特殊改造.
"""
import datetime as dt

import httpx
from sqlalchemy import String, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.exceptions import BizError, NotFoundError


class FederatedPeer(Base):
    """联邦对等实例: 注册后可被目录检索 / 数据查询透传访问."""

    __tablename__ = "federated_peers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    base_url: Mapped[str] = mapped_column(String(512))  # 如 http://peer-host:8000
    api_token: Mapped[str | None] = mapped_column(String(512), nullable=True)  # 远端访问令牌
    status: Mapped[str] = mapped_column(String(16), default="active")  # active/disabled
    created_at: Mapped[dt.datetime] = mapped_column(server_default=func.now())


async def list_peers(session: AsyncSession) -> list[FederatedPeer]:
    result = await session.execute(select(FederatedPeer).order_by(FederatedPeer.name))
    return list(result.scalars().all())


async def get_peer(session: AsyncSession, peer_id: int) -> FederatedPeer:
    peer = await session.get(FederatedPeer, peer_id)
    if peer is None:
        raise NotFoundError(f"联邦实例不存在: {peer_id}")
    return peer


async def create_peer(session: AsyncSession, name: str, base_url: str, api_token: str | None) -> FederatedPeer:
    if not name or not base_url:
        raise BizError("实例名称与地址不能为空")
    peer = FederatedPeer(name=name, base_url=base_url.rstrip("/"), api_token=api_token)
    session.add(peer)
    await session.commit()
    await session.refresh(peer)
    return peer


async def set_peer_status(session: AsyncSession, peer_id: int, status: str) -> FederatedPeer:
    peer = await get_peer(session, peer_id)
    if status not in ("active", "disabled"):
        raise BizError("状态仅支持 active/disabled")
    peer.status = status
    await session.commit()
    await session.refresh(peer)
    return peer


async def delete_peer(session: AsyncSession, peer_id: int) -> None:
    peer = await get_peer(session, peer_id)
    await session.delete(peer)
    await session.commit()


def _headers(peer: FederatedPeer) -> dict:
    headers = {"Accept": "application/json"}
    if peer.api_token:
        headers["Authorization"] = f"Bearer {peer.api_token}"
    return headers


async def _request(
    peer: FederatedPeer, path: str, params: dict | None = None, request_timeout: float = 15.0
) -> dict:
    """透传 GET 请求到远端实例 (尽力而为: 失败返回错误信息而非抛出)."""
    try:
        async with httpx.AsyncClient(timeout=request_timeout) as client:
            resp = await client.get(f"{peer.base_url}{path}", params=params, headers=_headers(peer))
            if resp.status_code == 200:
                return {"ok": True, "peer": peer.name, "data": resp.json()}
            return {"ok": False, "peer": peer.name, "error": f"远端 HTTP {resp.status_code}"}
    except httpx.HTTPError as exc:
        return {"ok": False, "peer": peer.name, "error": f"远端不可达: {exc.__class__.__name__}"}


async def federated_search(
    session: AsyncSession,
    keyword: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """跨全部启用实例的目录检索 (并发透传)."""
    import asyncio

    peers = [p for p in await list_peers(session) if p.status == "active"]
    if not peers:
        return []
    tasks = [
        _request(p, "/api/access/catalog/tables", params={"keyword": keyword, "limit": limit})
        for p in peers
    ]
    results = await asyncio.gather(*tasks)
    return list(results)


async def federated_query(
    session: AsyncSession,
    peer_id: int,
    path: str,
    params: dict | None = None,
) -> dict:
    """对指定实例透传自定义查询 (如 /api/access/catalog/columns?keyword=phone)."""
    peer = await get_peer(session, peer_id)
    return await _request(peer, path, params=params)
