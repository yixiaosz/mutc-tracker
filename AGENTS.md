# AGENTS.md

## Project Overview

`mutc-tracker` monitors the Melbourne University Tennis Club's public GraphQL
API and sends ntfy notifications when event session availability changes.

The tracker:

- Primarily monitors Member Social Hitting.
- Includes session-based pop-up events under other names.
- Explicitly excludes Beginner Tennis Bootcamp by stable event ID.
- Does not require or store MUTC account credentials.
- Runs continuously as a systemd user service with a one-hour default interval.

## Development Commands

Run commands from the repository root:

```bash
uv sync
uv run pytest
uvx ruff check .
uvx ruff format --check .
uv run mutc-tracker --list
```

Use `uv run mutc-tracker --once` only when intentionally performing a stateful
check. The first stateful run creates a silent baseline.

## Architecture

- `src/mutc_tracker/config.py`: defaults, environment configuration, stable
  event exclusions, and API URLs.
- `src/mutc_tracker/tracker.py`: GraphQL client, session model, transition
  detection, state persistence, and ntfy delivery.
- `src/mutc_tracker/cli.py`: command-line parsing, logging, and polling loop.
- `tests/test_tracker.py`: transition, notification, pagination, exclusion, and
  state-retry tests.
- `deploy/mutc-tracker.service`: systemd user service template.

The implementation intentionally uses only the Python standard library at
runtime. Keep new runtime dependencies out unless they solve a concrete need.

## Behavioral Invariants

Preserve these notification transitions:

- Unavailable to available and not full: notify `Session released`.
- New session first observed as available and not full: notify
  `New session released`.
- Available and full to available and not full: notify `Place reopened`.
- Available and not full to available and full: notify `Session now full`.
- Unchanged states remain silent.
- A session first observed as full must not produce a misleading
  `Session now full` notification.

Availability and fullness are separate fields. A session is actionable only
when `isAvailable` is true and `isBookedOut` is false.

Full notifications are informational and must not include a booking action.
Release and reopening notifications should include the direct booking URL.

The first run must save a baseline without notifying. Save updated state only
after every notification succeeds so failed delivery is retried on the next
check.

## Configuration

The polling default is deliberately visible in
`DEFAULT_POLL_INTERVAL_SECONDS` and is currently 3600 seconds. It can be
overridden with `MUTC_POLL_INTERVAL_SECONDS` or `--interval-seconds`.

Supported environment variables are documented in `README.md` and
`.env.example`. Never commit a real ntfy topic, access token, MUTC credential,
or generated state file.

## Editing Guidelines

- Prefer the smallest correct change.
- Keep network operations bounded with timeouts.
- Continue paginating the GraphQL collection; do not assume the first page
  contains every relevant session.
- Use stable event IDs for exclusions rather than mutable titles.
- Keep state writes atomic.
- Do not add browser automation for monitoring while the public API remains
  sufficient.
- Avoid automatic booking changes unless explicitly requested and separately
  designed.

## Verification

Before considering a change complete, run:

```bash
uv run pytest
uvx ruff check .
uvx ruff format --check .
git diff --check
```

For API-related changes, also run `uv run mutc-tracker --list`. This command is
read-only: it does not change tracker state or send notifications.

Do not run a live ntfy delivery test against the configured production topic
unless explicitly needed, because it sends a real phone notification.
