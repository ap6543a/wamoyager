"""Flask webhook server — reserved for future two-way messaging integration.

Currently unused. Users are managed manually via scripts/add_user.py.
Kept for forward compatibility if a two-way SMS provider is added later.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from brain.interface import BrainInterface
    from memory.db import Database

logger = logging.getLogger(__name__)


def create_webhook_app(db: "Database", brain: "BrainInterface") -> object:
    """Create and return the Flask app. Not active in current deployment."""
    from flask import Flask, Response, request  # type: ignore[import]

    app = Flask(__name__)

    @app.route("/health", methods=["GET"])
    def health() -> Response:
        return Response("ok", status=200)

    return app
