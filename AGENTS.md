# AGENTS.md

## Project Overview

`mutc-tracker` monitors the Melbourne University Tennis Club's public GraphQL
API and sends ntfy notifications when event session availability changes.

The tracker:

- Primarily monitors Member Social Hitting.
- Includes session-based pop-up events under other names.
- Explicitly excludes Beginner Tennis Bootcamp by stable event ID.
- Does not require or store MUTC account credentials.
- Runs the same Python tracker on Linux and macOS with a one-hour default interval.
- Supports a systemd user service on Linux and a launchd LaunchAgent on macOS.
- Pauses monitoring while the host is asleep or shut down; macOS deployment runs
  in the logged-in user's session.

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
- `deploy/run-macos.sh`: launcher that sources the private environment file and
  executes the checkout's virtual-environment tracker.
- `deploy/install-macos-launchagent.py`: standard-library installer that generates
  a per-user LaunchAgent plist using absolute checkout paths.
- `tests/test_macos_deploy.py`: plist generation, existing-agent preservation,
  required setup files, configuration loading, and paths-with-spaces tests.
- `.env.example`: shared configuration template for both deployment methods.

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

Both services load `~/.config/mutc-tracker/env`. On macOS this is a trusted shell
configuration file sourced with automatic export; use quoted `NAME="value"`
assignments compatible with both shell and systemd environment-file syntax.
LaunchAgents do not inherit the interactive shell's environment. Use absolute
paths for service overrides.

Default state and rotating application logs remain under
`~/.local/state/mutc-tracker/` on both platforms. `XDG_STATE_HOME` changes this
base directory; `MUTC_STATE_FILE` and `MUTC_LOG_FILE` override individual files.

## macOS Deployment

- Run the installer from the repository root after `uv sync` and configuration:
  `uv run python deploy/install-macos-launchagent.py`.
- The installer only writes `~/Library/LaunchAgents/au.com.mutc.tracker.plist`;
  it does not start monitoring and refuses to overwrite an existing plist.
- `launchctl bootstrap` starts stateful monitoring immediately. The agent then
  starts at login and restarts after unsuccessful process exits with a 60-second
  throttle. Polling and check-error retries remain handled by the shared CLI.
- Preserve support for checkout paths containing spaces. Stop and remove the old
  plist before moving the checkout or reinstalling.
- Uninstalling removes only the plist; preserve configuration, logs, and state.
- Console output and startup errors go to
  `~/Library/Logs/mutc-tracker/launchd.log`, which is not rotated. The application's
  separate `tracker.log` remains rotating.
- Do not run multiple stateful trackers against the same state file. Use
  `launchctl bootout` before a manual stateful check or configuration changes.

## Editing Guidelines

- Prefer the smallest correct change.
- Keep monitoring logic shared between platforms; put platform-specific service
  integration in `deploy/`.
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

For macOS deployment changes, also check the launcher syntax:

```bash
/bin/sh -n deploy/run-macos.sh
```

On macOS, validate the generated plist with `plutil -lint` and verify the launcher
with `--list` as documented in `README.md`. For an end-to-end launchd check, use a
temporary uniquely labeled agent with `--list`, temporary configuration and log
paths, and unload it afterward. Do not bootstrap the production agent merely to
test installation: its normal invocation is stateful and may send alerts.

Do not run a live ntfy delivery test against the configured production topic
unless explicitly needed, because it sends a real phone notification.
