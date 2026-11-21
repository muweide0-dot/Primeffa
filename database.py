"""SQLite Datenschicht – alles überlebt Neustarts."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
DB_DIR = BASE_DIR / "data"
DB_PATH = DB_DIR / "primeffa.db"

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    guild_id INTEGER NOT NULL,
    key      TEXT    NOT NULL,
    value    TEXT,
    PRIMARY KEY (guild_id, key)
);

CREATE TABLE IF NOT EXISTS ticket_counter (
    guild_id INTEGER PRIMARY KEY,
    counter  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS tickets (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id     INTEGER NOT NULL,
    channel_id   INTEGER NOT NULL UNIQUE,
    owner_id     INTEGER NOT NULL,
    category     TEXT    NOT NULL,
    number       INTEGER NOT NULL,
    status       TEXT    NOT NULL DEFAULT 'open',
    claimed_by   INTEGER,
    created_at   REAL    NOT NULL,
    closed_at    REAL,
    close_reason TEXT,
    transcript   TEXT
);
CREATE INDEX IF NOT EXISTS idx_tickets_guild ON tickets(guild_id);

CREATE TABLE IF NOT EXISTS giveaways (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id     INTEGER NOT NULL,
    channel_id   INTEGER NOT NULL,
    message_id   INTEGER,
    prize        TEXT    NOT NULL,
    winners      INTEGER NOT NULL DEFAULT 1,
    host_id      INTEGER NOT NULL,
    ends_at      REAL    NOT NULL,
    entrants     TEXT    NOT NULL DEFAULT '[]',
    ended        INTEGER NOT NULL DEFAULT 0,
    cancelled    INTEGER NOT NULL DEFAULT 0,
    winners_list TEXT    NOT NULL DEFAULT '[]',
    created_at   REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS counting (
    guild_id   INTEGER PRIMARY KEY,
    channel_id INTEGER,
    current    INTEGER NOT NULL DEFAULT 0,
    record     INTEGER NOT NULL DEFAULT 0,
    last_user  INTEGER
);

CREATE TABLE IF NOT EXISTS voice_ping (
    guild_id         INTEGER PRIMARY KEY,
    voice_channel_id INTEGER,
    text_channel_id  INTEGER,
    roles            TEXT    NOT NULL DEFAULT '[]',
    message          TEXT,
    cooldown         INTEGER NOT NULL DEFAULT 60,
    last_ping        REAL    NOT NULL DEFAULT 0
);
"""


def init() -> None:
    """Datenbank + Tabellen anlegen (inkl. Sicherheit bei alten Schemata)."""
    global _conn
    DB_DIR.mkdir(parents=True, exist_ok=True)

    # Falls eine alte/inkompatible Datenbank existiert: sichern & neu anlegen
    if DB_PATH.exists():
        try:
            probe = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
            cols = {r[1] for r in probe.execute("PRAGMA table_info(tickets)")}
            probe.close()
            if cols and "number" not in cols:
                stamp = time.strftime("%Y%m%d-%H%M%S")
                backup = DB_DIR / f"primeffa_alt-{stamp}.db"
                DB_PATH.rename(backup)
                for suffix in ("-wal", "-shm"):
                    src = Path(str(DB_PATH) + suffix)
                    if src.exists():
                        src.rename(Path(str(backup) + suffix))
        except sqlite3.DatabaseError:
            stamp = time.strftime("%Y%m%d-%H%M%S")
            broken = DB_DIR / f"primeffa_broken-{stamp}.db"
            DB_PATH.rename(broken)

    _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    _conn.row_factory = sqlite3.Row
    _conn.execute("PRAGMA journal_mode=WAL")
    _conn.executescript(SCHEMA)
    _conn.commit()


def _ex(sql: str, params: tuple = ()) -> sqlite3.Cursor:
    with _lock:
        assert _conn is not None
        cur = _conn.execute(sql, params)
        _conn.commit()
        return cur


