"""动态脱敏: 敏感列识别 + 按角色掩码 (M3).

设计原则:
- 列名模式识别敏感类型 (phone/id_card/bank/email/name/address)
- 脱敏按消费角色动态生效: viewer/analyst -> 掩码, admin -> 原文
- 作用于所有数据出口: 目录样例 / 指标查询 / Agent 数据工具
"""
import re
from typing import Any

# 敏感类型 -> (列名匹配规则, 说明)
SENSITIVE_RULES: dict[str, dict] = {
    "phone": {"patterns": [r"(?i)phone|mobile|tel|contact_no|手机|电话"], "label": "手机号"},
    "id_card": {"patterns": [r"(?i)id[_]?card|idno|id_no|证件|身份证|cert"], "label": "身份证号"},
    "bank": {"patterns": [r"(?i)bank|account_no|card_no|卡号|账号"], "label": "银行账号"},
    "email": {"patterns": [r"(?i)email|e_mail|mail|邮箱"], "label": "邮箱"},
    "name": {"patterns": [r"(?i)name|customer|client|user_name|姓名|客户|联系人"], "label": "姓名"},
    "address": {"patterns": [r"(?i)address|addr|住址|地址|location"], "label": "地址"},
}

# 角色 -> 是否脱敏
MASK_ROLES = {"viewer": True, "analyst": True, "admin": False}


def detect_sensitive_columns(column_names: list[str]) -> dict[str, str]:
    """按列名识别敏感类型: {column: sensitive_type}."""
    detected: dict[str, str] = {}
    for column in column_names:
        for s_type, rule in SENSITIVE_RULES.items():
            if any(re.search(p, column) for p in rule["patterns"]):
                detected[column] = s_type
                break
    return detected


def mask_value(value: Any, s_type: str) -> Any:
    """按敏感类型掩码."""
    if value is None:
        return None
    text = str(value)
    if not text:
        return ""
    if s_type == "name":
        return _mask_name(text)
    if s_type == "phone":
        return _mask_middle(text, 3, 4)
    if s_type == "id_card":
        return _mask_middle(text, 3, 4)
    if s_type == "bank":
        return _mask_middle(text, 4, 4)
    if s_type == "email":
        return _mask_email(text)
    if s_type == "address":
        return text[:2] + "****" if len(text) > 2 else "****"
    return _mask_middle(text, 1, 1)


def _mask_name(text: str) -> str:
    if len(text) <= 1:
        return "*"
    if re.match(r"^[\u4e00-\u9fff]+$", text):
        return text[0] + "*" * (len(text) - 1)  # 张* / 张三*
    return text[0] + "*" * max(len(text) - 1, 1)  # J****


def _mask_middle(text: str, head: int, tail: int) -> str:
    if len(text) <= head + tail:
        return "*" * len(text)
    return text[:head] + "*" * (len(text) - head - tail) + text[-tail:]


def _mask_email(text: str) -> str:
    if "@" not in text:
        return _mask_middle(text, 1, 1)
    local, domain = text.split("@", 1)
    local_masked = local[0] + "*" * max(len(local) - 1, 1) if local else "*"
    return f"{local_masked}@{domain}"


def apply_masking(rows: list[dict], sensitive: dict[str, str], role: str) -> list[dict]:
    """对行集按角色应用脱敏; 脱敏关闭时原样返回."""
    if not MASK_ROLES.get(role, True) or not sensitive or not rows:
        return rows
    masked: list[dict] = []
    for row in rows:
        item = dict(row)
        for column, s_type in sensitive.items():
            if column in item:
                item[column] = mask_value(item[column], s_type)
        masked.append(item)
    return masked


def masking_policies() -> list[dict]:
    """策略清单, 供治理台展示."""
    return [
        {
            "sensitive_type": s_type,
            "label": rule["label"],
            "patterns": rule["patterns"],
            "example": _example(s_type),
            "mask_roles": [r for r, m in MASK_ROLES.items() if m],
        }
        for s_type, rule in SENSITIVE_RULES.items()
    ]


def _example(s_type: str) -> str:
    samples = {
        "phone": "138****5678",
        "id_card": "110***********1234",
        "bank": "**** **** **** 1234",
        "email": "a***@example.com",
        "name": "张**",
        "address": "北京****",
    }
    return samples.get(s_type, "****")
