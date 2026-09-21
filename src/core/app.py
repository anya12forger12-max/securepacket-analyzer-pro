"""Application entry point.

Provides :func:`main`, the process entry point referenced by the
``securepacket`` console script (``[project.scripts]`` in ``pyproject.toml``)
and invoked by the documented ``python -m src`` module runner.
"""

from __future__ import annotations

import argparse
import logging
import sys
import tomllib
from pathlib import Path

from src import __version__
from src.config.settings import SettingsManager
from src.logframework.setup import AppLogger
from src.utils.paths import AppPaths
from src.workspace.manager import WorkspaceManager

_LOG_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
}


def _parse_toml(path: Path) -> bool:
    """Return *True* when *path* exists and parses as valid TOML."""
    try:
        with path.open("rb") as fh:
            tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return False
    return True


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="securepacket",
        description="SecurePacket Analyzer Pro - network packet analysis platform",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        metavar="PATH",
        help="Settings directory containing defaults.toml / user_settings.json",
    )
    parser.add_argument(
        "--log-level",
        choices=sorted(_LOG_LEVELS),
        default=None,
        metavar="LEVEL",
        help="Console logging verbosity (DEBUG, INFO, WARNING, ERROR)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Bootstrap the application.

    Initialises the config manager, logging system, storage directories and
    workspace manager, then prints a status summary.  Returns the process
    exit code (0 on success).
    """
    args = _build_parser().parse_args(argv)

    if args.config is not None:
        if args.config.is_file():
            if not _parse_toml(args.config):
                print(f"error: {args.config} is not a valid TOML file", file=sys.stderr)
                return 2
            config_dir = args.config.parent
        else:
            print(f"error: config path does not exist: {args.config}", file=sys.stderr)
            return 2
    else:
        config_dir = None

    AppPaths.ensure_directories()
    settings = SettingsManager(config_dir)

    if args.log_level is not None:
        settings.set("logging.level", args.log_level.upper())

    logger = AppLogger(settings)
    logger.setup()
    log = logger.get_logger("src.app")
    log.info("SecurePacket Analyzer Pro %s starting", __version__)

    workspaces = WorkspaceManager(settings)
    log.info("Configuration directory: %s", settings._config_dir)
    log.info("Workspaces directory: %s", workspaces.workspaces_dir)
    profiles = workspaces.list_workspaces()

    print(
        f"\nSecurePacket Analyzer Pro {__version__}\n"
        f"  config:     {settings._config_dir}\n"
        f"  workspaces: {', '.join(profiles) if profiles else '(none yet)'}\n"
        f"  log level:  {args.log_level or settings.get('logging.level', 'INFO')}"
    )
    log.info("Startup complete (workspaces: %d)", len(profiles))
    return 0
