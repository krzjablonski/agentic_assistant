from __future__ import annotations

import asyncio
import threading
from concurrent.futures import Future
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Coroutine, Optional, TypeVar

from agent.agent_event import AgentEvent, AgentEventType
from agent.message_factory import message_from_dict
from agent.simple_agent.simple_agent import SimpleAgent
from memory.short_term_memory import ShortTermMemory
from message_logger.agent_event_subscriber import AgentEventSubscriber
from message_logger.session_logger import SessionLogger

if TYPE_CHECKING:
    from typing import Type

    from pydantic import BaseModel

T = TypeVar("T")
RUN_LOG_DIR = Path(__file__).resolve().parents[1] / "src" / "data" / "agent_runs"


class AsyncRuntime:
    """Dedicated asyncio loop running in a background thread for Streamlit."""

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._ready = threading.Event()
        self._stopped = False
        self._thread = threading.Thread(
            target=self._run_loop,
            name="personal-ops-async-runtime",
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
    log_path: Optional[str] = None
    jsonl_path: Optional[str] = None


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


def _create_session_logger(agent: SimpleAgent) -> SessionLogger:
    logger = SessionLogger(session_id=agent.session_id, log_dir=RUN_LOG_DIR)
    logger.log_system_prompt(agent.system_prompt, agent_name=agent.name)
    return logger


def _log_input_messages(logger: SessionLogger, messages: list[dict]) -> None:
    for message in messages:
        logger.log_message(message_from_dict(message))


async def run_agent_turn(
    agent: SimpleAgent,
    messages: list[dict],
    short_term_memory: Optional[ShortTermMemory],
    subscriber: EventBufferSubscriber,
    response_schema: Optional["Type[BaseModel]"] = None,
) -> AgentRunResult:
    session_logger = _create_session_logger(agent)
    agent.subscribe(subscriber)
    agent.subscribe(session_logger)
    try:
        processed_messages = messages
        if short_term_memory is not None:
            processed_messages = await short_term_memory.process_messages(messages)

        _log_input_messages(session_logger, processed_messages)
        response = await agent.run(
            user_query=processed_messages,
            response_schema=response_schema,
        )  # type: ignore
        events = subscriber.snapshot()
        return AgentRunResult(
            response=response,
            status=agent.status.value,
            iterations=agent.iteration_count,
            events=events,
            usage=extract_latest_usage(events),
            log_path=str(session_logger.log_path),
            jsonl_path=str(session_logger.jsonl_path),
        )
    finally:
        agent.unsubscribe(session_logger)
        agent.unsubscribe(subscriber)
