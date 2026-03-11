# Wamoyager

A Raspberry Pi–hosted agent that monitors **WMATA Metrorail** service status and
sends commuters SMS alerts via Twilio. The system uses a swappable **Brain module**
so the AI decision layer can be built during a team session without touching anything
else.

---

## What it does

| Trigger | What happens |
|---|---|
| Every 2 minutes (configurable) | Polls WMATA for incidents; Brain decides whether to notify users |
| 5:00 PM ET daily | Brain composes a personalised "next train" SMS for each active user |
| 2:00 AM ET daily | Housekeeping: prunes old notifications and incidents from the DB |

---

## Project layout

```
wamoyager/
├── wamoyager_runtime/
│   ├── main.py           # entrypoint — wires everything together, starts scheduler
│   ├── config.py         # all settings read from environment / .env
│   ├── logging_setup.py  # structured logging config
│   └── rails.py          # safety rails: rate limits, cooldowns, schema validation
│
├── services/
│   ├── wmata_client.py    # WMATA API calls + incident/prediction normalisation
│   ├── notifier_twilio.py # Twilio SMS send + retries + dry-run mode
│   ├── scheduler.py       # APScheduler: poll job, daily job, housekeeping job
│   ├── webhook_server.py  # Flask inbound SMS webhook (POST /sms)
│   └── inbound_handler.py # Routes inbound messages to Brain, manages setup state
│
├── memory/
│   ├── db.py             # SQLite connection + initialisation
│   ├── models.py         # dataclasses: User, UserPreferences, Incident, Notification
│   ├── queries.py        # typed query functions (no raw SQL outside this file)
│   └── migrations/
│       ├── 001_initial.sql
│       └── 002_conversation_state.sql
│
├── brain/                # ← TEAM SESSION FOCUS
│   ├── interface.py      # BrainInterface ABC + IncidentDecision + DailyMessageResult
│   ├── stub_brain.py     # deterministic rule-based brain (used pre-session)
│   └── agents_sdk_brain.py  # ← BUILD THIS in the session
│
├── scripts/
│   ├── init_db.py        # initialise SQLite DB from migrations
│   ├── add_user.py       # CLI: add a user + preferences
│   ├── run_poll_once.py  # run one poll cycle (dry-run safe)
│   └── run_daily_once.py # run daily message cycle for all active users
│
├── deploy/
│   ├── systemd/wamoyager.service
│   └── setup_pi.sh
│
├── requirements.txt
├── .env.example
└── plan.md
```

---

## Quick start

### 1. Clone and install dependencies

```bash
git clone <repo-url> wamoyager
cd wamoyager
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env — fill in WMATA_API_KEY, TWILIO_* credentials
```

Set `DRY_RUN=true` while testing so no real SMS messages are sent.

### 3. Initialise the database

```bash
python scripts/init_db.py
```

### 4. Add a user

```bash
python scripts/add_user.py \
  --name "Alice" \
  --phone "+12025551234" \
  --station-codes "A01,A02" \
  --lines "RD"
```

### 5. Test a poll cycle (dry-run)

```bash
python scripts/run_poll_once.py
```

### 6. Test the daily message (dry-run)

```bash
python scripts/run_daily_once.py
```

### 7. Run the full service

```bash
python -m wamoyager_runtime.main
```

---

## Configuration reference

All settings are read from environment variables (or a `.env` file at the project root).

| Variable | Default | Description |
|---|---|---|
| `WMATA_API_KEY` | **required** | WMATA developer API key |
| `TWILIO_ACCOUNT_SID` | **required** | Twilio account SID |
| `TWILIO_AUTH_TOKEN` | **required** | Twilio auth token |
| `TWILIO_FROM_NUMBER` | **required** | Twilio sender number (E.164) |
| `DATABASE_PATH` | `./wamoyager.db` | Path to SQLite database file |
| `DRY_RUN` | `false` | Log SMS instead of sending |
| `POLL_INTERVAL_SECONDS` | `120` | How often to poll WMATA |
| `DAILY_JOB_TIME` | `17:00` | Daily message time (24h, ET) |
| `RATE_LIMIT_MAX_PER_HOUR` | `3` | Max SMS per user per hour |
| `COOLDOWN_MINUTES` | `30` | Suppress repeat alerts for same incident |
| `LOG_LEVEL` | `INFO` | Python log level |

---

