from __future__ import annotations
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent.i_agent import Message


DEFAULT_LOG_PATH = Path("agent_messages.log")


class MessageLoggerService:
    def __init__(self, log_path: Path = DEFAULT_LOG_PATH):
        self._log_path = log_path
        self._enabled = True

    def configure(self, log_path: Path) -> None:
        """Override the log file path. Call before reset() to take effect."""
        self._log_path = log_path

    def disable(self) -> None:
        """Suppress all writes (useful in tests)."""
        self._enabled = False

    def enable(self) -> None:
        self._enabled = True

    def reset(self) -> None:
        """Clear the log file and write the session header."""
        if not self._enabled:
            return
        try:
            with open(self._log_path, "w", encoding="utf-8") as f:
                f.write("=== Agent Started ===\n")
        except Exception as e:
            print(f"Warning: Could not initialize log file: {e}")

    def log(self, message: Any) -> None:
        """Append a JSON-serialised message to the log file."""
        if not self._enabled:
            return
        try:
            data = message if isinstance(message, dict) else message.to_dict()
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        except Exception as e:
            print(f"Warning: Could not write to log file: {e}")

    @property
    def log_path(self) -> Path:
        return self._log_path


message_logger_service = MessageLoggerService()
