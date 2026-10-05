# MUTC Tracker

`mutc-tracker` checks the Melbourne University Tennis Club's public GraphQL API
and sends [ntfy](https://ntfy.sh/) notifications when sessions become bookable,
places reopen, or previously bookable sessions become full.

It primarily covers **Member Social Hitting**, also catches session-based pop-up
events with other names, and explicitly excludes **Beginner Tennis Bootcamp**.
No MUTC username or password is needed for monitoring.

## Platform support

Linux and macOS share one implementation in `main`, with the same CLI, ntfy
notifications, configuration, and state format. Run it directly in a terminal or
use your platform's background service:

| Platform | Background service | Deployment files |
| --- | --- | --- |
| Linux | systemd user service | `deploy/mutc-tracker.service` |
| macOS | launchd LaunchAgent | `deploy/install-macos-launchagent.py`, `deploy/run-macos.sh` |

The default polling interval is one hour. Monitoring requires an awake host and
network access; changes that occur entirely between checks may be missed. The
macOS agent runs while the user is logged in and resumes after sleep.

Python 3.13 or newer is required. The application uses only the Python standard
library at runtime; `uv sync` installs the project and development tools and can
provision a compatible Python version.

## Detection behavior

- The first run records a baseline and intentionally sends no notifications.
- `Session released`: a session changes from unavailable to available and not full.
- `New session released`: a new session is first observed as available and not full
  after the initial baseline.
- `Place reopened`: an available, booked-out session gets a free place.
- `Session now full`: a previously bookable session remains available but becomes
  full, so there is no need to open the login page to check it.
- A session first observed as full does not trigger a misleading "now full"
  notification; the tracker must previously have observed it as bookable.
- Unchanged checks are logged and remain silent.
- State is saved only after notifications succeed, so failed alerts are retried.

Availability and fullness are separate: a session is bookable only when
`isAvailable` is true and `isBookedOut` is false. Release and reopening alerts
include a direct booking link; full alerts are informational and have no booking
action. The tracker monitors availability; it does not book sessions automatically.

## Setup

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then install
the project and development tools from your checkout:

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

These shell settings apply to manual runs. For automatic startup, use the private
environment file described in the Linux or macOS deployment section below.

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

## Run at login on Linux with systemd

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

## Run at login on macOS with launchd

The same Python tracker runs on macOS using a per-user LaunchAgent. It sends the
same ntfy alerts and uses the same configuration and state format as Linux.
Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then run
`uv sync` from your checkout. uv will provision the required Python version.
The checkout can be anywhere, including a path containing spaces; keep it at that
location after installing the agent.

Create a private configuration file:

```bash
mkdir -p ~/.config/mutc-tracker
cp .env.example ~/.config/mutc-tracker/env
chmod 600 ~/.config/mutc-tracker/env
```

Edit `~/.config/mutc-tracker/env` and replace the sample ntfy topic. The macOS
launcher sources this file as shell configuration: use `NAME="value"` assignments
and only include trusted contents. A LaunchAgent does not inherit settings from
your interactive shell. Use absolute paths for state or log overrides.

Verify the launcher and live API without changing state or sending notifications:

```bash
/bin/sh deploy/run-macos.sh "$PWD" "$HOME/.config/mutc-tracker/env" --list
```

Install the LaunchAgent (this only generates its plist), validate it, and start it:

```bash
uv run python deploy/install-macos-launchagent.py
plutil -lint "$HOME/Library/LaunchAgents/au.com.mutc.tracker.plist"
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/au.com.mutc.tracker.plist"
```

Starting the service begins stateful monitoring immediately. With no existing
state, it creates the normal silent baseline. With existing state, it may send
notifications for detected changes. Avoid running another continuous tracker
against the same state file while the service is running.

The agent starts at subsequent logins and restarts after an unexpected failure,
with a 60-second throttle. Monitoring pauses while the Mac sleeps and continues
after wake; the next check follows the existing polling loop. It does not run
while the Mac is shut down or the user is logged out. Changes that occur entirely
between checks may be missed.

Inspect status and the rotating application log:

```bash
launchctl print "gui/$(id -u)/au.com.mutc.tracker"
tail -f "$HOME/.local/state/mutc-tracker/tracker.log"
```

The usual default state path is `~/.local/state/mutc-tracker/state.json`.
`XDG_STATE_HOME`, when supplied in the configuration file, changes the default
state and application-log directory. Startup errors and console output are also
captured in `~/Library/Logs/mutc-tracker/launchd.log`; that diagnostic file is not
rotated and can be cleared periodically.

Stop the service before editing configuration or running a manual stateful check:

```bash
launchctl bootout "gui/$(id -u)" "$HOME/Library/LaunchAgents/au.com.mutc.tracker.plist"
```

To start it again, use the `launchctl bootstrap` command above. A booted-out agent
will also load at the next login while its plist remains installed.

To uninstall, stop it first and then remove the plist:

```bash
rm "$HOME/Library/LaunchAgents/au.com.mutc.tracker.plist"
```

Configuration, logs, and state are preserved. To move the checkout or reinstall,
stop and remove the old plist, then rerun the installer from the new checkout.
The installer refuses to overwrite an existing plist.

## Other configuration

| Environment variable | Default | Purpose |
| --- | --- | --- |
| `MUTC_POLL_INTERVAL_SECONDS` | `3600` | Seconds between checks |
| `MUTC_NTFY_TOPIC` | unset | Required to deliver alerts |
| `MUTC_NTFY_SERVER` | `https://ntfy.sh` | ntfy server URL |
| `MUTC_NTFY_TOKEN` | unset | Optional ntfy access token |
| `MUTC_STATE_FILE` | XDG state directory | Override state location |
| `MUTC_LOG_FILE` | XDG state directory | Override log location |
| `XDG_STATE_HOME` | `~/.local/state` | Base directory for default state and log paths |

Run `uv run mutc-tracker --help` for equivalent command-line options.

## Development checks

Run from the repository root:

```bash
uv run pytest
uvx ruff check .
uvx ruff format --check .
git diff --check
```

Tests cover notification transitions, silent baselines, pagination, Bootcamp
exclusion, failed-delivery state preservation, and macOS deployment behavior,
including configuration loading and paths containing spaces.

For macOS deployment changes, also run `/bin/sh -n deploy/run-macos.sh`, validate
the generated plist with `plutil -lint`, and use the launcher's read-only `--list`
check above. Starting the normal background service is a stateful operation.
