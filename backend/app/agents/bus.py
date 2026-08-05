"""事件总线抽象 (M4): 进程内总线 + Kafka 适配器.

设计: 编排器把 Agent 事件发布到总线, 总线分发到订阅者 (审计/观测/持久化).
生产环境配置 KAFKA_BROKERS 后自动切换 Kafka 适配器, 业务代码不变.
"""
import asyncio
import json
import logging
import os
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

EventHandler = Callable[[dict], Awaitable[None]]


class EventBus(ABC):
    """消息总线契约 (M4): 发布 / 订阅."""

    @abstractmethod
    async def publish(self, topic: str, event: dict) -> None:
        """发布事件."""

    @abstractmethod
    def subscribe(self, handler: EventHandler) -> None:
        """注册订阅者."""


class InProcessBus(EventBus):
    """进程内总线: asyncio 队列缓冲 + 后台 Worker 分发 (零依赖)."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[tuple[str, dict]] = asyncio.Queue()
        self._handlers: list[EventHandler] = []
        self._worker: asyncio.Task | None = None
        self._started = False
        self.published_count = 0

    def subscribe(self, handler: EventHandler) -> None:
        self._handlers.append(handler)

    async def publish(self, topic: str, event: dict) -> None:
        self.published_count += 1
        await self._queue.put((topic, event))

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._worker = asyncio.create_task(self._run(), name="event-bus-worker")

    async def stop(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass
            self._worker = None
        self._started = False

    async def _run(self) -> None:
        while True:
            topic, event = await self._queue.get()
            for handler in list(self._handlers):
                try:
                    await handler({"topic": topic, **event})
                except Exception:
                    logger.exception("总线订阅者处理失败: topic=%s", topic)

    def stats(self) -> dict:
        return {"type": "in-process", "published": self.published_count, "queue_size": self._queue.qsize()}


class KafkaBus(EventBus):
    """Kafka 适配器 (M4): 配置 KAFKA_BROKERS 后启用, 需 aiokafka 可选依赖."""

    def __init__(self, brokers: str) -> None:
        self._brokers = brokers
        self._handlers: list[EventHandler] = []

    def subscribe(self, handler: EventHandler) -> None:
        self._handlers.append(handler)

    async def publish(self, topic: str, event: dict) -> None:
        try:
            from aiokafka import AIOKafkaProducer  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError("Kafka 总线需要安装 aiokafka") from exc
        producer = AIOKafkaProducer(bootstrap_servers=self._brokers)
        await producer.start()
        try:
            await producer.send(topic, json.dumps(event, ensure_ascii=False).encode())
        finally:
            await producer.stop()

    def stats(self) -> dict:
        return {"type": "kafka", "brokers": self._brokers}


def get_bus() -> EventBus:
    """按环境选择总线: KAFKA_BROKERS -> Kafka; 否则进程内."""
    brokers = os.getenv("KAFKA_BROKERS", "")
    if brokers:
        return KafkaBus(brokers)
    return InProcessBus()


# 应用生命周期内唯一实例
bus = get_bus()


async def _log_subscriber(event: dict) -> None:
    """默认订阅者: 事件日志 (供后端观测)."""
    logger.info("[bus] %s | %s", event.get("topic"), json.dumps(event, ensure_ascii=False, default=str)[:200])


bus.subscribe(_log_subscriber)
