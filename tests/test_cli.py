"""Tests for cli.py — import, version string, exit codes, subcommand registration."""

import os
import subprocess
import sys
from importlib import import_module
from pathlib import Path

_UTF8_ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}


def test_cli_imports():
    cli = import_module("cli")
    assert hasattr(cli, "main")
    assert hasattr(cli, "_VERSION")


def test_version_string_is_semver():
    cli = import_module("cli")
    parts = cli._VERSION.split(".")
    assert len(parts) == 3, f"_VERSION must be X.Y.Z, got {cli._VERSION!r}"
    assert all(p.isdigit() for p in parts), f"Non-numeric version part in {cli._VERSION!r}"


def test_version_matches_app():
    """cli._VERSION must stay in sync with app.py's setApplicationVersion."""
    cli = import_module("cli")
    app_src = (Path(__file__).parent.parent / "app.py").read_text(encoding="utf-8")
    assert f'setApplicationVersion("{cli._VERSION}")' in app_src, (
        f"cli._VERSION={cli._VERSION!r} not found in app.py — run bump_version.py"
    )


def test_help_exits_zero():
    result = subprocess.run(
        [sys.executable, "cli.py", "--help"],
        capture_output=True,
        text=True,
        env=_UTF8_ENV,
    )
    assert result.returncode == 0
    assert "netsentinel" in result.stdout.lower()


def test_version_flag():
    result = subprocess.run(
        [sys.executable, "cli.py", "--version"],
        capture_output=True,
        text=True,
        env=_UTF8_ENV,
    )
    assert result.returncode == 0
    cli = import_module("cli")
    assert cli._VERSION in result.stdout


def test_all_subcommands_registered():
    result = subprocess.run(
        [sys.executable, "cli.py", "--help"],
        capture_output=True,
        text=True,
        env=_UTF8_ENV,
    )
    for cmd in ("scan", "diagnose", "log", "ports", "check-endpoints", "cloud-metadata", "log-chart"):
        assert cmd in result.stdout, f"Subcommand {cmd!r} missing from --help output"


def test_unknown_subcommand_exits_nonzero():
    result = subprocess.run(
        [sys.executable, "cli.py", "does-not-exist"],
        capture_output=True,
        text=True,
        env=_UTF8_ENV,
    )
    assert result.returncode != 0


def test_scan_help_exits_zero():
    result = subprocess.run(
        [sys.executable, "cli.py", "scan", "--help"],
        capture_output=True,
        text=True,
        env=_UTF8_ENV,
    )
    assert result.returncode == 0
    assert "--format" in result.stdout
    assert "--output" in result.stdout
