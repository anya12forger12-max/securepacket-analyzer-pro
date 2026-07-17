"""Data models for reporting, case management, evidence, bookmarks, and notes.

All models support full JSON serialization via ``to_dict`` / ``from_dict``
and follow the same conventions as :mod:`src.analysis.models`.
"""

from __future__ import annotations

import hashlib
import json
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any

from src.analysis.models import _now_iso


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ReportSeverity(Enum):
    """Severity level assigned to generated reports."""

    LOW = auto()
    MEDIUM = auto()
    HIGH = auto()
    CRITICAL = auto()


class CaseStatus(Enum):
    """Lifecycle states for an investigation case."""

    OPEN = auto()
    IN_PROGRESS = auto()
    PENDING_REVIEW = auto()
    RESOLVED = auto()
    ARCHIVED = auto()


class CasePriority(Enum):
    """Priority level for an investigation case."""

    LOW = auto()
    MEDIUM = auto()
    HIGH = auto()
    CRITICAL = auto()


class EvidenceImportance(Enum):
    """Relative importance of a piece of evidence."""

    LOW = auto()
    MEDIUM = auto()
    HIGH = auto()
    CRITICAL = auto()


class ExportFormat(Enum):
    """Supported export / report output formats."""

    PDF = auto()
    HTML = auto()
    MARKDOWN = auto()
    CSV = auto()
    JSON = auto()
    TXT = auto()
    XML = auto()
    PCAP_METADATA = auto()


class ReportSection(Enum):
    """Identifiable sections that can appear in a report."""

    TITLE = auto()
    EXECUTIVE_SUMMARY = auto()
    CAPTURE_INFO = auto()
    TRAFFIC_STATS = auto()
    PROTOCOL_DISTRIBUTION = auto()
    HOST_OVERVIEW = auto()
    CONNECTION_OVERVIEW = auto()
    TOP_TALKERS = auto()
    BANDWIDTH_SUMMARY = auto()
    TIMELINE = auto()
    ALERT_SUMMARY = auto()
    EVIDENCE = auto()
    BOOKMARKS = auto()
    NOTES = auto()
    RECOMMENDATIONS = auto()
    APPENDIX = auto()


# ---------------------------------------------------------------------------
# ReportTemplate
# ---------------------------------------------------------------------------

@dataclass
class ReportTemplate:
    """A reusable template that defines the structure of a generated report.

    Templates specify which :class:`ReportSection` instances are included
    and carry metadata about authorship and versioning.
    """

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str = ""
    description: str = ""
    sections: list[ReportSection] = field(default_factory=list)
    created_at: str = field(default_factory=_now_iso)
    modified_at: str = field(default_factory=_now_iso)
    is_builtin: bool = False
    author: str = "System"
    version: str = "1.0"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "sections": [s.name for s in self.sections],
            "created_at": self.created_at,
            "modified_at": self.modified_at,
            "is_builtin": self.is_builtin,
            "author": self.author,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReportTemplate:
        """Reconstruct a ``ReportTemplate`` from a serialized dict."""
        tmpl = cls(
            id=data.get("id", uuid.uuid4().hex[:12]),
            name=data.get("name", ""),
            description=data.get("description", ""),
        )
        tmpl.sections = [ReportSection[s] for s in data.get("sections", [])]
        tmpl.created_at = data.get("created_at", "")
        tmpl.modified_at = data.get("modified_at", "")
        tmpl.is_builtin = data.get("is_builtin", False)
        tmpl.author = data.get("author", "System")
        tmpl.version = data.get("version", "1.0")
        return tmpl


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

