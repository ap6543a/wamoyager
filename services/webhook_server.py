"""Flask webhook server that receives inbound SMS from Twilio.

Twilio sends a POST to /sms whenever someone texts the Wamoyager number.
We reply with TwiML so Twilio delivers our response back to the user.

To point Twilio at this server:
  1. Expose port WEBHOOK_PORT (default 8080) to the internet, e.g. via ngrok:
       ngrok http 8080
  2. Set your Twilio number's inbound webhook URL to:
       https://<your-domain>/sms
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from brain.interface import BrainInterface
    from memory.db import Database

logger = logging.getLogger(__name__)


def create_webhook_app(db: "Database", brain: "BrainInterface") -> object:
    """Create and return the Flask app wired to the given DB and Brain."""
    from flask import Flask, Response, request  # type: ignore[import]
    from twilio.twiml.messaging_response import MessagingResponse  # type: ignore[import]
    from services.inbound_handler import handle as handle_inbound

    app = Flask(__name__)

    @app.route("/sms", methods=["POST"])
    def sms() -> Response:
        from_number: str = request.form.get("From", "").strip()
        body: str = request.form.get("Body", "").strip()

        logger.info("Inbound SMS from=%s body=%r", from_number, body[:80])

        if not from_number:
            logger.warning("Inbound SMS missing From field; ignoring.")
            return Response("", status=400)

        try:
            reply = handle_inbound(from_number=from_number, body=body, db=db, brain=brain)
        except Exception:
            logger.exception("Unhandled error in inbound_handler for from=%s", from_number)
            reply = "Something went wrong. Please try again."

        resp = MessagingResponse()
        resp.message(reply)
        return Response(str(resp), mimetype="text/xml")

    @app.route("/health", methods=["GET"])
    def health() -> Response:
        return Response("ok", status=200)

    return app
