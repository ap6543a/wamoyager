# Wamoyager — Team Session Build Guide

This guide walks you through building the AI brain step by step. Every task
tells you exactly what to write, where it goes, and how it connects to the
rest of the repo.

**The only file you edit is `brain/agents_sdk_brain.py`.**
Everything else — Gmail, scheduler, DB, safety rails — is already running.

---

## How the brain plugs in

When a WMATA incident is detected or 5pm arrives, the runtime calls the brain
and waits for a decision. Here is the exact call in `wamoyager_runtime/main.py`:

```python
# run_poll_cycle (line ~85) — incident alert path
decision = brain.decide_incident(incident_dict, user_dicts, history)

# run_daily_cycle (line ~150) — daily 5pm path
result = brain.compose_daily_message(user_dict, predictions, system_status_summary)
```

The brain returns a structured result. The runtime then applies safety rails
(rate limit, cooldown) and calls `EmailNotifier.send_sms()` to deliver the
message. **The brain never sends anything directly.**

The contract the brain must satisfy is defined in `brain/interface.py`:

```python
class BrainInterface(ABC):
    def decide_incident(...) -> IncidentDecision
    def compose_daily_message(...) -> DailyMessageResult
```

`StubBrain` in `brain/stub_brain.py` is the working example — read it if you
get stuck. `AgentsSdkBrain` in `brain/agents_sdk_brain.py` is what you build.

---

## Task 1 — Imports and API key

**Where:** top of `brain/agents_sdk_brain.py`, replace the existing imports block.

```python
from __future__ import annotations

import json
import os
from typing import Any

from agents import Agent, Runner, function_tool

from brain.interface import BrainInterface, DailyMessageResult, IncidentDecision
```

**API key** — add this to your `.env` file:
```
OPENAI_API_KEY=sk-...
```

The SDK picks it up automatically from the environment — no extra code needed.

**Verify it works:**
```bash
python - <<'EOF'
from agents import Agent, Runner
print("SDK imported OK")
EOF
```

---

## Task 2 — System prompt

**Where:** module level in `brain/agents_sdk_brain.py`, below the imports,
before the class definition.

This is the personality and ruleset baked into the agent. Write it as a
plain string constant:

```python
SYSTEM_PROMPT = """
You are Wamoyager, a WMATA Metrorail commute assistant.
You receive structured data about Metro incidents or train predictions
and you decide how to alert commuters via text message.

URGENCY LEVELS:
  CRITICAL — station closure, total line suspension, safety incident
  MAJOR    — significant delay (>10 min), single-tracking, major disruption
  MINOR    — minor delay (<10 min), slow speeds, partial disruption
  INFO     — informational only, no immediate impact

INCIDENT NOTIFICATION RULES:
  - Notify users only if urgency is MAJOR or CRITICAL
  - Only notify users whose subscribed lines match the affected lines
    (if a user has no line preference, notify them of everything MAJOR+)
  - Keep messages under 160 characters
  - Be specific: mention the line, direction, and estimated delay if known
  - Do NOT include personal data or speculative information

DAILY MESSAGE STYLE:
  - Friendly, brief greeting using the user's first name
  - List the next 1-3 trains: line, destination, minutes away
  - Mention any active alerts on the user's line
  - Keep under 160 characters
"""
```

---

## Task 3 — Tools

Tools are plain Python functions the agent can call during its reasoning.
They give the agent access to the database and WMATA station data.

**Where:** module level in `brain/agents_sdk_brain.py`, below `SYSTEM_PROMPT`.

These functions call the query functions already built in `memory/queries.py`.
The DB instance is passed in via a module-level variable set in `__init__`.

