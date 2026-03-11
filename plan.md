# Wamoyager — One-Page Build Plan (Raspberry Pi + WMATA + Twilio + SQLite + OpenAI Agents SDK)

## Purpose
**Wamoyager** is a Raspberry Pi–hosted agent that:
- Monitors **WMATA Metrorail** service status (outages, delays, disruptions).
- Sends each known user a **daily “next train” SMS at 5:00 PM (America/New_York)**.
- Decides when a WMATA incident is **urgent enough** to notify users immediately.
- Uses **SQLite** for local memory/state.
- Uses **Twilio** for messaging.
- Uses the **OpenAI Agents SDK** for the *agent brain* (built during the team session).

---

## Build Strategy (Educational)
### Pre-build (before session)
Have everything working **except** the AI brain:
- Pi runtime + service management
- WMATA client + normalization
- SQLite schema + migrations + queries
- Twilio send + logging + retries
- Scheduler jobs (poll + daily 5pm)
- “Brain interface” + **stub brain** (deterministic rules)
- Test scripts + fixtures + dry-run mode

### Build session focus
Replace `stub_brain` with `agents_sdk_brain` using **OpenAI Agents SDK**, keeping the rest of the system unchanged.

---

## Architecture (Replaceable Brain Seam)
**Runtime** (scheduler + services) calls a **Brain module** that returns structured decisions.

**Modules**
- `wmata_client`: fetch predictions + alerts/incidents; normalize to internal models.
- `memory_sqlite`: users, prefs, subscriptions, incident history, notification log, agent state.
- `notifier_twilio`: SMS send + retries; records provider IDs and statuses.
- `scheduler`: poll WMATA every N minutes; run daily job at **17:00 ET**.
- `brain`:
  - `interface.py` defines the contract.
  - `stub_brain.py` used pre-session.
  - `agents_sdk_brain.py` implemented in-session (OpenAI Agents SDK).

**Rule:** Only the Brain decides *what to say* and *who to notify*; only Runtime performs side effects (Twilio sends, DB writes).

---

## Brain Contract (Inputs → Outputs)
### 1) Incident decision
**Input:** `incident`, `users_relevant`, `history_recent`  
**Output (structured):**
- `notify: bool`
- `urgency_level: "INFO" | "MINOR" | "MAJOR" | "CRITICAL"`
- `audience_user_ids: [..]`
- `messages: { user_id: "sms text" }` (or `message_all`)

### 2) Daily 5pm next-train message
**Input:** `user`, `predictions`, optional `system_status_summary`  
**Output:** `message: "sms text"`

**Pre-session stub behavior**
- Always sends at 5pm to active users.
- Picks next 1–3 trains for user’s configured station/line/direction.
- Keyword/heuristic urgency classification for incidents.

---

## Data & Memory (SQLite Minimum)
Tables (minimum viable):
- `users(id, name, phone_e164, active, timezone, created_at)`
- `user_preferences(user_id, station_codes_json, lines_json, direction_json, daily_enabled, daily_time)`
- `incidents(id, fingerprint, normalized_json, first_seen, last_seen, severity)`
- `notifications(id, user_id, incident_id, type, body, status, provider_id, created_at)`
- `agent_state(key, value, updated_at)`

**Dedupe:** stable `fingerprint` per incident; re-notify only if severity increases, impacted scope changes, or cooldown expires.

---

## Scheduling
- **Poll job:** every 1–5 minutes (configurable).
- **Daily job:** 5:00 PM **America/New_York** (configurable per-user later if desired).
- **Housekeeping:** daily/weekly (log rotation, pruning old incidents/notifications).

---

## Safety Rails (Runtime-Enforced)
Even with an AI brain, Runtime must enforce:
- **Rate limit:** max X messages/user/hour unless `CRITICAL`.
- **Dedupe/cooldown:** block repeats for same fingerprint within Y minutes.
- **Schema validation:** brain output must match contract.
- **Dry-run mode:** log intended sends without sending SMS.
- **Message guardrails:** length cap, no sensitive data beyond what’s needed.

---

## Repository Layout (Suggested)
- `wamoyager_runtime/` (entrypoint, config, logging)
- `services/` (`wmata_client.py`, `notifier_twilio.py`, `scheduler.py`)
- `memory/` (`db.py`, `migrations/`, `queries.py`, `models.py`)
- `brain/` (`interface.py`, `stub_brain.py`, `agents_sdk_brain.py`)
- `scripts/` (`init_db.py`, `add_user.py`, `run_poll_once.py`, `run_daily_once.py`)
- `deploy/` (`systemd/`, `setup_pi.sh`)

---

## Team Session Tasks (Agent Brain Only)
1. Implement `brain/agents_sdk_brain.py` using **OpenAI Agents SDK**:
   - Instruction prompt (urgency rules + message style)
   - Tools: read/write memory, (optional) fetch WMATA details, format SMS
   - Return structured decision JSON
2. Run test scenarios:
   - Minor delay (line-specific)
   - Station closure affecting subscribed station
   - Multi-line disruption during commute window
3. Verify rails: dedupe, rate limits, dry-run.

---

## Done Definition
- Pi service runs continuously; WMATA polling works; DB updates; Twilio send works.
- 5pm daily messages go out correctly.
- Incidents trigger alerts only when Brain says notify **and** rails allow.
- Swapping `stub_brain` → `agents_sdk_brain` requires no changes outside `brain/`.