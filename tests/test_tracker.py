from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Self

import pytest

from mutc_tracker.tracker import (
    Alert,
    MutcClient,
    NtfyNotifier,
    Session,
    StateStore,
    detect_alerts,
    run_check,
)


def make_session(
    session_id: str = "session-1",
    *,
    available: bool = False,
    booked_out: bool = False,
    event_id: str = "64c27f952d6e3df88e383e3d",
    title: str = "Member Social Hitting",
) -> Session:
    return Session(
        id=session_id,
        event_id=event_id,
        event_title=title,
        event_slug="member-social-hitting",
        day="Monday 28 September",
        start_time="2:00 pm",
        end_time="3:30 pm",
        start_day_and_time="2026-09-28T04:00:00.000Z",
        end_day_and_time="2026-09-28T05:30:00.000Z",
        is_available=available,
        is_booked_out=booked_out,
        no_of_bookings=36 if booked_out else 5,
    )


def api_session(
    session_id: str,
    event_id: str = "64c27f952d6e3df88e383e3d",
) -> dict[str, object]:
    return {
        "id": session_id,
        "day": "Monday 28 September",
        "startTime": "2:00 pm",
        "endTime": "3:30 pm",
        "startDayAndTime": "2026-09-28T04:00:00.000Z",
        "endDayAndTime": "2026-09-28T05:30:00.000Z",
        "isAvailable": True,
        "isBookedOut": False,
        "noOfBookings": 5,
        "event": {
            "id": event_id,
            "title": "Beginner Tennis Bootcamp"
            if event_id == "64b52d6fdcda7bc59fa6b749"
            else "Member Social Hitting",
            "slug": "event-slug",
        },
    }


class FakeResponse(io.BytesIO):
    status = 200

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def test_detects_newly_released_session() -> None:
    old = make_session(available=False)
    new = make_session(available=True)

    alerts = detect_alerts({old.id: old}, [new])

    assert len(alerts) == 1
    assert alerts[0].reason == "Session released"


def test_detects_reopened_place() -> None:
    old = make_session(available=True, booked_out=True)
    new = make_session(available=True, booked_out=False)

    alerts = detect_alerts({old.id: old}, [new])

    assert len(alerts) == 1
    assert alerts[0].reason == "Place reopened"


def test_detects_session_becoming_full() -> None:
    old = make_session(available=True, booked_out=False)
    new = make_session(available=True, booked_out=True)

    alerts = detect_alerts({old.id: old}, [new])

    assert len(alerts) == 1
    assert alerts[0].reason == "Session now full"
    assert alerts[0].is_full


def test_full_session_remains_silent() -> None:
    full = make_session(available=True, booked_out=True)

    assert detect_alerts({full.id: full}, [full]) == []


def test_unavailable_session_first_observed_as_full_remains_silent() -> None:
    old = make_session(available=False, booked_out=False)
    new = make_session(available=True, booked_out=True)

    assert detect_alerts({old.id: old}, [new]) == []


def test_full_notification_has_no_booking_action() -> None:
    requests: list[object] = []

    def fake_urlopen(request: object, timeout: int) -> FakeResponse:
        requests.append(request)
        return FakeResponse(b"{}")

    alert = Alert(make_session(available=True, booked_out=True), "Session now full")
    NtfyNotifier("https://ntfy.sh", "test-topic", urlopen=fake_urlopen).send(alert)

    headers = requests[0].headers  # type: ignore[attr-defined]
    assert headers["Title"] == "MUTC session now full"
    assert headers["Priority"] == "default"
    assert "Click" not in headers
    assert "Actions" not in headers


def test_reopened_notification_has_booking_action() -> None:
    requests: list[object] = []

    def fake_urlopen(request: object, timeout: int) -> FakeResponse:
        requests.append(request)
        return FakeResponse(b"{}")

    alert = Alert(make_session(available=True), "Place reopened")
    NtfyNotifier("https://ntfy.sh", "test-topic", urlopen=fake_urlopen).send(alert)

    headers = requests[0].headers  # type: ignore[attr-defined]
    assert headers["Title"] == "MUTC session available"
    assert headers["Priority"] == "high"
    assert headers["Click"] == alert.session.booking_url
    assert "Book session" in headers["Actions"]


def test_suppresses_unchanged_and_full_sessions() -> None:
    bookable = make_session(available=True)
    full = make_session("session-2", available=True, booked_out=True)

    alerts = detect_alerts({bookable.id: bookable}, [bookable, full])

    assert alerts == []


def test_new_popup_event_session_is_detected() -> None:
    popup = make_session(
        "popup-1", available=True, event_id="popup-event", title="Lawn Social"
    )

    alerts = detect_alerts({}, [popup])

    assert len(alerts) == 1
    assert alerts[0].session.event_title == "Lawn Social"


def test_client_paginates_and_excludes_bootcamp() -> None:
    responses = iter(
        [
            {
                "data": {
                    "EventSessions": {
                        "docs": [api_session("social-1")],
                        "hasNextPage": True,
                        "nextPage": 2,
                    }
                }
            },
            {
                "data": {
                    "EventSessions": {
                        "docs": [api_session("bootcamp-1", "64b52d6fdcda7bc59fa6b749")],
                        "hasNextPage": False,
                        "nextPage": None,
                    }
                }
            },
        ]
    )

    def fake_urlopen(request: object, timeout: int) -> FakeResponse:
        assert timeout == 30
        return FakeResponse(json.dumps(next(responses)).encode())

    sessions = MutcClient(urlopen=fake_urlopen).fetch_sessions()

    assert [session.id for session in sessions] == ["social-1"]


def test_first_run_creates_silent_baseline(tmp_path: Path) -> None:
    session = make_session(available=True)

    class Client:
        def fetch_sessions(self) -> list[Session]:
            return [session]

    class Notifier:
        def send(self, alert: object) -> None:
            pytest.fail("First run should not notify")

    store = StateStore(tmp_path / "state.json")
    alerts = run_check(Client(), store, Notifier())  # type: ignore[arg-type]

    assert alerts == []
    assert store.load()[session.id] == session


def test_failed_notification_preserves_previous_state(tmp_path: Path) -> None:
    old = make_session(available=False)
    new = make_session(available=True)
    store = StateStore(tmp_path / "state.json")
    store.save([old])

    class Client:
        def fetch_sessions(self) -> list[Session]:
            return [new]

    class Notifier:
        def send(self, alert: object) -> None:
            raise RuntimeError("ntfy unavailable")

    with pytest.raises(RuntimeError, match="ntfy unavailable"):
        run_check(Client(), store, Notifier())  # type: ignore[arg-type]

    assert store.load()[old.id] == old
