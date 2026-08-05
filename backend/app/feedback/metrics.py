"""轻量运行指标: 请求量 / 时延 / 错误率 (内存实现, M1 基础观测).

M5 将替换为 Prometheus + OpenTelemetry 全链路 Trace.
"""
import threading
import time
from collections import deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

_MEASURE_WINDOW = 300  # 秒

_lock = threading.Lock()
_request_times: deque[tuple[float, float]] = deque()  # (ts, latency)
_status_counts: dict[int, int] = {}


class MetricsMiddleware(BaseHTTPMiddleware):
    """记录每个请求的时延与状态码, 用于 /api/feedback/metrics."""

    async def dispatch(self, request: Request, call_next):
        start = time.monotonic()
        response = await call_next(request)
        latency = time.monotonic() - start
        now = time.time()
        with _lock:
            _request_times.append((now, latency))
            _status_counts[response.status_code] = _status_counts.get(response.status_code, 0) + 1
            # 清理窗口外的样本
            while _request_times and _request_times[0][0] < now - _MEASURE_WINDOW:
                _request_times.popleft()
        return response


def snapshot() -> dict:
    """导出近 5 分钟运行指标."""
    with _lock:
        times = list(_request_times)
        statuses = dict(_status_counts)
    total = len(times)
    errors = sum(v for k, v in statuses.items() if k >= 500)
    if total:
        latencies = [t[1] for t in times]
        avg = round(sum(latencies) / total * 1000, 2)
        p95 = round(sorted(latencies)[int(total * 0.95) - 1] * 1000, 2) if total > 1 else avg
        error_rate = round(errors / total * 100, 2)
    else:
        avg = p95 = 0.0
        error_rate = 0.0
    return {
        "window_seconds": _MEASURE_WINDOW,
        "requests": total,
        "avg_latency_ms": avg,
        "p95_latency_ms": p95,
        "error_rate": error_rate,
        "status_distribution": statuses,
    }
