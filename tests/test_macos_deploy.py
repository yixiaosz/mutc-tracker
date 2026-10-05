from __future__ import annotations

import os
import plistlib
import runpy
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
INSTALLER = runpy.run_path(str(ROOT / "deploy" / "install-macos-launchagent.py"))


def prepare_installation(tmp_path: Path) -> tuple[Path, Path]:
    project = tmp_path / "checkout with spaces"
    home = tmp_path / "home with spaces"
    for path in (
        project / ".venv" / "bin" / "mutc-tracker",
        project / "deploy" / "run-macos.sh",
        home / ".config" / "mutc-tracker" / "env",
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    return project, home


def test_installer_generates_portable_paths_without_starting_tracker(
    tmp_path: Path,
) -> None:
    project, home = prepare_installation(tmp_path)
    destination = INSTALLER["install"](project, home)

    with destination.open("rb") as file:
        plist = plistlib.load(file)
    assert destination == home / "Library/LaunchAgents/au.com.mutc.tracker.plist"
    assert plist["ProgramArguments"] == [
        "/bin/sh",
        str(project / "deploy/run-macos.sh"),
        str(project),
        str(home / ".config/mutc-tracker/env"),
    ]
    assert plist["WorkingDirectory"] == str(project)
    assert plist["RunAtLoad"] is True
    assert plist["KeepAlive"] == {"SuccessfulExit": False}
    assert plist["ThrottleInterval"] == 60
    assert Path(plist["StandardErrorPath"]).parent.is_dir()
    assert destination.stat().st_mode & 0o777 == 0o600
    assert not (home / ".local/state/mutc-tracker/state.json").exists()


def test_installer_preserves_existing_agent(tmp_path: Path) -> None:
    project, home = prepare_installation(tmp_path)
    destination = INSTALLER["install"](project, home)
    destination.write_bytes(b"existing user configuration")

    with pytest.raises(FileExistsError):
        INSTALLER["install"](project, home)
    assert destination.read_bytes() == b"existing user configuration"


@pytest.mark.parametrize("missing", ["executable", "launcher", "configuration"])
def test_installer_requires_setup_files(tmp_path: Path, missing: str) -> None:
    project, home = prepare_installation(tmp_path)
    paths = {
        "executable": project / ".venv/bin/mutc-tracker",
        "launcher": project / "deploy/run-macos.sh",
        "configuration": home / ".config/mutc-tracker/env",
    }
    paths[missing].unlink()

    with pytest.raises(FileNotFoundError, match="Required file is missing"):
        INSTALLER["install"](project, home)
    assert not (home / "Library/LaunchAgents/au.com.mutc.tracker.plist").exists()


def test_launcher_loads_config_and_forwards_arguments(tmp_path: Path) -> None:
    project, home = prepare_installation(tmp_path)
    executable = project / ".venv/bin/mutc-tracker"
    executable.write_text('#!/bin/sh\nprintf "%s\\n" "$MUTC_NTFY_TOPIC" "$PWD" "$@"\n')
    executable.chmod(0o700)
    config = home / ".config/mutc-tracker/env"
    config.write_text('MUTC_NTFY_TOPIC="test topic with spaces"\n')

    result = subprocess.run(
        [
            "/bin/sh",
            str(ROOT / "deploy/run-macos.sh"),
            str(project),
            str(config),
            "--list",
            "argument with spaces",
        ],
        env={**os.environ, "MUTC_NTFY_TOPIC": "inherited-value"},
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.splitlines() == [
        "test topic with spaces",
        str(project),
        "--list",
        "argument with spaces",
    ]


def test_launcher_fails_when_configuration_is_missing(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            "/bin/sh",
            str(ROOT / "deploy/run-macos.sh"),
            str(tmp_path),
            str(tmp_path / "missing-env"),
            "--list",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "Missing configuration file:" in result.stderr
