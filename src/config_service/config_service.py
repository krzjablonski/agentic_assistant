import os
import sqlite3
import base64
from dataclasses import dataclass
from typing import Optional
from pathlib import Path
from collections import OrderedDict

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes


@dataclass
class ConfigEntry:
    key: str
    value: Optional[str]
    group_name: str
    label: str
    description: str
    is_secret: bool
    value_type: str


CONFIG_REGISTRY: list[dict] = [
    # LLM
    {
        "key": "llm.anthropic_api_key",
        "group": "LLM",
        "label": "Anthropic API Key",
        "description": "API key for Anthropic Claude models",
        "secret": True,
        "type": "string",
        "env": "ANTHROPIC_API_KEY",
    },
    {
        "key": "llm.openai_api_key",
        "group": "LLM",
        "label": "OpenAI API Key",
        "description": "API key for OpenAI models",
        "secret": True,
        "type": "string",
        "env": "OPEN_AI_API_KEY",
    },
    {
        "key": "llm.google_gemini_api_key",
        "group": "LLM",
        "label": "Google Gemini API Key",
        "description": "API key for Google Gemini models",
        "secret": True,
        "type": "string",
        "env": "GEMINI_API_KEY",
    },
    {
        "key": "llm.openrouter_api_key",
        "group": "LLM",
        "label": "OpenRouter API Key",
        "description": "API key for OpenRouter models",
        "secret": True,
        "type": "string",
        "env": "OPENROUTER_API_KEY",
    },
    # Email
    {
        "key": "email.from",
        "group": "Email",
        "label": "Gmail Address",
        "description": "Gmail address used as the sender",
        "secret": False,
        "type": "email",
        "env": "EMAIL_FROM",
    },
    {
        "key": "email.to",
        "group": "Email",
        "label": "Default Recipient",
        "description": "Default email recipient address",
        "secret": False,
        "type": "email",
        "env": "EMAIL_TO",
    },
    {
        "key": "email.app_password",
        "group": "Email",
        "label": "Gmail App Password",
        "description": "App password for Gmail SMTP authentication",
        "secret": True,
        "type": "string",
        "env": "EMAIL_APP_PASSWORD",
    },
    {
        "key": "email.attachments_dir",
        "group": "Email",
        "label": "Attachments Directory",
        "description": "Directory path for saving downloaded attachments",
        "secret": False,
        "type": "path",
        "env": "ATTACHMENTS_DIR",
    },
    # Calendar
    {
        "key": "calendar.service_account_key_path",
        "group": "Calendar",
        "label": "Service Account Key (JSON Content)",
        "description": "Paste the contents of your Google service account JSON key file here. Note: This data will not be stored in the database, but saved to a local file.",
        "secret": False,
        "type": "json_content",
        "env": "GOOGLE_SERVICE_ACCOUNT_KEY_PATH",
    },
    {
        "key": "calendar.calendar_id",
        "group": "Calendar",
        "label": "Google Calendar ID",
        "description": "Google Calendar ID to use for events",
        "secret": False,
        "type": "string",
        "env": "GOOGLE_CALENDAR_ID",
    },
    # Web Search
    {
        "key": "web_search.tavily_api_key",
        "group": "Web Search",
        "label": "Tavily API Key",
        "description": "API key for Tavily Web Search and Extract",
        "secret": True,
        "type": "string",
        "env": "TAVILY_API_KEY",
    },
    # File System
    {
        "key": "filesystem.base_dir",
        "group": "File System",
        "label": "Base Directory",
        "description": "Root directory the agent is allowed to read from and write to. All file paths are resolved relative to this directory.",
        "secret": False,
        "type": "path",
        "env": "FILESYSTEM_BASE_DIR",
    },
]


