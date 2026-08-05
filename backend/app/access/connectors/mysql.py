"""MySQL 连接器."""
import re
from typing import Any

import aiomysql

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
class MySqlConnector(SourceContract):
    """通过 aiomysql 直连 MySQL, 扫描 information_schema 并采样质量画像."""

    source_type = "mysql"

    async def _connect(self) -> aiomysql.Connection:
        return await aiomysql.connect(
            host=self.params["host"],
            port=int(self.params.get("port", 3306)),
            user=self.params["username"],
            password=self.params["password"],
            db=self.params["database"],
            autocommit=True,
        )

    async def test_connection(self) -> None:
        conn = await self._connect()
        conn.close()

    async def discover_schema(self) -> list[TableProfile]:
        conn = await self._connect()
        try:
            db = self.params["database"]
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    """
                    SELECT table_name FROM information_schema.tables
                    WHERE table_schema = %s AND table_type = 'BASE TABLE'
                    ORDER BY table_name
                    """,
                    (db,),
                )
                tables = await cur.fetchall()
                profiles: list[TableProfile] = []
                for row in tables:
                    table = _safe_ident(row["table_name"])
                    await cur.execute(f"SELECT count(*) FROM `{db}`.`{table}`")
                    count_row = await cur.fetchone()
                    count = int(list(count_row.values())[0])
                    await cur.execute(
                        """
                        SELECT column_name, data_type, is_nullable, column_key
                        FROM information_schema.columns
                        WHERE table_schema = %s AND table_name = %s
                        ORDER BY ordinal_position
                        """,
                        (db, table),
                    )
                    cols = await cur.fetchall()
                    column_profiles: list[ColumnProfile] = []
                    for c in cols:
                        profile = await self._profile_column(conn, db, table, c)
                        column_profiles.append(profile)
                    profiles.append(
                        TableProfile(schema_name=db, table_name=table, row_count=count, columns=column_profiles)
                    )
                return profiles
        finally:
            conn.close()

    async def _profile_column(
        self, conn: aiomysql.Connection, db: str, table: str, col: dict[str, Any]
    ) -> ColumnProfile:
        name = _safe_ident(col["column_name"])
        null_rate, distinct_ratio = 0.0, 0.0
        samples: list[Any] = []
        try:
            async with conn.cursor() as cur:
                await cur.execute(f'SELECT count(*) FROM `{db}`.`{table}`')
                total = int((await cur.fetchone())[0])
                if total:
                    await cur.execute(f'SELECT count(*) FROM `{db}`.`{table}` WHERE `{name}` IS NULL')
                    nulls = int((await cur.fetchone())[0])
                    null_rate = round(nulls / total, 4)
                    await cur.execute(f'SELECT count(DISTINCT `{name}`) FROM `{db}`.`{table}`')
                    distinct = int((await cur.fetchone())[0])
                    distinct_ratio = round(distinct / total, 4)
                    await cur.execute(
                        f'SELECT DISTINCT `{name}` FROM `{db}`.`{table}` WHERE `{name}` IS NOT NULL LIMIT 3'
                    )
                    samples = [str(r[0]) for r in await cur.fetchall()]
        except Exception:
            pass
        return ColumnProfile(
            name=name,
            data_type=col["data_type"],
            is_nullable=col["is_nullable"] == "YES",
            is_primary_key=col["column_key"] == "PRI",
            null_rate=null_rate,
            distinct_ratio=distinct_ratio,
            sample_values=samples,
        )

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

        db = _safe_ident(self.params["database"])
        table_name = _safe_ident(table)
        sql, params = build_aggregate_sql(
            aggregation=aggregation,
            measure=measure,
            table_ref=f"`{db}`.`{table_name}`",
            group_by=group_by,
            filters=filters,
            limit=limit,
            ph=lambda _i: "%s",
        )
        conn = await self._connect()
        try:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(sql, params)
                rows = await cur.fetchall()
        finally:
            conn.close()
        return [dict(r) for r in rows]
