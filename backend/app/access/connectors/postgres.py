"""PostgreSQL 连接器."""
import datetime as dt
import re
from typing import Any

import asyncpg

from app.access.connectors import (
    ColumnProfile,
    SourceContract,
    TableProfile,
    register_connector,
)

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _safe_ident(name: str) -> str:
    """标识符白名单校验: 仅允许合法表/列名, 杜绝注入."""
    if not _IDENT_RE.match(name):
        raise ValueError(f"非法标识符: {name}")
    return name


@register_connector
class PostgresConnector(SourceContract):
    """通过 asyncpg 直连 PostgreSQL, 扫描 information_schema 并采样质量画像."""

    source_type = "postgres"

    def _dsn(self) -> str:
        return (
            f"postgresql://{self.params['username']}:{self.params['password']}"
            f"@{self.params['host']}:{self.params.get('port', 5432)}/{self.params['database']}"
        )

    async def _connect(self) -> asyncpg.Connection:
        return await asyncpg.connect(self._dsn())

    async def test_connection(self) -> None:
        conn = await self._connect()
        await conn.close()

    async def detect_changes(self, previous_watermark: str | None) -> dict:
        """增量检测 (M6): 表集合指纹 (每表 行数 + 列名), 行数/结构变化即重采.

        轻量启发式, 适合演示与小库; 生产建议切换逻辑复制 (wal2json) 级 CDC.
        """
        schema = self.params.get("schema_name") or "public"
        conn = await self._connect()
        try:
            tables = await conn.fetch(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = $1 AND table_type = 'BASE TABLE' ORDER BY table_name",
                schema,
            )
            parts = []
            for t in tables:
                tname = t["table_name"]
                count = await conn.fetchval(f'SELECT COUNT(*) FROM "{_safe_ident(schema)}"."{_safe_ident(tname)}"')
                cols = await conn.fetch(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = $1 AND table_name = $2 ORDER BY ordinal_position",
                    schema,
                    tname,
                )
                parts.append(f"{tname}:{count}:[{','.join(c['column_name'] for c in cols)}]")
            fingerprint = "|".join(parts)
        finally:
            await conn.close()
        changed = previous_watermark != fingerprint
        return {
            "changed": changed,
            "watermark": fingerprint,
            "detail": "表结构/行数有变化, 重新采集" if changed else "无变化, 增量跳过",
        }

    async def sample_rows(self, table_name: str, limit: int = 10) -> list[dict]:
        """SELECT 数据样例, 值序列化为 JSON 安全类型."""
        schema = self.params.get("schema_name") or "public"
        conn = await self._connect()
        try:
            rows = await conn.fetch(f'SELECT * FROM "{_safe_ident(schema)}"."{_safe_ident(table_name)}" LIMIT $1', limit)
            return [dict(r) for r in rows]
        finally:
            await conn.close()

    async def discover_schema(self) -> list[TableProfile]:
        conn = await self._connect()
        try:
            schema = self.params.get("schema_name") or "public"
            tables = await conn.fetch(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = $1 AND table_type = 'BASE TABLE'
                ORDER BY table_name
                """,
                schema,
            )
            profiles: list[TableProfile] = []
            for row in tables:
                table = _safe_ident(row["table_name"])
                try:
                    count = await conn.fetchval(f'SELECT count(*) FROM "{schema}"."{table}"')
                except Exception:
                    count = 0
                cols = await conn.fetch(
                    """
                    SELECT column_name, data_type, is_nullable,
                           (SELECT count(*) FROM information_schema.table_constraints tc
                            JOIN information_schema.key_column_usage kcu
                              ON tc.constraint_name = kcu.constraint_name
                            WHERE tc.table_schema = $1 AND tc.table_name = $2
                              AND tc.constraint_type = 'PRIMARY KEY' AND kcu.column_name = c.column_name) > 0 AS is_pk
                    FROM information_schema.columns c
                    WHERE table_schema = $1 AND table_name = $2
                    ORDER BY ordinal_position
                    """,
                    schema,
                    table,
                )
                column_profiles: list[ColumnProfile] = []
                for c in cols:
                    profile = await self._profile_column(conn, schema, table, c)
                    column_profiles.append(profile)
                profiles.append(
                    TableProfile(schema_name=schema, table_name=table, row_count=count or 0, columns=column_profiles)
                )
            return profiles
        finally:
            await conn.close()

    async def _profile_column(self, conn: asyncpg.Connection, schema: str, table: str, col: dict[str, Any]) -> ColumnProfile:
        name = _safe_ident(col["column_name"])
        dtype = col["data_type"]
        nullable = col["is_nullable"] == "YES"
        null_rate = 0.0
        distinct_ratio = 0.0
        samples: list[Any] = []
        try:
            total = await conn.fetchval(f'SELECT count(*) FROM "{schema}"."{table}"')
            if total:
                nulls = await conn.fetchval(f'SELECT count(*) FROM "{schema}"."{table}" WHERE "{name}" IS NULL')
                null_rate = round(nulls / total, 4)
                distinct = await conn.fetchval(f'SELECT count(DISTINCT "{name}") FROM "{schema}"."{table}"')
                distinct_ratio = round(distinct / total, 4)
                rows = await conn.fetch(
                    f'SELECT DISTINCT "{name}" FROM "{schema}"."{table}" WHERE "{name}" IS NOT NULL LIMIT 3'
                )
                samples = [self._serialize(r[name]) for r in rows]
        except Exception:
            pass
        return ColumnProfile(
            name=name,
            data_type=dtype,
            is_nullable=nullable,
            is_primary_key=bool(col["is_pk"]),
            null_rate=null_rate,
            distinct_ratio=distinct_ratio,
            sample_values=samples,
        )

    @staticmethod
    def _serialize(value: Any) -> Any:
        if isinstance(value, (dt.datetime, dt.date, dt.time)):
            return value.isoformat()
        if isinstance(value, (bytearray, memoryview)):
            return str(bytes(value))[:200]
        return value

    async def query_aggregate(
        self,
        table: str,
        aggregation: str,
        measure: str,
        group_by: list[str] | None = None,
        filters: list[dict] | None = None,
        limit: int = 100,
    ) -> list[dict]:
        from app.access.connectors.expr import build_aggregate_sql

        schema = _safe_ident(self.params.get("schema_name") or "public")
        table_name = _safe_ident(table)
        sql, params = build_aggregate_sql(
            aggregation=aggregation,
            measure=measure,
            table_ref=f'"{schema}"."{table_name}"',
            group_by=group_by,
            filters=filters,
            limit=limit,
            ph=lambda i: f"${i + 1}",
        )
        conn = await self._connect()
        try:
            rows = await conn.fetch(sql, *params)
        finally:
            await conn.close()
        results: list[dict] = []
        for row in rows:
            item = {k: self._serialize(v) for k, v in dict(row).items()}
            results.append(item)
        return results
