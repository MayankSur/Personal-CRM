from __future__ import annotations

import csv
import json
from pathlib import Path
from urllib import parse, request

import sqlite3

from .importers import _upsert_person


def import_google_contacts_csv(conn: sqlite3.Connection, csv_path: Path) -> tuple[int, int]:
    added = 0
    updated = 0

    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            name = (
                row.get("Name")
                or row.get("Given Name")
                or row.get("First Name")
                or ""
            ).strip()
            if not name:
                continue

            phone = _pick_first(
                row,
                ["Phone 1 - Value", "Phone 2 - Value", "Phone 3 - Value"],
            )
            email = _pick_first(
                row,
                ["E-mail 1 - Value", "E-mail 2 - Value", "E-mail 3 - Value"],
            )

            before = conn.execute(
                "SELECT id FROM people WHERE full_name = ? LIMIT 1",
                (name,),
            ).fetchone()
            _upsert_person(
                conn,
                full_name=name,
                phone=phone,
                email=email,
                linkedin_url=None,
                source="google-contacts",
            )
            if before is None:
                added += 1
            else:
                updated += 1

    conn.commit()
    return added, updated


def import_google_contacts_api(
    conn: sqlite3.Connection,
    *,
    access_token: str,
    page_size: int = 500,
) -> tuple[int, int]:
    added = 0
    updated = 0

    page_token = None
    while True:
        qs = {
            "personFields": "names,emailAddresses,phoneNumbers",
            "pageSize": str(page_size),
        }
        if page_token:
            qs["pageToken"] = page_token

        url = "https://people.googleapis.com/v1/people/me/connections?" + parse.urlencode(qs)
        req = request.Request(
            url=url,
            method="GET",
            headers={"authorization": f"Bearer {access_token}"},
        )
        with request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))

        people = body.get("connections") or []
        for item in people:
            names = item.get("names") or []
            display = ""
            if names:
                display = (names[0].get("displayName") or "").strip()
            if not display:
                continue

            phone = None
            emails = item.get("emailAddresses") or []
            phones = item.get("phoneNumbers") or []
            email = (emails[0].get("value") if emails else None) or None
            phone = (phones[0].get("value") if phones else None) or None

            before = conn.execute(
                "SELECT id FROM people WHERE full_name = ? LIMIT 1",
                (display,),
            ).fetchone()
            _upsert_person(
                conn,
                full_name=display,
                phone=phone,
                email=email,
                linkedin_url=None,
                source="google-contacts",
            )
            if before is None:
                added += 1
            else:
                updated += 1

        page_token = body.get("nextPageToken")
        if not page_token:
            break

    conn.commit()
    return added, updated


def _pick_first(row: dict, keys: list[str]) -> str | None:
    for key in keys:
        val = (row.get(key) or "").strip()
        if val:
            return val
    return None
