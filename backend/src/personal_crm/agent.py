from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sqlite3

from .recommender import Recommendation


def render_daily_digest(recommendations: list[Recommendation], output_path: Path | None = None) -> str:
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"# Personal CRM Daily Suggestions ({generated_at})",
        "",
        "## Who to message today",
        "",
    ]

    if not recommendations:
        lines.append("No suggestions today. Your outreach cadence looks healthy.")
    else:
        for i, rec in enumerate(recommendations, start=1):
            lines.extend(
                [
                    f"{i}. {rec.full_name} ({rec.group_name})",
                    f"   - Why: {rec.reason}",
                    f"   - Prompt: {rec.prompt}",
                    "",
                ]
            )

    digest = "\n".join(lines)
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(digest, encoding="utf-8")
    return digest


def assign_group(conn: sqlite3.Connection, full_name: str, group_name: str) -> int:
    group_row = conn.execute(
        "SELECT id FROM groups_meta WHERE name = ? LIMIT 1", (group_name,)
    ).fetchone()
    if not group_row:
        raise ValueError(f"Unknown group '{group_name}'. Create it first with group-create.")

    cur = conn.execute(
        """
        UPDATE people
        SET group_id = ?
        WHERE full_name = ?
        """,
        (int(group_row["id"]), full_name),
    )
    conn.commit()
    return cur.rowcount


def create_group(
    conn: sqlite3.Connection,
    *,
    name: str,
    description: str,
    cadence_days: int,
    prompt_style: str,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO groups_meta(name, description, cadence_days, prompt_style)
        VALUES (?, ?, ?, ?)
        """,
        (name, description, cadence_days, prompt_style),
    )
    conn.commit()
    return int(cur.lastrowid)
