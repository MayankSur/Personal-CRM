from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path

from .agent import assign_group, create_group, render_daily_digest
from .db import DEFAULT_DB_PATH, get_connection, init_db
from .google_contacts import import_google_contacts_api, import_google_contacts_csv
from .importers import import_contacts_csv, import_linkedin_csv, import_message_csv, import_whatsapp_chat
from .llm import enhance_recommendation_prompts
from .notifications import send_whatsapp_text
from .recommender import build_recommendations


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    db_path = Path(args.db)
    conn = get_connection(db_path)

    if args.command == "init-db":
        init_db(conn)
        print(f"Initialized database at {db_path}")
        return

    if args.command == "import-contacts":
        init_db(conn)
        added, updated = import_contacts_csv(conn, Path(args.csv))
        print(f"Imported contacts: added={added}, existing={updated}")
        return

    if args.command == "import-linkedin":
        init_db(conn)
        added, updated = import_linkedin_csv(conn, Path(args.csv))
        print(f"Imported LinkedIn connections: added={added}, existing={updated}")
        return

    if args.command == "import-whatsapp":
        init_db(conn)
        inserted = import_whatsapp_chat(conn, Path(args.chat_file))
        print(f"Imported WhatsApp messages: {inserted}")
        return

    if args.command == "import-messages":
        init_db(conn)
        inserted = import_message_csv(conn, Path(args.csv))
        print(f"Imported messages from CSV: {inserted}")
        return

    if args.command == "import-google-contacts":
        init_db(conn)
        if args.csv:
            added, updated = import_google_contacts_csv(conn, Path(args.csv))
        else:
            access_token = args.access_token or os.getenv("GOOGLE_CONTACTS_ACCESS_TOKEN", "")
            if not access_token:
                raise ValueError("Set --access-token or GOOGLE_CONTACTS_ACCESS_TOKEN")
            added, updated = import_google_contacts_api(conn, access_token=access_token, page_size=args.page_size)
        print(f"Imported Google contacts: added={added}, existing={updated}")
        return

    if args.command == "log-message":
        init_db(conn)
        _log_message(
            conn,
            full_name=args.full_name,
            direction=args.direction,
            channel=args.channel,
            body=args.body,
            sent_at=args.sent_at,
        )
        print(f"Logged {args.direction} message for {args.full_name}")
        return

    if args.command == "group-create":
        init_db(conn)
        group_id = create_group(
            conn,
            name=args.name,
            description=args.description,
            cadence_days=args.cadence_days,
            prompt_style=args.prompt_style,
        )
        print(f"Created group '{args.name}' (id={group_id})")
        return

    if args.command == "group-assign":
        init_db(conn)
        changed = assign_group(conn, full_name=args.full_name, group_name=args.group)
        print(f"Updated {changed} person record(s)")
        return

    if args.command == "recommend":
        init_db(conn)
        recs = build_recommendations(conn, max_results=args.max)
        _maybe_enhance_prompts(recs, args)
        if not recs:
            print("No recommendations available.")
            return
        for i, rec in enumerate(recs, start=1):
            print(f"{i}. {rec.full_name} [{rec.group_name}] score={rec.score:.1f}")
            print(f"   why: {rec.reason}")
            print(f"   prompt: {rec.prompt}")
        return

    if args.command == "daily-agent":
        init_db(conn)
        recs = build_recommendations(conn, max_results=args.max)
        _maybe_enhance_prompts(recs, args)
        output_path = Path(args.output) if args.output else None
        digest = render_daily_digest(recs, output_path=output_path)
        print(digest)

        if args.notify_whatsapp_to:
            token = args.whatsapp_token or os.getenv("WHATSAPP_ACCESS_TOKEN", "")
            phone_number_id = args.whatsapp_phone_number_id or os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
            if not token or not phone_number_id:
                raise ValueError(
                    "To send WhatsApp notifications, set --whatsapp-token and "
                    "--whatsapp-phone-number-id (or env vars WHATSAPP_ACCESS_TOKEN, WHATSAPP_PHONE_NUMBER_ID)."
                )

            resp = send_whatsapp_text(
                access_token=token,
                phone_number_id=phone_number_id,
                to_number=args.notify_whatsapp_to,
                message=digest[:3900],
            )
            print(f"WhatsApp notification sent: {resp}")
        return

    if args.command == "notify-whatsapp":
        token = args.whatsapp_token or os.getenv("WHATSAPP_ACCESS_TOKEN", "")
        phone_number_id = args.whatsapp_phone_number_id or os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
        if not token or not phone_number_id:
            raise ValueError(
                "Set --whatsapp-token and --whatsapp-phone-number-id "
                "(or env vars WHATSAPP_ACCESS_TOKEN and WHATSAPP_PHONE_NUMBER_ID)."
            )
        resp = send_whatsapp_text(
            access_token=token,
            phone_number_id=phone_number_id,
            to_number=args.to,
            message=args.message,
        )
        print(f"WhatsApp notification sent: {resp}")
        return

    parser.print_help()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="personal-crm", description="Personal CRM assistant")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="Path to sqlite database")

    sub = parser.add_subparsers(dest="command")

    sub.add_parser("init-db", help="Initialize database schema")

    contacts = sub.add_parser("import-contacts", help="Import contacts CSV")
    contacts.add_argument("--csv", required=True)

    linkedin = sub.add_parser("import-linkedin", help="Import LinkedIn CSV")
    linkedin.add_argument("--csv", required=True)

    whatsapp = sub.add_parser("import-whatsapp", help="Import WhatsApp exported chat .txt")
    whatsapp.add_argument("--chat-file", required=True)

    google_contacts = sub.add_parser(
        "import-google-contacts",
        help="Import Google Contacts from CSV export or People API",
    )
    google_contacts.add_argument("--csv", help="Path to Google Contacts CSV export")
    google_contacts.add_argument("--access-token", help="Google OAuth access token with contacts.readonly scope")
    google_contacts.add_argument("--page-size", type=int, default=500)

    msg = sub.add_parser("import-messages", help="Import generic message CSV")
    msg.add_argument("--csv", required=True)

    log = sub.add_parser("log-message", help="Log a single message manually")
    log.add_argument("--full-name", required=True)
    log.add_argument("--direction", choices=["incoming", "outgoing"], required=True)
    log.add_argument("--channel", required=True)
    log.add_argument("--body", default="")
    log.add_argument("--sent-at", default=datetime.now(timezone.utc).isoformat())

    group_create = sub.add_parser("group-create", help="Create a custom relationship group")
    group_create.add_argument("--name", required=True)
    group_create.add_argument("--description", default="")
    group_create.add_argument("--cadence-days", type=int, default=21)
    group_create.add_argument("--prompt-style", default="friendly and personal")

    group_assign = sub.add_parser("group-assign", help="Assign person to group")
    group_assign.add_argument("--full-name", required=True)
    group_assign.add_argument("--group", required=True)

    rec = sub.add_parser("recommend", help="Show who to message next")
    rec.add_argument("--max", type=int, default=8)
    _add_llm_args(rec)

    daily = sub.add_parser("daily-agent", help="Generate daily outreach digest")
    daily.add_argument("--max", type=int, default=8)
    daily.add_argument("--output", default="output/daily_digest.md")
    _add_llm_args(daily)
    daily.add_argument("--notify-whatsapp-to", help="Send digest to this WhatsApp number (E.164 format)")
    daily.add_argument("--whatsapp-token", help="WhatsApp Cloud API token")
    daily.add_argument("--whatsapp-phone-number-id", help="WhatsApp Cloud API phone number id")

    notify = sub.add_parser("notify-whatsapp", help="Send a custom WhatsApp text notification")
    notify.add_argument("--to", required=True, help="Destination number in E.164 format")
    notify.add_argument("--message", required=True)
    notify.add_argument("--whatsapp-token", help="WhatsApp Cloud API token")
    notify.add_argument("--whatsapp-phone-number-id", help="WhatsApp Cloud API phone number id")

    return parser


