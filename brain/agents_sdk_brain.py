"""OpenAI Agents SDK brain — BUILD THIS during the team session.

=============================================================================
TEAM SESSION ROADMAP
=============================================================================

This file is the only one you need to touch.  Everything else (scheduler,
Gmail notifier, DB, safety rails) is already wired up and working.

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

That's it.  The Runtime, Gmail notifier, DB, and scheduler are untouched.

=============================================================================
IMPLEMENTATION TASKS (complete in order)
=============================================================================

TASK 1 — Install and import the SDK
--------------------------------------
  pip install openai-agents   (already in requirements.txt) CHECK

  Pseudocode:
    from agents import Agent, Runner, function_tool
    import openai
    openai.api_key = os.environ["OPENAI_API_KEY"]   # add to .env
"""
from __future__ import annotations
from agents import Agent, Runner, function_tool
import openai
import os
openai.api_key = os.environ["OPENAI_API_KEY"]
from typing import Any
from brain.interface import BrainInterface, DailyMessageResult, IncidentDecision
import json
import logging



class AgentsSdkBrain(BrainInterface):
    """Agent brain backed by the OpenAI Agents SDK.

    See the module-level docstring above for the full step-by-step build guide.

    TASK 1: Add imports (agents, openai, json, os) at the top of the file.
    TASK 2: Define SYSTEM_PROMPT as a module-level string.
    TASK 3: Define tool functions with @function_tool.
    TASK 4: Instantiate self.agent in __init__.
    TASK 5: Implement decide_incident.
    TASK 6: Implement compose_daily_message.
    """


    def __init__(self, db):
        global _db 
        _db = db

        SYSTEM_PROMPT= """
        You are Wamoyager, a WMATA Metrorail commute assistant.
        You receive structured data about Metro incidents or train predictions
        and you decide how to alert commuters via text message.

        URGENCY LEVELS:
            CRITICAL — station closure, total line suspension, safety incident
            MAJOR    — significant delay (>10 min), single-tracking, major disruption
            MINOR    — minor delay (<10 min), slow speeds, partial disruption
            INFO     — informational only, no immediate impact

        INCIDENT NOTIFICATION RULES:
            - Notify users if urgency is MAJOR or CRITICAL
            - Only notify users whose subscribed lines match lines_affected
            (if a user has no line preference, notify them of everything critical)
            - Be specific: mention the line, direction, and estimated delay if known
            - Do NOT include personal data or speculative information

        DAILY MESSAGE STYLE:
            - Friendly, brief, first-name greeting
            - Provide train cars that are departing within 15 minutes of alert time
            - List only 1-3 trains: line, destination, minutes away
            - Factor walk time from the National Gallery of Art, Washington DC 
                into relevant departures from desired station
            - Mention any new active alerts or updates after the last service alert affecting the user's line
            - Always include an emoji in the response
        """

        self.agent = Agent(
            name="WamoyagerBrain",
            instructions=SYSTEM_PROMPT,
            tools=[self.read_agent_state, self.write_agent_state, self.lookup_station_name],
            model="gpt-4.1-nano",   #gpt-4.1-mini is next best for cost (THIS IS TIED TO ADAM'S CC)
        )

    #TODO update build runtime
        # raise NotImplementedError(
        #     "AgentsSdkBrain.__init__: create the Agent here (see TASK 4 above)."
        # )

    @function_tool
    def read_agent_state(key: str) -> str:
        #open DB connection, SELECT value FROM agent_state WHERE key=key
        from memory.queries import get_agent_state

        #return value or empty string if not found
        try:
            value = get_agent_state(_db, key)
            return value
        except:
            return ""

    @function_tool
    def write_agent_state(key: str, value: str) -> str:
        # PSEUDO: UPSERT into agent_state (key, value, updated_at=now)
        from memory.queries import set_agent_state
        try:
            set_agent_state(_db, key, value)
            print("ok")
        except:
            print("agent state not set")


    @function_tool
    def lookup_station_name(station_code: str) -> str:
        # PSEUDO: return a human-readable station name for a WMATA station code
        # PSEUDO: use a hardcoded dict or call WMATA Station Information API
        # Example: "A01" → "Metro Center"

        stations = {
            "A01":"Metro Center",
            "A02":"Farragut North",
            "A03":"Dupont Circle",
            "A04":"Woodley Park-Zoo/Adams Morgan",
            "A05":"Cleveland Park",
            "A06":"Van Ness-UDC",
            "A07":"Tenleytown-AU",
            "A08":"Friendship Heights",
            "A09":"Bethesda",
            "A10":"Medical Center",
            "A11":"Grosvenor-Strathmore",
            "A12":"North Bethesda",
            "A13":"Twinbrook",
            "A14":"Rockville",
            "A15":"Shady Grove",
            "B01":"Gallery Pl-Chinatown",
            "B02":"Judiciary Square",
            "B03":"Union Station",
            "B04":"Rhode Island Ave-Brentwood",
            "B05":"Brookland-CUA",
            "B06":"Fort Totten",
            "B07":"Takoma",
            "B08":"Silver Spring",
            "B09":"Forest Glen",
            "B10":"Wheaton",
            "B11":"Glenmont",
            "B35":"NoMa-Gallaudet U",
            "C01":"Metro Center",
            "C02":"McPherson Square",
            "C03":"Farragut West",
            "C04":"Foggy Bottom-GWU",
            "C05":"Rosslyn",
            "C06":"Arlington Cemetery",
            "C07":"Pentagon",
            "C08":"Pentagon City",
            "C09":"Crystal City",
            "C10":"DCA",
            "C11":"Potomac Yard",
            "C12":"Braddock Road",
            "C13":"King St-Old Town",
            "C14":"Eisenhower Avenue",
            "C15":"Huntington",
            "D01":"Federal Triangle",
            "D02":"Smithsonian",
            "D03":"L'Enfant Plaza",
            "D04":"Federal Center SW",
            "D05":"Capitol South",
            "D06":"Eastern Market",
            "D07":"Potomac Ave",
            "D08":"Stadium-Armory",
            "D09":"Minnesota Ave",
            "D10":"Deanwood",
            "D11":"Cheverly",
            "D12":"Landover",
            "D13":"New Carrollton",
            "E01":"Mt Vernon Sq 7th St-Convention Center",
            "E02":"Shaw-Howard U",
            "E03":"U Street/African-Amer Civil War Memorial/Cardozo",
            "E04":"Columbia Heights",
            "E05":"Georgia Ave-Petworth",
            "E06":"Fort Totten",
            "E07":"West Hyattsville",
            "E08":"Hyattsville Crossing",
            "E09":"College Park-U of Md",
            "E10":"Greenbelt",
            "F01":"Gallery Pl-Chinatown",
            "F02":"Archives-Navy Memorial-Penn Quarter",
            "F03":"L'Enfant Plaza",
            "F04":"Waterfront",
            "F05":"Navy Yard-Ballpark",
            "F06":"Anacostia",
            "F07":"Congress Heights",
            "F08":"Southern Avenue",
            "F09":"Naylor Road",
            "F10":"Suitland",
            "F11":"Branch Ave",
            "G01":"Benning Road",
            "G02":"Capitol Heights",
            "G03":"Addison Road-Seat Pleasant",
            "G04":"Morgan Boulevard",
            "G05":"Downtown Largo",
            "J02":"Van Dorn Street",
            "J03":"Franconia-Springfield",
            "K01":"Court House",
            "K02":"Clarendon",
            "K03":"Virginia Square-GMU",
            "K04":"Ballston-MU",
            "K05":"East Falls Church",
            "K06":"West Falls Church",
            "K07":"Dunn Loring-Merrifield",
            "K08":"Vienna/Fairfax-GMU",
            "N01":"McLean",
            "N02":"Tysons",
            "N03":"Greensboro",
            "N04":"Spring Hill",
            "N06":"Wiehle-Reston East",
            "N07":"Reston Town Center",
            "N08":"Herndon",
            "N09":"Innovation Center",
            "N10":"Washington Dulles International Airport",
            "N11":"Loudoun Gateway",
            "N12":"Ashburn"
        }
        return stations.get(station_code.upper(), f"Station {station_code}")
    """
    Optional / stretch tools:
    """
    @function_tool
    def get_recent_notifications_for_user(user_id: int) -> str:
        # PSEUDO: query notifications table for last N notifications for this user
        # PSEUDO: return a JSON string summary (type, body, created_at)
        print("stretch goal")
        pass
    """
    TASK 5 — Implement decide_incident
    --------------------------------------
    This method must return an IncidentDecision dataclass.

    """
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
          "message_all": "the message text or null"
        }}
        """
        print(prompt)
        try:
            # 2. Run the agent synchronously
            result = Runner.run_sync(self.agent, prompt)
            print("Running the agent synchronously")
            # 3. Parse the agent's text output as JSON
            data = json.loads(result.final_output)             # parse to dict

            # 4. Map parsed dict → IncidentDecision dataclass
            return IncidentDecision(
                notify=data["notify"],
                urgency_level=data["urgency_level"],
                audience_user_ids=data.get("audience_user_ids", []),
                messages={},
                message_all=data.get("message_all"),
            )
        except:
            print("decision failed - decide_incident()")
#TODO add exception logic for failure


        # HINT: wrap json.loads in a try/except and fall back to StubBrain
        #       if the agent returns malformed output

    """
    TASK 6 — Implement compose_daily_message
    --------------------------------------
    This method must return a DailyMessageResult dataclass.
    """
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
        - Note any relevant alerts if present
        - Always recommend a song for the commute but do not repeat a song across users
        Return only the message text, no JSON wrapper.
        """