class ConfigService:
    DB_PATH = Path(__file__).parent.parent / "data" / "agent_config.db"
    _PBKDF2_ITERATIONS = 480_000

    def __init__(self):
        self._fernet: Optional[Fernet] = None
        self._env_key_map = {entry["key"]: entry["env"] for entry in CONFIG_REGISTRY}
        self._secret_keys = {
            entry["key"] for entry in CONFIG_REGISTRY if entry["secret"]
        }
        self._ensure_db()

    def _ensure_db(self):
        self.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.DB_PATH), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS config_settings (
                key         TEXT PRIMARY KEY,
                value       TEXT NOT NULL,
                group_name  TEXT NOT NULL,
                label       TEXT NOT NULL,
                description TEXT DEFAULT '',
                is_secret   INTEGER DEFAULT 0,
                value_type  TEXT DEFAULT 'string',
                updated_at  TEXT DEFAULT (datetime('now'))
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS config_meta (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    # --- Encryption ---

    def has_master_password(self) -> bool:
        cursor = self._conn.execute(
            "SELECT value FROM config_meta WHERE key = 'encryption_salt'"
        )
        return cursor.fetchone() is not None

    def is_locked(self) -> bool:
        return self._fernet is None

    def set_master_password(self, password: str) -> None:
        salt = os.urandom(16)
        fernet_key = self._derive_key(password, salt)
        self._fernet = Fernet(fernet_key)

        check_token = self._fernet.encrypt(b"__config_check__")

        self._conn.execute(
            "INSERT OR REPLACE INTO config_meta (key, value) VALUES (?, ?)",
            ("encryption_salt", base64.b64encode(salt).decode()),
        )
        self._conn.execute(
            "INSERT OR REPLACE INTO config_meta (key, value) VALUES (?, ?)",
            ("encryption_check", check_token.decode()),
        )
        self._conn.commit()

    def unlock(self, master_password: str) -> bool:
        cursor = self._conn.execute(
            "SELECT value FROM config_meta WHERE key = 'encryption_salt'"
        )
        row = cursor.fetchone()
        if not row:
            return False

        salt = base64.b64decode(row[0])
        fernet_key = self._derive_key(master_password, salt)
        fernet = Fernet(fernet_key)

        cursor = self._conn.execute(
            "SELECT value FROM config_meta WHERE key = 'encryption_check'"
        )
        check_row = cursor.fetchone()
        if not check_row:
            return False

        try:
            decrypted = fernet.decrypt(check_row[0].encode())
            if decrypted == b"__config_check__":
                self._fernet = fernet
                return True
        except InvalidToken:
            pass

        return False

    def _derive_key(self, password: str, salt: bytes) -> bytes:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=self._PBKDF2_ITERATIONS,
        )
        return base64.urlsafe_b64encode(kdf.derive(password.encode()))

    # --- Config access ---

    def get(self, key: str) -> Optional[str]:
        cursor = self._conn.execute(
            "SELECT value, is_secret FROM config_settings WHERE key = ?", (key,)
        )
        row = cursor.fetchone()
        if row:
            value, is_secret = row
            if is_secret and self._fernet:
                try:
                    return self._fernet.decrypt(value.encode()).decode()
                except InvalidToken:
                    return None
            elif is_secret and not self._fernet:
                # Encrypted value but no key available — fall through to env var
                pass
            else:
                return value

        # Fallback to environment variable
        env_key = self._env_key_map.get(key)
        if env_key:
            return os.getenv(env_key)
        return None

    def set(self, key: str, value: str) -> None:
        schema_entry = next(
            (entry for entry in CONFIG_REGISTRY if entry["key"] == key), None
        )
        if not schema_entry:
            raise ValueError(f"Unknown config key: {key}")

        stored_value = value
        is_secret = schema_entry["secret"]
        if is_secret and self._fernet:
            stored_value = self._fernet.encrypt(value.encode()).decode()

        self._conn.execute(
            """
            INSERT OR REPLACE INTO config_settings
                (key, value, group_name, label, description, is_secret, value_type, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                key,
                stored_value,
                schema_entry["group"],
                schema_entry["label"],
                schema_entry.get("description", ""),
                1 if is_secret else 0,
                schema_entry["type"],
            ),
        )
        self._conn.commit()

    def get_all_by_group(self) -> dict[str, list[ConfigEntry]]:
        groups: dict[str, list[ConfigEntry]] = OrderedDict()

        for schema_entry in CONFIG_REGISTRY:
            key = schema_entry["key"]
            group = schema_entry["group"]

            current_value = self.get(key)

            entry = ConfigEntry(
                key=key,
                value=current_value,
                group_name=group,
                label=schema_entry["label"],
                description=schema_entry.get("description", ""),
                is_secret=schema_entry["secret"],
                value_type=schema_entry["type"],
            )

            if group not in groups:
                groups[group] = []
            groups[group].append(entry)

        return groups

    def seed_from_env(self) -> int:
        imported = 0
        for entry in CONFIG_REGISTRY:
            env_val = os.getenv(entry["env"])
            if env_val:
                self.set(entry["key"], env_val)
                imported += 1
        return imported


config_service = ConfigService()
