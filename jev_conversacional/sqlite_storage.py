"""Armazenamento persistente SQLite para histórico de conversas, preferências e recomendações."""
from __future__ import annotations

import sqlite3
import pathlib
import datetime
from typing import Any

DB_PATH = pathlib.Path(__file__).parent.parent / "data" / "jev_memory.db"


def _get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Cria tabelas no SQLite se não existirem."""
    with _get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                sender TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS user_preferences (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS recommendation_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                recomendacao TEXT NOT NULL,
                score_ponderado REAL NOT NULL,
                confianca REAL NOT NULL,
                preco_na_data REAL,
                data TEXT NOT NULL,
                timestamp TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
            CREATE INDEX IF NOT EXISTS idx_rec_ticker ON recommendation_history(ticker);
        """)


def save_message(session_id: str, sender: str, content: str) -> None:
    """Salva mensagem do usuário ou do agente no histórico persistente."""
    init_db()
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with _get_connection() as conn:
        conn.execute(
            "INSERT INTO messages (session_id, sender, content, timestamp) VALUES (?, ?, ?, ?)",
            (session_id, sender, content, now),
        )


def get_recent_messages(session_id: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    """Recupera mensagens recentes."""
    init_db()
    with _get_connection() as conn:
        if session_id:
            cursor = conn.execute(
                "SELECT sender, content, timestamp FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                (session_id, limit),
            )
        else:
            cursor = conn.execute(
                "SELECT sender, content, timestamp FROM messages ORDER BY id DESC LIMIT ?",
                (limit,),
            )
        rows = cursor.fetchall()
        return [dict(r) for r in reversed(rows)]


def set_user_preference(key: str, value: str) -> None:
    """Define ou atualiza preferência persistente do usuário (ex: perfil_risco, horizonte_default)."""
    init_db()
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with _get_connection() as conn:
        conn.execute(
            """INSERT INTO user_preferences (key, value, updated_at) 
               VALUES (?, ?, ?) 
               ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at""",
            (key.strip().lower(), str(value).strip(), now),
        )


def get_user_preference(key: str, default: str | None = None) -> str | None:
    """Recupera preferência persistente."""
    init_db()
    with _get_connection() as conn:
        cursor = conn.execute("SELECT value FROM user_preferences WHERE key = ?", (key.strip().lower(),))
        row = cursor.fetchone()
        return row["value"] if row else default


def get_all_preferences() -> dict[str, str]:
    """Retorna todas as preferências salvas."""
    init_db()
    with _get_connection() as conn:
        cursor = conn.execute("SELECT key, value FROM user_preferences")
        return {r["key"]: r["value"] for r in cursor.fetchall()}


def log_recommendation(
    ticker: str,
    recomendacao: str,
    score_ponderado: float,
    confianca: float,
    preco: float | None = None,
) -> None:
    """Registra recomendação gerada para auditoria e tracking de performance futura."""
    init_db()
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    today = datetime.date.today().isoformat()
    with _get_connection() as conn:
        conn.execute(
            """INSERT INTO recommendation_history 
               (ticker, recomendacao, score_ponderado, confianca, preco_na_data, data, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (ticker.upper().strip(), recomendacao.lower().strip(), float(score_ponderado), float(confianca), preco, today, now),
        )


def get_past_recommendations(ticker: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
    """Consulta histórico de recomendações passadas."""
    init_db()
    with _get_connection() as conn:
        if ticker:
            cursor = conn.execute(
                """SELECT ticker, recomendacao, score_ponderado, confianca, preco_na_data, data, timestamp 
                   FROM recommendation_history WHERE ticker = ? ORDER BY id DESC LIMIT ?""",
                (ticker.upper().strip(), limit),
            )
        else:
            cursor = conn.execute(
                """SELECT ticker, recomendacao, score_ponderado, confianca, preco_na_data, data, timestamp 
                   FROM recommendation_history ORDER BY id DESC LIMIT ?""",
                (limit,),
            )
        return [dict(r) for r in cursor.fetchall()]
