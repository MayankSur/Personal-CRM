from __future__ import annotations

import csv
import re
from datetime import datetime
from pathlib import Path
from typing import Iterable

import sqlite3

WHATSAPP_HEADER_RE = re.compile(
    r"^(?P<date>\d{1,2}/\d{1,2}/\d{2,4}),\s(?P<time>\d{1,2}:\d{2})\s-\s(?P<name>.*?):\s(?P<body>.*)$"
)


class ImportErrorDetail(Exception):
    pass


def _upsert_person(
    conn: sqlite3.Connection,
    *,
    full_name: str,
    phone: str | None,
    email: str | None,
    linkedin_url: str | None,
    source: str,
) -> int:
    phone = _norm_optional(phone)
    email = _norm_optional(email)

    # Prefer existing person rows to avoid duplicate identities across sources.
    existing = conn.execute(
        """
        SELECT id, phone, email, linkedin_url
        FROM people
        WHERE full_name = ?
        ORDER BY id ASC
        """,
        (full_name.strip(),),
    ).fetchall()

    if existing:
        chosen = None
        for row in existing:
            if row["phone"] == phone and row["email"] == email:
                chosen = row
                break
        if chosen is None:
            chosen = existing[0]

        # Backfill useful identity fields when importing from richer sources.
        merged_phone = chosen["phone"] or phone
        merged_email = chosen["email"] or email
        merged_linkedin = chosen["linkedin_url"] or linkedin_url

        conn.execute(
            """
            UPDATE people
            SET phone = ?, email = ?, linkedin_url = ?
            WHERE id = ?
            """,
            (merged_phone, merged_email, merged_linkedin, int(chosen["id"])),
        )
        return int(chosen["id"])

    cur = conn.execute(
        """
        INSERT OR IGNORE INTO people(full_name, phone, email, linkedin_url, source)
        VALUES (?, ?, ?, ?, ?)
        """,
        (full_name.strip(), phone, email, linkedin_url, source),
    )
    if cur.lastrowid:
        return int(cur.lastrowid)

    row = conn.execute(
        """
        SELECT id FROM people
        WHERE full_name = ?
          AND COALESCE(phone, '') = COALESCE(?, '')
          AND COALESCE(email, '') = COALESCE(?, '')
        LIMIT 1
        """,
        (full_name.strip(), phone, email),
    ).fetchone()
    if not row:
        raise ImportErrorDetail(f"Could not upsert person {full_name}")
    return int(row["id"])


def import_contacts_csv(conn: sqlite3.Connection, csv_path: Path) -> tuple[int, int]:
    added = 0
    updated = 0
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            name = (row.get("name") or row.get("full_name") or "").strip()
            if not name:
                continue
            phone = (row.get("phone") or "").strip() or None
            email = (row.get("email") or "").strip() or None
            linkedin = (row.get("linkedin_url") or "").strip() or None
            before = conn.execute(
                "SELECT id FROM people WHERE full_name = ? LIMIT 1",
                (name,),
            ).fetchone()
            _upsert_person(
                conn,
                full_name=name,
                phone=phone,
                email=email,
                linkedin_url=linkedin,
                source="contacts",
            )
            if before is None:
                added += 1
            else:
                updated += 1
    conn.commit()
    return added, updated


def import_linkedin_csv(conn: sqlite3.Connection, csv_path: Path) -> tuple[int, int]:
    added = 0
    updated = 0
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            name = (row.get("First Name", "").strip() + " " + row.get("Last Name", "").strip()).strip()
            if not name:
                name = (row.get("Name") or "").strip()
            if not name:
                continue

            linkedin_url = (row.get("Profile URL") or row.get("URL") or "").strip() or None
            before = conn.execute(
                "SELECT id FROM people WHERE full_name = ? LIMIT 1",
                (name,),
            ).fetchone()
            _upsert_person(
                conn,
                full_name=name,
                phone=None,
                email=None,
                linkedin_url=linkedin_url,
                source="linkedin",
            )
            if before is None:
                added += 1
            else:
                updated += 1
    conn.commit()
    return added, updated


def import_whatsapp_chat(conn: sqlite3.Connection, chat_path: Path, default_channel: str = "whatsapp") -> int:
    inserted = 0
    with chat_path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip("\n")
            match = WHATSAPP_HEADER_RE.match(line)
            if not match:
                continue

            sender = match.group("name").strip()
            body = match.group("body").strip()
            date_str = match.group("date")
            time_str = match.group("time")
            dt = _parse_whatsapp_datetime(date_str, time_str)

            person_id = _upsert_person(
                conn,
                full_name=sender,
                phone=None,
                email=None,
                linkedin_url=None,
                source="whatsapp",
            )

            # WhatsApp exports are usually incoming from the sender perspective.
            conn.execute(
                """
                INSERT INTO messages(person_id, direction, channel, body, sent_at, imported)
                VALUES (?, 'incoming', ?, ?, ?, 1)
                """,
                (person_id, default_channel, body, dt.isoformat()),
            )
            inserted += 1
    conn.commit()
    return inserted


def import_message_csv(conn: sqlite3.Connection, csv_path: Path) -> int:
    """
    Expected CSV columns:
    - full_name (required)
    - direction ('incoming' or 'outgoing', required)
    - channel (required)
    - body (optional)
    - sent_at (ISO datetime, required)
    """
    inserted = 0
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            full_name = (row.get("full_name") or "").strip()
            direction = (row.get("direction") or "").strip().lower()
            channel = (row.get("channel") or "").strip().lower()
            sent_at = (row.get("sent_at") or "").strip()
            body = (row.get("body") or "").strip()

            if not full_name or direction not in {"incoming", "outgoing"} or not channel or not sent_at:
                continue

            person_id = _upsert_person(
                conn,
                full_name=full_name,
                phone=None,
                email=None,
                linkedin_url=None,
                source="messages",
            )

            conn.execute(
                """
                INSERT INTO messages(person_id, direction, channel, body, sent_at, imported)
                VALUES (?, ?, ?, ?, ?, 1)
                """,
                (person_id, direction, channel, body, sent_at),
            )
            inserted += 1
    conn.commit()
    return inserted


def _parse_whatsapp_datetime(date_str: str, time_str: str) -> datetime:
    formats: Iterable[str] = (
        "%d/%m/%y %H:%M",
        "%d/%m/%Y %H:%M",
        "%m/%d/%y %H:%M",
        "%m/%d/%Y %H:%M",
    )
    value = f"{date_str} {time_str}"
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise ImportErrorDetail(f"Could not parse WhatsApp datetime: {value}")


def _norm_optional(value: str | None) -> str:
    return value.strip() if value else ""
