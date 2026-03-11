"""OpenAI Agents SDK brain — BUILD THIS during the team session.

=============================================================================
TEAM SESSION ROADMAP
=============================================================================

This file is the only one you need to touch.  Everything else (scheduler,
Twilio, DB, safety rails) is already wired up and working.

GOAL: Replace the deterministic StubBrain with an AI agent that uses the
OpenAI Agents SDK to make smarter decisions about incident urgency and compose
more natural-sounding daily commute messages.

HOW TO SWAP IN: Once this class works, open wamoyager_runtime/main.py and
change two lines:

    # FROM:
    from brain.stub_brain import StubBrain
    brain = StubBrain()

    # TO:
    from brain.agents_sdk_brain import AgentsSdkBrain
    brain = AgentsSdkBrain()

That's it.  The Runtime, Twilio, DB, and scheduler are untouched.

=============================================================================
IMPLEMENTATION TASKS (complete in order)
=============================================================================

TASK 1 — Install and import the SDK
--------------------------------------
  pip install openai-agents   (already in requirements.txt)

  Pseudocode:
    from agents import Agent, Runner, function_tool
    import openai
    openai.api_key = os.environ["OPENAI_API_KEY"]   # add to .env

TASK 2 — Write the system prompt
--------------------------------------
  The prompt tells the agent its job, the urgency rules, and the SMS style.

  Pseudocode (SYSTEM_PROMPT string):

    You are Wamoyager, a WMATA Metrorail commute assistant.
    You receive structured data about Metro incidents or train predictions
    and you decide how to alert commuters via SMS.

    URGENCY LEVELS:
      CRITICAL — station closure, total line suspension, safety incident
      MAJOR    — significant delay (>10 min), single-tracking, major disruption
      MINOR    — minor delay (<10 min), slow speeds, partial disruption
      INFO     — informational only, no immediate impact

    INCIDENT NOTIFICATION RULES:
      - Notify users if urgency is MAJOR or CRITICAL
      - Only notify users whose subscribed lines match lines_affected
        (if a user has no line preference, notify them of everything MAJOR+)
      - Keep SMS under 160 characters
      - Be specific: mention the line, direction, and estimated delay if known
      - Do NOT include personal data or speculative information

    DAILY MESSAGE STYLE:
      - Friendly, brief, first-name greeting
      - List the next 1–3 trains: line, destination, minutes away
      - Mention any active alerts affecting the user's line
      - Keep under 160 characters

TASK 3 — Define tools the agent can call
--------------------------------------
  Tools let the agent read memory or look up extra WMATA data.
  Each tool is a plain Python function decorated with @function_tool.

  Pseudocode:

    @function_tool
    def read_agent_state(key: str) -> str:
        # PSEUDO: open DB connection, SELECT value FROM agent_state WHERE key=key
        # PSEUDO: return value or empty string if not found
        pass

    @function_tool
    def write_agent_state(key: str, value: str) -> str:
        # PSEUDO: UPSERT into agent_state (key, value, updated_at=now)
        # PSEUDO: return "ok"
        pass

    @function_tool
    def lookup_station_name(station_code: str) -> str:
        # PSEUDO: return a human-readable station name for a WMATA station code
        # PSEUDO: use a hardcoded dict or call WMATA Station Information API
        # Example: "A01" → "Metro Center"
        pass

  Optional / stretch tools:
    @function_tool
    def get_recent_notifications_for_user(user_id: int) -> str:
        # PSEUDO: query notifications table for last N notifications for this user
        # PSEUDO: return a JSON string summary (type, body, created_at)
        pass

TASK 4 — Create the Agent
--------------------------------------
  Pseudocode:

    agent = Agent(
        name="WamoyagerBrain",
        instructions=SYSTEM_PROMPT,
        tools=[read_agent_state, write_agent_state, lookup_station_name],
        model="gpt-4o",   # or "gpt-4o-mini" for lower cost
    )

TASK 5 — Implement decide_incident
--------------------------------------
  This method must return an IncidentDecision dataclass.

  Pseudocode:

    def decide_incident(self, incident, users_relevant, history_recent):

        # 1. Build a structured prompt describing the incident
        prompt = f"""
        INCIDENT:
        {json.dumps(incident, indent=2)}

        ACTIVE USERS (with their line subscriptions):
        {json.dumps(users_relevant, indent=2)}

        RECENT NOTIFICATION HISTORY (for deduplication context):
        {json.dumps(history_recent[-10:], indent=2)}

        Task: Decide whether to notify users about this incident.
        Return a JSON object with this exact shape:
        {{
          "notify": true or false,
          "urgency_level": "INFO" | "MINOR" | "MAJOR" | "CRITICAL",
          "audience_user_ids": [list of user id integers],
          "message_all": "the SMS text (max 160 chars) or null"
        }}
        """

        # 2. Run the agent synchronously
        result = Runner.run_sync(self.agent, prompt)

        # 3. Parse the agent's text output as JSON
        raw = result.final_output          # string from agent
        data = json.loads(raw)             # parse to dict

        # 4. Map parsed dict → IncidentDecision dataclass
        return IncidentDecision(
            notify=data["notify"],
            urgency_level=data["urgency_level"],
            audience_user_ids=data.get("audience_user_ids", []),
            messages={},
            message_all=data.get("message_all"),
        )

        # HINT: wrap json.loads in a try/except and fall back to StubBrain
        #       if the agent returns malformed output

TASK 6 — Implement compose_daily_message (see below)

=============================================================================
TASK 7 — Implement handle_inbound_sms  ← NEW for inbound SMS setup
=============================================================================
  This method powers the conversational onboarding flow.  When someone texts
  your Twilio number for the first time, the agent guides them through setup
  step by step using natural language instead of rigid commands.

  The Runtime (inbound_handler.py) handles all DB reads/writes and user
  creation.  The Brain just decides what to say and what data has been
  collected.  conv_state holds where the user is in the conversation.

  conv_state shape:
    {
      "step": "new" | "awaiting_name" | "awaiting_station" |
              "awaiting_line" | "awaiting_confirm" | "complete",
      "data": {
        "name": "Alice",               ← filled in after awaiting_name
        "station_codes": ["A01"],      ← filled in after awaiting_station
        "lines": ["RD"],               ← filled in after awaiting_line
        "direction": []                ← optional
      }
    }

  Pseudocode:

    def handle_inbound_sms(self, from_number, body, conv_state):

        # 1. Build a prompt with the current state and the user's message
        prompt = f"""
        You are a friendly Metro commute assistant helping a new user sign up
        for Wamoyager alerts via SMS.

        CURRENT CONVERSATION STATE:
        Step: {conv_state["step"]}
        Collected so far: {json.dumps(conv_state["data"])}

        USER JUST SENT: "{body}"

        Your job:
        - Understand what the user meant (be forgiving of typos)
        - Advance the conversation toward collecting: name, station code(s), line(s)
        - Confirm the summary before finalising
        - Keep all replies under 160 characters
        - Be warm and concise — this is an SMS conversation

        Valid WMATA lines: RD (Red), BL (Blue), OR (Orange), SV (Silver),
                           GR (Green), YL (Yellow)
        Station codes are 3-character codes like A01, C05, etc.

        Return a JSON object with this exact shape:
        {{
          "reply": "the SMS text to send back",
          "next_step": "awaiting_name" | "awaiting_station" | "awaiting_line"
                     | "awaiting_confirm" | "complete",
          "data_update": {{
            "name": "...",            ← include only fields collected in THIS turn
            "station_codes": [...],
            "lines": [...],
            "direction": [...]
          }},
          "setup_complete": true | false   ← true only when user confirms
        }}
        """

        # 2. Run the agent
        result = Runner.run_sync(self.agent, prompt)

        # 3. Parse the response
        data = json.loads(result.final_output)

        # 4. Map to InboundSmsResult
        return InboundSmsResult(
            reply=data["reply"][:160],          # enforce 160-char cap
            next_step=data["next_step"],
            data_update=data.get("data_update", {}),
            setup_complete=data.get("setup_complete", False),
        )

  HINT: The agent is great at handling messy input — "red line" → "RD",
  "metro center" → "A01" (combine with lookup_station_name tool).
  This is where it beats the StubBrain significantly.

=============================================================================
--------------------------------------
  This method must return a DailyMessageResult dataclass.

  Pseudocode:

    def compose_daily_message(self, user, predictions, system_status_summary):

        # 1. Build a structured prompt with user context and train data
        prompt = f"""
        USER:
        {json.dumps(user, indent=2)}

        UPCOMING TRAINS (real-time predictions):
        {json.dumps(predictions, indent=2)}

        SYSTEM STATUS SUMMARY: {system_status_summary or "No active alerts."}

        Task: Compose a friendly daily commute SMS for this user.
        - Greet them by first name
        - List their next 1–3 trains (line, destination, minutes)
        - Note any relevant alerts if present
        - Stay under 160 characters
        Return only the SMS text, no JSON wrapper.
        """

        # 2. Run the agent
        result = Runner.run_sync(self.agent, prompt)

        # 3. Return the message text
        message = result.final_output.strip()

        # 4. Hard cap at 160 chars as a safety rail
        if len(message) > 160:
            message = message[:159] + "…"

        return DailyMessageResult(message=message)

=============================================================================
TESTING YOUR IMPLEMENTATION
=============================================================================

After implementing:

  # Quick unit test (no Twilio, no live WMATA):
  python scripts/run_poll_once.py     # DRY_RUN is forced true

  # Daily message dry-run:
  python scripts/run_daily_once.py

  # Check the notifications table to see what would have been sent:
  sqlite3 wamoyager.db "SELECT * FROM notifications ORDER BY created_at DESC LIMIT 10;"

=============================================================================
STRETCH GOALS (if time allows)
=============================================================================

  A. Per-user messages instead of message_all
     — Remove message_all, populate messages dict keyed by user_id
     — Allows personalised tone ("Alice, your Red Line train..." vs generic)

  B. Agent memory between polls
     — Use write_agent_state to store last severity per fingerprint
     — Use read_agent_state in the prompt so agent knows if this is new or escalating

  C. Multi-step agent (handoffs)
     — Create a "classifier" agent and a "composer" agent
     — Classifier decides notify/urgency; Composer writes the SMS text
     — Demonstrates agent handoffs with the OpenAI Agents SDK

=============================================================================
"""

