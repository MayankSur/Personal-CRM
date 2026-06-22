from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import sqlite3


@dataclass
class Recommendation:
    person_id: int
    full_name: str
    group_name: str
    last_outgoing_at: str | None
    days_since_outgoing: int
    cadence_days: int
    score: float
    reason: str
    prompt: str


def build_recommendations(conn: sqlite3.Connection, max_results: int = 8) -> list[Recommendation]:
    now = datetime.now(timezone.utc)
    rows = conn.execute(
        """
        SELECT
            p.id AS person_id,
            p.full_name,
            COALESCE(g.name, 'ungrouped') AS group_name,
            COALESCE(g.cadence_days, 21) AS cadence_days,
            COALESCE(g.prompt_style, 'friendly and thoughtful') AS prompt_style,
            (
                SELECT MAX(m.sent_at)
                FROM messages m
                WHERE m.person_id = p.id AND m.direction = 'outgoing'
            ) AS last_outgoing_at,
            (
                SELECT MAX(m.sent_at)
                FROM messages m
                WHERE m.person_id = p.id
            ) AS last_any_message_at
        FROM people p
        LEFT JOIN groups_meta g ON g.id = p.group_id
        """
    ).fetchall()

    recommendations: list[Recommendation] = []

    for row in rows:
        last_outgoing_at = row["last_outgoing_at"]
        cadence_days = int(row["cadence_days"])

        if last_outgoing_at:
            last_dt = _parse_iso(last_outgoing_at)
            days_since = max(0, (now - last_dt).days)
        else:
            days_since = cadence_days + 10

        stale_bonus = max(0, days_since - cadence_days)
        no_outgoing_bonus = 8 if not last_outgoing_at else 0
        score = float(days_since + stale_bonus + no_outgoing_bonus)

        reason = _build_reason(
            full_name=row["full_name"],
            group_name=row["group_name"],
            days_since=days_since,
            cadence_days=cadence_days,
            had_outgoing=bool(last_outgoing_at),
        )

        prompt = _build_prompt(
            full_name=row["full_name"],
            group_name=row["group_name"],
            prompt_style=row["prompt_style"],
            days_since=days_since,
        )

        recommendations.append(
            Recommendation(
                person_id=int(row["person_id"]),
                full_name=row["full_name"],
                group_name=row["group_name"],
                last_outgoing_at=last_outgoing_at,
                days_since_outgoing=days_since,
                cadence_days=cadence_days,
                score=score,
                reason=reason,
                prompt=prompt,
            )
        )

    recommendations.sort(key=lambda rec: rec.score, reverse=True)
    top = recommendations[:max_results]

    for rec in top:
        conn.execute(
            """
            INSERT INTO touchpoint_recommendations(person_id, score, reason, prompt)
            VALUES (?, ?, ?, ?)
            """,
            (rec.person_id, rec.score, rec.reason, rec.prompt),
        )
    conn.commit()

    return top


def _build_reason(
    *,
    full_name: str,
    group_name: str,
    days_since: int,
    cadence_days: int,
    had_outgoing: bool,
) -> str:
    if not had_outgoing:
        return f"No outgoing message logged with {full_name} yet; this is a strong candidate for first outreach."
    if days_since > cadence_days:
        return (
            f"Last outgoing message was {days_since} days ago, above the {cadence_days}-day target "
            f"for the {group_name} group."
        )
    return (
        f"{full_name} is within cadence but still worth a light touch after {days_since} days "
        f"to maintain momentum."
    )


def _build_prompt(*, full_name: str, group_name: str, prompt_style: str, days_since: int) -> str:
    return (
        f"Write a short message to {full_name}. Tone: {prompt_style}. "
        f"Context: they are in your {group_name} group and it has been about {days_since} days "
        "since your last outbound message. Include one concrete personal detail or question."
    )


def _parse_iso(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
