"""
SQLite persistence for Isagi Bot.

Tables
------
users       : one row per Telegram user — coins, free trials left, sub expiry.
history     : one row per generated description (for /userinfo).
"""
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id         INTEGER PRIMARY KEY,
    username        TEXT,
    coins           INTEGER NOT NULL DEFAULT 0,
    free_trials     INTEGER NOT NULL DEFAULT 3,
    sub_expiry      REAL,              -- unix timestamp, NULL = no active sub
    sub_plan        TEXT,
    created_at      REAL NOT NULL,
    total_generated INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    created_at  REAL NOT NULL,
    num_images  INTEGER NOT NULL,
    summary     TEXT
);
"""


@contextmanager
def _conn():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with _conn() as conn:
        conn.executescript(_SCHEMA)


def ensure_user(user_id: int, username: str | None = None):
    """Create the user row if it doesn't exist yet."""
    with _conn() as conn:
        row = conn.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,)).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO users (user_id, username, coins, free_trials, created_at) "
                "VALUES (?, ?, 0, ?, ?)",
                (user_id, username, config.FREE_TRIAL_GENERATIONS, time.time()),
            )
        elif username:
            conn.execute("UPDATE users SET username=? WHERE user_id=?", (username, user_id))


def get_user(user_id: int) -> sqlite3.Row | None:
    with _conn() as conn:
        return conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()


def is_sub_active(row: sqlite3.Row) -> bool:
    if row is None or row["sub_expiry"] is None:
        return False
    return row["sub_expiry"] > time.time()


def add_coins(user_id: int, amount: int):
    with _conn() as conn:
        conn.execute(
            "UPDATE users SET coins = coins + ? WHERE user_id=?", (amount, user_id)
        )


def remove_coins(user_id: int, amount: int):
    """Floors at 0."""
    with _conn() as conn:
        conn.execute(
            "UPDATE users SET coins = MAX(0, coins - ?) WHERE user_id=?",
            (amount, user_id),
        )


def set_subscription(user_id: int, days: int, plan_label: str):
    expiry = time.time() + days * 86400
    with _conn() as conn:
        conn.execute(
            "UPDATE users SET sub_expiry=?, sub_plan=? WHERE user_id=?",
            (expiry, plan_label, user_id),
        )


def remove_subscription(user_id: int):
    with _conn() as conn:
        conn.execute(
            "UPDATE users SET sub_expiry=NULL, sub_plan=NULL WHERE user_id=?",
            (user_id,),
        )


def consume_free_trial(user_id: int):
    with _conn() as conn:
        conn.execute(
            "UPDATE users SET free_trials = MAX(0, free_trials - 1) WHERE user_id=?",
            (user_id,),
        )


def spend_coins(user_id: int, amount: int):
    with _conn() as conn:
        conn.execute(
            "UPDATE users SET coins = MAX(0, coins - ?) WHERE user_id=?",
            (amount, user_id),
        )


def log_generation(user_id: int, num_images: int, summary: str):
    with _conn() as conn:
        conn.execute(
            "INSERT INTO history (user_id, created_at, num_images, summary) VALUES (?, ?, ?, ?)",
            (user_id, time.time(), num_images, summary),
        )
        conn.execute(
            "UPDATE users SET total_generated = total_generated + 1 WHERE user_id=?",
            (user_id,),
        )


def get_history(user_id: int, limit: int = 10):
    with _conn() as conn:
        return conn.execute(
            "SELECT * FROM history WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()


def fmt_expiry(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%d-%m-%Y %H:%M UTC")