def _q(sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    with _lock:
        assert _conn is not None
        return _conn.execute(sql, params).fetchall()


def _q1(sql: str, params: tuple = ()) -> sqlite3.Row | None:
    with _lock:
        assert _conn is not None
        return _conn.execute(sql, params).fetchone()


# ---------------------------------------------------------------- Einstellungen

def get_setting(guild_id: int, key: str, default: Any = None) -> Any:
    row = _q1("SELECT value FROM settings WHERE guild_id=? AND key=?", (guild_id, key))
    return row["value"] if row else default


def set_setting(guild_id: int, key: str, value: Any) -> None:
    _ex(
        "INSERT INTO settings (guild_id, key, value) VALUES (?, ?, ?) "
        "ON CONFLICT(guild_id, key) DO UPDATE SET value=excluded.value",
        (guild_id, key, str(value)),
    )


def delete_setting(guild_id: int, key: str) -> None:
    _ex("DELETE FROM settings WHERE guild_id=? AND key=?", (guild_id, key))


def get_int(guild_id: int, key: str, default: int = 0) -> int:
    try:
        return int(get_setting(guild_id, key, default))
    except (TypeError, ValueError):
        return default


def get_all_settings(guild_id: int) -> list[sqlite3.Row]:
    return _q("SELECT key, value FROM settings WHERE guild_id=? ORDER BY key", (guild_id,))


# ------------------------------------------------------------------- Tickets

def next_ticket_number(guild_id: int) -> int:
    with _lock:
        assert _conn is not None
        row = _conn.execute(
            "SELECT counter FROM ticket_counter WHERE guild_id=?", (guild_id,)
        ).fetchone()
        if row:
            n = int(row["counter"]) + 1
            _conn.execute(
                "UPDATE ticket_counter SET counter=? WHERE guild_id=?", (n, guild_id)
            )
        else:
            n = 1
            _conn.execute(
                "INSERT INTO ticket_counter (guild_id, counter) VALUES (?, 1)",
                (guild_id,),
            )
        _conn.commit()
        return n


def add_ticket(
    guild_id: int,
    channel_id: int,
    owner_id: int,
    category: str,
    number: int,
) -> int:
    cur = _ex(
        "INSERT INTO tickets (guild_id, channel_id, owner_id, category, number, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (guild_id, channel_id, owner_id, category, number, time.time()),
    )
    return int(cur.lastrowid or 0)


def get_ticket_by_channel(channel_id: int) -> dict | None:
    row = _q1("SELECT * FROM tickets WHERE channel_id=?", (channel_id,))
    return dict(row) if row else None


def get_ticket_by_number(guild_id: int, number: int) -> dict | None:
    row = _q1("SELECT * FROM tickets WHERE guild_id=? AND number=?", (guild_id, number))
    return dict(row) if row else None


def get_open_ticket(guild_id: int, owner_id: int) -> dict | None:
    row = _q1(
        "SELECT * FROM tickets WHERE guild_id=? AND owner_id=? AND status='open' "
        "ORDER BY id DESC LIMIT 1",
        (guild_id, owner_id),
    )
    return dict(row) if row else None


def set_ticket_claimed(channel_id: int, user_id: int | None) -> None:
    _ex("UPDATE tickets SET claimed_by=? WHERE channel_id=?", (user_id, channel_id))


def close_ticket(channel_id: int, reason: str) -> None:
    _ex(
        "UPDATE tickets SET status='closed', closed_at=?, close_reason=? WHERE channel_id=?",
        (time.time(), reason, channel_id),
    )


def reopen_ticket(channel_id: int) -> None:
    _ex(
        "UPDATE tickets SET status='open', closed_at=NULL, close_reason=NULL "
        "WHERE channel_id=?",
        (channel_id,),
    )


def set_ticket_transcript(channel_id: int, path: str) -> None:
    _ex("UPDATE tickets SET transcript=? WHERE channel_id=?", (path, channel_id))


def delete_ticket_record(channel_id: int) -> None:
    _ex("DELETE FROM tickets WHERE channel_id=?", (channel_id,))


def list_closed_tickets(guild_id: int, limit: int = 10) -> list[dict]:
    rows = _q(
        "SELECT * FROM tickets WHERE guild_id=? AND status='closed' "
        "ORDER BY closed_at DESC LIMIT ?",
        (guild_id, limit),
    )
    return [dict(r) for r in rows]


def ticket_stats(guild_id: int) -> dict:
    total = _q1("SELECT COUNT(*) c FROM tickets WHERE guild_id=?", (guild_id,))["c"]
    open_c = _q1(
        "SELECT COUNT(*) c FROM tickets WHERE guild_id=? AND status='open'", (guild_id,)
    )["c"]
    closed = _q1(
        "SELECT COUNT(*) c FROM tickets WHERE guild_id=? AND status='closed'",
        (guild_id,),
    )["c"]
    by_cat = {
        r["category"]: r["c"]
        for r in _q(
            "SELECT category, COUNT(*) c FROM tickets WHERE guild_id=? GROUP BY category",
            (guild_id,),
        )
    }
    return {"total": total, "open": open_c, "closed": closed, "by_category": by_cat}


# ----------------------------------------------------------------- Giveaways

def add_giveaway(
    guild_id: int,
    channel_id: int,
    message_id: int | None,
    prize: str,
    winners: int,
    host_id: int,
    ends_at: float,
) -> int:
    cur = _ex(
        "INSERT INTO giveaways (guild_id, channel_id, message_id, prize, winners, "
        "host_id, ends_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (guild_id, channel_id, message_id, prize, winners, host_id, ends_at, time.time()),
    )
    return int(cur.lastrowid or 0)


def set_giveaway_message(gid: int, message_id: int) -> None:
    _ex("UPDATE giveaways SET message_id=? WHERE id=?", (message_id, gid))


def get_giveaway(gid: int) -> dict | None:
    row = _q1("SELECT * FROM giveaways WHERE id=?", (gid,))
    return dict(row) if row else None


def get_giveaway_by_message(message_id: int) -> dict | None:
    row = _q1("SELECT * FROM giveaways WHERE message_id=?", (message_id,))
    return dict(row) if row else None


def latest_active_giveaway(guild_id: int, channel_id: int) -> dict | None:
    row = _q1(
        "SELECT * FROM giveaways WHERE guild_id=? AND channel_id=? AND ended=0 "
        "ORDER BY id DESC LIMIT 1",
        (guild_id, channel_id),
    )
    return dict(row) if row else None


def due_giveaways(now: float) -> list[dict]:
    rows = _q("SELECT * FROM giveaways WHERE ended=0 AND ends_at<=?", (now,))
    return [dict(r) for r in rows]


def set_entrants(gid: int, entrants: list[int]) -> None:
    _ex("UPDATE giveaways SET entrants=? WHERE id=?", (json.dumps(entrants), gid))


def finish_giveaway(gid: int, winners: list[int], cancelled: bool = False) -> None:
    _ex(
        "UPDATE giveaways SET ended=1, cancelled=?, winners_list=? WHERE id=?",
        (1 if cancelled else 0, json.dumps(winners), gid),
    )


def parse_entrants(raw: str) -> list[int]:
    try:
        data = json.loads(raw or "[]")
        return [int(x) for x in data]
    except (ValueError, TypeError):
        return []


# ------------------------------------------------------------------- Counting

def get_counting(guild_id: int) -> dict | None:
    row = _q1("SELECT * FROM counting WHERE guild_id=?", (guild_id,))
    return dict(row) if row else None


def set_counting_channel(guild_id: int, channel_id: int) -> None:
    _ex(
        "INSERT INTO counting (guild_id, channel_id, current, record, last_user) "
        "VALUES (?, ?, 0, 0, NULL) "
        "ON CONFLICT(guild_id) DO UPDATE SET channel_id=excluded.channel_id, "
        "current=0, last_user=NULL",
        (guild_id, channel_id),
    )


def update_counting(guild_id: int, current: int, last_user: int | None) -> None:
    _ex(
        "UPDATE counting SET current=?, last_user=? WHERE guild_id=?",
        (current, last_user, guild_id),
    )


def set_counting_record(guild_id: int, record: int) -> None:
    _ex("UPDATE counting SET record=? WHERE guild_id=?", (record, guild_id))


def reset_counting(guild_id: int) -> None:
    _ex(
        "UPDATE counting SET current=0, last_user=NULL WHERE guild_id=?",
        (guild_id,),
    )


# --------------------------------------------------------------- Voice-Ping

def get_voice_ping(guild_id: int) -> dict | None:
    row = _q1("SELECT * FROM voice_ping WHERE guild_id=?", (guild_id,))
    if not row:
        return None
    data = dict(row)
    try:
        data["roles"] = [int(x) for x in json.loads(data.get("roles") or "[]")]
    except (ValueError, TypeError):
        data["roles"] = []
    return data


def set_voice_ping(
    guild_id: int,
    voice_channel_id: int,
    text_channel_id: int,
    roles: list[int],
    message: str | None,
    cooldown: int,
) -> None:
    _ex(
        "INSERT INTO voice_ping (guild_id, voice_channel_id, text_channel_id, roles, "
        "message, cooldown, last_ping) VALUES (?, ?, ?, ?, ?, ?, 0) "
        "ON CONFLICT(guild_id) DO UPDATE SET voice_channel_id=excluded.voice_channel_id, "
        "text_channel_id=excluded.text_channel_id, roles=excluded.roles, "
        "message=excluded.message, cooldown=excluded.cooldown",
        (guild_id, voice_channel_id, text_channel_id, json.dumps(roles), message, cooldown),
    )


def set_voice_ping_last(guild_id: int, ts: float) -> None:
    _ex("UPDATE voice_ping SET last_ping=? WHERE guild_id=?", (ts, guild_id))
