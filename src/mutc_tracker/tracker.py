from __future__ import annotations

import json
import logging
import os
import tempfile
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .config import BOOKING_URL, EXCLUDED_EVENT_IDS, GRAPHQL_URL

LOGGER = logging.getLogger(__name__)
PAGE_SIZE = 100

SESSION_QUERY = """
query EventSessions($page: Int!, $limit: Int!) {
  EventSessions(sort: "-startDayAndTime", page: $page, limit: $limit) {
    docs {
      id
      day
      startTime
      endTime
      startDayAndTime
      endDayAndTime
      isAvailable
      isBookedOut
      noOfBookings
      event {
        id
        title
        slug
      }
    }
    hasNextPage
    nextPage
  }
}
"""


@dataclass(frozen=True)
class Session:
    id: str
    event_id: str
    event_title: str
    event_slug: str
    day: str
    start_time: str
    end_time: str
    start_day_and_time: str
    end_day_and_time: str
    is_available: bool
    is_booked_out: bool
    no_of_bookings: int

    @property
    def is_actionable(self) -> bool:
        return self.is_available and not self.is_booked_out

    @property
    def booking_url(self) -> str:
        return BOOKING_URL.format(session_id=self.id)

    @classmethod
    def from_api(cls, value: dict[str, Any]) -> Session:
        event = value.get("event")
        if not isinstance(event, dict):
            raise TypeError(f"Session {value.get('id', '<unknown>')} has no event")
        return cls(
            id=str(value["id"]),
            event_id=str(event["id"]),
            event_title=str(event["title"]),
            event_slug=str(event["slug"]),
            day=str(value["day"]),
            start_time=str(value["startTime"]),
            end_time=str(value["endTime"]),
            start_day_and_time=str(value["startDayAndTime"]),
            end_day_and_time=str(value["endDayAndTime"]),
            is_available=bool(value["isAvailable"]),
            is_booked_out=bool(value["isBookedOut"]),
            no_of_bookings=int(value["noOfBookings"]),
        )


@dataclass(frozen=True)
class Alert:
    session: Session
    reason: str

    @property
    def message(self) -> str:
        session = self.session
        return (
            f"{self.reason}: {session.event_title}\n"
            f"{session.day}, {session.start_time} - {session.end_time}\n"
            f"Current bookings: {session.no_of_bookings}"
        )

    @property
    def is_full(self) -> bool:
        return self.reason == "Session now full"


class MutcClient:
    def __init__(
        self,
        endpoint: str = GRAPHQL_URL,
        urlopen: Callable[..., Any] = urllib.request.urlopen,
    ) -> None:
        self.endpoint = endpoint
        self.urlopen = urlopen

    def fetch_sessions(self) -> list[Session]:
        sessions: list[Session] = []
        page = 1

        while True:
            payload = json.dumps(
                {
                    "query": SESSION_QUERY,
                    "variables": {"page": page, "limit": PAGE_SIZE},
                }
            ).encode()
            request = urllib.request.Request(
                self.endpoint,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "mutc-tracker/0.1",
                },
                method="POST",
            )
            with self.urlopen(request, timeout=30) as response:
                result = json.load(response)

            if result.get("errors"):
                raise RuntimeError(f"GraphQL returned errors: {result['errors']}")

            collection = result.get("data", {}).get("EventSessions")
            if not isinstance(collection, dict):
                raise TypeError("GraphQL response did not contain EventSessions")

            for raw_session in collection.get("docs", []):
                session = Session.from_api(raw_session)
                if session.event_id not in EXCLUDED_EVENT_IDS:
                    sessions.append(session)

            if not collection.get("hasNextPage"):
                break
            page = int(collection["nextPage"])

        return sessions


class StateStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def exists(self) -> bool:
        return self.path.exists()

    def load(self) -> dict[str, Session]:
        with self.path.open(encoding="utf-8") as file:
            data = json.load(file)
        if data.get("version") != 1 or not isinstance(data.get("sessions"), dict):
            raise ValueError(f"Unsupported state file format: {self.path}")
        return {
            session_id: Session(**session)
            for session_id, session in data["sessions"].items()
        }

    def save(self, sessions: list[Session]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": 1,
            "sessions": {session.id: asdict(session) for session in sessions},
        }
        file_descriptor, temporary_name = tempfile.mkstemp(
            dir=self.path.parent, prefix=f".{self.path.name}.", text=True
        )
        try:
            with os.fdopen(file_descriptor, "w", encoding="utf-8") as file:
                json.dump(data, file, indent=2, sort_keys=True)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary_name, self.path)
        except BaseException:
            Path(temporary_name).unlink(missing_ok=True)
            raise


class NtfyNotifier:
    def __init__(
        self,
        server: str,
        topic: str | None,
        token: str | None = None,
        urlopen: Callable[..., Any] = urllib.request.urlopen,
    ) -> None:
        self.server = server.rstrip("/")
        self.topic = topic
        self.token = token
        self.urlopen = urlopen

    def send(self, alert: Alert) -> None:
        if not self.topic:
            raise RuntimeError(
                "MUTC_NTFY_TOPIC is not configured; refusing to discard an alert"
            )

        headers = {
            "Title": "MUTC session now full"
            if alert.is_full
            else "MUTC session available",
            "Priority": "default" if alert.is_full else "high",
            "Tags": "no_entry,tennis_ball" if alert.is_full else "tennis_ball,calendar",
            "User-Agent": "mutc-tracker/0.1",
        }
        if not alert.is_full:
            headers["Click"] = alert.session.booking_url
            headers["Actions"] = (
                f"view, Book session, {alert.session.booking_url}, clear=true"
            )
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        request = urllib.request.Request(
            f"{self.server}/{self.topic}",
            data=alert.message.encode(),
            headers=headers,
            method="POST",
        )
        with self.urlopen(request, timeout=30) as response:
            if not 200 <= response.status < 300:
                raise RuntimeError(f"ntfy returned HTTP {response.status}")


def detect_alerts(previous: dict[str, Session], current: list[Session]) -> list[Alert]:
    alerts: list[Alert] = []
    for session in current:
        old_session = previous.get(session.id)
        if session.is_actionable and old_session is None:
            alerts.append(Alert(session, "New session released"))
        elif session.is_actionable and not old_session.is_actionable:
            reason = (
                "Place reopened"
                if old_session.is_available and old_session.is_booked_out
                else "Session released"
            )
            alerts.append(Alert(session, reason))
        elif (
            old_session is not None
            and old_session.is_actionable
            and session.is_available
            and session.is_booked_out
        ):
            alerts.append(Alert(session, "Session now full"))
    return alerts


def run_check(
    client: MutcClient,
    store: StateStore,
    notifier: NtfyNotifier,
) -> list[Alert]:
    sessions = client.fetch_sessions()
    actionable = sum(session.is_actionable for session in sessions)
    LOGGER.info("Fetched %d sessions; %d currently bookable", len(sessions), actionable)

    if not store.exists():
        store.save(sessions)
        LOGGER.info("Created initial baseline without sending notifications")
        return []

    previous = store.load()
    alerts = detect_alerts(previous, sessions)
    for alert in alerts:
        notifier.send(alert)
        LOGGER.info(
            "Sent alert for %s on %s at %s",
            alert.session.event_title,
            alert.session.day,
            alert.session.start_time,
        )

    # Save only after all notifications succeed, so a failed alert is retried.
    store.save(sessions)
    if not alerts:
        LOGGER.info("No session status changes requiring notification")
    return alerts


def format_session(session: Session) -> str:
    status = "BOOKABLE" if session.is_actionable else "not bookable"
    return (
        f"{status}: {session.event_title} | {session.day} | "
        f"{session.start_time} - {session.end_time} | {session.no_of_bookings} bookings"
    )
