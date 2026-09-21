"""Centralized logging configuration for SecurePacketAnalyzerPro.

Provides coloured console output, rotating file handlers, and
dedicated log streams for security events and performance data.
"""

from __future__ import annotations

import atexit
import contextlib
import logging
import logging.handlers
import sys
import traceback
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from src.config.settings import SettingsManager
from src.utils.paths import AppPaths

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from pathlib import Path

# ------------------------------------------------------------------
# Colour helpers (ANSI escapes – silently ignored by non-TTY sinks)
# ------------------------------------------------------------------

_COLOR_CODES: dict[str, str] = {
    logging.DEBUG: "\033[36m",  # cyan
    logging.INFO: "\033[32m",  # green
    logging.WARNING: "\033[33m",  # yellow
    logging.ERROR: "\033[31m",  # red
    logging.CRITICAL: "\033[1;31m",  # bold red
}
_RESET = "\033[0m"


class _ColouredFormatter(logging.Formatter):
    """Colourises log output for terminal display."""

    def format(self, record: logging.LogRecord) -> str:
        colour = _COLOR_CODES.get(record.levelno, "")
        record.colour_start = colour
        record.colour_end = _RESET if colour else ""
        return super().format(record)


# ------------------------------------------------------------------
# Specialised handlers
# ------------------------------------------------------------------


class _SecurityFileHandler(logging.Handler):
    """Appends security-related events to a dedicated log file."""

    def __init__(self, path: Path, max_bytes: int, backup_count: int) -> None:
        super().__init__(level=logging.INFO)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._handler = logging.handlers.RotatingFileHandler(
            str(path),
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        self._handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s | SECURITY | %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S%z",
            )
        )

    def emit(self, record: logging.LogRecord) -> None:
        self._handler.emit(record)

    def flush(self) -> None:
        self._handler.flush()

    def close(self) -> None:
        self._handler.close()


class _PerformanceFileHandler(logging.Handler):
    """Appends performance metrics to a dedicated log file."""

    def __init__(self, path: Path, max_bytes: int, backup_count: int) -> None:
        super().__init__(level=logging.INFO)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._handler = logging.handlers.RotatingFileHandler(
            str(path),
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        self._handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s | PERF | %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S%z",
            )
        )

    def emit(self, record: logging.LogRecord) -> None:
        self._handler.emit(record)

    def flush(self) -> None:
        self._handler.flush()

    def close(self) -> None:
        self._handler.close()


class _ShutdownFlusher:
    """Ensures all handlers are flushed when the process exits."""

    def __init__(self) -> None:
        self._handlers: list[logging.Handler] = []

    def register(self, handler: logging.Handler) -> None:
        self._handlers.append(handler)

    def flush_all(self) -> None:
        for handler in self._handlers:
            with contextlib.suppress(Exception):
                handler.flush()


_shutdown_flusher = _ShutdownFlusher()
atexit.register(_shutdown_flusher.flush_all)


# ------------------------------------------------------------------
# AppLogger
# ------------------------------------------------------------------


