"""指标度量表达式: 安全解析与求值.

设计目标: 度量 (measure) 支持简单算术表达式 (如 `unit_price * quantity`),
但必须经白名单校验, 杜绝注入与任意代码执行:

- 合法 token 仅限: 数字 / 标识符 / `+ - * / ( )`
- 标识符必须是数据源目录中已注册的列名
- CSV 连接器在本模块内做逐行求值; SQL 连接器用同一 token 校验后拼接 SQL
"""
from __future__ import annotations

import re
from typing import Any

_EXPR_TOKEN = re.compile(r"\s*(\d+(?:\.\d+)?|[A-Za-z_][A-Za-z0-9_]*|[()+\-*/])")

_AGGREGATIONS = ("sum", "avg", "count", "min", "max", "count_distinct")


class ExprError(ValueError):
    """度量表达式非法."""


def tokenize_expr(expr: str) -> list[str]:
    """将表达式拆为 token 序列, 出现非法字符即抛错."""
    tokens: list[str] = []
    pos = 0
    while pos < len(expr):
        m = _EXPR_TOKEN.match(expr, pos)
        if m is None:
            raise ExprError(f"度量表达式包含非法字符: {expr!r}")
        tokens.append(m.group(1))
        pos = m.end()
    if not tokens:
        raise ExprError("度量表达式为空")
    return tokens


def validate_expr_columns(expr: str, columns: set[str]) -> list[str]:
    """校验表达式中所有标识符均属于允许的列名集合, 返回 token 列表."""
    tokens = tokenize_expr(expr)
    for tok in tokens:
        if tok in ("+", "-", "*", "/", "(", ")"):
            continue
        if re.fullmatch(r"\d+(\.\d+)?", tok):
            continue
        if tok not in columns:
            raise ExprError(f"度量表达式引用了未注册的列: {tok!r}")
    return tokens


def _to_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if text == "":
        return None
    try:
        return float(text)
    except ValueError:
        return None


class _Parser:
    """递归下降解析器: 支持 + - * / 与括号, 无求值副作用."""

    def __init__(self, tokens: list[str], row: dict[str, Any]) -> None:
        self.tokens = tokens
        self.pos = 0
        self.row = row

    def _peek(self) -> str | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def _next(self) -> str:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def parse(self) -> float:
        value = self._expr()
        if self._peek() is not None:
            raise ExprError("度量表达式结尾存在多余内容")
        return value

    def _expr(self) -> float:
        value = self._term()
        while self._peek() in ("+", "-"):
            op = self._next()
            right = self._term()
            value = value + right if op == "+" else value - right
        return value

    def _term(self) -> float:
        value = self._factor()
        while self._peek() in ("*", "/"):
            op = self._next()
            right = self._factor()
            if op == "*":
                value = value * right
            else:
                value = value / right if right else 0.0
        return value

    def _factor(self) -> float:
        tok = self._next()
        if tok == "(":
            value = self._expr()
            if self._next() != ")":
                raise ExprError("括号不匹配")
            return value
        if tok == "-":
            return -self._factor()
        if re.fullmatch(r"\d+(\.\d+)?", tok):
            return float(tok)
        number = _to_number(self.row.get(tok))
        if number is None:
            raise ExprError(f"列 {tok!r} 的值为空或非数字")
        return number


def evaluate_expr(expr: str, row: dict[str, Any]) -> float:
    """对单行数据求值 (CSV 连接器使用). 非法表达式抛 ExprError."""
    tokens = tokenize_expr(expr)
    return _Parser(tokens, row).parse()


# ---------- 聚合 ----------

def aggregate_values(aggregation: str, values: list[float | None], raw: list[Any]) -> float | int | None:
    """对已求值的度量序列做聚合 (CSV 连接器使用)."""
    non_null = [v for v in values if v is not None]
    if aggregation == "count":
        return len(values)  # count 语义: 命中行数
    if aggregation == "count_distinct":
        return len({v for v in values if v is not None})
    if not non_null:
        return None
    if aggregation == "sum":
        return round(sum(non_null), 6)
    if aggregation == "avg":
        return round(sum(non_null) / len(non_null), 6)
    if aggregation == "min":
        return min(non_null)
    if aggregation == "max":
        return max(non_null)
    raise ExprError(f"不支持的聚合方式: {aggregation}")


# ---------- SQL 构建 (PostgreSQL / MySQL 连接器共用) ----------

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def safe_ident(name: str) -> str:
    """标识符白名单校验: 仅允许合法表/列名, 杜绝注入."""
    if not _IDENT_RE.match(name):
        raise ExprError(f"非法标识符: {name!r}")
    return name


_FILTER_OPS = {"eq": "=", "neq": "<>", "gt": ">", "ge": ">=", "lt": "<", "le": "<="}


def _build_where(filters: list[dict] | None, ph) -> tuple[str, list[Any]]:
    """将过滤规则转为 WHERE 子句; ph(i) 生成第 i 个参数占位符."""
    clauses: list[str] = []
    params: list[Any] = []
    for rule in filters or []:
        column = safe_ident(rule["column"])
        op = rule.get("op", "eq")
        value = rule.get("value")
        if op in _FILTER_OPS:
            clauses.append(f"{column} {_FILTER_OPS[op]} {ph(len(params))}")
            params.append(value)
        elif op == "in":
            values = list(value or [])
            if not values:
                clauses.append("1 = 0")
                continue
            marks = ", ".join(ph(len(params) + i) for i in range(len(values)))
            clauses.append(f"{column} IN ({marks})")
            params.extend(values)
        elif op == "contains":
            clauses.append(f"{column} LIKE {ph(len(params))}")
            params.append(f"%{value}%")
        else:
            raise ExprError(f"不支持的过滤操作: {op}")
    return " AND ".join(clauses), params


def build_aggregate_sql(
    *,
    aggregation: str,
    measure: str,
    table_ref: str,
    group_by: list[str] | None = None,
    filters: list[dict] | None = None,
    limit: int = 100,
    ph,
) -> tuple[str, list[Any]]:
    """构建聚合查询 SQL. 所有标识符/度量表达式均经白名单校验."""
    dims = [safe_ident(d) for d in (group_by or [])]
    if measure.strip() == "*":
        expr_sql = "*"
    else:
        tokens = tokenize_expr(measure)
        for tok in tokens:
            if tok in ("+", "-", "*", "/", "(", ")"):
                continue
            if re.fullmatch(r"\d+(\.\d+)?", tok):
                continue
            safe_ident(tok)
        expr_sql = " ".join(tokens)

    if aggregation == "count" and expr_sql == "*":
        agg_sql = "COUNT(*)"
    elif aggregation == "count_distinct":
        agg_sql = f"COUNT(DISTINCT {expr_sql})"
    elif aggregation in ("sum", "avg", "min", "max"):
        agg_sql = f"{aggregation.upper()}({expr_sql})"
    else:
        raise ExprError(f"不支持的聚合方式: {aggregation}")

    select_cols = ", ".join(dims) + ", " if dims else ""
    parts = [f"SELECT {select_cols}{agg_sql} AS value FROM {table_ref}"]
    where, params = _build_where(filters, ph)
    if where:
        parts.append(f"WHERE {where}")
    if dims:
        parts.append(f"GROUP BY {', '.join(dims)}")
    parts.append("ORDER BY value DESC")
    parts.append(f"LIMIT {int(limit)}")
    return " ".join(parts), params
