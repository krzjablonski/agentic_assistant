from message_logger.agent_event_subscriber import AgentEventSubscriber
from typing import Optional

import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.agent_event import AgentEvent
    from agent.i_agent import Message


class SessionLogger(AgentEventSubscriber):
    def __init__(self, session_id: str, log_dir: Path, clean: bool = False) -> None:
        log_dir.mkdir(parents=True, exist_ok=True)
        self._log_path = log_dir / f"{session_id}.log"
        self._jsonl_path = log_dir / f"{session_id}.jsonl"
        if clean:
            for p in (self._log_path, self._jsonl_path):
                if p.exists():
                    p.unlink()
        self._is_new = not self._log_path.exists() or self._log_path.stat().st_size == 0
        self._write_separator()

    def _write_separator(self) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._append(f"\n{'=' * 60}")
        self._append(f"  NEW REQUEST @ {timestamp}")
        self._append(f"{'=' * 60}\n")
        self._append_json({"type": "session_start", "ts": timestamp})

    def on_event(self, event: "AgentEvent") -> None:
        self.log_event(event)

    def log_system_prompt(self, prompt: str, agent_name: Optional[str] = None) -> None:
        if not self._is_new:
            return
        if agent_name:
            self._append(f"[{agent_name.upper()}]")
        self._append("[SYSTEM PROMPT]")
        self._append(prompt)
        self._append("")
        self._append_json(
            {
                "type": "system_prompt",
                "ts": datetime.now().isoformat(),
                "data": {"text": prompt},
            }
        )

    def log_message(self, message: "Message") -> None:
        role = message.role.upper()
        if isinstance(message.content, str):
            content = message.content
        else:
            content = json.dumps(
                [
                    block.to_dict() if hasattr(block, "to_dict") else str(block)
                    for block in message.content
                ],
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        self._append(f"[{role}] {content}")
        self._append_json(
            {
                "type": "message",
                "ts": datetime.now().isoformat(),
                "data": {"role": message.role, "content": content},
            }
        )

    def log_event(self, event: "AgentEvent") -> None:
        from agent.agent_event import AgentEventType

        ts = event.timestamp.strftime("%H:%M:%S")
        data = event.data or {}
        a = f"[{event.agent_name}] " if event.agent_name else ""

        # --- Text log ---
        if event.event_type == AgentEventType.LLM_RESPONSE:
            usage = data.get("usage", {})
            tokens_in = usage.get("input_tokens", "?")
            tokens_out = usage.get("output_tokens", "?")
            tools = data.get("tools_to_be_used", [])
            tools_str = f" | tools: {tools}" if tools else ""
            self._append(
                f"  [{ts}] {a}[LLM] stop={data.get('stop_reason')} "
                f"| tokens: {tokens_in}→{tokens_out}{tools_str}"
            )

        elif event.event_type == AgentEventType.TOOL_CALL:
            raw_args = data.get("args", {})
            unpacked_args = self._unpack_json_strings(raw_args)
            args = json.dumps(unpacked_args, ensure_ascii=False, indent=2, default=str)
            self._append(f"  [{ts}] {a}[TOOL_CALL] {data.get('tool_name')}(\n{args}\n)")

        elif event.event_type == AgentEventType.TOOL_RESULT:
            result = data.get("result", "")
            error = " [ERROR]" if data.get("is_error") else ""
            result = self._try_format_json(result)
            self._append(
                f"  [{ts}] {a}[TOOL_RESULT]{error} {data.get('tool_name')} →\n{result}"
            )

        elif event.event_type == AgentEventType.STATUS_CHANGE:
            self._append(f"  [{ts}] {a}[STATUS] {data.get('status')}")

        elif event.event_type == AgentEventType.ASSISTANT_MESSAGE:
            self._append(f"  [{ts}] {a}[ASSISTANT] {data.get('text', event.message)}")

        elif event.event_type == AgentEventType.ERROR:
            self._append(f"  [{ts}] {a}[ERROR] {event.message}")

        elif event.event_type == AgentEventType.REASONING:
            self._append(f"  [{ts}] {a}[REASONING] {data.get('text', event.message)}")

        elif event.event_type == AgentEventType.SELF_REFLECTION:
            self._append(f"  [{ts}] {a}[REFLECTION] {event.message}")

        elif event.event_type in (
            AgentEventType.PLAN_CREATED,
            AgentEventType.PLAN_UPDATED,
        ):
            self._append(
                f"  [{ts}] {a}[{event.event_type.value.upper()}] {event.message}"
            )
            plan_text = None
            if isinstance(data, dict):
                plan_text = data.get("plan")
            elif isinstance(data, str):
                try:
                    plan_text = json.loads(data).get("plan")
                except (json.JSONDecodeError, AttributeError):
                    pass
            if plan_text:
                self._append(plan_text)

        elif event.event_type == AgentEventType.USER_MESSAGE:
            pass  # already logged via log_message

        else:
            self._append(f"  [{ts}] {a}[{event.event_type.value}] {event.message}")

        # --- JSONL log (structured) ---
        if event.event_type != AgentEventType.USER_MESSAGE:
            self._append_json(
                {
                    "type": event.event_type.value,
                    "ts": event.timestamp.isoformat(),
                    "iteration": event.iteration,
                    "agent_name": event.agent_name,
                    "message": event.message,
                    "data": data,
                }
            )

    @staticmethod
    def _unpack_json_strings(obj: object) -> object:
        """Recursively parse string values that contain JSON."""
        if isinstance(obj, dict):
            return {k: SessionLogger._unpack_json_strings(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [SessionLogger._unpack_json_strings(item) for item in obj]
        if isinstance(obj, str):
            stripped = obj.strip()
            if stripped and stripped[0] in ("{", "["):
                try:
                    parsed = json.loads(stripped)
                    return SessionLogger._unpack_json_strings(parsed)
                except (json.JSONDecodeError, TypeError):
                    pass
        return obj

    @staticmethod
    def _try_format_json(text: str) -> str:
        """Try to pretty-print text as JSON, unpacking nested JSON strings."""
        if not isinstance(text, str):
            return str(text)
        stripped = text.strip()
        if stripped and stripped[0] in ("{", "["):
            try:
                parsed = json.loads(stripped)
                unpacked = SessionLogger._unpack_json_strings(parsed)
                return json.dumps(unpacked, ensure_ascii=False, indent=2, default=str)
            except (json.JSONDecodeError, TypeError):
                pass
        return text

    def _append(self, line: str) -> None:
        try:
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception as e:
            print(f"Warning: Could not write to session log: {e}")

    def _append_json(self, entry: dict) -> None:
        try:
            with open(self._jsonl_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        except Exception as e:
            print(f"Warning: Could not write to JSONL log: {e}")

    @property
    def log_path(self) -> Path:
        return self._log_path

    @property
    def jsonl_path(self) -> Path:
        return self._jsonl_path