def _add_llm_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--llm-provider", choices=["anthropic", "openai"], help="Provider for prompt enhancement")
    parser.add_argument("--llm-model", help="Model id (e.g. claude-3-5-sonnet-latest or gpt-4o-mini)")
    parser.add_argument("--llm-api-key", help="LLM API key. If omitted, env var is used.")
    parser.add_argument("--owner-context", default="", help="Optional context about your relationship style")


def _maybe_enhance_prompts(recs, args) -> None:
    provider = getattr(args, "llm_provider", None)
    if not provider or not recs:
        return

    if provider == "anthropic":
        api_key = args.llm_api_key or os.getenv("ANTHROPIC_API_KEY", "")
        model = args.llm_model or "claude-3-5-sonnet-latest"
    else:
        api_key = args.llm_api_key or os.getenv("OPENAI_API_KEY", "")
        model = args.llm_model or "gpt-4o-mini"

    if not api_key:
        raise ValueError(
            "Missing LLM API key. Pass --llm-api-key or set ANTHROPIC_API_KEY/OPENAI_API_KEY."
        )

    enhance_recommendation_prompts(
        recs,
        provider=provider,
        api_key=api_key,
        model=model,
        owner_context=getattr(args, "owner_context", ""),
    )


def _log_message(
    conn,
    *,
    full_name: str,
    direction: str,
    channel: str,
    body: str,
    sent_at: str,
) -> None:
    person = conn.execute(
        "SELECT id FROM people WHERE full_name = ? LIMIT 1", (full_name,)
    ).fetchone()

    if not person:
        conn.execute(
            "INSERT INTO people(full_name, source) VALUES (?, 'manual')",
            (full_name,),
        )
        person = conn.execute(
            "SELECT id FROM people WHERE full_name = ? LIMIT 1", (full_name,)
        ).fetchone()

    conn.execute(
        """
        INSERT INTO messages(person_id, direction, channel, body, sent_at, imported)
        VALUES (?, ?, ?, ?, ?, 0)
        """,
        (int(person["id"]), direction, channel, body, sent_at),
    )
    conn.commit()


if __name__ == "__main__":
    main()
