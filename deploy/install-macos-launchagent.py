"""Generate a per-user launchd service without starting stateful monitoring."""

from __future__ import annotations

import argparse
import os
import plistlib
import sys
from pathlib import Path

LABEL = "au.com.mutc.tracker"


def build_plist(project_dir: Path, home: Path) -> dict[str, object]:
    return {
        "Label": LABEL,
        "ProgramArguments": [
            "/bin/sh",
            str(project_dir / "deploy" / "run-macos.sh"),
            str(project_dir),
            str(home / ".config" / "mutc-tracker" / "env"),
        ],
        "WorkingDirectory": str(project_dir),
        "RunAtLoad": True,
        "KeepAlive": {"SuccessfulExit": False},
        "ThrottleInterval": 60,
        "StandardOutPath": "/dev/null",
        "StandardErrorPath": str(
            home / "Library" / "Logs" / "mutc-tracker" / "launchd.log"
        ),
    }


def install(project_dir: Path, home: Path) -> Path:
    project_dir = project_dir.resolve()
    for required in (
        project_dir / ".venv" / "bin" / "mutc-tracker",
        project_dir / "deploy" / "run-macos.sh",
        home / ".config" / "mutc-tracker" / "env",
    ):
        if not required.is_file():
            raise FileNotFoundError(f"Required file is missing: {required}")

    destination = home / "Library" / "LaunchAgents" / f"{LABEL}.plist"
    destination.parent.mkdir(parents=True, exist_ok=True)
    (home / "Library" / "Logs" / "mutc-tracker").mkdir(parents=True, exist_ok=True)
    # Exclusive creation avoids overwriting an installed or currently loaded agent.
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as file:
        plistlib.dump(build_plist(project_dir, home), file)
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-dir", type=Path, default=Path(__file__).resolve().parent.parent
    )
    args = parser.parse_args()
    if sys.platform != "darwin":
        parser.error("LaunchAgents are supported only on macOS")
    try:
        destination = install(args.project_dir.expanduser(), Path.home())
    except OSError as error:
        parser.exit(1, f"Unable to install LaunchAgent: {error}\n")
    print(f"Installed {destination}")
    print("Start it with the launchctl bootstrap command in README.md.")


if __name__ == "__main__":
    main()
