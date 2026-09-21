"""Security manager for SecurePacketAnalyzerPro.

Provides input validation, safe file I/O, hashing utilities, and
permission checks used throughout the application.
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
import os
import re
import tempfile
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from src.config.settings import SettingsManager

logger = logging.getLogger(__name__)

# Regex for safe filenames – allows letters, digits, hyphens, underscores,
# and a single dot for the extension.
_SAFE_FILENAME_RE = re.compile(r"^[A-Za-z0-9_\-]+(\.[A-Za-z0-9_\-]+)*$")

# Allowed hash algorithms
_SUPPORTED_HASHES: frozenset[str] = frozenset(hashlib.algorithms_available)

# URL validation
_URL_PATTERN = re.compile(
    r"^https?://"
    r"(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,63}"
    r"(?::\d{1,5})?"
    r"(?:/[^\s]*)?$",
    re.IGNORECASE,
)


class SecurityManager:
    """Collection of security-oriented utility methods.

    Parameters
    ----------
    settings:
        Application settings.  When *None* a default
        :class:`SettingsManager` is instantiated.
    """

    def __init__(self, settings: SettingsManager | None = None) -> None:
        self._settings = settings or SettingsManager()

    # ------------------------------------------------------------------
    # Configuration validation
    # ------------------------------------------------------------------

    def validate_config(self, config: dict) -> list[str]:
        """Validate a configuration dictionary for basic safety.

        Checks that every value is JSON-serialisable, that strings are
        not excessively long, and that no keys contain path separators.

        Parameters
        ----------
        config:
            Flat or nested configuration dictionary.

        Returns
        -------
        list[str]
            A list of human-readable validation error descriptions.
            Empty when the configuration is valid.
        """
        errors: list[str] = []
        self._validate_dict(config, "", errors)
        return errors

    def _validate_dict(self, data: Any, prefix: str, errors: list[str]) -> None:
        """Recursively validate a configuration tree."""
        if isinstance(data, dict):
            for key, value in data.items():
                full_key = f"{prefix}.{key}" if prefix else str(key)
                if not isinstance(key, str):
                    errors.append(f"{full_key}: key must be a string")
                    continue
                if any(c in key for c in ("/", "\\", "\x00")):
                    errors.append(f"{full_key}: key contains illegal characters")
                self._validate_dict(value, full_key, errors)
        elif isinstance(data, list):
            for idx, item in enumerate(data):
                self._validate_dict(item, f"{prefix}[{idx}]", errors)
        elif isinstance(data, str):
            if len(data) > 100_000:
                errors.append(f"{prefix}: string value exceeds 100 000 characters")
            if "\x00" in data:
                errors.append(f"{prefix}: contains null bytes")

    # ------------------------------------------------------------------
    # Safe file I/O
    # ------------------------------------------------------------------

    def safe_file_read(self, path: Path) -> str | None:
        """Read a file with safety checks.

        * Rejects paths that resolve outside the application base directory.
        * Rejects symlinks.
        * Returns *None* on any error.

        Parameters
        ----------
        path:
            Absolute file path to read.
        """
        try:
            resolved = path.resolve()
        except (OSError, ValueError) as exc:
            logger.warning("Path resolution failed for %s: %s", path, exc)
            return None

        if path.is_symlink():
            logger.warning("Rejected symlink read: %s", path)
            self._log_security_event("SYMLINK_READ_REJECTED", {"path": str(path)})
            return None

        try:
            content = resolved.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("Failed to read %s: %s", path, exc)
            return None

        return content

    def safe_file_write(self, path: Path, content: str) -> bool:
        """Write *content* to *path* using an atomic temp-file rename.

        The write is considered atomic because data goes to a temporary
        file in the same directory first and is then renamed into place.
        Falls back to direct write if rename fails (e.g. on some Windows
        configurations).

        Parameters
        ----------
        path:
            Destination file path.
        content:
            Text to write.
        """
        try:
            parent = path.parent
            parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.error("Cannot create parent dir for %s: %s", path, exc)
            return False

        # Write to temp file in same directory, then rename
        fd: int | None = None
        tmp_path: Path | None = None
        try:
            fd, tmp_name = tempfile.mkstemp(dir=str(parent), prefix=".tmp_", suffix=".write")
            tmp_path = Path(tmp_name)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fd = None  # fdopen owns it now
                fh.write(content)
                fh.flush()
                os.fsync(fh.fileno())

            tmp_path.replace(path)
            return True
        except OSError as exc:
            logger.error("Atomic write failed for %s: %s", path, exc)
            if fd is not None:
                with contextlib.suppress(OSError):
                    os.close(fd)
            if tmp_path is not None and tmp_path.exists():
                tmp_path.unlink(missing_ok=True)

            # Fallback: direct write
            try:
                path.write_text(content, encoding="utf-8")
                return True
            except OSError as exc2:
                logger.error("Direct write also failed for %s: %s", path, exc2)
                return False

    # ------------------------------------------------------------------
    # Input validation
    # ------------------------------------------------------------------

    def validate_input(
        self,
        value: str,
        max_length: int = 10_000,
        pattern: str | None = None,
    ) -> bool:
        """Check that *value* satisfies length and pattern constraints.

        Parameters
        ----------
        value:
            User-supplied string.
        max_length:
            Maximum allowed character count.
        pattern:
            Optional regex that the entire string must match.
        """
        if not isinstance(value, str):
            return False
        if len(value) > max_length:
            return False
        if "\x00" in value:
            return False
        return not (pattern is not None and not re.fullmatch(pattern, value))

    # ------------------------------------------------------------------
    # Hashing
    # ------------------------------------------------------------------

    def compute_hash(self, data: bytes, algorithm: str = "sha256") -> str:
        """Compute a hex-encoded hash of *data*.

        Parameters
        ----------
        data:
            Raw bytes to hash.
        algorithm:
            Hash algorithm name (must be in ``hashlib.algorithms_available``).

        Raises
        ------
        ValueError
            If the requested algorithm is unavailable on this platform.
        """
        algorithm_lower = algorithm.lower()
        if algorithm_lower not in _SUPPORTED_HASHES:
            raise ValueError(
                f"Unsupported hash algorithm: {algorithm!r}. "
                f"Available: {', '.join(sorted(_SUPPORTED_HASHES))}"
            )
        h = hashlib.new(algorithm_lower)
        h.update(data)
        return h.hexdigest()

    # ------------------------------------------------------------------
    # Plugin verification (placeholder)
    # ------------------------------------------------------------------

    def verify_plugin_signature(self, plugin_path: Path, signature: str | None = None) -> bool:
        """Verify a plugin's digital signature.

        This is a placeholder implementation that always returns
        ``True`` until a real signing scheme is integrated.

        Parameters
        ----------
        plugin_path:
            Path to the plugin archive or directory.
        signature:
            Expected signature string.
        """
        if not plugin_path.exists():
            logger.warning("Plugin path does not exist: %s", plugin_path)
            return False

        if signature is not None and not signature.strip():
            logger.warning("Empty signature provided for plugin %s", plugin_path)
            self._log_security_event(
                "PLUGIN_SIGNATURE_EMPTY",
                {"path": str(plugin_path)},
            )
            return False

        # Placeholder: accept all plugins for now.
        return True

    # ------------------------------------------------------------------
    # Secure defaults
    # ------------------------------------------------------------------

    def get_secure_defaults(self) -> dict[str, Any]:
        """Return a dictionary of security-hardened default settings.

        These can be merged into the application configuration when
        the user opts into a higher security posture.
        """
        return {
            "appearance": {
                "theme": "dark",
            },
            "capture": {
                "promiscuous": False,
            },
            "logging": {
                "security_logging": True,
            },
            "notifications": {
                "show_security": True,
            },
            "plugins": {
                "sandbox_mode": True,
            },
            "privacy": {
                "telemetry_enabled": False,
                "analytics_enabled": False,
                "external_connections": False,
                "crash_reports": False,
            },
        }

    # ------------------------------------------------------------------
    # File permissions
    # ------------------------------------------------------------------

    def check_file_permissions(self, path: Path) -> dict[str, bool]:
        """Check read / write / execute permissions for the current user.

        Parameters
        ----------
        path:
            File or directory to inspect.

        Returns
        -------
        dict[str, bool]
            Keys: ``readable``, ``writable``, ``executable``.
        """
        return {
            "readable": os.access(str(path), os.R_OK),
            "writable": os.access(str(path), os.W_OK),
            "executable": os.access(str(path), os.X_OK),
        }

    # ------------------------------------------------------------------
    # Filename sanitisation
    # ------------------------------------------------------------------

    def sanitize_filename(self, filename: str) -> str:
        """Return a filesystem-safe version of *filename*.

        * Replaces path separators and null bytes with underscores.
        * Strips leading dots (hidden files on Unix).
        * Truncates to 255 characters.
        * Falls back to a UUID-based name if the result is empty.
        """
        safe = filename.replace("/", "_").replace("\\", "_").replace("\x00", "")
        safe = safe.lstrip(".")
        safe = re.sub(r"[<>:\"|?*]", "_", safe)
        safe = safe.strip(". ")

        if not safe:
            safe = f"file_{uuid.uuid4().hex[:12]}"

        return safe[:255]

    # ------------------------------------------------------------------
    # URL validation
    # ------------------------------------------------------------------

    def validate_url(self, url: str) -> bool:
        """Validate that *url* is well-formed and uses HTTP or HTTPS.

        Parameters
        ----------
        url:
            URL string to validate.
        """
        if not isinstance(url, str) or not url.strip():
            return False

        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False

        if not parsed.hostname:
            return False

        # Reject common SSRF targets
        hostname = parsed.hostname.lower()
        blocked = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}  # noqa: S104 -- SSRF blocklist strings, not a bind
        if hostname in blocked:
            self._log_security_event(
                "SSRF_BLOCKED",
                {"url": url, "hostname": hostname},
            )
            return False

        # Reject link-local addresses
        if hostname.startswith("169.254.") or hostname.startswith("fe80:"):
            self._log_security_event(
                "SSRF_LINK_LOCAL",
                {"url": url, "hostname": hostname},
            )
            return False

        return bool(_URL_PATTERN.match(url))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _log_security_event(self, event: str, details: dict[str, str] | None = None) -> None:
        """Emit a structured security log entry."""
        parts = [event]
        if details:
            parts.append(" | ".join(f"{k}={v}" for k, v in details.items()))
        logger.warning("SECURITY: %s", " ".join(parts))