#TODO: see if this conflict with system prompt message (daily messaging style)
        try:
            # 2. Run the agent
            result = Runner.run_sync(self.agent, prompt)

            # 3. Return the message text
            message = result.final_output.strip()

            # # 4. Hard cap at 160 chars as a safety rail
            # if len(message) > 160:
            #     message = message[:159] + "…"
            
            return DailyMessageResult(message=message)
#TODO: see if we get hard cap on message 
        except Exception as e:
            logging.getLogger(__name__).error("AgentsSdkBrain.compose_daily_message failed: %s", e)
            return DailyMessageResult(message="hey it's broken")
        
"""
=============================================================================
TESTING YOUR IMPLEMENTATION
=============================================================================

After implementing:

  # Quick unit test (dry-run, no real emails sent, no live WMATA):
  python scripts/run_poll_once.py

  # Daily message dry-run:
  python scripts/run_daily_once.py

  # Check the notifications table to see what would have been sent:
  python - <<'EOF'
  import sqlite3
  conn = sqlite3.connect("wamoyager.db")
  conn.row_factory = sqlite3.Row
  for r in conn.execute("SELECT * FROM notifications ORDER BY created_at DESC LIMIT 10").fetchall():
      print(dict(r))
  EOF

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

# from __future__ import annotations

# from typing import Any

# from brain.interface import BrainInterface, DailyMessageResult, IncidentDecision


# class AgentsSdkBrain(BrainInterface):
#     """Agent brain backed by the OpenAI Agents SDK.

