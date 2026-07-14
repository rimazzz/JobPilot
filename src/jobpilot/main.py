"""ASGI entrypoint.

Run with:  ``uvicorn jobpilot.main:app --host 0.0.0.0 --port 8000``
"""

from __future__ import annotations

from jobpilot.api.app import create_app

app = create_app()
