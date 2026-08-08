"""观测遥测 (M6): OTLP/HTTP JSON 导出, 零额外依赖 (httpx).

配置 OTEL_ENDPOINT (如 http://localhost:4318) 后启用:
- 关键操作 (采集 / 指标查询 / Agent 任务 / 文档入库) 以 span 形式上报;
- 未配置时 span() 为空实现, 不影响任何业务路径 (零开销, 不抛错).
协议: OTLP/HTTP JSON 编码 (application/json), 兼容 Jaeger / Grafana Tempo /
Docker 内置 OTLP 收集器等标准 OTLP 接收端.
"""
import contextlib
import secrets
import time

import httpx

from app.core.config import settings


def configured() -> bool:
    return bool(settings.otel_endpoint)


def _hex(nbytes: int) -> str:
    return secrets.token_hex(nbytes)


@contextlib.asynccontextmanager
async def span(name: str, **attributes):
    """记录一段操作的耗时与状态, 配置 OTLP 时上报 (尽力而为, 不抛错)."""
    start_ns = time.time_ns()
    trace_id = _hex(16)
    span_id = _hex(8)
    status_code = 0
    try:
        yield
    except BaseException as exc:
        status_code = 2
        attributes = {**attributes, "error": str(exc)[:500]}
        raise
    finally:
        end_ns = time.time_ns()
        if configured():
            try:
                await _export_span(trace_id, span_id, name, start_ns, end_ns, status_code, attributes)
            except Exception:
                pass  # 遥测失败绝不影响业务


async def _export_span(
    trace_id: str,
    span_id: str,
    name: str,
    start_ns: int,
    end_ns: int,
    status_code: int,
    attributes: dict,
) -> None:
    attrs = [
        {"key": k, "value": {"stringValue": str(v)}}
        for k, v in [("service.name", settings.otel_service_name), *attributes.items()]
    ]
    payload = {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": settings.otel_service_name}}
                    ]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "budai-agent-mesh"},
                        "spans": [
                            {
                                "traceId": trace_id,
                                "spanId": span_id,
                                "name": name,
                                "kind": 2,  # SPAN_KIND_SERVER
                                "startTimeUnixNano": str(start_ns),
                                "endTimeUnixNano": str(end_ns),
                                "attributes": attrs,
                                "status": {"code": status_code},
                            }
                        ],
                    }
                ],
            }
        ]
    }
    async with httpx.AsyncClient(timeout=5) as client:
        await client.post(
            f"{settings.otel_endpoint.rstrip('/')}/v1/traces",
            json=payload,
            headers={"Content-Type": "application/json"},
        )
