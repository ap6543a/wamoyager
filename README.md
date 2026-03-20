# Wamoyager

A Raspberry Pi–hosted agent that monitors **WMATA Metrorail** service status and
sends commuters SMS alerts via Mailgun. The system uses a swappable **Brain module**
so the AI decision layer can be replaced without touching the scheduler, notifier, or DB.

---

## What it does

| Trigger | What happens |
|---|---|
| Every 2 minutes (configurable) | Polls WMATA for incidents; Brain decides whether to notify users |
| 5:00 PM ET daily (weekdays) | Brain composes a personalised "next train" SMS for each active user |
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
│   ├── notifier_email.py  # Mailgun SMTP send + retries + dry-run mode
│   ├── scheduler.py       # APScheduler: poll job, daily job, housekeeping job
│   └── inbound_handler.py # reserved for future two-way messaging
│
├── memory/
│   ├── db.py             # SQLite connection + initialisation
│   ├── models.py         # dataclasses: User, UserPreferences, Incident, Notification
│   ├── queries.py        # typed query functions (no raw SQL outside this file)
│   └── migrations/
│       ├── 001_initial.sql
│       └── 002_conversation_state.sql
│
├── brain/
│   ├── interface.py         # BrainInterface ABC + IncidentDecision + DailyMessageResult
│   ├── stub_brain.py        # deterministic rule-based brain (reference implementation)
│   └── agents_sdk_brain.py  # ← production AI brain (OpenAI Agents SDK)
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
└── .env.example
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
# Edit .env — fill in WMATA_API_KEY, MAILGUN_*, OPENAI_API_KEY
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
  --email "2025551234@tmomail.net" \
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

## Architecture: the Brain seam

The Brain module is the only swappable layer. The Runtime, notifier, DB, and safety
rails are fixed infrastructure. Swapping brains requires one change in `main.py`:

```python
# Rule-based (no LLM):
from brain.stub_brain import StubBrain
brain = StubBrain()

# AI brain (current):
from brain.agents_sdk_brain import AgentsSdkBrain
brain = AgentsSdkBrain(db)
```

**The Brain never sends messages or writes to the DB directly.**
It only returns `IncidentDecision` and `DailyMessageResult` — the Runtime does everything else.

---

## Agent design: before and after

### Before — single-agent, fragile JSON parsing

The original implementation used one agent for everything. It received raw incident
JSON in a text prompt and was asked to return a JSON string. `json.loads()` was called
directly on the model's text output with no schema validation or fallback, making the
system brittle.

```
┌─────────────────────────────────────────────────────────────────┐
│  Runtime                                                        │
│                                                                 │
│  poll_job ──► WmataClient ──► NormalizedIncident                │
│                                     │                           │
│                          decide_incident()                       │
│                                     │                           │
│                                     ▼                           │
│                        ┌────────────────────────┐               │
│                        │  WamoyagerBrain (×1)   │               │
│                        │  single Agent          │               │
│                        │                        │               │
│                        │  • builds text prompt  │               │
│                        │    with raw JSON dump  │               │
│                        │  • Runner.run_sync()   │               │
│                        │  • json.loads(output)  │  ← fragile    │
│                        │  • no schema validation│               │
│                        │  • bare except: pass   │  ← silent fail│
│                        └──────────┬─────────────┘               │
│                                   │                             │
│              Tools (3): read/write_agent_state,                 │
│                          lookup_station_name                    │
│              (all via global _db — not thread-safe)             │
│                                   │                             │
│                                   ▼                             │
│               IncidentDecision ──► Safety Rails ──► Notifier    │
└─────────────────────────────────────────────────────────────────┘
```

### After — two-agent pipeline with structured outputs and guardrails

The current implementation separates classification from composition into two
purpose-built agents. Each agent uses `output_type` (Pydantic model) so the SDK
enforces the schema — no JSON parsing, no `KeyError`. Tools are closures over `self._db`
(no globals). A length guardrail on the composer catches over-limit messages before
they reach the notifier.

