# Personal CRM

A local-first personal relationship CRM to help you:

- Import people and conversations from contacts, WhatsApp, LinkedIn, and generic message exports.
- Import directly from Google Contacts (CSV or Google People API).
- Track last outreach and interaction history.
- Group people by relationship style and cadence.
- Generate a daily "who should I message" digest with suggested prompts.
- Optionally enhance prompts with Claude/OpenAI and send daily digest over WhatsApp.

## 1) Quick setup

### Prerequisites

- Python 3.11+
- macOS (for launchd schedule example)

### Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Launch the web UI

```bash
personal-crm-web --db data/personal_crm.db --host 127.0.0.1 --port 5050
```

If you have not installed package scripts yet, use:

```bash
chmod +x scripts/run_ui.sh
./scripts/run_ui.sh
```

Or directly:

```bash
PYTHONPATH=backend/src:interface/src .venv/bin/python -m personal_crm_interface.webapp --db data/personal_crm.db --host 127.0.0.1 --port 5050
```

Open: `http://127.0.0.1:5050`

The UI includes:

- dashboard KPIs (people, messages, groups)
- imports (contacts/linkedin/messages/whatsapp/google)
- recommendation run panel with optional LLM enhancement
- daily digest generation with optional WhatsApp delivery
- people list and group assignment

### Initialize

```bash
personal-crm init-db --db data/personal_crm.db
```

## 2) Import your network

### Contacts CSV

Use headers like:

- `name`
- `phone`
- `email`
- `linkedin_url`

Then run:

```bash
personal-crm import-contacts --csv path/to/contacts.csv
```

### Google Contacts integration

#### Option A: Import from Google Contacts CSV export

```bash
personal-crm import-google-contacts --csv examples/google_contacts_template.csv
```

#### Option B: Import from Google People API

Use a Google OAuth access token with `https://www.googleapis.com/auth/contacts.readonly` scope:

```bash
export GOOGLE_CONTACTS_ACCESS_TOKEN="your_token_here"
personal-crm import-google-contacts --page-size 500
```

You can also pass token directly:

```bash
personal-crm import-google-contacts --access-token "your_token_here"
```

### LinkedIn CSV

Use your LinkedIn connections export and run:

```bash
personal-crm import-linkedin --csv path/to/LinkedInConnections.csv
```

### WhatsApp chat export

From WhatsApp, export a chat as `.txt` (without media preferred), then:

```bash
personal-crm import-whatsapp --chat-file path/to/chat.txt
```

### SMS/texts and other message exports

Normalize to CSV with columns:

- `full_name`
- `direction` (`incoming` or `outgoing`)
- `channel` (e.g. `sms`, `whatsapp`, `linkedin`)
- `body`
- `sent_at` (ISO datetime)

Run:

```bash
personal-crm import-messages --csv path/to/messages.csv
```

## 3) Relationship grouping and personalization

Built-in groups:

- `inner-circle` (7-day cadence)
- `close-friends` (14-day cadence)
- `professional` (30-day cadence)
- `old-friends` (45-day cadence)

Create a custom group:

```bash
personal-crm group-create \
  --name travel-buddies \
  --description "Friends I travel with" \
  --cadence-days 21 \
  --prompt-style "fun, playful, and specific"
```

Assign someone to a group:

```bash
personal-crm group-assign --full-name "Alex Johnson" --group close-friends
```

## 4) Daily recommendations and prompts

Get immediate recommendations:

```bash
personal-crm recommend --max 8
```

### LLM-enhanced prompts (Claude or OpenAI)

Use Anthropic (Claude):

```bash
export ANTHROPIC_API_KEY="your_claude_token"
personal-crm recommend --max 8 \
  --llm-provider anthropic \
  --llm-model claude-3-5-sonnet-latest \
  --owner-context "I prefer warm, concise messages and usually mention one shared memory."
```

Use OpenAI:

```bash
export OPENAI_API_KEY="your_openai_key"
personal-crm recommend --max 8 \
  --llm-provider openai \
  --llm-model gpt-4o-mini
```

Run the daily agent digest:

```bash
personal-crm daily-agent --max 8 --output output/daily_digest.md
```

LLM-enhanced daily digest:

```bash
personal-crm daily-agent --max 8 --output output/daily_digest.md \
  --llm-provider anthropic \
  --llm-model claude-3-5-sonnet-latest
```

### Send daily digest via WhatsApp

This uses Meta WhatsApp Cloud API.

```bash
export WHATSAPP_ACCESS_TOKEN="your_whatsapp_cloud_api_token"
export WHATSAPP_PHONE_NUMBER_ID="your_phone_number_id"

personal-crm daily-agent --max 8 --output output/daily_digest.md \
  --notify-whatsapp-to "+15555550123"
```

Send a one-off WhatsApp message:

```bash
personal-crm notify-whatsapp \
  --to "+15555550123" \
  --message "Your CRM digest is ready in output/daily_digest.md"
```

The digest contains:

- prioritized people to message
- reason for ranking
- personalized prompt for your next message

## 5) Automate daily run on macOS

Make script executable:

```bash
chmod +x scripts/run_daily.sh
```

Create the launchd plist at `~/Library/LaunchAgents/com.personalcrm.daily.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>com.personalcrm.daily</string>

    <key>ProgramArguments</key>
    <array>
      <string>/bin/bash</string>
      <string>/Users/YOUR_USERNAME/Documents/Personal/Personal CRM/scripts/run_daily.sh</string>
    </array>

    <key>StartCalendarInterval</key>
    <dict>
      <key>Hour</key>
      <integer>8</integer>
      <key>Minute</key>
      <integer>30</integer>
    </dict>

    <key>WorkingDirectory</key>
    <string>/Users/YOUR_USERNAME/Documents/Personal/Personal CRM</string>

    <key>StandardOutPath</key>
    <string>/Users/YOUR_USERNAME/Documents/Personal/Personal CRM/output/launchd.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/YOUR_USERNAME/Documents/Personal/Personal CRM/output/launchd.err.log</string>

    <key>RunAtLoad</key>
    <true/>
  </dict>
</plist>
```

Load job:

```bash
launchctl unload ~/Library/LaunchAgents/com.personalcrm.daily.plist 2>/dev/null || true
launchctl load ~/Library/LaunchAgents/com.personalcrm.daily.plist
```

## 6) Manual message logging

If you send a message and want to keep history accurate:

```bash
personal-crm log-message \
  --full-name "Alex Johnson" \
  --direction outgoing \
  --channel whatsapp \
  --body "How did your interview go?" \
  --sent-at "2026-06-19T08:20:00+00:00"
```

## Notes

- This repo is local-first and keeps data in `data/personal_crm.db`.
- Importers are resilient to partial rows and skip malformed records.
- You can evolve scoring logic in `backend/src/personal_crm/recommender.py`.
- `daily-agent` supports optional LLM prompt enhancement and optional WhatsApp delivery.

## Repository structure

- `backend/src/personal_crm`: backend services, data model, importers, CLI, recommendation engine
- `interface/src/personal_crm_interface`: Flask UI, templates, and styles
