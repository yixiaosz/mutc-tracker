from __future__ import annotations

import argparse
import logging
import time
from collections.abc import Sequence
from dataclasses import replace
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import Settings
from .tracker import MutcClient, NtfyNotifier, StateStore, format_session, run_check

LOGGER = logging.getLogger(__name__)


def build_parser(settings: Settings) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Notify when MUTC event sessions become bookable."
    )
    parser.add_argument(
        "--interval-seconds",
        type=float,
        default=settings.poll_interval_seconds,
        help="seconds between checks (default: 3600, or MUTC_POLL_INTERVAL_SECONDS)",
    )
    parser.add_argument(
        "--once", action="store_true", help="perform one stateful check and exit"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_sessions",
        help="list live sessions without changing state or notifying",
    )
    parser.add_argument("--state-file", type=Path, default=settings.state_file)
    parser.add_argument("--log-file", type=Path, default=settings.log_file)
    parser.add_argument("--ntfy-server", default=settings.ntfy_server)
    parser.add_argument("--ntfy-topic", default=settings.ntfy_topic)
    parser.add_argument("--ntfy-token", default=settings.ntfy_token)
    return parser


def configure_logging(log_file: Path) -> None:
    log_file = log_file.expanduser()
    log_file.parent.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    rotating_file = RotatingFileHandler(
        log_file, maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    rotating_file.setFormatter(formatter)
    logging.basicConfig(level=logging.INFO, handlers=[console, rotating_file])


def main(argv: Sequence[str] | None = None) -> None:
    environment_settings = Settings.from_env()
    parser = build_parser(environment_settings)
    args = parser.parse_args(argv)
    if args.interval_seconds <= 0:
        parser.error("--interval-seconds must be greater than zero")

    settings = replace(
        environment_settings,
        poll_interval_seconds=args.interval_seconds,
        state_file=args.state_file.expanduser(),
        log_file=args.log_file.expanduser(),
        ntfy_server=args.ntfy_server,
        ntfy_topic=args.ntfy_topic,
        ntfy_token=args.ntfy_token,
    )
    configure_logging(settings.log_file)

    client = MutcClient()
    if args.list_sessions:
        try:
            for session in client.fetch_sessions():
                if session.is_available:
                    print(format_session(session))
        except Exception:
            LOGGER.exception("Unable to fetch MUTC sessions")
            raise SystemExit(1) from None
        return

    store = StateStore(settings.state_file)
    notifier = NtfyNotifier(
        settings.ntfy_server, settings.ntfy_topic, settings.ntfy_token
    )

    LOGGER.info(
        "Starting MUTC tracker with a %.0f-second polling interval",
        settings.poll_interval_seconds,
    )
    while True:
        try:
            run_check(client, store, notifier)
        except Exception:
            LOGGER.exception("MUTC check failed")
            if args.once:
                raise SystemExit(1) from None

        if args.once:
            return
        try:
            time.sleep(settings.poll_interval_seconds)
        except KeyboardInterrupt:
            LOGGER.info("MUTC tracker stopped")
            return