from __future__ import annotations

from typing import Any

from brain.interface import BrainInterface, DailyMessageResult, IncidentDecision, InboundSmsResult


class AgentsSdkBrain(BrainInterface):
    """Agent brain backed by the OpenAI Agents SDK.

    See the module-level docstring above for the full step-by-step build guide.

    TASK 1: Add imports (agents, openai, json, os) at the top of the file.
    TASK 2: Define SYSTEM_PROMPT as a module-level string.
    TASK 3: Define tool functions with @function_tool.
    TASK 4: Instantiate self.agent in __init__.
    TASK 5: Implement decide_incident.
    TASK 6: Implement compose_daily_message.
    TASK 7: Implement handle_inbound_sms.
    """

    def __init__(self) -> None:
        # TASK 4: Replace this with:
        #   self.agent = Agent(
        #       name="WamoyagerBrain",
        #       instructions=SYSTEM_PROMPT,
        #       tools=[read_agent_state, write_agent_state, lookup_station_name],
        #       model="gpt-4o",
        #   )
        raise NotImplementedError(
            "AgentsSdkBrain.__init__: create the Agent here (see TASK 4 above)."
        )

    def handle_inbound_sms(
        self,
        from_number: str,
        body: str,
        conv_state: dict[str, Any],
    ) -> InboundSmsResult:
        """Guide a new user through the SMS setup conversation.

        See TASK 7 in the module docstring for the full pseudocode.

        Args:
            from_number: E.164 number of the sender.
            body:        Cleaned SMS body text.
            conv_state:  Current state dict with keys "step" and "data".

        Returns:
            InboundSmsResult — reply text, next step, data collected this
            turn, and a flag to trigger user creation when setup is done.
        """
        # TASK 7: implement this method.
        # Rough skeleton to fill in:
        #
        #   import json
        #   prompt = build_inbound_prompt(body, conv_state)
        #   result = Runner.run_sync(self.agent, prompt)
        #   data = json.loads(result.final_output)
        #   return InboundSmsResult(
        #       reply=data["reply"][:160],
        #       next_step=data["next_step"],
        #       data_update=data.get("data_update", {}),
        #       setup_complete=data.get("setup_complete", False),
        #   )
        raise NotImplementedError(
            "AgentsSdkBrain.handle_inbound_sms: implement this (see TASK 7 above)."
        )

    def decide_incident(
        self,
        incident: dict[str, Any],
        users_relevant: list[dict[str, Any]],
        history_recent: list[dict[str, Any]],
    ) -> IncidentDecision:
        """Decide whether and how to notify users about a WMATA incident.

        See TASK 5 in the module docstring for the full pseudocode.

        Args:
            incident:        normalized incident dict (fingerprint, title,
                             description, lines_affected, severity, raw)
            users_relevant:  list of active user dicts, each with a
                             "preferences" key containing lines, station_codes,
                             and direction
            history_recent:  last ~50 known incidents (for dedup context)

        Returns:
            IncidentDecision — notify flag, urgency level, audience IDs,
            and message text.
        """
        # TASK 5: implement this method.
        # Rough skeleton to fill in:
        #
        #   import json
        #   prompt = build_incident_prompt(incident, users_relevant, history_recent)
        #   result = Runner.run_sync(self.agent, prompt)
        #   data = json.loads(result.final_output)
        #   return IncidentDecision(
        #       notify=data["notify"],
        #       urgency_level=data["urgency_level"],
        #       audience_user_ids=data.get("audience_user_ids", []),
        #       messages={},
        #       message_all=data.get("message_all"),
        #   )
        raise NotImplementedError(
            "AgentsSdkBrain.decide_incident: implement this (see TASK 5 above)."
        )

    def compose_daily_message(
        self,
        user: dict[str, Any],
        predictions: list[dict[str, Any]],
        system_status_summary: str | None,
    ) -> DailyMessageResult:
        """Compose the daily 5pm next-train SMS for a user.

        See TASK 6 in the module docstring for the full pseudocode.

        Args:
            user:                   user dict merged with preferences
                                    (name, phone_e164, preferences.lines,
                                     preferences.station_codes, preferences.direction)
            predictions:            real-time train predictions for user's stations
                                    (station_code, destination, line, minutes, car_count)
            system_status_summary:  optional brief system-wide status string

        Returns:
            DailyMessageResult with the SMS text (max 160 chars).
        """
        # TASK 6: implement this method.
        # Rough skeleton to fill in:
        #
        #   import json
        #   prompt = build_daily_prompt(user, predictions, system_status_summary)
        #   result = Runner.run_sync(self.agent, prompt)
        #   message = result.final_output.strip()[:160]
        #   return DailyMessageResult(message=message)
        raise NotImplementedError(
            "AgentsSdkBrain.compose_daily_message: implement this (see TASK 6 above)."
        )
