"""Restore account-scoped conversations from existing LangGraph checkpoints."""
import sqlite3
from contextlib import closing

from fastapi import HTTPException


class ConversationHistory:
    def __init__(self, agent, database_path):
        self.agent = agent
        self.database_path = str(database_path)
        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS conversation_settings (thread_id TEXT PRIMARY KEY, title TEXT, archived INTEGER NOT NULL DEFAULT 0 CHECK (archived IN (0,1)))")
            connection.commit()

    def _messages(self, snapshot):
        result = []
        for message in snapshot.values.get("messages", []):
            if message.type not in {"human", "ai"}:
                continue
            metadata = message.additional_kwargs or {}
            result.append({
                "role": "user" if message.type == "human" else "assistant",
                "content": str(message.content),
                "sources": metadata.get("sources", []),
                "status": metadata.get("status", "unknown"),
            })
        return result

    def is_archived(self, scope, thread_id):
        with closing(sqlite3.connect(self.database_path)) as connection:
            row = connection.execute("SELECT archived FROM conversation_settings WHERE thread_id = ?", (f"{scope}:{thread_id}",)).fetchone()
        return bool(row and row[0])

    def get(self, scope, thread_id):
        internal_id = f"{scope}:{thread_id}"
        # Checking the scoped row first also avoids revealing other users' IDs.
        with closing(sqlite3.connect(self.database_path)) as connection:
            exists = connection.execute(
                "SELECT 1 FROM checkpoints WHERE thread_id = ? AND checkpoint_ns = '' LIMIT 1",
                (internal_id,),
            ).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="Conversation not found")
        snapshot = self.agent.get_state({"configurable": {"thread_id": internal_id}})
        messages = self._messages(snapshot)
        with closing(sqlite3.connect(self.database_path)) as connection:
            settings = connection.execute("SELECT title, archived FROM conversation_settings WHERE thread_id = ?", (internal_id,)).fetchone()
        first = next((item["content"] for item in messages if item["role"] == "user"), "Conversation")
        return {"thread_id": thread_id, "messages": messages, "title": settings[0] if settings and settings[0] else first[:80], "archived": bool(settings and settings[1]), "updated_at": snapshot.created_at}

    def update(self, scope, thread_id, **changes):
        self.get(scope, thread_id)  # Verify ownership and existence before modifying metadata.
        internal_id = f"{scope}:{thread_id}"
        with closing(sqlite3.connect(self.database_path)) as connection:
            with connection:
                connection.execute("INSERT OR IGNORE INTO conversation_settings (thread_id) VALUES (?)", (internal_id,))
                if "title" in changes:
                    connection.execute("UPDATE conversation_settings SET title = ? WHERE thread_id = ?", (changes["title"], internal_id))
                if "archived" in changes:
                    connection.execute("UPDATE conversation_settings SET archived = ? WHERE thread_id = ?", (int(changes["archived"]), internal_id))
        return self.get(scope, thread_id)

    def list(self, scope, offset=0, limit=20, query="", archived=False):
        prefix = f"{scope}:"
        escaped = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        with closing(sqlite3.connect(self.database_path)) as connection:
            rows = connection.execute(
                "SELECT c.thread_id FROM checkpoints c LEFT JOIN conversation_settings s ON s.thread_id = c.thread_id "
                "WHERE c.thread_id LIKE ? ESCAPE '\\' AND c.checkpoint_ns = '' AND COALESCE(s.archived, 0) = ? "
                "GROUP BY c.thread_id ORDER BY MAX(c.checkpoint_id) DESC" + ("" if query.strip() else " LIMIT ? OFFSET ?"),
                (escaped + "%", int(archived)) if query.strip() else (escaped + "%", int(archived), limit + 1, offset),
            ).fetchall()
        items = []
        for (internal_id,) in rows if query.strip() else rows[:limit]:
            public_id = internal_id[len(prefix):]
            saved = self.get(scope, public_id)
            if query.strip() and query.strip().casefold() not in saved["title"].casefold():
                continue
            items.append({key: saved[key] for key in ("thread_id", "title", "archived", "updated_at")})
        if query.strip():
            return {"items": items[offset:offset+limit], "next_offset": offset + limit if len(items) > offset + limit else None}
        return {"items": items, "next_offset": offset + limit if len(rows) > limit else None}