@dataclass
class Report:
    """A generated analysis report linking templates to captured data.

    Reports progress through a lifecycle of *draft* -> *generated* ->
    *exported*.  The ``content`` dict holds the fully-rendered report
    data produced by the reporting engine.
    """

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    title: str = ""
    description: str = ""
    template_id: str = ""
    template_name: str = ""
    created_at: str = field(default_factory=_now_iso)
    modified_at: str = field(default_factory=_now_iso)
    generated_at: str = ""
    status: str = "draft"
    sections_enabled: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    workspace: str = ""
    content: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    is_starred: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dictionary."""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "template_id": self.template_id,
            "template_name": self.template_name,
            "created_at": self.created_at,
            "modified_at": self.modified_at,
            "generated_at": self.generated_at,
            "status": self.status,
            "sections_enabled": self.sections_enabled,
            "metadata": self.metadata,
            "workspace": self.workspace,
            "content": self.content,
            "tags": self.tags,
            "is_starred": self.is_starred,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Report:
        """Reconstruct a ``Report`` from a serialized dict."""
        rpt = cls(
            id=data.get("id", uuid.uuid4().hex[:12]),
            title=data.get("title", ""),
            description=data.get("description", ""),
            template_id=data.get("template_id", ""),
            template_name=data.get("template_name", ""),
            created_at=data.get("created_at", ""),
            modified_at=data.get("modified_at", ""),
        )
        rpt.generated_at = data.get("generated_at", "")
        rpt.status = data.get("status", "draft")
        rpt.sections_enabled = data.get("sections_enabled", [])
        rpt.metadata = data.get("metadata", {})
        rpt.workspace = data.get("workspace", "")
        rpt.content = data.get("content", {})
        rpt.tags = data.get("tags", [])
        rpt.is_starred = data.get("is_starred", False)
        return rpt


# ---------------------------------------------------------------------------
# Case
# ---------------------------------------------------------------------------

@dataclass
class Case:
    """An investigation case that groups captures, hosts, alerts, evidence, and more.

    All mutable collection helpers are thread-safe via the internal lock so
    that multiple analysis threads may contribute findings concurrently.
    """

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    title: str = ""
    description: str = ""
    status: CaseStatus = CaseStatus.OPEN
    priority: CasePriority = CasePriority.MEDIUM
    created_at: str = field(default_factory=_now_iso)
    modified_at: str = field(default_factory=_now_iso)
    created_by: str = "Analyst"
    workspace: str = ""
    tags: list[str] = field(default_factory=list)
    associated_captures: list[str] = field(default_factory=list)
    associated_hosts: list[str] = field(default_factory=list)
    associated_connections: list[str] = field(default_factory=list)
    associated_alerts: list[str] = field(default_factory=list)
    bookmark_ids: list[str] = field(default_factory=list)
    note_ids: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    timeline_event_ids: list[str] = field(default_factory=list)
    report_ids: list[str] = field(default_factory=list)
    custom_statuses: dict[str, str] = field(default_factory=dict)
    notes: str = ""
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def update_status(self, new_status: CaseStatus) -> None:
        """Thread-safe status transition."""
        with self._lock:
            self.status = new_status
            self.modified_at = _now_iso()

    def add_tag(self, tag: str) -> None:
        """Add a tag to the case if not already present."""
        if tag not in self.tags:
            self.tags.append(tag)
            self.modified_at = _now_iso()

    def remove_tag(self, tag: str) -> None:
        """Remove a tag from the case."""
        if tag in self.tags:
            self.tags.remove(tag)
            self.modified_at = _now_iso()

    def add_host(self, host_ip: str) -> None:
        """Associate a host IP with this case."""
        if host_ip not in self.associated_hosts:
            self.associated_hosts.append(host_ip)
            self.modified_at = _now_iso()

    def add_alert(self, alert_id: str) -> None:
        """Associate an alert with this case."""
        if alert_id not in self.associated_alerts:
            self.associated_alerts.append(alert_id)
            self.modified_at = _now_iso()

    def add_evidence(self, evidence_id: str) -> None:
        """Link an evidence item to this case."""
        if evidence_id not in self.evidence_ids:
            self.evidence_ids.append(evidence_id)
            self.modified_at = _now_iso()

    def add_note(self, note_id: str) -> None:
        """Link a note to this case."""
        if note_id not in self.note_ids:
            self.note_ids.append(note_id)
            self.modified_at = _now_iso()

    def add_bookmark(self, bookmark_id: str) -> None:
        """Link a bookmark to this case."""
        if bookmark_id not in self.bookmark_ids:
            self.bookmark_ids.append(bookmark_id)
            self.modified_at = _now_iso()

    def add_report(self, report_id: str) -> None:
        """Link a report to this case."""
        if report_id not in self.report_ids:
            self.report_ids.append(report_id)
            self.modified_at = _now_iso()

    def link_capture(self, capture_id: str) -> None:
        """Associate a capture file with this case."""
        if capture_id not in self.associated_captures:
            self.associated_captures.append(capture_id)
            self.modified_at = _now_iso()

    def is_active(self) -> bool:
        """Return *True* when the case is neither RESOLVED nor ARCHIVED."""
        return self.status not in (CaseStatus.RESOLVED, CaseStatus.ARCHIVED)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dictionary."""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "status": self.status.name,
            "priority": self.priority.name,
            "created_at": self.created_at,
            "modified_at": self.modified_at,
            "created_by": self.created_by,
            "workspace": self.workspace,
            "tags": self.tags,
            "associated_captures": self.associated_captures,
            "associated_hosts": self.associated_hosts,
            "associated_connections": self.associated_connections,
            "associated_alerts": self.associated_alerts,
            "bookmark_ids": self.bookmark_ids,
            "note_ids": self.note_ids,
            "evidence_ids": self.evidence_ids,
            "timeline_event_ids": self.timeline_event_ids,
            "report_ids": self.report_ids,
            "custom_statuses": self.custom_statuses,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Case:
        """Reconstruct a ``Case`` from a serialized dict."""
        case = cls(
            id=data.get("id", uuid.uuid4().hex[:12]),
            title=data.get("title", ""),
            description=data.get("description", ""),
        )
        case.status = CaseStatus[data.get("status", "OPEN")]
        case.priority = CasePriority[data.get("priority", "MEDIUM")]
        case.created_at = data.get("created_at", "")
        case.modified_at = data.get("modified_at", "")
        case.created_by = data.get("created_by", "Analyst")
        case.workspace = data.get("workspace", "")
        case.tags = data.get("tags", [])
        case.associated_captures = data.get("associated_captures", [])
        case.associated_hosts = data.get("associated_hosts", [])
        case.associated_connections = data.get("associated_connections", [])
        case.associated_alerts = data.get("associated_alerts", [])
        case.bookmark_ids = data.get("bookmark_ids", [])
        case.note_ids = data.get("note_ids", [])
        case.evidence_ids = data.get("evidence_ids", [])
        case.timeline_event_ids = data.get("timeline_event_ids", [])
        case.report_ids = data.get("report_ids", [])
        case.custom_statuses = data.get("custom_statuses", {})
        case.notes = data.get("notes", "")
        return case


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------

