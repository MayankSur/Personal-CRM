from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

from flask import Flask, redirect, render_template, request, url_for

from personal_crm.agent import assign_group, render_daily_digest
from personal_crm.db import get_connection, init_db
from personal_crm.google_contacts import import_google_contacts_api, import_google_contacts_csv
from personal_crm.importers import import_contacts_csv, import_linkedin_csv, import_message_csv, import_whatsapp_chat
from personal_crm.llm import enhance_recommendation_prompts
from personal_crm.notifications import send_whatsapp_text
from personal_crm.recommender import Recommendation, build_recommendations


def create_app(db_path: Path) -> Flask:
    app = Flask(__name__)
    app.config["DB_PATH"] = db_path

    @app.get("/")
    def dashboard() -> str:
        conn = get_connection(app.config["DB_PATH"])
        init_db(conn)

        counts = {
            "people": conn.execute("SELECT COUNT(*) AS c FROM people").fetchone()["c"],
            "messages": conn.execute("SELECT COUNT(*) AS c FROM messages").fetchone()["c"],
            "groups": conn.execute("SELECT COUNT(*) AS c FROM groups_meta").fetchone()["c"],
        }

        latest_run = conn.execute(
            "SELECT MAX(run_at) AS run_at FROM touchpoint_recommendations"
        ).fetchone()["run_at"]

        latest_recs = []
        if latest_run:
            latest_recs = conn.execute(
                """
                SELECT r.score, r.reason, r.prompt, p.full_name, COALESCE(g.name, 'ungrouped') AS group_name
                FROM touchpoint_recommendations r
                JOIN people p ON p.id = r.person_id
                LEFT JOIN groups_meta g ON g.id = p.group_id
                WHERE r.run_at = ?
                ORDER BY r.score DESC
                LIMIT 12
                """,
                (latest_run,),
            ).fetchall()

        groups = conn.execute(
            "SELECT id, name, cadence_days, prompt_style FROM groups_meta ORDER BY cadence_days ASC"
        ).fetchall()
        people = conn.execute(
            """
            SELECT p.id, p.full_name, p.phone, p.email, p.source, COALESCE(g.name, 'ungrouped') AS group_name
            FROM people p
            LEFT JOIN groups_meta g ON g.id = p.group_id
            ORDER BY p.full_name COLLATE NOCASE ASC
            LIMIT 200
            """
        ).fetchall()
        conn.close()

        status = request.args.get("status", "")
        error = request.args.get("error", "")

        return render_template(
            "index.html",
            counts=counts,
            latest_recs=latest_recs,
            latest_run=latest_run,
            groups=groups,
            people=people,
            status=status,
            error=error,
        )

    @app.post("/recommend/run")
    def run_recommend() -> Any:
        try:
            conn = get_connection(app.config["DB_PATH"])
            init_db(conn)
            max_results = int(request.form.get("max", "8"))
            recs = build_recommendations(conn, max_results=max_results)

            provider = (request.form.get("llm_provider") or "").strip()
            if provider:
                if provider == "anthropic":
                    key = (request.form.get("llm_api_key") or "").strip() or os.getenv("ANTHROPIC_API_KEY", "")
                    model = (request.form.get("llm_model") or "").strip() or "claude-3-5-sonnet-latest"
                elif provider == "openai":
                    key = (request.form.get("llm_api_key") or "").strip() or os.getenv("OPENAI_API_KEY", "")
                    model = (request.form.get("llm_model") or "").strip() or "gpt-4o-mini"
                else:
                    raise ValueError("Unsupported LLM provider")

                if not key:
                    raise ValueError("Missing LLM key in form or environment")

                enhance_recommendation_prompts(
                    recs,
                    provider=provider,
                    api_key=key,
                    model=model,
                    owner_context=(request.form.get("owner_context") or "").strip(),
                )
                _overwrite_latest_prompts(conn, recs)

            conn.close()
            return redirect(url_for("dashboard", status="Recommendations updated"))
        except Exception as exc:
            return redirect(url_for("dashboard", error=str(exc)))

    @app.post("/digest/run")
    def run_digest() -> Any:
        try:
            conn = get_connection(app.config["DB_PATH"])
            init_db(conn)
            max_results = int(request.form.get("max", "8"))
            output = Path(request.form.get("output", "output/daily_digest.md"))
            recs = build_recommendations(conn, max_results=max_results)
            digest = render_daily_digest(recs, output_path=output)

            send_to = (request.form.get("notify_whatsapp_to") or "").strip()
            if send_to:
                token = (request.form.get("whatsapp_token") or "").strip() or os.getenv("WHATSAPP_ACCESS_TOKEN", "")
                phone_number_id = (
                    (request.form.get("whatsapp_phone_number_id") or "").strip()
                    or os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
                )
                if not token or not phone_number_id:
                    raise ValueError("Missing WhatsApp token or phone number id")
                send_whatsapp_text(
                    access_token=token,
                    phone_number_id=phone_number_id,
                    to_number=send_to,
                    message=digest[:3900],
                )

            conn.close()
            return redirect(url_for("dashboard", status=f"Digest generated at {output}"))
        except Exception as exc:
            return redirect(url_for("dashboard", error=str(exc)))

    @app.post("/people/add")
    def add_person() -> Any:
        try:
            conn = get_connection(app.config["DB_PATH"])
            init_db(conn)
            full_name = (request.form.get("full_name") or "").strip()
            if not full_name:
                raise ValueError("Full name is required")
            phone = (request.form.get("phone") or "").strip()
            email = (request.form.get("email") or "").strip()
            source = (request.form.get("source") or "manual").strip() or "manual"
            conn.execute(
                """
                INSERT OR IGNORE INTO people(full_name, phone, email, source)
                VALUES (?, ?, ?, ?)
                """,
                (full_name, phone, email, source),
            )
            conn.commit()
            conn.close()
            return redirect(url_for("dashboard", status=f"Added {full_name}"))
        except Exception as exc:
            return redirect(url_for("dashboard", error=str(exc)))

    @app.post("/people/assign-group")
    def people_assign_group() -> Any:
        try:
            full_name = (request.form.get("full_name") or "").strip()
            group_name = (request.form.get("group_name") or "").strip()
            conn = get_connection(app.config["DB_PATH"])
            init_db(conn)
            changed = assign_group(conn, full_name=full_name, group_name=group_name)
            conn.close()
            return redirect(url_for("dashboard", status=f"Updated {changed} row(s) for {full_name}"))
        except Exception as exc:
            return redirect(url_for("dashboard", error=str(exc)))

    @app.post("/import/run")
    def run_import() -> Any:
        try:
            kind = (request.form.get("kind") or "").strip()
            path = (request.form.get("path") or "").strip()
            conn = get_connection(app.config["DB_PATH"])
            init_db(conn)

            if kind == "contacts":
                added, updated = import_contacts_csv(conn, Path(path))
                msg = f"Contacts import done: added={added}, existing={updated}"
            elif kind == "linkedin":
                added, updated = import_linkedin_csv(conn, Path(path))
                msg = f"LinkedIn import done: added={added}, existing={updated}"
            elif kind == "messages":
                inserted = import_message_csv(conn, Path(path))
                msg = f"Messages import done: inserted={inserted}"
            elif kind == "whatsapp":
                inserted = import_whatsapp_chat(conn, Path(path))
                msg = f"WhatsApp import done: inserted={inserted}"
            elif kind == "google-csv":
                added, updated = import_google_contacts_csv(conn, Path(path))
                msg = f"Google contacts CSV import done: added={added}, existing={updated}"
            elif kind == "google-api":
                token = (request.form.get("google_access_token") or "").strip() or os.getenv(
                    "GOOGLE_CONTACTS_ACCESS_TOKEN", ""
                )
                if not token:
                    raise ValueError("Missing Google access token")
                added, updated = import_google_contacts_api(conn, access_token=token)
                msg = f"Google API import done: added={added}, existing={updated}"
            else:
                raise ValueError("Unknown import type")

            conn.close()
            return redirect(url_for("dashboard", status=msg))
        except Exception as exc:
            return redirect(url_for("dashboard", error=str(exc)))

    return app


def _overwrite_latest_prompts(conn, recs: list[Recommendation]) -> None:
    latest_run = conn.execute("SELECT MAX(run_at) AS run_at FROM touchpoint_recommendations").fetchone()["run_at"]
    if not latest_run:
        return

    for rec in recs:
        conn.execute(
            """
            UPDATE touchpoint_recommendations
            SET prompt = ?
            WHERE rowid = (
                SELECT rowid
                FROM touchpoint_recommendations
                WHERE person_id = ? AND run_at = ?
                ORDER BY rowid DESC
                LIMIT 1
            )
            """,
            (rec.prompt, rec.person_id, latest_run),
        )
    conn.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Personal CRM web UI")
    parser.add_argument("--db", default="data/personal_crm.db", help="Path to sqlite database")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface")
    parser.add_argument("--port", type=int, default=5050, help="Port")
    parser.add_argument("--debug", action="store_true", help="Enable Flask debug mode")
    args = parser.parse_args()

    app = create_app(Path(args.db))
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