```python
# Module-level DB handle — set by AgentsSdkBrain.__init__
_db = None

@function_tool
def read_agent_state(key: str) -> str:
    """Read a value from the agent's persistent key-value memory store."""
    # Calls get_agent_state() defined in memory/queries.py (line ~371)
    from memory.queries import get_agent_state
    value = get_agent_state(_db, key)
    return value or ""

@function_tool
def write_agent_state(key: str, value: str) -> str:
    """Write a value to the agent's persistent key-value memory store."""
    # Calls set_agent_state() defined in memory/queries.py (line ~378)
    from memory.queries import set_agent_state
    set_agent_state(_db, key, value)
    return "ok"

@function_tool
def lookup_station_name(station_code: str) -> str:
    """Return the human-readable name for a WMATA station code."""
    # Hardcoded lookup — extend as needed
    stations = {
        "A01": "Metro Center", "A02": "Farragut North", "A03": "Dupont Circle",
        "A04": "Woodley Park", "A05": "Cleveland Park", "A06": "Van Ness",
        "A07": "Tenleytown", "A08": "Friendship Heights", "A09": "Bethesda",
        "A10": "Friendship Heights", "A11": "White Flint", "A12": "Twinbrook",
        "A13": "Rockville", "A14": "Shady Grove",
        "B01": "Gallery Place", "B02": "Judiciary Square", "B03": "Union Station",
        "B04": "Rhode Island Ave", "B05": "Brookland", "B06": "Fort Totten",
        "B07": "Takoma", "B08": "Silver Spring", "B09": "Forest Glen",
        "B10": "Wheaton", "B11": "Glenmont", "B35": "NoMa-Gallaudet",
        "C01": "Metro Center", "C02": "McPherson Square", "C03": "Farragut West",
        "C04": "Foggy Bottom", "C05": "Rosslyn", "C06": "Arlington Cemetery",
        "C07": "Pentagon", "C08": "Pentagon City", "C09": "Crystal City",
        "C10": "Reagan Airport", "C12": "Braddock Road", "C13": "King St",
    }
    return stations.get(station_code.upper(), f"Station {station_code}")
```

**How the DB gets wired in** — you'll set `_db` in `__init__` (Task 4):
```python
# In __init__:
global _db
_db = db
```

---

## Task 4 — Create the Agent

**Where:** `AgentsSdkBrain.__init__` in `brain/agents_sdk_brain.py`.

Replace the `raise NotImplementedError` with this:

```python
def __init__(self, db) -> None:
    global _db
    _db = db                    # wire the DB into the tool functions above

    self.agent = Agent(
        name="WamoyagerBrain",
        instructions=SYSTEM_PROMPT,
        tools=[read_agent_state, write_agent_state, lookup_station_name],
        model="gpt-4o",         # swap for "gpt-4o-mini" to reduce cost
    )
```

**Note:** the `__init__` signature changes from `()` to `(self, db)`.
That means the swap in `wamoyager_runtime/main.py` becomes:

```python
# In build_runtime() — wamoyager_runtime/main.py line ~34
from brain.agents_sdk_brain import AgentsSdkBrain
brain = AgentsSdkBrain(db=db)   # pass the db instance
```

---

## Task 5 — decide_incident

**Where:** `AgentsSdkBrain.decide_incident` in `brain/agents_sdk_brain.py`.

This method is called by `run_poll_cycle` in `wamoyager_runtime/main.py` every
time a WMATA incident is detected. It must return an `IncidentDecision`
(defined in `brain/interface.py`).

Replace the `raise NotImplementedError` with:

```python
def decide_incident(self, incident, users_relevant, history_recent):
    prompt = f"""
INCIDENT:
{json.dumps(incident, indent=2)}

ACTIVE USERS (with their subscribed lines):
{json.dumps(users_relevant, indent=2)}

RECENT NOTIFICATION HISTORY (last 10, for deduplication):
{json.dumps(history_recent[-10:], indent=2)}

Task: Decide whether to notify users about this incident.
Return a JSON object with exactly this shape — no extra text:
{{
  "notify": true,
  "urgency_level": "MAJOR",
  "audience_user_ids": [4, 5],
  "message_all": "[MAJOR] Red Line delays near Metro Center. Expect 15+ min delays."
}}
"""
    try:
        result = Runner.run_sync(self.agent, prompt)
        data = json.loads(result.final_output)
        return IncidentDecision(
            notify=data["notify"],
            urgency_level=data["urgency_level"],
            audience_user_ids=data.get("audience_user_ids", []),
            messages={},
            message_all=data.get("message_all"),
        )
    except Exception as e:
        # Fall back to a safe no-notify decision if the agent fails
        import logging
        logging.getLogger(__name__).error("AgentsSdkBrain.decide_incident failed: %s", e)
        return IncidentDecision(notify=False, urgency_level="INFO",
                                audience_user_ids=[], messages={})
```

**What the runtime does with this result** — after you return it, the runtime
in `wamoyager_runtime/main.py` (line ~87) runs it through the safety rails:

