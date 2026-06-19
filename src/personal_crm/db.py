from __future__ import annotations

import sqlite3
from pathlib import Path


DEFAULT_DB_PATH = Path("data/personal_crm.db")


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        PRAGMA foreign_keys = ON;

        CREATE TABLE IF NOT EXISTS groups_meta (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT DEFAULT '',
            cadence_days INTEGER NOT NULL DEFAULT 30,
            prompt_style TEXT DEFAULT 'friendly and personal'
        );

        CREATE TABLE IF NOT EXISTS people (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            phone TEXT NOT NULL DEFAULT '',
            email TEXT NOT NULL DEFAULT '',
            linkedin_url TEXT,
            source TEXT NOT NULL,
            group_id INTEGER,
            notes TEXT DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(full_name, phone, email),
            FOREIGN KEY (group_id) REFERENCES groups_meta(id)
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            person_id INTEGER NOT NULL,
            direction TEXT NOT NULL CHECK (direction IN ('incoming', 'outgoing')),
            channel TEXT NOT NULL,
            body TEXT DEFAULT '',
            sent_at TEXT NOT NULL,
            imported INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY (person_id) REFERENCES people(id)
        );

        CREATE TABLE IF NOT EXISTS touchpoint_recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            person_id INTEGER NOT NULL,
            score REAL NOT NULL,
            reason TEXT NOT NULL,
            prompt TEXT NOT NULL,
            run_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (person_id) REFERENCES people(id)
        );

        CREATE INDEX IF NOT EXISTS idx_messages_person_sent
            ON messages(person_id, sent_at DESC);

        CREATE INDEX IF NOT EXISTS idx_people_group
            ON people(group_id);
        """
    )

    conn.executemany(
        """
        INSERT OR IGNORE INTO groups_meta(name, description, cadence_days, prompt_style)
        VALUES (?, ?, ?, ?)
        """,
        [
            ("inner-circle", "Closest family and friends", 7, "warm and emotionally close"),
            ("close-friends", "Friends you speak with regularly", 14, "casual, upbeat, and specific"),
            ("professional", "Mentors and professional network", 30, "thoughtful and concise"),
            ("old-friends", "People you want to reconnect with", 45, "nostalgic and easygoing"),
        ],
    )
    conn.commit()