class AppLogger:
    """Application-wide logging façade.

    Parameters
    ----------
    settings:
        An optional :class:`SettingsManager` instance.  When *None* a
        fresh default instance is created.
    """

    def __init__(self, settings: SettingsManager | None = None) -> None:
        self._settings = settings or SettingsManager()
        self._handlers: list[logging.Handler] = []
        self._security_handler: _SecurityFileHandler | None = None
        self._performance_handler: _PerformanceFileHandler | None = None
        self._configured = False

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def setup(self) -> None:
        """Configure the root logger with all required handlers.

        Safe to call multiple times – duplicate handlers are prevented.
        """
        if self._configured:
            return

        root = logging.getLogger()
        root.setLevel(logging.DEBUG)

        log_settings = self._settings.as_dict("logging")
        log_level_str: str = log_settings.get("level", "INFO")
        log_level = getattr(logging, log_level_str.upper(), logging.INFO)

        max_bytes = log_settings.get("max_size_mb", 50) * 1024 * 1024
        backup_count = int(log_settings.get("backup_count", 5))

        # -- Console handler --
        if log_settings.get("log_to_console", True):
            console = logging.StreamHandler(sys.stdout)
            console.setLevel(log_level)
            console.setFormatter(
                _ColouredFormatter(
                    fmt="%(colour_start)s%(asctime)s [%(levelname)-8s] "
                    "%(name)s: %(message)s%(colour_end)s",
                    datefmt="%H:%M:%S",
                )
            )
            root.addHandler(console)
            self._handlers.append(console)

        # -- File handler --
        if log_settings.get("log_to_file", True):
            AppPaths.logs_dir().mkdir(parents=True, exist_ok=True)
            app_log_path = AppPaths.logs_dir() / "application.log"
            file_handler = logging.handlers.RotatingFileHandler(
                str(app_log_path),
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
            )
            file_handler.setLevel(log_level)
            file_handler.setFormatter(
                logging.Formatter(
                    fmt="%(asctime)s [%(levelname)-8s] %(name)s.%(funcName)s: %(message)s",
                    datefmt="%Y-%m-%dT%H:%M:%S%z",
                )
            )
            root.addHandler(file_handler)
            self._handlers.append(file_handler)
            _shutdown_flusher.register(file_handler)

        # -- Security handler --
        if log_settings.get("security_logging", True):
            AppPaths.logs_dir().mkdir(parents=True, exist_ok=True)
            sec_path = AppPaths.logs_dir() / "security.log"
            self._security_handler = _SecurityFileHandler(sec_path, max_bytes, backup_count)
            self._security_handler.setLevel(logging.INFO)
            root.addHandler(self._security_handler)
            _shutdown_flusher.register(self._security_handler)

        # -- Performance handler --
        if log_settings.get("performance_logging", False):
            AppPaths.logs_dir().mkdir(parents=True, exist_ok=True)
            perf_path = AppPaths.logs_dir() / "performance.log"
            self._performance_handler = _PerformanceFileHandler(perf_path, max_bytes, backup_count)
            self._performance_handler.setLevel(logging.INFO)
            root.addHandler(self._performance_handler)
            _shutdown_flusher.register(self._performance_handler)

        self._configured = True
        logger.info("Logging system initialised (level=%s)", log_level_str)

    # ------------------------------------------------------------------
    # Logger access
    # ------------------------------------------------------------------

    def get_logger(self, name: str) -> logging.Logger:
        """Return a child logger with the given *name*.

        Parameters
        ----------
        name:
            Typically the ``__name__`` of the calling module.
        """
        return logging.getLogger(name)

    # ------------------------------------------------------------------
    # Specialised logging helpers
    # ------------------------------------------------------------------

    def log_security(self, event: str, details: dict[str, str] | None = None) -> None:
        """Record a security-related event.

        Parameters
        ----------
        event:
            Short event label, e.g. ``"PERMISSION_DENIED"``.
        details:
            Optional key/value metadata.
        """
        parts = [event]
        if details:
            parts.append(" | ".join(f"{k}={v}" for k, v in details.items()))
        message = " ".join(parts)

        sec_logger = logging.getLogger("security")
        sec_logger.warning(message)

    def log_performance(
        self,
        operation: str,
        duration_ms: float,
        details: str | None = None,
    ) -> None:
        """Record a performance measurement.

        Parameters
        ----------
        operation:
            Name of the measured operation.
        duration_ms:
            Elapsed time in milliseconds.
        details:
            Optional supplementary text.
        """
        parts = [f"{operation}={duration_ms:.2f}ms"]
        if details:
            parts.append(details)
        message = " ".join(parts)

        perf_logger = logging.getLogger("performance")
        perf_logger.info(message)

    def log_crash(
        self,
        exc_type: type,
        exc_value: BaseException,
        traceback_obj: Any,
    ) -> None:
        """Log an uncaught exception as a crash event.

        Parameters
        ----------
        exc_type:
            Exception class.
        exc_value:
            Exception instance.
        traceback_obj:
            Traceback object from ``sys.exc_info()``.
        """
        tb_text = "".join(traceback.format_exception(exc_type, exc_value, traceback_obj))
        crash_logger = logging.getLogger("crash")
        crash_logger.critical(
            "Unhandled exception %s: %s\n%s",
            exc_type.__name__,
            exc_value,
            tb_text,
        )

        # Also try to write to a dedicated crash file for reliability
        try:
            AppPaths.logs_dir().mkdir(parents=True, exist_ok=True)
            crash_path = AppPaths.logs_dir() / "crash.log"
            timestamp = datetime.now(UTC).isoformat()
            with crash_path.open("a", encoding="utf-8") as fh:
                fh.write(f"\n{'=' * 60}\n")
                fh.write(f"CRASH @ {timestamp}\n")
                fh.write(f"{'=' * 60}\n")
                fh.write(f"{exc_type.__name__}: {exc_value}\n")
                fh.write(tb_text)
                fh.write("\n")
        except OSError:
            pass

        # Attempt to flush everything
        _shutdown_flusher.flush_all()

    # ------------------------------------------------------------------
    # Housekeeping
    # ------------------------------------------------------------------

    def flush(self) -> None:
        """Flush all active handlers immediately."""
        for handler in self._handlers:
            with contextlib.suppress(Exception):
                handler.flush()
        if self._security_handler is not None:
            self._security_handler.flush()
        if self._performance_handler is not None:
            self._performance_handler.flush()

    def shutdown(self) -> None:
        """Remove all handlers from the root logger and close them."""
        root = logging.getLogger()
        for handler in list(self._handlers):
            root.removeHandler(handler)
            handler.close()
        self._handlers.clear()

        if self._security_handler is not None:
            root.removeHandler(self._security_handler)
            self._security_handler.close()
            self._security_handler = None

        if self._performance_handler is not None:
            root.removeHandler(self._performance_handler)
            self._performance_handler.close()
            self._performance_handler = None

        self._configured = False