## Architecture: the Brain seam

```
┌─────────────────────────────────────────────────┐
│                   Runtime                        │
│  scheduler → run_poll_cycle / run_daily_cycle    │
│                    │                             │
│          calls Brain methods                     │
│                    │                             │
│   Brain returns: what to say + who to notify     │
│                    │                             │
│  Runtime applies safety rails (rate limit,       │
│  cooldown, schema validation) then calls Twilio  │
└─────────────────────────────────────────────────┘
```

**The Brain never touches Twilio or the DB directly.**
Swapping `StubBrain` → `AgentsSdkBrain` in `main.py` is the only change needed
after the team session.

### Brain contract (`brain/interface.py`)

```python
brain.decide_incident(incident, users_relevant, history_recent)
    → IncidentDecision(notify, urgency_level, audience_user_ids, messages, message_all)

brain.compose_daily_message(user, predictions, system_status_summary)
    → DailyMessageResult(message)
```

### Safety rails (always enforced by Runtime, regardless of Brain)

- **Rate limit:** max `RATE_LIMIT_MAX_PER_HOUR` SMS per user per hour (bypassed for CRITICAL)
- **Cooldown:** suppress re-notification for the same incident fingerprint within `COOLDOWN_MINUTES` (bypassed for CRITICAL)
- **Schema validation:** Brain output is validated before any send is attempted
- **Dry-run:** `DRY_RUN=true` logs all intended sends without touching Twilio
- **Length cap:** SMS body truncated to 160 characters

---

## SQLite schema

| Table | Purpose |
|---|---|
| `users` | Name, phone number, active flag, timezone |
| `user_preferences` | Station codes, lines, direction, daily SMS enable/time |
| `incidents` | Deduplicated WMATA incidents (fingerprint = sha256 of title+lines) |
| `notifications` | Log of every attempted send with provider ID and status |
| `agent_state` | Key/value store for Brain memory (used by AgentsSdkBrain) |
| `conversation_state` | Per-phone setup flow state (step + collected data) |

---

## Inbound SMS: self-service user setup

Users can enroll themselves by texting your Twilio number. No admin needed.

### Conversation flow

```
User texts: "setup"
  → "Welcome to Wamoyager! What's your first name?"
User texts: "Alice"
  → "Hi Alice! What's your Metro station code(s)? (e.g. A01, A15)"
User texts: "A01"
  → "Got it. Which line(s) do you ride? (e.g. RD, BL, OR)"
User texts: "RD"
  → "Ready to set up: Alice, station A01, line RD. Reply YES to confirm."
User texts: "yes"
  → "You're all set! You'll get daily Metro updates at 5pm ET."
```

Other supported keywords: `STOP` / `UNSUBSCRIBE` to deactivate.

### How to expose the webhook

The webhook server runs on `WEBHOOK_PORT` (default `8080`).
Twilio needs a public URL — use **ngrok** for local dev or the Pi's static IP in production:

```bash
# Local dev:
ngrok http 8080
# → copy the https URL, e.g. https://abc123.ngrok.io

# Set in Twilio console:
# Phone Numbers → your number → Messaging → Webhook URL:
#   https://abc123.ngrok.io/sms   (HTTP POST)
```

On the Pi in production, either port-forward 8080 on your router or use a reverse proxy (nginx).

### Config

| Variable | Default | Description |
|---|---|---|
| `WEBHOOK_ENABLED` | `true` | Start the webhook server on launch |
| `WEBHOOK_PORT` | `8080` | Port the Flask server listens on |

---

## Team session: building the AI brain

See [`brain/agents_sdk_brain.py`](brain/agents_sdk_brain.py) for a step-by-step
pseudo-code roadmap with all seven implementation tasks clearly marked.

The only file you need to edit during the session is `agents_sdk_brain.py`.
Once it works, change one line in `wamoyager_runtime/main.py`:

```python
# Before (pre-session):
from brain.stub_brain import StubBrain
brain = StubBrain()

# After (session complete):
from brain.agents_sdk_brain import AgentsSdkBrain
brain = AgentsSdkBrain()
```

---

## Deploying to Raspberry Pi

```bash
# On the Pi:
bash deploy/setup_pi.sh

# Install the systemd service:
sudo cp deploy/systemd/wamoyager.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable wamoyager
sudo systemctl start wamoyager
sudo journalctl -u wamoyager -f
```
