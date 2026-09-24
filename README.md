# MUTC Tracker

`mutc-tracker` checks the Melbourne University Tennis Club's public GraphQL API
and sends an [ntfy](https://ntfy.sh/) notification when an event session becomes
bookable.

It primarily covers **Member Social Hitting**, also catches session-based pop-up
events with other names, and explicitly excludes **Beginner Tennis Bootcamp**.
No MUTC username or password is needed for monitoring.

## Detection behavior

- The first run records a baseline and intentionally sends no notifications.
- A notification is sent when a session changes from unavailable to available.
- A notification is also sent if a booked-out session gets a free place.
- A notification is sent when a previously bookable session becomes full, so
  there is no need to open the login page to check it.
- A session first observed as full does not trigger a misleading "now full"
  notification; the tracker must previously have observed it as bookable.
- Unchanged checks are logged and remain silent.
- State is saved only after notifications succeed, so failed alerts are retried.

## Setup

Install the project and development tools:

```bash
cd ~/mutc-tracker
uv sync
```

Install the ntfy app, choose a long random topic name, and subscribe to that
topic. Public ntfy topic names are effectively passwords, so do not use a
guessable name.

Set the topic for the current shell:

```bash
export MUTC_NTFY_TOPIC="mutc-tennis-your-long-random-value"
```

Verify what the API currently reports without changing tracker state:

```bash
uv run mutc-tracker --list
```

Create the initial silent baseline:

```bash
uv run mutc-tracker --once
```

Run continuously with the default one-hour interval:

```bash
uv run mutc-tracker
```

## Polling interval

The clearly defined default is `DEFAULT_POLL_INTERVAL_SECONDS = 60 * 60` in
`src/mutc_tracker/config.py`.

Override it temporarily on the command line:

```bash
uv run mutc-tracker --interval-seconds 300
```

Or set it persistently through the environment:

```bash
export MUTC_POLL_INTERVAL_SECONDS=300
```

Command-line values take precedence over environment values. One hour is 3600
seconds.

## Run at login with systemd

Create a private environment file:

```bash
mkdir -p ~/.config/mutc-tracker ~/.config/systemd/user
cp .env.example ~/.config/mutc-tracker/env
chmod 600 ~/.config/mutc-tracker/env
```

Edit `~/.config/mutc-tracker/env` and replace the sample ntfy topic. Then install
and start the included user service:

```bash
cp deploy/mutc-tracker.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now mutc-tracker.service
```

Inspect service status and recent logs:

```bash
systemctl --user status mutc-tracker.service
journalctl --user -u mutc-tracker.service -f
```

The tracker also writes rotating logs to
`~/.local/state/mutc-tracker/tracker.log` and state to
`~/.local/state/mutc-tracker/state.json`.

## Other configuration

| Environment variable | Default | Purpose |
| --- | --- | --- |
| `MUTC_POLL_INTERVAL_SECONDS` | `3600` | Seconds between checks |
| `MUTC_NTFY_TOPIC` | unset | Required to deliver alerts |
| `MUTC_NTFY_SERVER` | `https://ntfy.sh` | ntfy server URL |
| `MUTC_NTFY_TOKEN` | unset | Optional ntfy access token |
| `MUTC_STATE_FILE` | XDG state directory | Override state location |
| `MUTC_LOG_FILE` | XDG state directory | Override log location |

Run `uv run mutc-tracker --help` for equivalent command-line options.

## Tests

```bash
uv run pytest
```