@dataclass
class Evidence:
    """A discrete piece of evidence linked to one or more investigations.

    Evidence may reference packets, hosts, connections, or alerts and
    carries an optional checksum for integrity verification.
    """

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    title: str = ""
    description: str = ""
    importance: EvidenceImportance = EvidenceImportance.MEDIUM
    category: str = "general"
    case_id: str = ""
    tags: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=_now_iso)
    source_type: str = "manual"
    source_ids: list[str] = field(default_factory=list)
    packet_references: list[int] = field(default_factory=list)
    host_references: list[str] = field(default_factory=list)
    connection_references: list[str] = field(default_factory=list)
    alert_references: list[str] = field(default_factory=list)
    bookmark_references: list[str] = field(default_factory=list)
    notes: str = ""
    checksum: str = ""
    checksum_algorithm: str = "sha256"
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_now_iso)
    modified_at: str = field(default_factory=_now_iso)

    def add_packet_ref(self, packet_number: int) -> None:
        """Add a packet number reference if not already present."""
        if packet_number not in self.packet_references:
            self.packet_references.append(packet_number)
            self.modified_at = _now_iso()

    def add_host_ref(self, ip: str) -> None:
        """Add a host IP reference if not already present."""
        if ip not in self.host_references:
            self.host_references.append(ip)
            self.modified_at = _now_iso()

    def add_connection_ref(self, conn_id: str) -> None:
        """Add a connection ID reference if not already present."""
        if conn_id not in self.connection_references:
            self.connection_references.append(conn_id)
            self.modified_at = _now_iso()

    def add_alert_ref(self, alert_id: str) -> None:
        """Add an alert ID reference if not already present."""
        if alert_id not in self.alert_references:
            self.alert_references.append(alert_id)
            self.modified_at = _now_iso()

    def compute_checksum(self, data: bytes) -> str:
        """Compute and store a SHA-256 checksum for *data*.

        Returns the hex digest and stores it in :attr:`checksum`.
        """
        digest = hashlib.sha256(data).hexdigest()
        self.checksum = digest
        self.checksum_algorithm = "sha256"
        self.modified_at = _now_iso()
        return digest

    def verify_checksum(self, data: bytes) -> bool:
        """Return *True* if the SHA-256 of *data* matches :attr:`checksum`."""
        if not self.checksum:
            return False
        return hashlib.sha256(data).hexdigest() == self.checksum

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dictionary."""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "importance": self.importance.name,
            "category": self.category,
            "case_id": self.case_id,
            "tags": self.tags,
            "timestamp": self.timestamp,
            "source_type": self.source_type,
            "source_ids": self.source_ids,
            "packet_references": self.packet_references,
            "host_references": self.host_references,
            "connection_references": self.connection_references,
            "alert_references": self.alert_references,
            "bookmark_references": self.bookmark_references,
            "notes": self.notes,
            "checksum": self.checksum,
            "checksum_algorithm": self.checksum_algorithm,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "modified_at": self.modified_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Evidence:
        """Reconstruct an ``Evidence`` from a serialized dict."""
        ev = cls(
            id=data.get("id", uuid.uuid4().hex[:12]),
            title=data.get("title", ""),
            description=data.get("description", ""),
        )
        ev.importance = EvidenceImportance[data.get("importance", "MEDIUM")]
        ev.category = data.get("category", "general")
        ev.case_id = data.get("case_id", "")
        ev.tags = data.get("tags", [])
        ev.timestamp = data.get("timestamp", "")
        ev.source_type = data.get("source_type", "manual")
        ev.source_ids = data.get("source_ids", [])
        ev.packet_references = data.get("packet_references", [])
        ev.host_references = data.get("host_references", [])
        ev.connection_references = data.get("connection_references", [])
        ev.alert_references = data.get("alert_references", [])
        ev.bookmark_references = data.get("bookmark_references", [])
        ev.notes = data.get("notes", "")
        ev.checksum = data.get("checksum", "")
        ev.checksum_algorithm = data.get("checksum_algorithm", "sha256")
        ev.metadata = data.get("metadata", {})
        ev.created_at = data.get("created_at", "")
        ev.modified_at = data.get("modified_at", "")
        return ev


# ---------------------------------------------------------------------------
# AnalystNote
# ---------------------------------------------------------------------------

@dataclass
class AnalystNote:
    """A markdown note authored by an analyst during an investigation.

    Supports revision tracking via :attr:`revision_count` which is
    incremented each time :meth:`update_content` is called.
    """

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    title: str = ""
    content: str = ""
    tags: list[str] = field(default_factory=list)
    case_id: str = ""
    packet_references: list[int] = field(default_factory=list)
    host_references: list[str] = field(default_factory=list)
    connection_references: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=_now_iso)
    modified_at: str = field(default_factory=_now_iso)
    revision_count: int = 0
    is_pinned: bool = False

    def update_content(self, new_content: str) -> None:
        """Replace the note content and increment the revision counter."""
        self.content = new_content
        self.revision_count += 1
        self.modified_at = _now_iso()

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dictionary."""
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "tags": self.tags,
            "case_id": self.case_id,
            "packet_references": self.packet_references,
            "host_references": self.host_references,
            "connection_references": self.connection_references,
            "created_at": self.created_at,
            "modified_at": self.modified_at,
            "revision_count": self.revision_count,
            "is_pinned": self.is_pinned,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AnalystNote:
        """Reconstruct an ``AnalystNote`` from a serialized dict."""
        note = cls(
            id=data.get("id", uuid.uuid4().hex[:12]),
            title=data.get("title", ""),
            content=data.get("content", ""),
        )
        note.tags = data.get("tags", [])
        note.case_id = data.get("case_id", "")
        note.packet_references = data.get("packet_references", [])
        note.host_references = data.get("host_references", [])
        note.connection_references = data.get("connection_references", [])
        note.created_at = data.get("created_at", "")
        note.modified_at = data.get("modified_at", "")
        note.revision_count = data.get("revision_count", 0)
        note.is_pinned = data.get("is_pinned", False)
        return note


