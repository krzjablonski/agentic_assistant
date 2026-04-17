import sqlite3
from dataclasses import dataclass
from typing import List, Optional
from pathlib import Path


@dataclass
class MemoryEntry:
    """A single memory record."""

    id: int
    content: str
    category: str
    created_at: str
    last_accessed_at: str
    access_count: int


MEMORY_CATEGORIES = ("preference", "fact", "person", "instruction", "general")


class LongTermMemory:
    """Persistent long-term memory using SQLite with FTS5 full-text search.

    Stores facts, preferences, and information across sessions.
    """

    DB_PATH = Path(__file__).parent.parent / "data" / "agent_memory.db"

    def __init__(self):
        self._conn: Optional[sqlite3.Connection] = None
        self._ensure_db()

    def _ensure_db(self) -> None:
        """Create database and tables if they don't exist."""
        self.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.DB_PATH), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")

        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                content          TEXT NOT NULL,
                category         TEXT NOT NULL DEFAULT 'general',
                created_at       TEXT NOT NULL DEFAULT (datetime('now')),
                last_accessed_at TEXT NOT NULL DEFAULT (datetime('now')),
                access_count     INTEGER NOT NULL DEFAULT 0
            )
        """)

        self._conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
            USING fts5(content, category, content=memories, content_rowid=id)
        """)

        self._conn.executescript("""
            CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
                INSERT INTO memories_fts(rowid, content, category)
                VALUES (new.id, new.content, new.category);
            END;

            CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, content, category)
                VALUES ('delete', old.id, old.content, old.category);
            END;

            CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, content, category)
                VALUES ('delete', old.id, old.content, old.category);
                INSERT INTO memories_fts(rowid, content, category)
                VALUES (new.id, new.content, new.category);
            END;
        """)
        self._conn.commit()

    def save(self, content: str, category: str = "general") -> int:
        """Save a new memory. Returns the memory ID."""
        if category not in MEMORY_CATEGORIES:
            raise ValueError(
                f"Invalid category '{category}'. "
                f"Allowed: {', '.join(MEMORY_CATEGORIES)}"
            )
        cursor = self._conn.execute(
            "INSERT INTO memories (content, category) VALUES (?, ?)",
            (content, category),
        )
        self._conn.commit()
        return cursor.lastrowid

    def recall(
        self,
        query: str,
        category: Optional[str] = None,
        limit: int = 5,
    ) -> List[MemoryEntry]:
        """Search memories using FTS5 full-text search.

        Results are ranked by relevance (BM25).
        Accessing a memory updates its last_accessed_at and access_count.
        """
        safe_query = '"' + query.replace('"', '""') + '"'

        if category:
            rows = self._conn.execute(
                """
                SELECT m.id, m.content, m.category, m.created_at,
                       m.last_accessed_at, m.access_count
                FROM memories_fts fts
                JOIN memories m ON fts.rowid = m.id
                WHERE memories_fts MATCH ? AND m.category = ?
                ORDER BY fts.rank
                LIMIT ?
                """,
                (safe_query, category, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT m.id, m.content, m.category, m.created_at,
                       m.last_accessed_at, m.access_count
                FROM memories_fts fts
                JOIN memories m ON fts.rowid = m.id
                WHERE memories_fts MATCH ?
                ORDER BY fts.rank
                LIMIT ?
                """,
                (safe_query, limit),
            ).fetchall()

        entries = [
            MemoryEntry(
                id=row[0],
                content=row[1],
                category=row[2],
                created_at=row[3],
                last_accessed_at=row[4],
                access_count=row[5],
            )
            for row in rows
        ]

        if entries:
            ids = [e.id for e in entries]
            placeholders = ",".join("?" for _ in ids)
            self._conn.execute(
                f"""
                UPDATE memories
                SET last_accessed_at = datetime('now'), access_count = access_count + 1
                WHERE id IN ({placeholders})
                """,
                ids,
            )
            self._conn.commit()

        return entries

    def delete(self, memory_id: int) -> bool:
        """Delete a memory by ID. Returns True if found and deleted."""
        cursor = self._conn.execute(
            "DELETE FROM memories WHERE id = ?", (memory_id,)
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def get_all(
        self, category: Optional[str] = None, limit: int = 50
    ) -> List[MemoryEntry]:
        """Get all memories, optionally filtered by category."""
        if category:
            rows = self._conn.execute(
                "SELECT id, content, category, created_at, last_accessed_at, access_count "
                "FROM memories WHERE category = ? ORDER BY created_at DESC LIMIT ?",
                (category, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id, content, category, created_at, last_accessed_at, access_count "
                "FROM memories ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()

        return [
            MemoryEntry(
                id=r[0],
                content=r[1],
                category=r[2],
                created_at=r[3],
                last_accessed_at=r[4],
                access_count=r[5],
            )
            for r in rows
        ]
