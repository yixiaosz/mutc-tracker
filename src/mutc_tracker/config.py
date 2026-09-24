from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_POLL_INTERVAL_SECONDS = 60 * 60
GRAPHQL_URL = "https://cms.mutc.com.au/api/graphql"
BOOKING_URL = "https://www.mutc.com.au/book?sessionId={session_id}"

# Exclude Bootcamp even if it later starts using the EventSessions collection.
EXCLUDED_EVENT_IDS = frozenset({"64b52d6fdcda7bc59fa6b749"})


def default_state_dir() -> Path:
    root = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return root / "mutc-tracker"


@dataclass(frozen=True)
class Settings:
    poll_interval_seconds: float
    state_file: Path
    log_file: Path
    ntfy_server: str
    ntfy_topic: str | None
    ntfy_token: str | None

    @classmethod
    def from_env(cls) -> Settings:
        state_dir = default_state_dir()
        return cls(
            poll_interval_seconds=float(
                os.environ.get(
                    "MUTC_POLL_INTERVAL_SECONDS", DEFAULT_POLL_INTERVAL_SECONDS
                )
            ),
            state_file=Path(
                os.environ.get("MUTC_STATE_FILE", state_dir / "state.json")
            ).expanduser(),
            log_file=Path(
                os.environ.get("MUTC_LOG_FILE", state_dir / "tracker.log")
            ).expanduser(),
            ntfy_server=os.environ.get("MUTC_NTFY_SERVER", "https://ntfy.sh").rstrip(
                "/"
            ),
            ntfy_topic=os.environ.get("MUTC_NTFY_TOPIC") or None,
            ntfy_token=os.environ.get("MUTC_NTFY_TOKEN") or None,
        )
