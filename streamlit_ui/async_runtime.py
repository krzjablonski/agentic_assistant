from __future__ import annotations

import asyncio
import threading
from concurrent.futures import Future
from dataclasses import dataclass
from typing import Any, Coroutine, Optional, TypeVar

from agent.agent_event import AgentEvent, AgentEventType
from agent.simple_agent.simple_agent import SimpleAgent
from memory.short_term_memory import ShortTermMemory
from message_logger.agent_event_subscriber import AgentEventSubscriber

T = TypeVar("T")


class AsyncRuntime:
    """Dedicated asyncio loop running in a background thread for Streamlit."""

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._ready = threading.Event()
        self._stopped = False
        self._thread = threading.Thread(
            target=self._run_loop,
            name="streamlit-ui-async-runtime",
            daemon=True,
        )
        self._thread.start()
        self._ready.wait()

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._ready.set()
        self._loop.run_forever()

        pending = [task for task in asyncio.all_tasks(self._loop) if not task.done()]
        for task in pending:
            task.cancel()
        if pending:
            self._loop.run_until_complete(
                asyncio.gather(*pending, return_exceptions=True)
            )
        self._loop.close()

    def submit(self, coro: Coroutine[Any, Any, T]) -> Future[T]:
        if self._stopped:
            raise RuntimeError("Async runtime has already been stopped.")
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    def run(self, coro: Coroutine[Any, Any, T], timeout: Optional[float] = None) -> T:
        return self.submit(coro).result(timeout=timeout)

    def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)


class EventBufferSubscriber(AgentEventSubscriber):
    """Thread-safe in-memory event collector for live UI updates."""

    def __init__(self) -> None:
        self._events: list[AgentEvent] = []
        self._lock = threading.Lock()

    def on_event(self, event: AgentEvent) -> None:
        with self._lock:
            self._events.append(event)

    def snapshot(self) -> list[AgentEvent]:
        with self._lock:
            return list(self._events)


@dataclass
class AgentRunResult:
    response: str | dict
    status: str
    iterations: int
    events: list[AgentEvent]
    usage: Optional[dict]


@dataclass
class AgentRunHandle:
    future: Future[AgentRunResult]
    subscriber: EventBufferSubscriber
    assistant_index: int
    event_log_index: int


def extract_latest_usage(events: list[AgentEvent]) -> Optional[dict]:
    for event in reversed(events):
        if (
            event.event_type == AgentEventType.LLM_RESPONSE
            and event.data
            and "usage" in event.data
        ):
            return event.data["usage"]
    return None


async def run_agent_turn(
    agent: SimpleAgent,
    messages: list[dict],
    short_term_memory: Optional[ShortTermMemory],
    subscriber: EventBufferSubscriber,
) -> AgentRunResult:
    agent.subscribe(subscriber)
    try:
        processed_messages = messages
        if short_term_memory is not None:
            processed_messages = await short_term_memory.process_messages(messages)

        response = await agent.run(processed_messages)
        events = subscriber.snapshot()
        return AgentRunResult(
            response=response,
            status=agent.status.value,
            iterations=agent.iteration_count,
            events=events,
            usage=extract_latest_usage(events),
        )
    finally:
        agent.unsubscribe(subscriber)
