"""Real-time performance monitoring for the application."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any

from src.analysis.models import _now_iso
from src.services.event_bus import EventBus, Events

logger = logging.getLogger(__name__)

try:
    import psutil

    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class PerformanceLevel(Enum):
    """Severity classification for system resource usage."""

    NORMAL = auto()
    ELEVATED = auto()
    HIGH = auto()
    CRITICAL = auto()


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class PerformanceSnapshot:
    """A single point-in-time measurement of system and process metrics."""

    timestamp: float
    cpu_percent: float = 0.0
    memory_mb: float = 0.0
    memory_percent: float = 0.0
    disk_io_read: int = 0
    disk_io_write: int = 0
    thread_count: int = 0
    open_files: int = 0
    fps: float = 0.0
    app_memory_mb: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dictionary."""
        return {
            "timestamp": self.timestamp,
            "cpu_percent": self.cpu_percent,
            "memory_mb": self.memory_mb,
            "memory_percent": self.memory_percent,
            "disk_io_read": self.disk_io_read,
            "disk_io_write": self.disk_io_write,
            "thread_count": self.thread_count,
            "open_files": self.open_files,
            "fps": self.fps,
            "app_memory_mb": self.app_memory_mb,
        }


@dataclass
class PerformanceAlert:
    """A single threshold-violation event."""

    timestamp: str
    level: PerformanceLevel
    metric: str
    value: float
    threshold: float
    message: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dictionary."""
        return {
            "timestamp": self.timestamp,
            "level": self.level.name,
            "metric": self.metric,
            "value": self.value,
            "threshold": self.threshold,
            "message": self.message,
        }


# ---------------------------------------------------------------------------
# Performance monitor
# ---------------------------------------------------------------------------

_DEFAULT_THRESHOLDS: dict[str, float] = {
    "cpu_percent": 80.0,
    "memory_percent": 80.0,
    "memory_mb": 2048.0,
    "thread_count": 100.0,
    "app_memory_mb": 1024.0,
}


class PerformanceMonitor:
    """Background monitor that samples system and process metrics at a
    configurable interval and emits alerts when thresholds are exceeded.

    All public methods are thread-safe.  Snapshots are stored in a fixed-
    size ring buffer to bound memory usage.
    """

    def __init__(self) -> None:
        self._event_bus = EventBus.instance()
        self._snapshots: list[PerformanceSnapshot] = []
        self._alerts: list[PerformanceAlert] = []
        self._lock = threading.Lock()
        self._running: bool = False
        self._monitor_thread: threading.Thread | None = None
        self._interval: float = 1.0
        self._thresholds: dict[str, float] = dict(_DEFAULT_THRESHOLDS)
        self._max_snapshots: int = 600
        self._max_alerts: int = 100

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background monitoring thread."""
        if self._running:
            return
        self._running = True
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            name="perf-monitor",
            daemon=True,
        )
        self._monitor_thread.start()
        logger.debug("Performance monitor started")

    def stop(self) -> None:
        """Stop the background monitoring thread."""
        self._running = False
        if self._monitor_thread is not None:
            self._monitor_thread.join(timeout=5.0)
            self._monitor_thread = None
        logger.debug("Performance monitor stopped")

    def is_running(self) -> bool:
        """Return *True* if the monitor thread is active."""
        return self._running

    def shutdown(self) -> None:
        """Stop monitoring and release resources."""
        self.stop()
        with self._lock:
            self._snapshots.clear()
            self._alerts.clear()
        logger.debug("Performance monitor shut down")

    # ------------------------------------------------------------------
    # Snapshots
    # ------------------------------------------------------------------

    def get_current_snapshot(self) -> PerformanceSnapshot:
        """Take and return an immediate snapshot without waiting for the
        background loop."""
        return self._take_snapshot()

    def get_latest_snapshot(self) -> PerformanceSnapshot | None:
        """Return the most recent snapshot, or *None* if none exist."""
        with self._lock:
            if not self._snapshots:
                return None
            return self._snapshots[-1]

    def get_history(self, count: int = 60) -> list[PerformanceSnapshot]:
        """Return the last *count* snapshots."""
        with self._lock:
            return list(self._snapshots[-count:])

    # ------------------------------------------------------------------
    # Alerts
    # ------------------------------------------------------------------

    def get_alerts(self, count: int = 50) -> list[PerformanceAlert]:
        """Return the most recent *count* alerts."""
        with self._lock:
            return list(self._alerts[-count:])

    def get_alert_count(self) -> int:
        """Return the total number of recorded alerts."""
        with self._lock:
            return len(self._alerts)

    # ------------------------------------------------------------------
    # Aggregates
    # ------------------------------------------------------------------

    def get_average_cpu(self, seconds: float = 60.0) -> float:
        """Return average CPU usage over the last *seconds*."""
        cutoff = time.monotonic() - seconds
        samples: list[float] = []
        with self._lock:
            for snap in self._snapshots:
                if snap.timestamp >= cutoff:
                    samples.append(snap.cpu_percent)
        return sum(samples) / len(samples) if samples else 0.0

    def get_average_memory(self, seconds: float = 60.0) -> float:
        """Return average memory usage (MB) over the last *seconds*."""
        cutoff = time.monotonic() - seconds
        samples: list[float] = []
        with self._lock:
            for snap in self._snapshots:
                if snap.timestamp >= cutoff:
                    samples.append(snap.memory_mb)
        return sum(samples) / len(samples) if samples else 0.0

    def get_peak_cpu(self) -> float:
        """Return the highest CPU percentage recorded."""
        with self._lock:
            if not self._snapshots:
                return 0.0
            return max(s.cpu_percent for s in self._snapshots)

    def get_peak_memory(self) -> float:
        """Return the highest memory usage (MB) recorded."""
        with self._lock:
            if not self._snapshots:
                return 0.0
            return max(s.memory_mb for s in self._snapshots)

    # ------------------------------------------------------------------
    # Level
    # ------------------------------------------------------------------

    def get_level(self) -> PerformanceLevel:
        """Determine the current overall performance level from the
        latest snapshot."""
        latest = self.get_latest_snapshot()
        if latest is None:
            return PerformanceLevel.NORMAL

        cpu = latest.cpu_percent
        mem_pct = latest.memory_percent
        mem_mb = latest.memory_mb

        if cpu >= 95.0 or mem_pct >= 95.0 or mem_mb >= 3072.0:
            return PerformanceLevel.CRITICAL
        if (
            cpu >= self._thresholds.get("cpu_percent", 80.0)
            or mem_pct >= self._thresholds.get("memory_percent", 80.0)
            or mem_mb >= self._thresholds.get("memory_mb", 2048.0)
        ):
            return PerformanceLevel.HIGH
        if cpu >= 60.0 or mem_pct >= 60.0 or mem_mb >= 1024.0:
            return PerformanceLevel.ELEVATED
        return PerformanceLevel.NORMAL

    # ------------------------------------------------------------------
    # Thresholds
    # ------------------------------------------------------------------

    def set_threshold(self, metric: str, value: float) -> None:
        """Set a custom threshold for *metric*."""
        with self._lock:
            self._thresholds[metric] = value

    def get_thresholds(self) -> dict[str, float]:
        """Return a copy of the current threshold configuration."""
        with self._lock:
            return dict(self._thresholds)

    # ------------------------------------------------------------------
    # Background loop
    # ------------------------------------------------------------------

    def _monitor_loop(self) -> None:
        """Main loop executed by the background monitoring thread."""
        while self._running:
            snapshot = self._take_snapshot()
            self._check_thresholds(snapshot)
            time.sleep(self._interval)

    def _take_snapshot(self) -> PerformanceSnapshot:
        """Collect current system and process metrics into a snapshot."""
        cpu = self._get_cpu_percent()
        mem_mb, mem_pct = self._get_memory()
        app_mem = self._get_app_memory()
        threads = self._get_thread_count()
        read_bytes, write_bytes = self._get_disk_io()
        open_files = self._get_open_files()

        snapshot = PerformanceSnapshot(
            timestamp=time.monotonic(),
            cpu_percent=cpu,
            memory_mb=mem_mb,
            memory_percent=mem_pct,
            disk_io_read=read_bytes,
            disk_io_write=write_bytes,
            thread_count=threads,
            open_files=open_files,
            app_memory_mb=app_mem,
        )

        with self._lock:
            self._snapshots.append(snapshot)
            if len(self._snapshots) > self._max_snapshots:
                self._snapshots = self._snapshots[-self._max_snapshots :]

        return snapshot

    def _check_thresholds(self, snapshot: PerformanceSnapshot) -> None:
        """Evaluate *snapshot* against configured thresholds and emit
        alerts for any violations."""
        checks: list[tuple[str, float, str]] = [
            ("cpu_percent", snapshot.cpu_percent, "CPU usage"),
            ("memory_percent", snapshot.memory_percent, "Memory usage"),
            ("memory_mb", snapshot.memory_mb, "Memory consumption"),
            ("thread_count", float(snapshot.thread_count), "Thread count"),
            ("app_memory_mb", snapshot.app_memory_mb, "Application memory"),
        ]

        for metric, value, label in checks:
            threshold = self._thresholds.get(metric)
            if threshold is None or value < threshold:
                continue

            level = PerformanceLevel.CRITICAL if value >= threshold * 1.2 else PerformanceLevel.HIGH
            msg = f"{label} at {value:.1f} (threshold: {threshold:.1f})"

            alert = PerformanceAlert(
                timestamp=_now_iso(),
                level=level,
                metric=metric,
                value=value,
                threshold=threshold,
                message=msg,
            )

            with self._lock:
                self._alerts.append(alert)
                if len(self._alerts) > self._max_alerts:
                    self._alerts = self._alerts[-self._max_alerts :]

            event = (
                Events.PERFORMANCE_CRITICAL
                if level == PerformanceLevel.CRITICAL
                else Events.PERFORMANCE_WARNING
            )
            self._event_bus.emit(event, alert.to_dict())
            logger.warning("Performance alert: %s", msg)

    # ------------------------------------------------------------------
    # Metric collection helpers
    # ------------------------------------------------------------------

    def _get_cpu_percent(self) -> float:
        """Return system-wide CPU percentage."""
        if _HAS_PSUTIL:
            try:
                return psutil.cpu_percent(interval=None)
            except Exception:
                pass

        # Fallback: parse /proc/stat (Linux only)
        try:
            with open("/proc/stat", encoding="utf-8") as fh:
                line = fh.readline()
            parts = line.split()
            # user, nice, system, idle, iowait, irq, softirq, steal
            values = [int(parts[i]) for i in range(1, 9)]
            idle = values[3] + values[4]
            total = sum(values)
            # Since we cannot compute delta without state, return total utilisation
            # approximation.  A second call will give a better number.
            return max(0.0, (total - idle) / total * 100.0) if total else 0.0
        except (OSError, IndexError, ValueError):
            return 0.0

    def _get_memory(self) -> tuple[float, float]:
        """Return (used_mb, used_percent) for system memory."""
        if _HAS_PSUTIL:
            try:
                mem = psutil.virtual_memory()
                return mem.used / (1024 * 1024), mem.percent
            except Exception:
                pass

        # Fallback: parse /proc/meminfo
        try:
            info: dict[str, int] = {}
            with open("/proc/meminfo", encoding="utf-8") as fh:
                for line in fh:
                    parts = line.split()
                    if len(parts) >= 2:
                        key = parts[0].rstrip(":")
                        info[key] = int(parts[1])  # kB
            total = info.get("MemTotal", 0)
            available = info.get("MemAvailable", 0)
            used = total - available
            used_mb = used / 1024.0
            pct = (used / total * 100.0) if total else 0.0
            return used_mb, pct
        except (OSError, IndexError, ValueError):
            return 0.0, 0.0

    def _get_app_memory(self) -> float:
        """Return the current process RSS in megabytes."""
        if _HAS_PSUTIL:
            try:
                proc = psutil.Process()
                return proc.memory_info().rss / (1024 * 1024)
            except Exception:
                pass

        # Fallback: parse /proc/self/status
        try:
            with open("/proc/self/status", encoding="utf-8") as fh:
                for line in fh:
                    if line.startswith("VmRSS:"):
                        parts = line.split()
                        return float(parts[1]) / 1024.0  # kB -> MB
        except (OSError, IndexError, ValueError):
            pass
        return 0.0

    def _get_thread_count(self) -> int:
        """Return the number of threads in the current process."""
        if _HAS_PSUTIL:
            try:
                return psutil.Process().num_threads()
            except Exception:
                pass

        # Fallback: count /proc/self/task entries
        try:
            import os

            task_dir = "/proc/self/task"
            return len(os.listdir(task_dir))
        except (OSError, FileNotFoundError):
            return threading.active_count()

    def _get_disk_io(self) -> tuple[int, int]:
        """Return (read_bytes, write_bytes) since boot."""
        if _HAS_PSUTIL:
            try:
                counters = psutil.disk_io_counters()
                if counters is not None:
                    return counters.read_bytes, counters.write_bytes
            except Exception:
                pass
        return 0, 0

    def _get_open_files(self) -> int:
        """Return the number of open file descriptors for this process."""
        if _HAS_PSUTIL:
            try:
                return len(psutil.Process().open_files())
            except Exception:
                pass

        # Fallback: count /proc/self/fd entries
        try:
            import os

            fd_dir = "/proc/self/fd"
            return len(os.listdir(fd_dir))
        except (OSError, FileNotFoundError):
            return 0

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def generate_report(self) -> str:
        """Produce a formatted multi-line performance report string."""
        lines: list[str] = [
            "=" * 60,
            "  SecurePacketAnalyzerPro – Performance Report",
            "=" * 60,
            "",
        ]

        level = self.get_level()
        lines.append(f"  Overall Level : {level.name}")
        lines.append(f"  Samples       : {len(self._snapshots)}")
        lines.append(f"  Alerts        : {len(self._alerts)}")
        lines.append("")

        latest = self.get_latest_snapshot()
        if latest is not None:
            lines.append("  Latest Snapshot:")
            lines.append(f"    CPU             : {latest.cpu_percent:.1f}%")
            lines.append(
                f"    System Memory   : {latest.memory_mb:.1f} MB ({latest.memory_percent:.1f}%)"
            )
            lines.append(f"    App Memory      : {latest.app_memory_mb:.1f} MB")
            lines.append(f"    Threads         : {latest.thread_count}")
            lines.append(f"    Open Files      : {latest.open_files}")
            lines.append(f"    Disk Read       : {latest.disk_io_read} bytes")
            lines.append(f"    Disk Write      : {latest.disk_io_write} bytes")
        else:
            lines.append("  No snapshots available.")

        lines.append("")
        lines.append("  Averages (last 60 s):")
        lines.append(f"    CPU             : {self.get_average_cpu(60.0):.1f}%")
        lines.append(f"    Memory          : {self.get_average_memory(60.0):.1f} MB")

        lines.append("")
        lines.append("  Peaks:")
        lines.append(f"    CPU             : {self.get_peak_cpu():.1f}%")
        lines.append(f"    Memory          : {self.get_peak_memory():.1f} MB")

        if self._alerts:
            lines.append("")
            lines.append("  Recent Alerts:")
            for alert in self._alerts[-5:]:
                lines.append(f"    [{alert.level.name}] {alert.message}")

        lines.append("")
        lines.append("=" * 60)

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Clear helpers
    # ------------------------------------------------------------------

    def clear_history(self) -> None:
        """Discard all stored snapshots."""
        with self._lock:
            self._snapshots.clear()

    def clear_alerts(self) -> None:
        """Discard all stored alerts."""
        with self._lock:
            self._alerts.clear()
