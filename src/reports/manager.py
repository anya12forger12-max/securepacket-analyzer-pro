"""Centralized report management — creation, generation, storage, and lifecycle."""

from __future__ import annotations

import json
import logging
import threading
import uuid
from typing import TYPE_CHECKING, Any

from src.analysis.models import _now_iso
from src.analysis.reporting_models import (
    Report,
    ReportSection,
)
from src.reports.templates import ReportTemplateManager
from src.services.event_bus import EventBus, Events
from src.utils.paths import AppPaths

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


class ReportManager:
    """Creates, stores, retrieves, and generates reports.

    Reports are persisted as individual JSON files under the application's
    data directory.  An in-memory cache (``_reports``) is kept in sync
    with disk and protected by a reentrant lock for thread safety.

    Parameters
    ----------
    template_manager:
        Optional pre-configured template manager.  When *None* a fresh
        :class:`ReportTemplateManager` is created.
    """

    def __init__(self, template_manager: ReportTemplateManager | None = None) -> None:
        self._template_manager = template_manager or ReportTemplateManager()
        self._event_bus = EventBus.instance()
        self._reports_dir: Path = AppPaths.data_dir() / "reports"
        self._reports_dir.mkdir(parents=True, exist_ok=True)
        self._lock: threading.Lock = threading.Lock()
        self._reports: dict[str, Report] = {}
        self._load_reports()

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _load_reports(self) -> None:
        """Scan the reports directory and load all JSON files into memory."""
        loaded = 0
        for path in self._reports_dir.glob("*.json"):
            try:
                raw = path.read_text(encoding="utf-8")
                data = json.loads(raw)
                report = Report.from_dict(data)
                self._reports[report.report_id] = report
                loaded += 1
            except (json.JSONDecodeError, OSError, TypeError, KeyError) as exc:
                logger.warning("Failed to load report from %s: %s", path, exc)
        logger.info("Loaded %d report(s) from disk", loaded)

    def _get_report_path(self, report_id: str) -> Path:
        """Return the JSON file path for a report."""
        return self._reports_dir / f"{report_id}.json"

    def save_report(self, report: Report) -> bool:
        """Persist a report to its JSON file.

        Returns ``True`` on success, ``False`` on I/O error.
        """
        report.touch()
        path = self._get_report_path(report.report_id)
        try:
            data = report.to_dict()
            path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            return True
        except OSError as exc:
            logger.error("Failed to save report '%s': %s", report.report_id, exc)
            return False

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create_report(
        self,
        title: str,
        template_id: str,
        description: str = "",
        workspace: str = "",
    ) -> Report:
        """Create a new report from a template and persist it.

        Raises ``ValueError`` if *template_id* does not match any
        registered template.
        """
        tpl = self._template_manager.get_template(template_id)
        if tpl is None:
            raise ValueError(f"Unknown template: {template_id!r}")

        now = _now_iso()
        report = Report(
            report_id=str(uuid.uuid4()),
            title=title,
            template_id=template_id,
            description=description,
            workspace=workspace,
            created_at=now,
            modified_at=now,
        )
        with self._lock:
            self._reports[report.report_id] = report
        self.save_report(report)
        self._event_bus.emit(Events.REPORT_CREATED, report.to_dict())
        logger.info("Created report '%s' (%s)", title, report.report_id)
        return report

    def get_report(self, report_id: str) -> Report | None:
        """Return the report for *report_id*, or *None* if not found."""
        with self._lock:
            return self._reports.get(report_id)

    def list_reports(
        self,
        workspace: str | None = None,
        tags: list[str] | None = None,
    ) -> list[Report]:
        """Return reports optionally filtered by workspace and/or tags.

        Parameters
        ----------
        workspace:
            If provided, only reports in this workspace are returned.
        tags:
            If provided, only reports containing **all** of these tags
            are returned.
        """
        with self._lock:
            results = list(self._reports.values())

        if workspace is not None:
            results = [r for r in results if r.workspace == workspace]

        if tags is not None:
            tag_set = set(tags)
            results = [r for r in results if tag_set.issubset(set(r.tags))]

        return results

    def update_report(self, report_id: str, **kwargs: Any) -> Report | None:
        """Update fields on an existing report.

        Accepted keyword arguments: ``title``, ``description``,
        ``workspace``, ``severity``, ``tags``, ``status``, ``case_id``,
        ``content``.  Returns the updated report or *None* if not found.
        """
        with self._lock:
            report = self._reports.get(report_id)
            if report is None:
                logger.warning("Report '%s' not found for update", report_id)
                return None

            for key, value in kwargs.items():
                if hasattr(report, key):
                    setattr(report, key, value)

            report.touch()

        self.save_report(report)
        logger.info("Updated report '%s' (%s)", report.title, report_id)
        return report

    def delete_report(self, report_id: str) -> bool:
        """Delete a report from memory and disk.

        Returns ``True`` on success, ``False`` if not found.
        """
        with self._lock:
            report = self._reports.pop(report_id, None)

        if report is None:
            logger.warning("Report '%s' not found for deletion", report_id)
            return False

        path = self._get_report_path(report_id)
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("Failed to delete report file %s: %s", path, exc)

        self._event_bus.emit(Events.REPORT_DELETED, report.to_dict())
        logger.info("Deleted report '%s' (%s)", report.title, report_id)
        return True

    def duplicate_report(self, report_id: str, new_title: str) -> Report | None:
        """Create a copy of *report_id* with *new_title*.

        Returns the new report or *None* if the source is not found.
        """
        source = self.get_report(report_id)
        if source is None:
            logger.warning("Report '%s' not found for duplication", report_id)
            return None

        now = _now_iso()
        dup = Report(
            report_id=str(uuid.uuid4()),
            title=new_title,
            template_id=source.template_id,
            description=source.description,
            workspace=source.workspace,
            severity=source.severity,
            tags=list(source.tags),
            content=dict(source.content),
            status=source.status,
            starred=False,
            case_id=source.case_id,
            export_formats=list(source.export_formats),
            created_at=now,
            modified_at=now,
        )
        with self._lock:
            self._reports[dup.report_id] = dup
        self.save_report(dup)
        logger.info(
            "Duplicated report '%s' -> '%s' (%s)",
            source.title,
            new_title,
            dup.report_id,
        )
        return dup

    def star_report(self, report_id: str, starred: bool = True) -> Report | None:
        """Set or clear the starred flag on a report.

        Returns the updated report or *None* if not found.
        """
        return self.update_report(report_id, starred=starred)

    # ------------------------------------------------------------------
    # Report content generation
    # ------------------------------------------------------------------

    def generate_report_content(self, report_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Populate report content from *data* according to the template.

        Each section enabled in the report's template is populated from
        the corresponding key in *data*.  Returns the generated content
        dictionary which is also stored on the report.

        Parameters
        ----------
        report_id:
            The report to populate.
        data:
            A dictionary whose keys map to section data.  Missing keys
            result in empty section content.
        """
        report = self.get_report(report_id)
        if report is None:
            logger.warning("Report '%s' not found for content generation", report_id)
            return {}

        tpl = self._template_manager.get_template(report.template_id)
        if tpl is None:
            logger.warning(
                "Template '%s' not found for report '%s'",
                report.template_id,
                report_id,
            )
            return {}

        content: dict[str, Any] = {}

        for section in tpl.sections:
            section_data: dict[str, Any] = {}

            if section is ReportSection.TITLE:
                section_data = {
                    "title": report.title,
                    "description": report.description,
                    "generated_at": _now_iso(),
                }

            elif section is ReportSection.EXECUTIVE_SUMMARY:
                section_data = {
                    "summary_text": data.get("summary_text", ""),
                }

            elif section is ReportSection.CAPTURE_INFO:
                section_data = {
                    "interface": data.get("interface", ""),
                    "duration": data.get("duration", 0.0),
                    "packet_count": data.get("packet_count", 0),
                }

            elif section is ReportSection.TRAFFIC_STATS:
                section_data = {
                    "total_packets": data.get("total_packets", 0),
                    "total_bytes": data.get("total_bytes", 0),
                    "pps": data.get("pps", 0.0),
                    "bps": data.get("bps", 0.0),
                }

            elif section is ReportSection.PROTOCOL_DISTRIBUTION:
                section_data = {
                    "protocols": data.get("protocols", []),
                }

            elif section is ReportSection.HOST_OVERVIEW:
                section_data = {
                    "hosts": data.get("hosts", []),
                }

            elif section is ReportSection.CONNECTION_OVERVIEW:
                section_data = {
                    "connections": data.get("connections", []),
                }

            elif section is ReportSection.TOP_TALKERS:
                section_data = {
                    "top_ips": data.get("top_ips", []),
                    "top_ports": data.get("top_ports", []),
                }

            elif section is ReportSection.BANDWIDTH_SUMMARY:
                section_data = {
                    "bandwidth_samples": data.get("bandwidth_samples", []),
                }

            elif section is ReportSection.TIMELINE:
                section_data = {
                    "timeline_events": data.get("timeline_events", []),
                }

            elif section is ReportSection.ALERT_SUMMARY:
                section_data = {
                    "alerts": data.get("alerts", []),
                }

            elif section is ReportSection.EVIDENCE:
                section_data = {
                    "evidence_items": data.get("evidence_items", []),
                }

            elif section is ReportSection.BOOKMARKS:
                section_data = {
                    "bookmarks": data.get("bookmarks", []),
                }

            elif section is ReportSection.NOTES:
                section_data = {
                    "notes": data.get("notes", ""),
                }

            elif section is ReportSection.RECOMMENDATIONS:
                section_data = {
                    "recommendations": data.get("recommendations", []),
                }

            elif section is ReportSection.APPENDIX:
                section_data = {
                    "appendix_data": data.get("appendix_data", {}),
                }

            content[section.name] = section_data

        report.content = content
        report.touch()
        self.save_report(report)
        self._event_bus.emit(Events.REPORT_GENERATED, report.to_dict())
        logger.info(
            "Generated content for report '%s' (%d sections)",
            report.report_id,
            len(content),
        )
        return content

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_reports_count(self, workspace: str | None = None) -> int:
        """Return the number of reports, optionally filtered by workspace."""
        if workspace is None:
            with self._lock:
                return len(self._reports)
        return len(self.list_reports(workspace=workspace))

    def search_reports(self, query: str) -> list[Report]:
        """Search reports by title, description, or tags.

        Case-insensitive substring match on title and description; tag
        match is exact and also case-insensitive.
        """
        query_lower = query.lower()
        results: list[Report] = []
        with self._lock:
            for report in self._reports.values():
                if query_lower in report.title.lower():
                    results.append(report)
                    continue
                if query_lower in report.description.lower():
                    results.append(report)
                    continue
                if any(query_lower == tag.lower() for tag in report.tags):
                    results.append(report)
        return results

    def get_recent_reports(self, limit: int = 10) -> list[Report]:
        """Return the most recently modified reports, newest first."""
        with self._lock:
            reports = list(self._reports.values())
        reports.sort(key=lambda r: r.modified_at, reverse=True)
        return reports[:limit]