# ---------------------------------------------------------------------------
# BookmarkFolder
# ---------------------------------------------------------------------------

@dataclass
class BookmarkFolder:
    """A folder for organising bookmarks with optional nesting via ``parent_id``."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str = ""
    parent_id: str = ""
    created_at: str = field(default_factory=_now_iso)
    color: str = "#0078D4"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "parent_id": self.parent_id,
            "created_at": self.created_at,
            "color": self.color,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BookmarkFolder:
        """Reconstruct a ``BookmarkFolder`` from a serialized dict."""
        folder = cls(
            id=data.get("id", uuid.uuid4().hex[:12]),
            name=data.get("name", ""),
        )
        folder.parent_id = data.get("parent_id", "")
        folder.created_at = data.get("created_at", "")
        folder.color = data.get("color", "#0078D4")
        return folder


# ---------------------------------------------------------------------------
# Bookmark
# ---------------------------------------------------------------------------

@dataclass
class Bookmark:
    """A user-created bookmark pointing at a packet, host, connection, or alert.

    Bookmarks can be organised into :class:`BookmarkFolder` instances and
    carry an optional colour for visual distinction in the UI.
    """

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    title: str = ""
    description: str = ""
    folder_id: str = ""
    tags: list[str] = field(default_factory=list)
    color: str = "#0078D4"
    category: str = "general"
    reference_type: str = ""
    reference_id: str = ""
    notes: str = ""
    created_at: str = field(default_factory=_now_iso)
    modified_at: str = field(default_factory=_now_iso)
    is_pinned: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dictionary."""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "folder_id": self.folder_id,
            "tags": self.tags,
            "color": self.color,
            "category": self.category,
            "reference_type": self.reference_type,
            "reference_id": self.reference_id,
            "notes": self.notes,
            "created_at": self.created_at,
            "modified_at": self.modified_at,
            "is_pinned": self.is_pinned,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Bookmark:
        """Reconstruct a ``Bookmark`` from a serialized dict."""
        bm = cls(
            id=data.get("id", uuid.uuid4().hex[:12]),
            title=data.get("title", ""),
            description=data.get("description", ""),
        )
        bm.folder_id = data.get("folder_id", "")
        bm.tags = data.get("tags", [])
        bm.color = data.get("color", "#0078D4")
        bm.category = data.get("category", "general")
        bm.reference_type = data.get("reference_type", "")
        bm.reference_id = data.get("reference_id", "")
        bm.notes = data.get("notes", "")
        bm.created_at = data.get("created_at", "")
        bm.modified_at = data.get("modified_at", "")
        bm.is_pinned = data.get("is_pinned", False)
        return bm