```
┌─────────────────────────────────────────────────────────────────┐
│  Runtime                                                        │
│                                                                 │
│  poll_job ──► WmataClient ──► NormalizedIncident                │
│                                     │                           │
│                          decide_incident()                       │
│                                     │                           │
│                     ┌───────────────▼───────────────┐           │
│                     │   IncidentClassifier Agent    │           │
│                     │   output_type=ClassifierOutput│           │
│                     │                               │           │
│                     │   • notify: bool              │           │
│                     │   • urgency_level: str        │           │
│                     │   • audience_user_ids: [int]  │           │
│                     │   • rationale: str            │           │
│                     └───────────────┬───────────────┘           │
│                                     │  calls tools              │
│          ┌──────────────────────────┼──────────────────────┐    │
│          │ Tools (×6):              │                      │    │
│          │  read/write_agent_state  │  get_line_severity_  │    │
│          │  lookup_station_name     │    trend             │    │
│          │  get_notification_       │  get_active_         │    │
│          │    history_for_user      │    incident_count    │    │
│          └──────────────────────────┘                      │    │
│                  (all closures over self._db)               │    │
│                                     │                           │
│                    if notify=True   │                           │
│                                     ▼                           │
│                     ┌───────────────────────────────┐           │
│                     │   MessageComposer Agent       │           │
│                     │   output_type=ComposerOutput  │           │
│                     │   + sms_length_guardrail      │           │
│                     │                               │           │
│                     │   • message: str (≤160 chars) │           │
│                     │                               │           │
│                     │   guardrail trips → truncate  │           │
│                     │   exception → safe default    │           │
│                     └───────────────┬───────────────┘           │
│                                     │                           │
│                                     ▼                           │
│               IncidentDecision ──► Safety Rails ──► Notifier    │
└─────────────────────────────────────────────────────────────────┘
```

The same `MessageComposer` agent handles both incident alerts and daily messages.

---

## Brain contract (`brain/interface.py`)

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
- **Dry-run:** `DRY_RUN=true` logs all intended sends without touching Mailgun
- **Length cap:** SMS body truncated to 160 characters (also enforced by composer guardrail)

---

## Configuration reference

| Variable | Default | Description |
|---|---|---|
| `WMATA_API_KEY` | **required** | WMATA developer API key |
| `OPENAI_API_KEY` | **required** | OpenAI API key (for AgentsSdkBrain) |
| `MAILGUN_SMTP_LOGIN` | **required** | Mailgun SMTP login |
| `MAILGUN_SMTP_PASSWORD` | **required** | Mailgun SMTP password |
| `MAILGUN_FROM_ADDRESS` | **required** | Sender address |
| `MAILGUN_FROM_NAME` | `Wamoyager` | Display name on outgoing messages |
| `DATABASE_PATH` | `./wamoyager.db` | Path to SQLite database file |
| `DRY_RUN` | `false` | Log messages instead of sending |
| `POLL_INTERVAL_SECONDS` | `120` | How often to poll WMATA |
| `DAILY_JOB_TIME` | `17:00` | Daily message time (24h, ET) |
| `RATE_LIMIT_MAX_PER_HOUR` | `3` | Max messages per user per hour |
| `COOLDOWN_MINUTES` | `30` | Suppress repeat alerts for same incident |
| `LOG_LEVEL` | `INFO` | Python log level |

---

## SQLite schema

| Table | Purpose |
|---|---|
| `users` | Name, email, active flag, timezone |
| `user_preferences` | Station codes, lines, direction, daily SMS enable/time |
| `incidents` | Deduplicated WMATA incidents (fingerprint = sha256 of title+lines) |
| `notifications` | Log of every attempted send with provider ID and status |
| `agent_state` | Key/value store for Brain memory (used by AgentsSdkBrain) |
| `conversation_state` | Per-phone setup flow state (reserved for future inbound SMS) |

---

## Adding users

```bash
python scripts/add_user.py \
  --name "Alice" \
  --email "2025551234@tmomail.net" \
  --station-codes "A01,C01" \
  --lines "RD"
```

**Carrier gateway addresses:**

| Carrier | Gateway |
|---|---|
| T-Mobile | `@tmomail.net` |
| Verizon | `@vtext.com` |
| AT&T | `@txt.att.net` |
| Sprint | `@messaging.sprintpcs.com` |
| Google Fi | `@msg.fi.google.com` |

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