```python
# Already built — you don't write this
if not check_rate_limit(user_id, db, ...):   # wamoyager_runtime/rails.py
    continue
if not check_cooldown(user_id, fingerprint, db, ...):
    continue
notifier.send_sms(to=user["email"], body=decision.message_all, ...)
```

---

## Task 6 — compose_daily_message

**Where:** `AgentsSdkBrain.compose_daily_message` in `brain/agents_sdk_brain.py`.

This method is called by `run_daily_cycle` in `wamoyager_runtime/main.py` at
5pm ET for every active user. It must return a `DailyMessageResult`
(defined in `brain/interface.py`).

Replace the `raise NotImplementedError` with:

```python
def compose_daily_message(self, user, predictions, system_status_summary):
    prompt = f"""
USER:
{json.dumps(user, indent=2)}

UPCOMING TRAINS (real-time predictions for their station):
{json.dumps(predictions, indent=2)}

SYSTEM STATUS: {system_status_summary or "No active alerts."}

Task: Compose a friendly daily commute text message for this user.
- Greet them by first name
- List their next 1-3 trains (line, destination, minutes away)
- Mention any relevant alerts if present
- Keep under 160 characters
Return only the message text — no JSON, no labels.
"""
    try:
        result = Runner.run_sync(self.agent, prompt)
        message = result.final_output.strip()
        if len(message) > 160:
            message = message[:159] + "…"
        return DailyMessageResult(message=message)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error("AgentsSdkBrain.compose_daily_message failed: %s", e)
        return DailyMessageResult(message=f"Hi {user.get('name', 'there')}! Check wmata.com for your train times.")
```

---

## Task 7 — Swap in the brain and test

**1. Update `wamoyager_runtime/main.py`** — find `build_runtime()` (~line 17)
and change these two lines:

```python
# FROM:
from brain.stub_brain import StubBrain
brain = StubBrain()

# TO:
from brain.agents_sdk_brain import AgentsSdkBrain
brain = AgentsSdkBrain(db=db)
```

**2. Test the daily message (dry run — no emails sent):**
```bash
DRY_RUN=true python scripts/run_daily_once.py
```

You should see the agent's composed messages in the log output.

**3. Test a poll cycle (dry run):**
```bash
python scripts/run_poll_once.py
```

**4. Check what the agent decided:**
```bash
python - <<'EOF'
import sqlite3
conn = sqlite3.connect("wamoyager.db")
conn.row_factory = sqlite3.Row
for r in conn.execute("SELECT * FROM notifications ORDER BY created_at DESC LIMIT 10").fetchall():
    print(dict(r))
EOF
```

**5. Send for real:**
```bash
DRY_RUN=false python scripts/run_daily_once.py
```

---

## Full file structure at the end of the session

```python
# brain/agents_sdk_brain.py — complete structure

from __future__ import annotations
import json, os
from typing import Any
from agents import Agent, Runner, function_tool
from brain.interface import BrainInterface, DailyMessageResult, IncidentDecision

SYSTEM_PROMPT = "..."       # Task 2

_db = None                  # Task 3 — module-level DB handle

@function_tool              # Task 3
def read_agent_state(key: str) -> str: ...

@function_tool              # Task 3
def write_agent_state(key: str, value: str) -> str: ...

@function_tool              # Task 3
def lookup_station_name(station_code: str) -> str: ...

class AgentsSdkBrain(BrainInterface):

    def __init__(self, db) -> None: ...         # Task 4 — create Agent

    def decide_incident(self, ...) -> IncidentDecision: ...       # Task 5

    def compose_daily_message(self, ...) -> DailyMessageResult: ...  # Task 6

```

---

## Stretch goals

**A. Per-user personalised messages**
Instead of `message_all`, populate the `messages` dict in `IncidentDecision`
with a unique message per user. The runtime in `main.py` already checks
`decision.messages.get(user_id)` before falling back to `message_all`.

**B. Agent memory across polls**
Use `write_agent_state("last_severity:{fingerprint}", "MAJOR")` after notifying,
then `read_agent_state(...)` in the next poll so the agent knows if an incident
is new or escalating. The `agent_state` table in the DB is already there.

**C. Two-agent handoff**
Split into a `ClassifierAgent` (decides urgency + audience) and a
`ComposerAgent` (writes the message). Use the Agents SDK handoff feature to
pass the classifier's output to the composer. This demonstrates multi-agent
orchestration with the SDK.
