"""Built-in report templates and template management."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from src.analysis.models import _now_iso
from src.analysis.reporting_models import ReportSection, ReportTemplate

logger = logging.getLogger(__name__)


class ReportTemplateManager:
    """Manages built-in and custom report templates.

    Built-in templates are created at construction time and cannot be
    deleted.  Custom templates are user-created and fully mutable.
    """

    def __init__(self) -> None:
        self._templates: dict[str, ReportTemplate] = {}
        self._build_builtins()

    # ------------------------------------------------------------------
    # Built-in template construction
    # ------------------------------------------------------------------

    def _build_builtins(self) -> None:
        """Create the ten built-in report templates."""
        now = _now_iso()

        builtins: list[ReportTemplate] = [
            ReportTemplate(
                template_id="builtin_capture_summary",
                name="Capture Summary",
                description="Quick overview of a packet capture session.",
                sections=[
                    ReportSection.TITLE,
                    ReportSection.EXECUTIVE_SUMMARY,
                    ReportSection.CAPTURE_INFO,
                    ReportSection.TRAFFIC_STATS,
                    ReportSection.TIMELINE,
                ],
                is_builtin=True,
                author="SecurePacketAnalyzerPro",
                created_at=now,
                modified_at=now,
            ),
            ReportTemplate(
                template_id="builtin_traffic_summary",
                name="Traffic Summary",
                description="High-level traffic statistics and top talkers.",
                sections=[
                    ReportSection.TITLE,
                    ReportSection.EXECUTIVE_SUMMARY,
                    ReportSection.TRAFFIC_STATS,
                    ReportSection.PROTOCOL_DISTRIBUTION,
                    ReportSection.BANDWIDTH_SUMMARY,
                    ReportSection.TOP_TALKERS,
                ],
                is_builtin=True,
                author="SecurePacketAnalyzerPro",
                created_at=now,
                modified_at=now,
            ),
            ReportTemplate(
                template_id="builtin_protocol_analysis",
                name="Protocol Analysis",
                description="Deep-dive into protocol distribution and usage.",
                sections=[
                    ReportSection.TITLE,
                    ReportSection.EXECUTIVE_SUMMARY,
                    ReportSection.PROTOCOL_DISTRIBUTION,
                    ReportSection.TRAFFIC_STATS,
                    ReportSection.APPENDIX,
                ],
                is_builtin=True,
                author="SecurePacketAnalyzerPro",
                created_at=now,
                modified_at=now,
            ),
            ReportTemplate(
                template_id="builtin_host_summary",
                name="Host Summary",
                description="Overview of discovered hosts and their activity.",
                sections=[
                    ReportSection.TITLE,
                    ReportSection.EXECUTIVE_SUMMARY,
                    ReportSection.HOST_OVERVIEW,
                    ReportSection.TOP_TALKERS,
                    ReportSection.BANDWIDTH_SUMMARY,
                ],
                is_builtin=True,
                author="SecurePacketAnalyzerPro",
                created_at=now,
                modified_at=now,
            ),
            ReportTemplate(
                template_id="builtin_connection_summary",
                name="Connection Summary",
                description="Summary of detected network connections.",
                sections=[
                    ReportSection.TITLE,
                    ReportSection.EXECUTIVE_SUMMARY,
                    ReportSection.CONNECTION_OVERVIEW,
                    ReportSection.TRAFFIC_STATS,
                ],
                is_builtin=True,
                author="SecurePacketAnalyzerPro",
                created_at=now,
                modified_at=now,
            ),
            ReportTemplate(
                template_id="builtin_bandwidth_summary",
                name="Bandwidth Summary",
                description="Bandwidth utilization over time with top talkers.",
                sections=[
                    ReportSection.TITLE,
                    ReportSection.EXECUTIVE_SUMMARY,
                    ReportSection.BANDWIDTH_SUMMARY,
                    ReportSection.TRAFFIC_STATS,
                    ReportSection.TOP_TALKERS,
                ],
                is_builtin=True,
                author="SecurePacketAnalyzerPro",
                created_at=now,
                modified_at=now,
            ),
            ReportTemplate(
                template_id="builtin_alert_summary",
                name="Alert Summary",
                description="Alerts, evidence, and recommended actions.",
                sections=[
                    ReportSection.TITLE,
                    ReportSection.EXECUTIVE_SUMMARY,
                    ReportSection.ALERT_SUMMARY,
                    ReportSection.EVIDENCE,
                    ReportSection.RECOMMENDATIONS,
                ],
                is_builtin=True,
                author="SecurePacketAnalyzerPro",
                created_at=now,
                modified_at=now,
            ),
            ReportTemplate(
                template_id="builtin_network_health",
                name="Network Health",
                description="Overall network health with traffic and protocol stats.",
                sections=[
                    ReportSection.TITLE,
                    ReportSection.EXECUTIVE_SUMMARY,
                    ReportSection.TRAFFIC_STATS,
                    ReportSection.PROTOCOL_DISTRIBUTION,
                    ReportSection.TIMELINE,
                ],
                is_builtin=True,
                author="SecurePacketAnalyzerPro",
                created_at=now,
                modified_at=now,
            ),
            ReportTemplate(
                template_id="builtin_executive_summary",
                name="Executive Summary",
                description="High-level overview for management review.",
                sections=[
                    ReportSection.TITLE,
                    ReportSection.EXECUTIVE_SUMMARY,
                    ReportSection.TRAFFIC_STATS,
                    ReportSection.HOST_OVERVIEW,
                    ReportSection.ALERT_SUMMARY,
                    ReportSection.RECOMMENDATIONS,
                ],
                is_builtin=True,
                author="SecurePacketAnalyzerPro",
                created_at=now,
                modified_at=now,
            ),
            ReportTemplate(
                template_id="builtin_technical_analysis",
                name="Technical Analysis",
                description="Comprehensive technical report with all available sections.",
                sections=list(ReportSection),
                is_builtin=True,
                author="SecurePacketAnalyzerPro",
                created_at=now,
                modified_at=now,
            ),
        ]

        for tpl in builtins:
            self._templates[tpl.template_id] = tpl

        logger.info("Loaded %d built-in report templates", len(builtins))

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get_template(self, template_id: str) -> ReportTemplate | None:
        """Return the template for *template_id*, or *None* if not found."""
        return self._templates.get(template_id)

    def get_template_by_name(self, name: str) -> ReportTemplate | None:
        """Return the first template matching *name*, or *None*."""
        name_lower = name.lower()
        for tpl in self._templates.values():
            if tpl.name.lower() == name_lower:
                return tpl
        return None

    def list_templates(self) -> list[ReportTemplate]:
        """Return every registered template sorted by name."""
        return sorted(self._templates.values(), key=lambda t: t.name.lower())

    def get_builtin_templates(self) -> list[ReportTemplate]:
        """Return only built-in templates sorted by name."""
        return sorted(
            (t for t in self._templates.values() if t.is_builtin),
            key=lambda t: t.name.lower(),
        )

    def get_custom_templates(self) -> list[ReportTemplate]:
        """Return only user-created templates sorted by name."""
        return sorted(
            (t for t in self._templates.values() if not t.is_builtin),
            key=lambda t: t.name.lower(),
        )

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create_template(
        self,
        name: str,
        description: str,
        sections: list[ReportSection],
        author: str = "User",
    ) -> ReportTemplate:
        """Create and register a new custom template.

        Parameters
        ----------
        name:
            Human-readable template name.
        description:
            Short description of the template's purpose.
        sections:
            Which report sections this template includes.
        author:
            Template author.  Defaults to ``"User"``.
        """
        now = _now_iso()
        tpl = ReportTemplate(
            template_id=f"custom_{uuid.uuid4().hex[:12]}",
            name=name,
            description=description,
            sections=list(sections),
            is_builtin=False,
            author=author,
            created_at=now,
            modified_at=now,
        )
        self._templates[tpl.template_id] = tpl
        logger.info("Created custom template '%s' (%s)", name, tpl.template_id)
        return tpl

    def update_template(self, template_id: str, **kwargs: Any) -> ReportTemplate | None:
        """Update fields on an existing template.

        Accepted keyword arguments: ``name``, ``description``, ``sections``,
        ``author``, ``version``.  Returns the updated template or *None* if
        the *template_id* is not found.
        """
        tpl = self._templates.get(template_id)
        if tpl is None:
            logger.warning("Template '%s' not found for update", template_id)
            return None

        for key, value in kwargs.items():
            if hasattr(tpl, key):
                setattr(tpl, key, value)

        tpl.modified_at = _now_iso()
        logger.info("Updated template '%s' (%s)", tpl.name, template_id)
        return tpl

    def delete_template(self, template_id: str) -> bool:
        """Delete a custom template.  Built-in templates cannot be deleted.

        Returns ``True`` on success, ``False`` if the template is built-in
        or does not exist.
        """
        tpl = self._templates.get(template_id)
        if tpl is None:
            logger.warning("Template '%s' not found for deletion", template_id)
            return False

        if tpl.is_builtin:
            logger.warning("Cannot delete built-in template '%s'", template_id)
            return False

        del self._templates[template_id]
        logger.info("Deleted custom template '%s' (%s)", tpl.name, template_id)
        return True

    def duplicate_template(
        self, template_id: str, new_name: str
    ) -> ReportTemplate | None:
        """Create a copy of *template_id* with *new_name*.

        Returns the new template or *None* if the source is not found.
        """
        source = self._templates.get(template_id)
        if source is None:
            logger.warning("Template '%s' not found for duplication", template_id)
            return None

        now = _now_iso()
        dup = ReportTemplate(
            template_id=f"custom_{uuid.uuid4().hex[:12]}",
            name=new_name,
            description=source.description,
            sections=list(source.sections),
            is_builtin=False,
            author=source.author,
            version=source.version,
            created_at=now,
            modified_at=now,
        )
        self._templates[dup.template_id] = dup
        logger.info(
            "Duplicated template '%s' -> '%s' (%s)",
            source.name,
            new_name,
            dup.template_id,
        )
        return dup

    # ------------------------------------------------------------------
    # Metadata helpers
    # ------------------------------------------------------------------

    @staticmethod
    def get_section_labels() -> dict[ReportSection, str]:
        """Return human-readable labels for every report section."""
        return {
            ReportSection.TITLE: "Title",
            ReportSection.EXECUTIVE_SUMMARY: "Executive Summary",
            ReportSection.CAPTURE_INFO: "Capture Information",
            ReportSection.TRAFFIC_STATS: "Traffic Statistics",
            ReportSection.PROTOCOL_DISTRIBUTION: "Protocol Distribution",
            ReportSection.HOST_OVERVIEW: "Host Overview",
            ReportSection.CONNECTION_OVERVIEW: "Connection Overview",
            ReportSection.TOP_TALKERS: "Top Talkers",
            ReportSection.BANDWIDTH_SUMMARY: "Bandwidth Summary",
            ReportSection.TIMELINE: "Timeline",
            ReportSection.ALERT_SUMMARY: "Alert Summary",
            ReportSection.EVIDENCE: "Evidence",
            ReportSection.BOOKMARKS: "Bookmarks",
            ReportSection.NOTES: "Notes",
            ReportSection.RECOMMENDATIONS: "Recommendations",
            ReportSection.APPENDIX: "Appendix",
        }
