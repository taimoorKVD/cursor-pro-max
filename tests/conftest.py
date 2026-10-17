"""Keep quota counters off unless a test opts in.

Must run before orchestrator.config loads so load_dotenv does not override it.
"""
from __future__ import annotations

import os

os.environ.setdefault("ORCH_QUOTAS", "false")
