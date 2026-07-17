"""Multi-format report exporter with formatting and portability.

Exports analysis reports to CSV, JSON, HTML, Markdown, plain text,
XML, and PCAP-metadata summaries. Each format preserves full report
data while adapting layout for the target medium.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.analysis.reporting_models import ExportFormat, Report
from src.services.event_bus import EventBus, Events
from src.utils.paths import AppPaths

logger = logging.getLogger(__name__)


class ReportExporter:
    """Export analysis reports to multiple file formats.

    Supports CSV, JSON, HTML, Markdown, plain text, XML, and
    PCAP-metadata-only summaries. Emits events via the central
    :class:`EventBus` on export completion and failure.

    Usage::

        exporter = ReportExporter()
        path = exporter.export(report, ExportFormat.HTML)
    """

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(self, export_dir: Path | None = None) -> None:
        """Initialise the exporter.

        Parameters
        ----------
        export_dir:
            Directory for generated files.  When *None*, defaults to
            ``AppPaths.exports_dir() / "reports"``.
        """
        if export_dir is None:
            export_dir = AppPaths.exports_dir() / "reports"
        self._export_dir: Path = export_dir
        self._export_dir.mkdir(parents=True, exist_ok=True)
        self._event_bus: EventBus = EventBus.instance()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def export(
        self,
        report: Report,
        format: ExportFormat,
        output_path: Path | None = None,
        password: str | None = None,
    ) -> Path:
        """Export a report to the specified format.

        Parameters
        ----------
        report:
            The report to export.
        format:
            Target file format.
        output_path:
            Exact file path.  When *None*, a filename is generated inside
            the export directory.
        password:
            Optional encryption password (reserved for future use).

        Returns
        -------
        Path
            Absolute path to the exported file.

        Raises
        ------
        ValueError:
            If *format* is not a recognised :class:`ExportFormat`.
        OSError:
            If the file cannot be written.
        """
        self._event_bus.emit(Events.EXPORT_STARTED, {
            "report_id": report.id,
            "format": format.value,
        })

        if output_path is None:
            output_path = self._export_dir / self._generate_filename(report, format)
        else:
            output_path.parent.mkdir(parents=True, exist_ok=True)

        dispatch: dict[ExportFormat, Any] = {
            ExportFormat.CSV: self.export_csv,
            ExportFormat.JSON: self.export_json,
            ExportFormat.HTML: self.export_html,
            ExportFormat.MARKDOWN: self.export_markdown,
            ExportFormat.TEXT: self.export_txt,
            ExportFormat.XML: self.export_xml,
            ExportFormat.PCAP_METADATA: self.export_pcap_metadata,
        }

        handler = dispatch.get(format)
        if handler is None:
            msg = f"Unsupported export format: {format!r}"
            logger.error(msg)
            self._event_bus.emit(Events.EXPORT_FAILED, {
                "report_id": report.id,
                "format": format.value,
                "error": msg,
            })
            raise ValueError(msg)

        try:
            result = handler(report, output_path)
            logger.info(
                "Exported report %s to %s (%s)", report.id, result, format.value,
            )
            self._event_bus.emit(Events.EXPORT_COMPLETED, {
                "report_id": report.id,
                "format": format.value,
                "path": str(result),
            })
            return result
        except Exception:
            logger.exception(
                "Failed to export report %s to %s", report.id, format.value,
            )
            self._event_bus.emit(Events.EXPORT_FAILED, {
                "report_id": report.id,
                "format": format.value,
            })
            raise

    def get_export_directory(self) -> Path:
        """Return the current export directory."""
        return self._export_dir

    def list_exports(self) -> list[Path]:
        """Return all files currently in the export directory."""
        return sorted(p for p in self._export_dir.iterdir() if p.is_file())

    def clean_exports(self, older_than_days: int = 30) -> int:
        """Delete exports older than *older_than_days* days.

        Parameters
        ----------
        older_than_days:
            Files with a modification time older than this many days are
            removed.

        Returns
        -------
        int
            Number of files deleted.
        """
        cutoff = datetime.now(timezone.utc).timestamp() - (older_than_days * 86400)
        removed = 0
        for path in self._export_dir.iterdir():
            if not path.is_file():
                continue
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink()
                    removed += 1
                    logger.debug("Removed stale export: %s", path)
            except OSError:
                logger.warning("Could not remove export: %s", path)
        return removed

    # ------------------------------------------------------------------
    # Format handlers
    # ------------------------------------------------------------------

    def export_csv(self, report: Report, path: Path) -> Path:
        """Export report content as CSV.

        Each section is flattened to key-value rows.  The title section
        appears first, followed by every enabled section's data.
        """
        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator="\n")
        writer.writerow(["Section", "Key", "Value"])

        writer.writerow(["Report Title", "title", report.title])
        writer.writerow(["Report Title", "description", report.description])
        writer.writerow(["Report Title", "template", report.template_name])
        writer.writerow(["Report Title", "status", report.status])
        writer.writerow(["Report Title", "created_at", report.created_at])
        writer.writerow(["Report Title", "generated_at", report.generated_at])
        if report.tags:
            writer.writerow(["Report Title", "tags", ", ".join(report.tags)])
        for meta_key, meta_val in report.metadata.items():
            writer.writerow(["Report Metadata", meta_key, str(meta_val)])

        for section_name in report.sections_enabled:
            section_data = report.content.get(section_name)
            if section_data is None:
                continue
            if isinstance(section_data, dict):
                for flat_key, flat_val in self._flatten_section_data(section_data):
                    writer.writerow([section_name, flat_key, flat_val])
            elif isinstance(section_data, list):
                for idx, item in enumerate(section_data):
                    if isinstance(item, dict):
                        for flat_key, flat_val in self._flatten_section_data(item):
                            writer.writerow([section_name, f"{idx}.{flat_key}", flat_val])
                    else:
                        writer.writerow([section_name, str(idx), str(item)])
            else:
                writer.writerow([section_name, "value", str(section_data)])

        path.write_text(buf.getvalue(), encoding="utf-8")
        return path

    def export_json(self, report: Report, path: Path) -> Path:
        """Export the full report as formatted JSON."""
        data: dict[str, Any] = {
            "id": report.id,
            "title": report.title,
            "description": report.description,
            "template_name": report.template_name,
            "content": report.content,
            "sections_enabled": report.sections_enabled,
            "metadata": report.metadata,
            "tags": report.tags,
            "created_at": report.created_at,
            "generated_at": report.generated_at,
            "status": report.status,
        }
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )
        return path

    def export_html(self, report: Report, path: Path) -> Path:
        """Generate a professional, styled HTML5 document."""
        css = self._generate_html_css()
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        escaped_title = self._escape_xml(report.title)

        sections_html_parts: list[str] = []

        for section_name in report.sections_enabled:
            section_data = report.content.get(section_name)
            if section_data is None:
                continue
            section_label = self._escape_xml(section_name.replace("_", " ").title())
            sections_html_parts.append(
                self._render_html_section(section_label, section_data)
            )

        sections_body = "\n".join(sections_html_parts)

        tags_html = ""
        if report.tags:
            tag_badges = " ".join(
                f'<span class="tag" role="img" aria-label="tag: {self._escape_xml(t)}">'
                f"{self._escape_xml(t)}</span>"
                for t in report.tags
            )
            tags_html = f'<div class="tags" aria-label="Tags">{tag_badges}</div>'

        meta_items: list[str] = []
        if report.created_at:
            meta_items.append(
                f'<div class="meta-item">'
                f'<span class="meta-label">Created:</span> '
                f"{self._escape_xml(report.created_at)}</div>"
            )
        if report.generated_at:
            meta_items.append(
                f'<div class="meta-item">'
                f'<span class="meta-label">Generated:</span> '
                f"{self._escape_xml(report.generated_at)}</div>"
            )
        if report.template_name:
            meta_items.append(
                f'<div class="meta-item">'
                f'<span class="meta-label">Template:</span> '
                f"{self._escape_xml(report.template_name)}</div>"
            )
        if report.status:
            meta_items.append(
                f'<div class="meta-item">'
                f'<span class="meta-label">Status:</span> '
                f'<span class="status-badge">{self._escape_xml(report.status)}</span>'
                f"</div>"
            )
        for key, val in report.metadata.items():
            meta_items.append(
                f'<div class="meta-item">'
                f'<span class="meta-label">{self._escape_xml(key)}:</span> '
                f"{self._escape_xml(str(val))}</div>"
            )

        meta_html = "\n".join(meta_items)

        html = (
            "<!DOCTYPE html>\n"
            '<html lang="en">\n'
            "<head>\n"
            '  <meta charset="UTF-8">\n'
            '  <meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
            f'  <title>{escaped_title}</title>\n'
            "  <style>\n"
            f"{css}\n"
            "  </style>\n"
            "</head>\n"
            "<body>\n"
            '  <header role="banner">\n'
            '    <h1 class="report-title">'
            f"{escaped_title}</h1>\n"
        )
        if report.description:
            html += (
                f'    <p class="report-description">'
                f"{self._escape_xml(report.description)}</p>\n"
            )
        html += (
            f'    <div class="metadata" role="contentinfo" '
            f'aria-label="Report metadata">\n'
            f"{meta_html}\n"
            "    </div>\n"
            f"{tags_html}\n"
            "  </header>\n"
            "\n"
            '  <main role="main" aria-label="Report content">\n'
            f"{sections_body}\n"
            "  </main>\n"
            "\n"
            '  <footer role="contentinfo">\n'
            f'    <p>Generated by <strong>SecurePacket Analyzer Pro</strong> '
            f"on {self._escape_xml(now_str)}</p>\n"
            f'    <p class="report-id">Report ID: '
            f"{self._escape_xml(report.id)}</p>\n"
            "  </footer>\n"
            "</body>\n"
            "</html>\n"
        )

        path.write_text(html, encoding="utf-8")
        return path

    def export_markdown(self, report: Report, path: Path) -> Path:
        """Generate Markdown with proper headings, tables, and lists."""
        lines: list[str] = []
        lines.append(f"# {report.title}")
        lines.append("")

        if report.description:
            lines.append(f"> {report.description}")
            lines.append("")

        lines.append("## Metadata")
        lines.append("")
        lines.append("| Field | Value |")
        lines.append("|-------|-------|")
        lines.append(f"| **Report ID** | `{report.id}` |")
        if report.template_name:
            lines.append(f"| **Template** | {report.template_name} |")
        if report.created_at:
            lines.append(f"| **Created** | {report.created_at} |")
        if report.generated_at:
            lines.append(f"| **Generated** | {report.generated_at} |")
        if report.status:
            lines.append(f"| **Status** | {report.status} |")
        for key, val in report.metadata.items():
            lines.append(f"| **{key}** | {val} |")
        lines.append("")

        if report.tags:
            lines.append("## Tags")
            lines.append("")
            lines.append(" ".join(f"`{t}`" for t in report.tags))
            lines.append("")

        for section_name in report.sections_enabled:
            section_data = report.content.get(section_name)
            if section_data is None:
                continue
            section_label = section_name.replace("_", " ").title()
            lines.append(f"## {section_label}")
            lines.append("")
            lines.append(self._render_markdown_section_data(section_data, indent=0))

        lines.append("---")
        lines.append(
            f"*Generated by SecurePacket Analyzer Pro*"
        )
        lines.append("")

        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    def export_txt(self, report: Report, path: Path) -> Path:
        """Plain text export with clear section separation."""
        width = 72
        lines: list[str] = []
        lines.append("=" * width)
        lines.append(f"  {report.title}")
        lines.append("=" * width)
        lines.append("")

        if report.description:
            lines.append(report.description)
            lines.append("")

        lines.append("-" * width)
        lines.append("  REPORT INFORMATION")
        lines.append("-" * width)
        lines.append(f"  Report ID:       {report.id}")
        if report.template_name:
            lines.append(f"  Template:        {report.template_name}")
        if report.created_at:
            lines.append(f"  Created:         {report.created_at}")
        if report.generated_at:
            lines.append(f"  Generated:       {report.generated_at}")
        if report.status:
            lines.append(f"  Status:          {report.status}")
        if report.tags:
            lines.append(f"  Tags:            {', '.join(report.tags)}")
        if report.metadata:
            lines.append("")
            lines.append("  Metadata:")
            for key, val in report.metadata.items():
                lines.append(f"    {key}: {val}")
        lines.append("")

        for section_name in report.sections_enabled:
            section_data = report.content.get(section_name)
            if section_data is None:
                continue
            section_label = section_name.replace("_", " ").title()
            lines.append("-" * width)
            lines.append(f"  {section_label.upper()}")
            lines.append("-" * width)
            lines.append("")
            lines.extend(self._render_txt_section(section_data, indent=2))
            lines.append("")

        lines.append("=" * width)
        lines.append(f"  End of Report — {report.id}")
        lines.append("=" * width)
        lines.append("")

        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    def export_xml(self, report: Report, path: Path) -> Path:
        """Well-formed XML with proper hierarchy."""
        root = ET.Element("report")
        root.set("id", report.id)

        title_el = ET.SubElement(root, "title")
        title_el.text = report.title

        desc_el = ET.SubElement(root, "description")
        desc_el.text = report.description

        template_el = ET.SubElement(root, "template")
        template_el.text = report.template_name

        status_el = ET.SubElement(root, "status")
        status_el.text = report.status

        created_el = ET.SubElement(root, "created_at")
        created_el.text = report.created_at

        generated_el = ET.SubElement(root, "generated_at")
        generated_el.text = report.generated_at

        if report.tags:
            tags_el = ET.SubElement(root, "tags")
            for tag_text in report.tags:
                tag_el = ET.SubElement(tags_el, "tag")
                tag_el.text = tag_text

        if report.metadata:
            meta_el = ET.SubElement(root, "metadata")
            for key, val in report.metadata.items():
                item_el = ET.SubElement(meta_el, "item")
                item_el.set("key", key)
                item_el.text = str(val)

        content_el = ET.SubElement(root, "content")
        for section_name in report.sections_enabled:
            section_data = report.content.get(section_name)
            if section_data is None:
                continue
            section_el = ET.SubElement(content_el, "section")
            section_el.set("name", section_name)
            self._populate_xml_section(section_el, section_data)

        ET.indent(root, space="  ")
        xml_bytes = ET.tostring(root, encoding="unicode", xml_declaration=False)
        path.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_bytes + "\n",
            encoding="utf-8",
        )
        return path

    def export_pcap_metadata(self, report: Report, path: Path) -> Path:
        """Metadata-only summary as JSON with PCAP-specific fields."""
        content = report.content
        metadata_section = content.get("metadata", {})
        if isinstance(metadata_section, dict):
            summary: dict[str, Any] = dict(metadata_section)
        else:
            summary: dict[str, Any] = {}

        summary["report_id"] = report.id
        summary["report_title"] = report.title
        summary["report_status"] = report.status
        summary["export_timestamp"] = datetime.now(timezone.utc).isoformat()
        summary["template_used"] = report.template_name
        summary["tags"] = report.tags

        proto_section = content.get("protocols", {})
        if isinstance(proto_section, dict):
            summary["protocols"] = proto_section

        hosts_section = content.get("hosts", {})
        if isinstance(hosts_section, dict):
            summary["hosts_summary"] = hosts_section

        stats_section = content.get("statistics", {})
        if isinstance(stats_section, dict):
            summary["capture_statistics"] = stats_section

        connections_section = content.get("connections", {})
        if isinstance(connections_section, dict):
            summary["connections_summary"] = connections_section

        alerts_section = content.get("alerts", {})
        if isinstance(alerts_section, dict):
            summary["security_alerts"] = alerts_section

        path.write_text(
            json.dumps(summary, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )
        return path

    # ------------------------------------------------------------------
    # Filename generation
    # ------------------------------------------------------------------

    def _generate_filename(self, report: Report, format: ExportFormat) -> str:
        """Build a sanitised filename: title-timestamp.ext."""
        raw_title = re.sub(r"[^\w\s\-]", "", report.title)
        raw_title = re.sub(r"\s+", "_", raw_title.strip()).strip("_")
        if not raw_title:
            raw_title = "report"

        if len(raw_title) > 80:
            raw_title = raw_title[:80]

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

        ext_map: dict[ExportFormat, str] = {
            ExportFormat.CSV: ".csv",
            ExportFormat.JSON: ".json",
            ExportFormat.HTML: ".html",
            ExportFormat.MARKDOWN: ".md",
            ExportFormat.TEXT: ".txt",
            ExportFormat.XML: ".xml",
            ExportFormat.PCAP_METADATA: ".json",
        }
        extension = ext_map.get(format, ".bin")

        if format == ExportFormat.PCAP_METADATA:
            return f"{raw_title}_{timestamp}_pcap_metadata{extension}"
        return f"{raw_title}_{timestamp}{extension}"

    # ------------------------------------------------------------------
    # Flattening / formatting helpers
    # ------------------------------------------------------------------

    def _flatten_section_data(
        self, data: dict[str, Any], prefix: str = "",
    ) -> list[tuple[str, str]]:
        """Recursively flatten nested dicts to ``(dotted.key, value)`` pairs."""
        result: list[tuple[str, str]] = []
        for key, value in data.items():
            full_key = f"{prefix}{key}" if prefix == "" else f"{prefix}.{key}"
            if isinstance(value, dict):
                result.extend(self._flatten_section_data(value, prefix=full_key))
            elif isinstance(value, list):
                if not value:
                    result.append((full_key, "[]"))
                else:
                    result.append((full_key, self._format_list_value(value)))
            elif isinstance(value, bool):
                result.append((full_key, "Yes" if value else "No"))
            else:
                result.append((full_key, str(value)))
        return result

    @staticmethod
    def _format_list_value(items: list[Any]) -> str:
        """Render a list as a comma-separated string."""
        parts = [str(item) for item in items]
        joined = ", ".join(parts)
        if len(joined) > 200:
            return joined[:197] + "..."
        return joined

    @staticmethod
    def _format_bytes(num_bytes: int) -> str:
        """Human-readable byte count (KB, MB, GB, TB)."""
        if num_bytes < 0:
            return "-" + ReportExporter._format_bytes(-num_bytes)
        if num_bytes == 0:
            return "0 B"
        units = ["B", "KB", "MB", "GB", "TB"]
        value = float(num_bytes)
        for unit in units:
            if abs(value) < 1024.0:
                if unit == "B":
                    return f"{int(value)} {unit}"
                return f"{value:.2f} {unit}"
            value /= 1024.0
        return f"{value:.2f} PB"

    @staticmethod
    def _format_duration(seconds: float) -> str:
        """Human-readable duration from a float second count."""
        if seconds < 0:
            return "-" + ReportExporter._format_duration(-seconds)
        if seconds < 0.001:
            return f"{seconds * 1_000_000:.0f} us"
        if seconds < 1.0:
            return f"{seconds * 1_000:.1f} ms"
        if seconds < 60.0:
            return f"{seconds:.2f} s"
        minutes = int(seconds // 60)
        secs = seconds % 60
        if minutes < 60:
            return f"{minutes}m {secs:.1f}s"
        hours = minutes // 60
        mins = minutes % 60
        if hours < 24:
            return f"{hours}h {mins}m {secs:.0f}s"
        days = hours // 24
        hrs = hours % 24
        return f"{days}d {hrs}h {mins}m"

    @staticmethod
    def _format_rate(bits_per_second: float) -> str:
        """Human-readable bit rate (bps, Kbps, Mbps, Gbps)."""
        if bits_per_second < 0:
            return "-" + ReportExporter._format_rate(-bits_per_second)
        if bits_per_second == 0:
            return "0 bps"
        units = ["bps", "Kbps", "Mbps", "Gbps", "Tbps"]
        value = bits_per_second
        for unit in units:
            if abs(value) < 1000.0:
                return f"{value:.2f} {unit}"
            value /= 1000.0
        return f"{value:.2f} Pbps"

    @staticmethod
    def _escape_xml(text: str) -> str:
        """Escape special XML characters."""
        text = text.replace("&", "&amp;")
        text = text.replace("<", "&lt;")
        text = text.replace(">", "&gt;")
        text = text.replace('"', "&quot;")
        text = text.replace("'", "&apos;")
        return text

    # ------------------------------------------------------------------
    # HTML helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_html_css() -> str:
        """Return embedded CSS for HTML reports."""
        return (
            "/* -- Reset & Base ----------------------------------------- */\n"
            "*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }\n"
            "\n"
            ":root {\n"
            "  --accent: #0078D4;\n"
            "  --accent-light: #e6f0fa;\n"
            "  --accent-dark: #005a9e;\n"
            "  --bg: #ffffff;\n"
            "  --bg-secondary: #f8f9fa;\n"
            "  --bg-header: #f0f4f8;\n"
            "  --text: #1a1a2e;\n"
            "  --text-secondary: #4a4a6a;\n"
            "  --border: #dde1e6;\n"
            "  --border-focus: #0078D4;\n"
            "  --shadow: 0 1px 3px rgba(0, 0, 0, 0.08);\n"
            "  --shadow-lg: 0 4px 12px rgba(0, 0, 0, 0.1);\n"
            "  --radius: 6px;\n"
            "  --font-sans: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, "
            "'Helvetica Neue', Arial, sans-serif;\n"
            "  --font-mono: 'SF Mono', 'Cascadia Code', 'Consolas', 'Fira Code', "
            "monospace;\n"
            "}\n"
            "\n"
            "@media (prefers-color-scheme: dark) {\n"
            "  :root {\n"
            "    --bg: #1a1a2e;\n"
            "    --bg-secondary: #22223a;\n"
            "    --bg-header: #16163a;\n"
            "    --text: #e0e0f0;\n"
            "    --text-secondary: #a0a0c0;\n"
            "    --border: #3a3a5c;\n"
            "    --border-focus: #4da6ff;\n"
            "    --shadow: 0 1px 3px rgba(0, 0, 0, 0.3);\n"
            "    --shadow-lg: 0 4px 12px rgba(0, 0, 0, 0.4);\n"
            "    --accent: #4da6ff;\n"
            "    --accent-light: #1e2a3e;\n"
            "    --accent-dark: #79c0ff;\n"
            "  }\n"
            "}\n"
            "\n"
            "body {\n"
            "  font-family: var(--font-sans);\n"
            "  line-height: 1.6;\n"
            "  color: var(--text);\n"
            "  background: var(--bg);\n"
            "  max-width: 960px;\n"
            "  margin: 0 auto;\n"
            "  padding: 2rem 1.5rem;\n"
            "}\n"
            "\n"
            "/* -- Typography ------------------------------------------- */\n"
            "h1, h2, h3, h4, h5, h6 {\n"
            "  font-weight: 600;\n"
            "  line-height: 1.3;\n"
            "  color: var(--text);\n"
            "}\n"
            "\n"
            "h1 { font-size: 1.75rem; margin-bottom: 0.5rem; }\n"
            "h2 {\n"
            "  font-size: 1.35rem;\n"
            "  margin-top: 2rem;\n"
            "  margin-bottom: 0.75rem;\n"
            "  padding-bottom: 0.4rem;\n"
            "  border-bottom: 2px solid var(--accent);\n"
            "  color: var(--accent);\n"
            "}\n"
            "h3 { font-size: 1.1rem; margin-top: 1.25rem; margin-bottom: 0.5rem; }\n"
            "\n"
            "p { margin-bottom: 0.75rem; }\n"
            "\n"
            "/* -- Header ------------------------------------------------ */\n"
            "header {\n"
            "  background: var(--bg-header);\n"
            "  border: 1px solid var(--border);\n"
            "  border-radius: var(--radius);\n"
            "  padding: 1.5rem;\n"
            "  margin-bottom: 2rem;\n"
            "  box-shadow: var(--shadow);\n"
            "}\n"
            "\n"
            ".report-title {\n"
            "  color: var(--accent);\n"
            "  margin-bottom: 0.5rem;\n"
            "}\n"
            "\n"
            ".report-description {\n"
            "  color: var(--text-secondary);\n"
            "  font-style: italic;\n"
            "  margin-bottom: 1rem;\n"
            "}\n"
            "\n"
            ".metadata {\n"
            "  display: grid;\n"
            "  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));\n"
            "  gap: 0.5rem 1.5rem;\n"
            "}\n"
            "\n"
            ".meta-item {\n"
            "  font-size: 0.875rem;\n"
            "}\n"
            "\n"
            ".meta-label {\n"
            "  font-weight: 600;\n"
            "  color: var(--text-secondary);\n"
            "}\n"
            "\n"
            ".status-badge {\n"
            "  display: inline-block;\n"
            "  padding: 0.1em 0.5em;\n"
            "  background: var(--accent);\n"
            "  color: #fff;\n"
            "  border-radius: 3px;\n"
            "  font-size: 0.8rem;\n"
            "  font-weight: 600;\n"
            "  text-transform: uppercase;\n"
            "  letter-spacing: 0.03em;\n"
            "}\n"
            "\n"
            ".tags {\n"
            "  margin-top: 0.75rem;\n"
            "  display: flex;\n"
            "  flex-wrap: wrap;\n"
            "  gap: 0.4rem;\n"
            "}\n"
            "\n"
            ".tag {\n"
            "  display: inline-block;\n"
            "  padding: 0.15em 0.6em;\n"
            "  background: var(--accent-light);\n"
            "  color: var(--accent-dark);\n"
            "  border-radius: 12px;\n"
            "  font-size: 0.8rem;\n"
            "  font-weight: 500;\n"
            "}\n"
            "\n"
            "/* -- Section ------------------------------------------------ */\n"
            "section {\n"
            "  background: var(--bg-secondary);\n"
            "  border: 1px solid var(--border);\n"
            "  border-radius: var(--radius);\n"
            "  padding: 1.25rem 1.5rem;\n"
            "  margin-bottom: 1.5rem;\n"
            "  box-shadow: var(--shadow);\n"
            "}\n"
            "\n"
            "section h2 {\n"
            "  margin-top: 0;\n"
            "}\n"
            "\n"
            "/* -- Tables ------------------------------------------------ */\n"
            "table {\n"
            "  width: 100%;\n"
            "  border-collapse: collapse;\n"
            "  margin: 0.75rem 0;\n"
            "  font-size: 0.875rem;\n"
            "}\n"
            "\n"
            "thead th {\n"
            "  background: var(--accent);\n"
            "  color: #ffffff;\n"
            "  padding: 0.5rem 0.75rem;\n"
            "  text-align: left;\n"
            "  font-weight: 600;\n"
            "  white-space: nowrap;\n"
            "}\n"
            "\n"
            "tbody td {\n"
            "  padding: 0.45rem 0.75rem;\n"
            "  border-bottom: 1px solid var(--border);\n"
            "  vertical-align: top;\n"
            "  word-break: break-word;\n"
            "}\n"
            "\n"
            "tbody tr:nth-child(even) {\n"
            "  background: var(--bg);\n"
            "}\n"
            "\n"
            "tbody tr:hover {\n"
            "  background: var(--accent-light);\n"
            "}\n"
            "\n"
            "/* -- Key-value list --------------------------------------- */\n"
            "dl.kv-list {\n"
            "  display: grid;\n"
            "  grid-template-columns: auto 1fr;\n"
            "  gap: 0.3rem 1rem;\n"
            "  margin: 0.5rem 0;\n"
            "}\n"
            "\n"
            "dl.kv-list dt {\n"
            "  font-weight: 600;\n"
            "  color: var(--text-secondary);\n"
            "  text-align: right;\n"
            "}\n"
            "\n"
            "dl.kv-list dd {\n"
            "  word-break: break-word;\n"
            "}\n"
            "\n"
            "code {\n"
            "  font-family: var(--font-mono);\n"
            "  background: var(--bg);\n"
            "  padding: 0.15em 0.35em;\n"
            "  border-radius: 3px;\n"
            "  font-size: 0.85em;\n"
            "  border: 1px solid var(--border);\n"
            "}\n"
            "\n"
            "pre {\n"
            "  background: var(--bg);\n"
            "  border: 1px solid var(--border);\n"
            "  border-radius: var(--radius);\n"
            "  padding: 1rem;\n"
            "  overflow-x: auto;\n"
            "  font-family: var(--font-mono);\n"
            "  font-size: 0.85em;\n"
            "  line-height: 1.5;\n"
            "}\n"
            "\n"
            "/* -- Footer ------------------------------------------------ */\n"
            "footer {\n"
            "  margin-top: 2rem;\n"
            "  padding-top: 1rem;\n"
            "  border-top: 1px solid var(--border);\n"
            "  text-align: center;\n"
            "  color: var(--text-secondary);\n"
            "  font-size: 0.8rem;\n"
            "}\n"
            "\n"
            "footer .report-id {\n"
            "  font-family: var(--font-mono);\n"
            "  font-size: 0.75rem;\n"
            "  margin-top: 0.25rem;\n"
            "}\n"
            "\n"
            "/* -- Accessibility ----------------------------------------- */\n"
            "@media (forced-colors: active) {\n"
            "  .status-badge { border: 1px solid; }\n"
            "  .tag { border: 1px solid; }\n"
            "  thead th { border-bottom: 2px solid; }\n"
            "}\n"
            "\n"
            "/* -- Print ------------------------------------------------- */\n"
            "@media print {\n"
            "  body { max-width: none; padding: 0; font-size: 11pt; }\n"
            "  header { box-shadow: none; border: 1px solid #ccc; }\n"
            "  section { box-shadow: none; break-inside: avoid; }\n"
            "  table { page-break-inside: avoid; }\n"
            "  thead th { color: #000 !important; background: #e0e0e0 !important; "
            "-webkit-print-color-adjust: exact; print-color-adjust: exact; }\n"
            "  .status-badge { border: 1px solid #333; }\n"
            "  .tag { border: 1px solid #666; }\n"
            "  footer { break-before: avoid; }\n"
            "  a { color: #000; text-decoration: underline; }\n"
            "}\n"
        )

    def _render_html_section(self, label: str, data: Any) -> str:
        """Render a single section to HTML."""
        parts: list[str] = []
        parts.append(f"    <section aria-label=\"{self._escape_xml(label)}\">")
        parts.append(f"      <h2>{self._escape_xml(label)}</h2>")

        if isinstance(data, dict):
            flat = self._flatten_section_data(data)
            parts.append(
                '      <table role="table" '
                f'aria-label="{self._escape_xml(label)} data">'
            )
            parts.append("        <thead><tr><th>Field</th><th>Value</th></tr></thead>")
            parts.append("        <tbody>")
            for key, val in flat:
                parts.append(
                    f"          <tr><td><code>{self._escape_xml(key)}</code></td>"
                    f"<td>{self._escape_xml(val)}</td></tr>"
                )
            parts.append("        </tbody>")
            parts.append("      </table>")
        elif isinstance(data, list):
            parts.append(self._render_html_list(data, label))
        else:
            parts.append(f"      <p>{self._escape_xml(str(data))}</p>")

        parts.append("    </section>")
        return "\n".join(parts)

    def _render_html_list(self, items: list[Any], label: str) -> str:
        """Render a list of items as HTML. Uses a table when items are dicts."""
        if not items:
            return '      <p><em>No data.</em></p>'

        if isinstance(items[0], dict):
            return self._render_html_table_from_dicts(items, label)

        lines: list[str] = []
        lines.append(f'      <ul aria-label="{self._escape_xml(label)} list">')
        for item in items:
            lines.append(f"        <li>{self._escape_xml(str(item))}</li>")
        lines.append("      </ul>")
        return "\n".join(lines)

    def _render_html_table_from_dicts(
        self, items: list[dict[str, Any]], label: str,
    ) -> str:
        """Render a list of dicts as an HTML table."""
        all_keys: list[str] = []
        seen: set[str] = set()
        for item in items:
            for key in item:
                if key not in seen:
                    all_keys.append(key)
                    seen.add(key)

        lines: list[str] = []
        lines.append(
            f'      <table role="table" '
            f'aria-label="{self._escape_xml(label)} data">'
        )
        lines.append("        <thead><tr>")
        for col in all_keys:
            lines.append(
                f"          <th scope=\"col\">{self._escape_xml(col)}</th>"
            )
        lines.append("        </tr></thead>")
        lines.append("        <tbody>")
        for item in items:
            lines.append("          <tr>")
            for col in all_keys:
                val = item.get(col, "")
                if isinstance(val, (dict, list)):
                    val = json.dumps(val, default=str)
                lines.append(
                    f"            <td>{self._escape_xml(str(val))}</td>"
                )
            lines.append("          </tr>")
        lines.append("        </tbody>")
        lines.append("      </table>")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Markdown helpers
    # ------------------------------------------------------------------

    def _render_markdown_section_data(self, data: Any, indent: int = 0) -> str:
        """Recursively render section data as Markdown."""
        prefix = "  " * indent

        if isinstance(data, dict):
            lines: list[str] = []
            flat = self._flatten_section_data(data)
            if flat:
                lines.append(f"{prefix}| Key | Value |")
                lines.append(f"{prefix}|-----|-------|")
                for key, val in flat:
                    safe_val = val.replace("|", "\\|")
                    lines.append(f"{prefix}| `{key}` | {safe_val} |")
                lines.append("")
            return "\n".join(lines)

        if isinstance(data, list):
            if not data:
                return f"{prefix}*No data.*\n"
            lines = []
            for item in data:
                if isinstance(item, dict):
                    inner = self._render_markdown_section_data(item, indent + 1)
                    lines.append(f"{prefix}-")
                    lines.append(inner)
                else:
                    lines.append(f"{prefix}- {item}")
            lines.append("")
            return "\n".join(lines)

        return f"{prefix}{data}\n"

    # ------------------------------------------------------------------
    # Plain-text helpers
    # ------------------------------------------------------------------

    def _render_txt_section(self, data: Any, indent: int = 2) -> list[str]:
        """Recursively render section data as plain text."""
        pad = " " * indent

        if isinstance(data, dict):
            lines: list[str] = []
            flat = self._flatten_section_data(data)
            for key, val in flat:
                lines.append(f"{pad}{key:<36s} {val}")
            return lines

        if isinstance(data, list):
            if not data:
                return [f"{pad}(no data)"]
            lines = []
            for idx, item in enumerate(data):
                if isinstance(item, dict):
                    lines.append(f"{pad}[{idx}]")
                    lines.extend(self._render_txt_section(item, indent + 4))
                else:
                    lines.append(f"{pad}- {item}")
            return lines

        return [f"{pad}{data}"]

    # ------------------------------------------------------------------
    # XML helpers
    # ------------------------------------------------------------------

    def _populate_xml_section(self, parent: ET.Element, data: Any) -> None:
        """Recursively populate XML elements from report data."""
        if isinstance(data, dict):
            for key, value in data.items():
                child = ET.SubElement(parent, self._xml_tag_name(key))
                if isinstance(value, (dict, list)):
                    self._populate_xml_section(child, value)
                else:
                    child.text = str(value) if value is not None else ""
        elif isinstance(data, list):
            for idx, item in enumerate(data):
                child = ET.SubElement(parent, "item")
                child.set("index", str(idx))
                if isinstance(item, (dict, list)):
                    self._populate_xml_section(child, item)
                else:
                    child.text = str(item) if item is not None else ""
        else:
            parent.text = str(data) if data is not None else ""

    @staticmethod
    def _xml_tag_name(name: str) -> str:
        """Convert an arbitrary string into a valid XML tag name."""
        sanitized = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", name)
        if sanitized and sanitized[0].isdigit():
            sanitized = f"_{sanitized}"
        return sanitized or "_unnamed"
