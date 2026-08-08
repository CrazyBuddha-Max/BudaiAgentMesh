"""CSV 文件连接器: 本地文件即数据源, 适合快速演示与起步."""
import csv
import os
import re

from app.access.connectors import (
    ColumnProfile,
    SourceContract,
    TableProfile,
    register_connector,
)
from app.access.connectors.expr import (
    ExprError,
    aggregate_values,
    evaluate_expr,
    validate_expr_columns,
)

# 后端根目录: 用于把相对 file_path 解析为绝对路径 (跨平台兼容)
BACKEND_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)


def _remap_linux_path(path: str) -> str:
    """兼容历史数据: 仅在 Windows 下把 WSL 绝对路径 (/mnt/d/xxx) 重映射为盘符路径."""
    if os.sep != "\\":  # POSIX (WSL/macOS): /mnt/d/... 本就是正确路径
        return path
    m = re.match(r"^/mnt/([a-zA-Z])/(.*)$", path)
    if m:
        drive, rest = m.group(1), m.group(2)
        return f"{drive.upper()}:\\{rest.replace('/', os.sep)}"
    return path


@register_connector
class CsvConnector(SourceContract):
    """读取本地 CSV 文件, 推断类型并生成质量画像."""

    source_type = "csv"

    @property
    def path(self) -> str:
        path = self.params.get("file_path") or ""
        path = os.path.expanduser(path)
        if not os.path.isabs(path):
            path = os.path.join(BACKEND_ROOT, path)
        return os.path.abspath(_remap_linux_path(path))

    async def test_connection(self) -> None:
        if not os.path.exists(self.path):
            raise FileNotFoundError(f"文件不存在: {self.path}")

    async def sample_rows(self, table_name: str, limit: int = 10) -> list[dict]:
        await self.test_connection()
        with open(self.path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            rows = []
            for i, row in enumerate(reader):
                if i >= limit:
                    break
                rows.append(dict(row))
        return rows

    async def detect_changes(self, previous_watermark: str | None) -> dict:
        """增量检测 (M6): 以文件指纹 (mtime + size) 判断是否变更."""
        await self.test_connection()
        st = os.stat(self.path)
        fingerprint = f"{st.st_mtime_ns}:{st.st_size}"
        changed = previous_watermark != fingerprint
        return {
            "changed": changed,
            "watermark": fingerprint,
            "detail": "文件已变更, 重新采集" if changed else "文件无变化, 增量跳过",
        }

    async def discover_schema(self) -> list[TableProfile]:
        await self.test_connection()
        with open(self.path, newline="", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            if not header:
                return []
            rows: list[list[str]] = []
            for i, row in enumerate(reader):
                if i >= 1000:  # 采样上限, 保证画像开销可控
                    break
                rows.append(row)

        total = len(rows)
        cols: list[ColumnProfile] = []
        for idx, name in enumerate(header):
            col_values = [r[idx] for r in rows if idx < len(r)]
            non_null = [v for v in col_values if v not in ("", None)]
            null_rate = round((len(col_values) - len(non_null)) / total, 4) if total else 0.0
            distinct_ratio = round(len(set(non_null)) / total, 4) if total else 0.0
            samples = list(dict.fromkeys(non_null))[:3]
            cols.append(
                ColumnProfile(
                    name=name,
                    data_type=_infer_type(non_null),
                    is_nullable=True,
                    is_primary_key=False,
                    null_rate=null_rate,
                    distinct_ratio=distinct_ratio,
                    sample_values=samples,
                )
            )

        base = os.path.splitext(os.path.basename(self.path))[0]
        return [TableProfile(schema_name="csv", table_name=base, row_count=total, columns=cols)]

    async def _read_rows(self) -> list[dict[str, str]]:
        await self.test_connection()
        with open(self.path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            return [dict(row) for row in reader]

    async def query_aggregate(
        self,
        table: str,
        aggregation: str,
        measure: str,
        group_by: list[str] | None = None,
        filters: list[dict] | None = None,
        limit: int = 100,
    ) -> list[dict]:
        rows = await self._read_rows()
        columns = set(rows[0].keys()) if rows else set()
        if measure.strip() != "*":
            # 防御: 文件表头与目录注册列不一致时拒绝执行
            validate_expr_columns(measure, columns)
        group_by = group_by or []
        filters = filters or []

        groups: dict[tuple, list[float | None]] = {}
        for row in rows:
            if not _row_matches(row, filters):
                continue
            key = tuple((row.get(d) or "") for d in group_by) if group_by else ()
            if aggregation == "count":
                if measure.strip() == "*" or str(row.get(measure, "")).strip() != "":
                    groups.setdefault(key, []).append(None)
            elif aggregation == "count_distinct":
                groups.setdefault(key, []).append(
                    _to_comparable(row.get(measure))
                )
            else:
                try:
                    value = evaluate_expr(measure, row)
                except ExprError:
                    value = None
                groups.setdefault(key, []).append(value)

        if not groups:
            return [{"value": 0}] if not group_by else []

        results: list[dict] = []
        for key, values in groups.items():
            agg = aggregate_values(aggregation, values, [])
            if group_by:
                item: dict = dict(zip(group_by, key, strict=True))
                item["value"] = agg
                results.append(item)
            else:
                results.append({"value": agg})
        results.sort(key=lambda r: str(r.get("value", "")), reverse=True)
        return results[:limit]


def _to_comparable(value: str | None) -> str:
    return (value or "").strip()


def _row_matches(row: dict[str, str], filters: list[dict]) -> bool:
    """按过滤条件逐行判定: 支持 eq/neq/gt/ge/lt/le/in/contains."""
    for rule in filters:
        column = rule["column"]
        op = rule.get("op", "eq")
        target = rule.get("value")
        actual = (row.get(column) or "").strip()
        if op == "eq":
            if actual != str(target):
                return False
        elif op == "neq":
            if actual == str(target):
                return False
        elif op in ("gt", "ge", "lt", "le"):
            a = _num(actual)
            b = _num(target)
            if a is None or b is None:
                return False
            if op == "gt" and not a > b:
                return False
            if op == "ge" and not a >= b:
                return False
            if op == "lt" and not a < b:
                return False
            if op == "le" and not a <= b:
                return False
        elif op == "in":
            if actual not in {str(v) for v in (target or [])}:
                return False
        elif op == "contains":
            if str(target) not in actual:
                return False
    return True


def _num(value) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _infer_type(values: list[str]) -> str:
    if not values:
        return "unknown"
    try:
        [int(v) for v in values]
        return "integer"
    except ValueError:
        pass
    try:
        [float(v) for v in values]
        return "number"
    except ValueError:
        pass
    return "string"
