"""Diagnostics system for SecurePacketAnalyzerPro.

Runs a battery of environment checks – Python version, OS, memory,
disk space, permissions, SQLite, Scapy – and produces a formatted
report suitable for display or attachment to bug reports.
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import sqlite3
import sys
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Minimum recommended Python major.minor
_MIN_PYTHON: tuple[int, int] = (3, 10)

# Minimum recommended free disk space (MB)
_MIN_DISK_MB: int = 100

# Minimum recommended free memory (MB)
_MIN_MEMORY_MB: int = 256


@dataclass
class DiagnosticResult:
    """Outcome of a single diagnostic check."""

    check_name: str
    status: str  # "pass", "warning", "fail", "info"
    message: str
    details: str = ""


class DiagnosticsManager:
    """Runs system checks and assembles a human-readable report.

    All ``check_*`` methods return a :class:`DiagnosticResult`.
    :meth:`run_all_checks` gathers every check into a single list.
    """

    def __init__(self) -> None:
        self._results: list[DiagnosticResult] = []

    # ------------------------------------------------------------------
    # Aggregate
    # ------------------------------------------------------------------

    def run_all_checks(self) -> list[DiagnosticResult]:
        """Execute every registered diagnostic check.

        Returns an ordered list of :class:`DiagnosticResult` objects.
        """
        self._results = [
            self.check_python_version(),
            self.check_dependencies(),
            self.check_operating_system(),
            self.check_memory(),
            self.check_disk_space(),
            self.check_permissions(),
            self.check_configuration(),
            self.check_sqlite(),
            self.check_scapy(),
        ]
        return list(self._results)

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def check_python_version(self) -> DiagnosticResult:
        """Verify the Python interpreter meets the minimum version."""
        current = (sys.version_info.major, sys.version_info.minor)
        version_str = f"{current[0]}.{current[1]}.{sys.version_info.micro}"
        if current >= _MIN_PYTHON:
            return DiagnosticResult(
                check_name="Python Version",
                status="pass",
                message=f"Python {version_str} is supported",
            )
        if current[0] == _MIN_PYTHON[0] and current[1] >= _MIN_PYTHON[1] - 1:
            return DiagnosticResult(
                check_name="Python Version",
                status="warning",
                message=(
                    f"Python {version_str} – recommend upgrading to "
                    f"{_MIN_PYTHON[0]}.{_MIN_PYTHON[1]}+"
                ),
            )
        return DiagnosticResult(
            check_name="Python Version",
            status="fail",
            message=(
                f"Python {version_str} is too old – minimum "
                f"{_MIN_PYTHON[0]}.{_MIN_PYTHON[1]} required"
            ),
        )

    def check_dependencies(self) -> DiagnosticResult:
        """Check that optional dependencies are importable."""
        missing: list[str] = []
        optional = {
            "PySide6": "PySide6",
            "scapy": "scapy",
            "numpy": "numpy",
            "matplotlib": "matplotlib",
        }
        found: list[str] = []
        for display_name, module_name in optional.items():
            try:
                __import__(module_name)
                found.append(display_name)
            except ImportError:
                missing.append(display_name)

        if not missing:
            return DiagnosticResult(
                check_name="Dependencies",
                status="pass",
                message=f"All optional dependencies found: {', '.join(found)}",
            )
        if found:
            return DiagnosticResult(
                check_name="Dependencies",
                status="warning",
                message=f"Missing: {', '.join(missing)}  |  Found: {', '.join(found)}",
            )
        return DiagnosticResult(
            check_name="Dependencies",
            status="info",
            message=f"Optional dependencies not installed: {', '.join(missing)}",
        )

    def check_operating_system(self) -> DiagnosticResult:
        """Report the detected operating system."""
        os_name = platform.system()
        os_release = platform.release()
        os_version = platform.version()
        machine = platform.machine()
        message = f"{os_name} {os_release} ({machine})"
        # All major OSes are supported; just report info.
        return DiagnosticResult(
            check_name="Operating System",
            status="pass",
            message=message,
            details=f"Full version: {os_version}",
        )

    def check_memory(self) -> DiagnosticResult:
        """Estimate available system memory."""
        mem_mb = self._available_memory_mb()
        if mem_mb is None:
            return DiagnosticResult(
                check_name="Memory",
                status="info",
                message="Could not determine available memory",
            )
        if mem_mb >= _MIN_MEMORY_MB * 4:
            return DiagnosticResult(
                check_name="Memory",
                status="pass",
                message=f"{mem_mb:.0f} MB available",
            )
        if mem_mb >= _MIN_MEMORY_MB:
            return DiagnosticResult(
                check_name="Memory",
                status="warning",
                message=f"{mem_mb:.0f} MB available – may be low for large captures",
            )
        return DiagnosticResult(
            check_name="Memory",
            status="fail",
            message=f"{mem_mb:.0f} MB available – below minimum {_MIN_MEMORY_MB} MB",
        )

    def check_disk_space(self) -> DiagnosticResult:
        """Check free disk space in the application's data directory."""
        from src.utils.paths import AppPaths

        target = AppPaths.data_dir()
        target.mkdir(parents=True, exist_ok=True)
        usage = shutil.disk_usage(str(target))
        free_mb = usage.free / (1024 * 1024)
        total_mb = usage.total / (1024 * 1024)
        pct = (usage.free / usage.total) * 100 if usage.total else 0

        if free_mb >= _MIN_DISK_MB * 10:
            return DiagnosticResult(
                check_name="Disk Space",
                status="pass",
                message=f"{free_mb:.0f} MB free of {total_mb:.0f} MB ({pct:.1f}%)",
            )
        if free_mb >= _MIN_DISK_MB:
            return DiagnosticResult(
                check_name="Disk Space",
                status="warning",
                message=f"{free_mb:.0f} MB free – disk space is getting low",
            )
        return DiagnosticResult(
            check_name="Disk Space",
            status="fail",
            message=f"{free_mb:.0f} MB free – below {_MIN_DISK_MB} MB minimum",
        )

    def check_permissions(self) -> DiagnosticResult:
        """Check that key application directories are accessible."""
        from src.utils.paths import AppPaths

        problems: list[str] = []
        for name, getter in [
            ("config", AppPaths.config_dir),
            ("data", AppPaths.data_dir),
            ("logs", AppPaths.logs_dir),
            ("workspaces", AppPaths.workspaces_dir),
        ]:
            d = getter()
            d.mkdir(parents=True, exist_ok=True)
            if not os.access(str(d), os.R_OK):
                problems.append(f"{name}: not readable")
            if not os.access(str(d), os.W_OK):
                problems.append(f"{name}: not writable")

        if not problems:
            return DiagnosticResult(
                check_name="Permissions",
                status="pass",
                message="All application directories are accessible",
            )
        return DiagnosticResult(
            check_name="Permissions",
            status="fail",
            message="Some directories have permission issues",
            details="; ".join(problems),
        )

    def check_configuration(self) -> DiagnosticResult:
        """Validate the current configuration."""
        from src.config.settings import SettingsManager

        try:
            mgr = SettingsManager()
            errors = mgr.validate()
        except Exception as exc:
            return DiagnosticResult(
                check_name="Configuration",
                status="fail",
                message=f"Failed to load configuration: {exc}",
            )

        if not errors:
            return DiagnosticResult(
                check_name="Configuration",
                status="pass",
                message="Configuration is valid",
            )
        return DiagnosticResult(
            check_name="Configuration",
            status="warning",
            message=f"{len(errors)} validation issue(s) found",
            details="\n".join(errors),
        )

    def check_sqlite(self) -> DiagnosticResult:
        """Verify that SQLite3 is available and functional."""
        try:
            conn = sqlite3.connect(":memory:")
            cur = conn.execute("SELECT sqlite_version()")
            version = cur.fetchone()[0]
            conn.close()
            return DiagnosticResult(
                check_name="SQLite",
                status="pass",
                message=f"SQLite {version} available",
            )
        except Exception as exc:
            return DiagnosticResult(
                check_name="SQLite",
                status="fail",
                message=f"SQLite check failed: {exc}",
            )

    def check_scapy(self) -> DiagnosticResult:
        """Verify that Scapy is importable and usable."""
        try:
            import scapy

            version = getattr(scapy, "VERSION", "unknown")
            return DiagnosticResult(
                check_name="Scapy",
                status="pass",
                message=f"Scapy {version} available",
            )
        except ImportError:
            return DiagnosticResult(
                check_name="Scapy",
                status="warning",
                message="Scapy is not installed – packet dissection will be limited",
            )
        except Exception as exc:
            return DiagnosticResult(
                check_name="Scapy",
                status="fail",
                message=f"Scapy import failed: {exc}",
            )

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def generate_report(self) -> str:
        """Produce a formatted multi-line text report.

        Results from the most recent :meth:`run_all_checks` call are
        used.  If no checks have been run yet the report will be empty.
        """
        if not self._results:
            self.run_all_checks()

        lines: list[str] = [
            "=" * 60,
            "  SecurePacketAnalyzerPro – Diagnostics Report",
            "=" * 60,
            "",
        ]

        sys_info = self.get_system_info()
        for key, value in sys_info.items():
            lines.append(f"  {key:<20s} {value}")
        lines.append("")
        lines.append("-" * 60)

        status_symbols: dict[str, str] = {
            "pass": "[PASS]",
            "warning": "[WARN]",
            "fail": "[FAIL]",
            "info": "[INFO]",
        }

        for result in self._results:
            symbol = status_symbols.get(result.status, "[????]")
            lines.append(f"  {symbol}  {result.check_name}: {result.message}")
            if result.details:
                for detail_line in result.details.splitlines():
                    lines.append(f"         {detail_line}")

        lines.append("")
        lines.append("-" * 60)
        summary = self._summary()
        lines.append(f"  Summary: {summary}")
        lines.append("=" * 60)

        return "\n".join(lines)

    def get_system_info(self) -> dict[str, str]:
        """Return a dictionary of basic system information."""
        info: dict[str, str] = {
            "Platform": platform.platform(),
            "Python": sys.version.split()[0],
            "Executable": sys.executable,
            "Architecture": platform.machine(),
            "Processor": platform.processor() or "N/A",
            "Node": platform.node(),
        }
        try:
            info["PID"] = str(os.getpid())
        except Exception:
            info["PID"] = "N/A"
        return info

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _summary(self) -> str:
        """Return a one-line summary of the diagnostic run."""
        counts: dict[str, int] = {"pass": 0, "warning": 0, "fail": 0, "info": 0}
        for r in self._results:
            counts[r.status] = counts.get(r.status, 0) + 1
        parts: list[str] = []
        if counts["pass"]:
            parts.append(f"{counts['pass']} passed")
        if counts["warning"]:
            parts.append(f"{counts['warning']} warnings")
        if counts["fail"]:
            parts.append(f"{counts['fail']} failures")
        if counts["info"]:
            parts.append(f"{counts['info']} informational")
        return ", ".join(parts) if parts else "No checks run"

    @staticmethod
    def _available_memory_mb() -> float | None:
        """Return available system memory in megabytes, or *None*."""
        try:
            with open("/proc/meminfo", encoding="utf-8", errors="ignore") as fh:  # noqa: PTH123 -- procfs
                for line in fh:
                    if line.startswith("MemAvailable:"):
                        parts = line.split()
                        # Value is in kB
                        return float(parts[1]) / 1024.0
        except (OSError, IndexError, ValueError):
            pass

        # Fallback: try psutil if available
        try:
            import psutil  # type: ignore[import-untyped]

            mem = psutil.virtual_memory()
            return mem.available / (1024 * 1024)
        except (ImportError, AttributeError):
            pass

        return None