#     See the module-level docstring above for the full step-by-step build guide.

#     TASK 1: Add imports (agents, openai, json, os) at the top of the file.
#     TASK 2: Define SYSTEM_PROMPT as a module-level string.
#     TASK 3: Define tool functions with @function_tool.
#     TASK 4: Instantiate self.agent in __init__.
#     TASK 5: Implement decide_incident.
#     TASK 6: Implement compose_daily_message.
#     """

#     def __init__(self, db):
#         global _db 
#         _db = db

#         self.agent = Agent(
#             name="WamoyagerBrain",
#             instructions=SYSTEM_PROMPT,
#             tools=[read_agent_state, write_agent_state, lookup_station_name],
#             model="gpt-4o-mini",   # or "gpt-4o-mini" for lower cost (THIS IS TIED TO ADAM'S CC)
#         )

#     #TODO update build runtime
#         raise NotImplementedError(
#             "AgentsSdkBrain.__init__: create the Agent here (see TASK 4 above)."
#         )

    # def decide_incident(
    #     self,
    #     incident: dict[str, Any],
    #     users_relevant: list[dict[str, Any]],
    #     history_recent: list[dict[str, Any]],
    # ) -> IncidentDecision:
    #     """Decide whether and how to notify users about a WMATA incident.

    #     See TASK 5 in the module docstring for the full pseudocode.

    #     Args:
    #         incident:        normalized incident dict (fingerprint, title,
    #                          description, lines_affected, severity, raw)
    #         users_relevant:  list of active user dicts, each with a
    #                          "preferences" key containing lines, station_codes,
    #                          and direction
    #         history_recent:  last ~50 known incidents (for dedup context)

    #     Returns:
    #         IncidentDecision — notify flag, urgency level, audience IDs,
    #         and message text.
    #     """
    #     # TASK 5: implement this method.
    #     # Rough skeleton to fill in:
    #     #
    #     #   import json
    #     #   prompt = build_incident_prompt(incident, users_relevant, history_recent)
    #     #   result = Runner.run_sync(self.agent, prompt)
    #     #   data = json.loads(result.final_output)
    #     #   return IncidentDecision(
    #     #       notify=data["notify"],
    #     #       urgency_level=data["urgency_level"],
    #     #       audience_user_ids=data.get("audience_user_ids", []),
    #     #       messages={},
    #     #       message_all=data.get("message_all"),
    #     #   )
    #     raise NotImplementedError(
    #         "AgentsSdkBrain.decide_incident: implement this (see TASK 5 above)."
    #     )

    # def compose_daily_message(
    #     self,
    #     user: dict[str, Any],
    #     predictions: list[dict[str, Any]],
    #     system_status_summary: str | None,
    # ) -> DailyMessageResult:
    #     """Compose the daily 5pm next-train SMS for a user.

    #     See TASK 6 in the module docstring for the full pseudocode.

    #     Args:
    #         user:                   user dict merged with preferences
    #                                 (name, email, preferences.lines,
    #                                  preferences.station_codes, preferences.direction)
    #         predictions:            real-time train predictions for user's stations
    #                                 (station_code, destination, line, minutes, car_count)
    #         system_status_summary:  optional brief system-wide status string

    #     Returns:
    #         DailyMessageResult with the SMS text (max 160 chars).
    #     """
    #     # TASK 6: implement this method.
    #     # Rough skeleton to fill in:
    #     #
    #     #   import json
    #     #   prompt = build_daily_prompt(user, predictions, system_status_summary)
    #     #   result = Runner.run_sync(self.agent, prompt)
    #     #   message = result.final_output.strip()[:160]
    #     #   return DailyMessageResult(message=message)
    #     raise NotImplementedError(
    #         "AgentsSdkBrain.compose_daily_message: implement this (see TASK 6 above)."
    #     )