# ---------------------------------------------------------------------------
# InvestigationEvent
# ---------------------------------------------------------------------------

@dataclass
class InvestigationEvent:
    """A single chronological event on the investigation timeline.

    Events are emitted by various engine components (capture, analysis,
    alerting) and rendered on the unified timeline view.
    """

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: str = field(default_factory=_now_iso)
    event_type: str = "custom"
    title: str = ""
    description: str = ""
    case_id: str = ""
    source: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dictionary."""
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "title": self.title,
            "description": self.description,
            "case_id": self.case_id,
            "source": self.source,
            "metadata": self.metadata,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InvestigationEvent:
        """Reconstruct an ``InvestigationEvent`` from a serialized dict."""
        evt = cls(
            id=data.get("id", uuid.uuid4().hex[:12]),
            timestamp=data.get("timestamp", ""),
            event_type=data.get("event_type", "custom"),
            title=data.get("title", ""),
            description=data.get("description", ""),
        )
        evt.case_id = data.get("case_id", "")
        evt.source = data.get("source", "")
        evt.metadata = data.get("metadata", {})
        evt.tags = data.get("tags", [])
        return evt


# ---------------------------------------------------------------------------
# ImportExportData
# ---------------------------------------------------------------------------

@dataclass
class ImportExportData:
    """Envelope for importing and exporting bundles of analysis data.

    The ``data`` dict carries the actual payload keyed by entity type.
    An optional SHA-256 ``checksum`` over the JSON-serialized payload
    provides tamper detection.
    """

    format_version: str = "1.0"
    export_type: str = "all"
    exported_at: str = field(default_factory=_now_iso)
    source_workspace: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    checksum: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dictionary."""
        return {
            "format_version": self.format_version,
            "export_type": self.export_type,
            "exported_at": self.exported_at,
            "source_workspace": self.source_workspace,
            "data": self.data,
            "checksum": self.checksum,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ImportExportData:
        """Reconstruct an ``ImportExportData`` from a serialized dict."""
        obj = cls(
            format_version=data.get("format_version", "1.0"),
            export_type=data.get("export_type", "all"),
        )
        obj.exported_at = data.get("exported_at", "")
        obj.source_workspace = data.get("source_workspace", "")
        obj.data = data.get("data", {})
        obj.checksum = data.get("checksum", "")
        obj.metadata = data.get("metadata", {})
        return obj

    def compute_checksum(self) -> str:
        """Compute a SHA-256 checksum over the JSON-serialized ``data`` dict.

        Stores the result in :attr:`checksum` and returns the hex digest.
        """
        payload = json.dumps(self.data, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        self.checksum = digest
        return digest

    def verify_checksum(self) -> bool:
        """Return *True* if the current ``data`` matches the stored checksum."""
        if not self.checksum:
            return False
        payload = json.dumps(self.data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest() == self.checksum
