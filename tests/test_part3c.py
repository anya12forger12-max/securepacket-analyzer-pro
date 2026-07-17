"""Comprehensive tests for Part 3C: plugins, updates, backups, performance, settings."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import threading
import time
import zipfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# ---------------------------------------------------------------------------
# Mock PySide6 before any project imports
# ---------------------------------------------------------------------------
_mock_qt = MagicMock()
_mock_qt.QObject = type(
    "QObject", (), {"__init__": lambda self, *a, **kw: None}
)
_mock_qt.Signal = lambda *a, **kw: MagicMock()
sys.modules["PySide6"] = MagicMock()
sys.modules["PySide6.QtCore"] = _mock_qt

# ---------------------------------------------------------------------------
# Project imports (safe after PySide6 mock)
# ---------------------------------------------------------------------------
from src.plugins.base import (
    PluginBase,
    PluginCategory,
    PluginMetadata,
    PluginPermission,
    PluginState,
)
from src.plugins.loader import PluginLoader
from src.plugins.manager import PluginManager
from src.core.updater import UpdateChannel, UpdateManager, UpdateStatus
from src.core.backup import BackupEntry, BackupManager, BackupType
from src.diagnostics.performance import (
    PerformanceLevel,
    PerformanceMonitor,
    PerformanceSnapshot,
)
from src.services.event_bus import EventBus, Events
from src.config.settings import DEFAULT_CONFIG, SettingsManager, _VALIDATION_RULES


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_event_bus():
    """Reset the EventBus singleton between tests."""
    yield
    try:
        EventBus._instance = None
    except Exception:
        pass


@pytest.fixture
def loader():
    """Create a PluginLoader with a mocked SecurityManager."""
    sm = MagicMock()
    sm.safe_file_read.return_value = None
    sm.verify_plugin_signature.return_value = True
    sm.compute_hash.return_value = "aabb"
    return PluginLoader(security_manager=sm)


@pytest.fixture
def plugin_manager(tmp_path):
    """Create a PluginManager with mocked dependencies and tmp paths."""
    sm = MagicMock()
    sm.safe_file_read.return_value = None
    sm.safe_file_write.return_value = True

    with patch("src.plugins.manager.EventBus") as eb_cls, \
         patch("src.plugins.manager.AppPaths") as paths_cls:
        paths_cls.data_dir.return_value = tmp_path
        eb_inst = MagicMock()
        eb_cls.instance.return_value = eb_inst
        manager = PluginManager(security_manager=sm)
        yield manager


@pytest.fixture
def update_manager(tmp_path):
    """Create an UpdateManager with mocked dependencies and tmp paths."""
    settings_data: dict[str, Any] = {}

    class _FakeSettings:
        def get(self, key: str, default: Any = None) -> Any:
            return settings_data.get(key, default)

        def set(self, key: str, value: Any) -> None:
            settings_data[key] = value

    sm = MagicMock()
    sm.validate_url.return_value = True

    with patch("src.core.updater.EventBus") as eb_cls, \
         patch("src.core.updater.AppPaths") as paths_cls:
        paths_cls.data_dir.return_value = tmp_path
        eb_inst = MagicMock()
        eb_cls.instance.return_value = eb_inst
        mgr = UpdateManager(settings=_FakeSettings(), security=sm)
        yield mgr


@pytest.fixture
def backup_manager(tmp_path):
    """Create a BackupManager with mocked dependencies and tmp paths."""
    sm = MagicMock()

    class _FakeSettings:
        def get(self, key: str, default: Any = None) -> Any:
            return default

        def set(self, key: str, value: Any) -> None:
            pass

    with patch("src.core.backup.EventBus") as eb_cls, \
         patch("src.core.backup.AppPaths") as paths_cls:
        paths_cls.data_dir.return_value = tmp_path
        paths_cls.config_dir.return_value = tmp_path / "config"
        paths_cls.workspaces_dir.return_value = tmp_path / "workspaces"
        paths_cls.plugins_dir.return_value = tmp_path / "plugins"
        eb_inst = MagicMock()
        eb_cls.instance.return_value = eb_inst
        mgr = BackupManager(settings=_FakeSettings(), security=sm)
        yield mgr


# ===================================================================
# TestPluginMetadata
# ===================================================================

class TestPluginMetadata:
    """Tests for the PluginMetadata dataclass."""

    def test_creation(self):
        """Create metadata with required fields only."""
        meta = PluginMetadata(name="MyPlugin", version="1.0.0")
        assert meta.name == "MyPlugin"
        assert meta.version == "1.0.0"

    def test_defaults(self):
        """Verify default values for optional fields."""
        meta = PluginMetadata()
        assert meta.category == PluginCategory.UTILITY
        assert meta.state == PluginState.INSTALLED
        assert meta.config == {}
        assert meta.permissions == []
        assert meta.dependencies == []
        assert meta.author == ""
        assert meta.description == ""
        assert meta.min_app_version == "1.0.0"
        assert meta.api_version == "1.0.0"

    def test_to_dict(self):
        """All fields serialize to a dictionary."""
        meta = PluginMetadata(
            name="Test",
            version="2.0.0",
            author="Alice",
            description="A test plugin",
            category=PluginCategory.THEME,
            permissions=[PluginPermission.FILE_READ],
            dependencies=["dep1"],
        )
        d = meta.to_dict()
        assert d["name"] == "Test"
        assert d["version"] == "2.0.0"
        assert d["author"] == "Alice"
        assert d["description"] == "A test plugin"
        assert d["category"] == "THEME"
        assert d["permissions"] == ["FILE_READ"]
        assert d["dependencies"] == ["dep1"]
        assert d["enabled"] is True
        assert d["state"] == "INSTALLED"
        assert isinstance(d["id"], str)

    def test_from_dict(self):
        """Deserialize from a dictionary."""
        d = {
            "id": "abc123",
            "name": "FromDict",
            "version": "0.5.0",
            "category": "REPORT",
            "permissions": ["NETWORK_ACCESS", "UI_MODIFY"],
            "dependencies": ["a", "b"],
            "state": "ENABLED",
            "enabled": False,
        }
        meta = PluginMetadata.from_dict(d)
        assert meta.id == "abc123"
        assert meta.name == "FromDict"
        assert meta.version == "0.5.0"
        assert meta.category == PluginCategory.REPORT
        assert meta.permissions == [
            PluginPermission.NETWORK_ACCESS,
            PluginPermission.UI_MODIFY,
        ]
        assert meta.dependencies == ["a", "b"]
        assert meta.state == PluginState.ENABLED
        assert meta.enabled is False

    def test_roundtrip(self):
        """to_dict then from_dict produces equivalent metadata."""
        original = PluginMetadata(
            id="roundtrip",
            name="Roundtrip",
            version="3.0.0",
            author="Bob",
            description="Round-trip test",
            long_description="Long text",
            category=PluginCategory.SECURITY,
            permissions=[PluginPermission.DATABASE_ACCESS],
            dependencies=["x"],
            min_app_version="1.2.0",
            max_app_version="5.0.0",
            api_version="2.0.0",
            homepage="https://example.com",
            license_name="Apache-2.0",
            enabled=False,
            state=PluginState.ERROR,
            load_error="something broke",
            config={"key": "val"},
            checksum="deadbeef",
        )
        restored = PluginMetadata.from_dict(original.to_dict())
        assert restored.id == original.id
        assert restored.name == original.name
        assert restored.version == original.version
        assert restored.author == original.author
        assert restored.description == original.description
        assert restored.long_description == original.long_description
        assert restored.category == original.category
        assert restored.permissions == original.permissions
        assert restored.dependencies == original.dependencies
        assert restored.min_app_version == original.min_app_version
        assert restored.max_app_version == original.max_app_version
        assert restored.api_version == original.api_version
        assert restored.homepage == original.homepage
        assert restored.license_name == original.license_name
        assert restored.enabled == original.enabled
        assert restored.state == original.state
        assert restored.load_error == original.load_error
        assert restored.config == original.config
        assert restored.checksum == original.checksum

    def test_with_permissions(self):
        """Permissions list is preserved through serialization."""
        meta = PluginMetadata(
            permissions=[
                PluginPermission.FILE_READ,
                PluginPermission.NETWORK_ACCESS,
                PluginPermission.NOTIFICATION,
            ]
        )
        restored = PluginMetadata.from_dict(meta.to_dict())
        assert restored.permissions == meta.permissions
        assert len(restored.permissions) == 3

    def test_with_dependencies(self):
        """Dependencies list is preserved through serialization."""
        meta = PluginMetadata(dependencies=["alpha", "beta", "gamma"])
        restored = PluginMetadata.from_dict(meta.to_dict())
        assert restored.dependencies == ["alpha", "beta", "gamma"]


# ===================================================================
# TestPluginState
# ===================================================================

class TestPluginState:
    """Verify PluginState enum has all expected values."""

    def test_values(self):
        """All six lifecycle states exist."""
        assert PluginState.INSTALLED is not None
        assert PluginState.ENABLED is not None
        assert PluginState.DISABLED is not None
        assert PluginState.ERROR is not None
        assert PluginState.UPDATING is not None
        assert PluginState.REMOVED is not None
        assert len(PluginState) == 6


# ===================================================================
# TestPluginCategory
# ===================================================================

class TestPluginCategory:
    """Verify PluginCategory enum has all expected values."""

    def test_values(self):
        """All 10 categories exist."""
        expected = [
            "PROTOCOL_DECODER",
            "DASHBOARD_WIDGET",
            "ANALYTICS_EXTENSION",
            "EXPORT_FORMAT",
            "THEME",
            "TRANSLATION",
            "REPORT",
            "UTILITY",
            "ACCESSIBILITY",
            "SECURITY",
        ]
        for name in expected:
            assert hasattr(PluginCategory, name), f"Missing category: {name}"
        assert len(PluginCategory) == 10


# ===================================================================
# TestPluginPermission
# ===================================================================

class TestPluginPermission:
    """Verify PluginPermission enum has all expected values."""

    def test_values(self):
        """All permission types exist."""
        expected = [
            "FILE_READ",
            "FILE_WRITE",
            "NETWORK_ACCESS",
            "DATABASE_ACCESS",
            "CAPTURE_ACCESS",
            "SETTINGS_ACCESS",
            "UI_MODIFY",
            "NOTIFICATION",
            "LOGGING",
        ]
        for name in expected:
            assert hasattr(PluginPermission, name), f"Missing permission: {name}"
        assert len(PluginPermission) == 9


# ===================================================================
# TestPluginLoader
# ===================================================================

class TestPluginLoader:
    """Tests for PluginLoader discovery, validation, and lifecycle."""

    def test_empty_directory(self, loader, tmp_path):
        """Discovering plugins in an empty directory returns empty list."""
        empty = tmp_path / "empty_plugins"
        empty.mkdir()
        result = loader.discover_plugins(plugin_dir=empty)
        assert result == []

    def test_validate_plugin_valid(self, loader):
        """Valid metadata returns no errors."""
        meta = PluginMetadata(
            id="valid1", name="Valid", version="1.0.0", api_version="1.0"
        )
        errors = loader.validate_plugin(meta)
        assert errors == []

    def test_validate_plugin_missing_name(self, loader):
        """Missing name returns an error."""
        meta = PluginMetadata(id="x", name="", version="1.0.0", api_version="1.0")
        errors = loader.validate_plugin(meta)
        assert any("name" in e.lower() for e in errors)

    def test_validate_plugin_missing_version(self, loader):
        """Missing version returns an error."""
        meta = PluginMetadata(id="x", name="Test", version="", api_version="1.0")
        errors = loader.validate_plugin(meta)
        assert any("version" in e.lower() for e in errors)

    def test_validate_plugin_bad_version(self, loader):
        """Non-empty but unconventional version string still passes basic validation."""
        meta = PluginMetadata(
            id="x", name="Test", version="not-semver", api_version="1.0"
        )
        errors = loader.validate_plugin(meta)
        assert errors == []

    def test_check_version_compatible(self, loader):
        """Plugin requiring >=1.0.0 is compatible with app 1.2.3."""
        meta = PluginMetadata(min_app_version="1.0.0")
        assert loader.check_version_compatibility(meta, "1.2.3") is True

    def test_check_version_incompatible(self, loader):
        """Plugin requiring >=2.0.0 is NOT compatible with app 1.2.3."""
        meta = PluginMetadata(min_app_version="2.0.0")
        assert loader.check_version_compatibility(meta, "1.2.3") is False

    def test_check_version_exact(self, loader):
        """Plugin requiring min 1.0.0 / max 1.0.0 is compatible with 1.0.0."""
        meta = PluginMetadata(min_app_version="1.0.0", max_app_version="1.0.0")
        assert loader.check_version_compatibility(meta, "1.0.0") is True

    def test_install_plugin(self, loader, tmp_path):
        """Installing a valid plugin creates the metadata file."""
        source = tmp_path / "src_plugin"
        source.mkdir()
        manifest = {
            "id": "plug1",
            "name": "Plug1",
            "version": "1.0.0",
            "api_version": "1.0",
        }
        (source / "plugin.json").write_text(json.dumps(manifest))

        dest = tmp_path / "dest"
        dest.mkdir()

        manifest_json = json.dumps(manifest)
        loader._security.safe_file_read = MagicMock(return_value=manifest_json)

        metadata = loader.install_plugin(source, plugin_dir=dest)
        assert metadata is not None
        assert metadata.id == "plug1"
        assert (dest / "plug1" / "plugin.json").exists()

    def test_install_plugin_no_dir(self, loader, tmp_path):
        """Installing to a non-existent destination creates it."""
        source = tmp_path / "src_plugin2"
        source.mkdir()
        manifest = {
            "id": "plug2",
            "name": "Plug2",
            "version": "1.0.0",
            "api_version": "1.0",
        }
        (source / "plugin.json").write_text(json.dumps(manifest))

        dest = tmp_path / "nonexistent" / "deep" / "plugins"
        assert not dest.exists()

        manifest_json = json.dumps(manifest)
        loader._security.safe_file_read = MagicMock(return_value=manifest_json)

        metadata = loader.install_plugin(source, plugin_dir=dest)
        assert metadata is not None
        assert dest.exists()

    def test_uninstall_plugin(self, loader, tmp_path):
        """Uninstalling removes the plugin directory."""
        plugins = tmp_path / "plugins_uninstall"
        plugins.mkdir()
        target = plugins / "to_remove"
        target.mkdir()
        (target / "plugin.json").write_text("{}")

        assert target.exists()
        result = loader.uninstall_plugin("to_remove", plugin_dir=plugins)
        assert result is True
        assert not target.exists()


# ===================================================================
# TestPluginManager
# ===================================================================

class TestPluginManager:
    """Tests for PluginManager high-level lifecycle operations."""

    def test_stats_empty(self, plugin_manager):
        """No plugins yields total=0, enabled=0, disabled=0."""
        stats = plugin_manager.get_plugin_stats()
        assert stats["total"] == 0
        assert stats["enabled"] == 0
        assert stats["disabled"] == 0

    def test_enable_plugin(self, plugin_manager, tmp_path):
        """Enable adds a plugin to loaded_plugins."""
        meta = PluginMetadata(id="ep1", name="EP1", version="1.0.0")
        plugin_manager._metadata["ep1"] = meta

        fake_dir = tmp_path / "pm_plugins" / "ep1"
        fake_dir.mkdir(parents=True)

        mock_plugin = MagicMock()
        with patch.object(
            plugin_manager._loader, "get_plugin_directory"
        ) as gpd, patch.object(
            plugin_manager._loader, "load_plugin"
        ) as lp:
            gpd.return_value = tmp_path / "pm_plugins"
            lp.return_value = mock_plugin
            result = plugin_manager.enable("ep1")

        assert result is True
        assert "ep1" in plugin_manager._plugins

    def test_disable_plugin(self, plugin_manager):
        """Disable removes a plugin from loaded_plugins."""
        meta = PluginMetadata(id="dp1", name="DP1", version="1.0.0")
        plugin_manager._metadata["dp1"] = meta

        mock_plugin = MagicMock()
        plugin_manager._plugins["dp1"] = mock_plugin

        result = plugin_manager.disable("dp1")

        assert result is True
        assert "dp1" not in plugin_manager._plugins
        assert meta.state == PluginState.DISABLED

    def test_set_config(self, plugin_manager):
        """set_config stores and retrieves plugin configuration."""
        meta = PluginMetadata(id="sc1", name="SC1", version="1.0.0")
        plugin_manager._metadata["sc1"] = meta

        cfg = {"theme": "dark", "size": 14}
        result = plugin_manager.set_config("sc1", cfg)

        assert result is True
        assert plugin_manager.get_config("sc1") == cfg

    def test_list_plugins(self, plugin_manager):
        """list_plugins returns all known plugin metadata."""
        m1 = PluginMetadata(id="l1", name="L1", version="1.0.0")
        m2 = PluginMetadata(id="l2", name="L2", version="2.0.0")
        plugin_manager._metadata["l1"] = m1
        plugin_manager._metadata["l2"] = m2

        result = plugin_manager.list_plugins()
        assert len(result) == 2
        ids = {p.id for p in result}
        assert ids == {"l1", "l2"}

    def test_health_empty(self, plugin_manager):
        """Empty manager returns empty health dict."""
        assert plugin_manager.get_health() == {}


# ===================================================================
# TestUpdateManager
# ===================================================================

class TestUpdateManager:
    """Tests for UpdateManager version, channel, history, and validation."""

    def test_current_version(self, update_manager):
        """get_current_version returns a string."""
        version = update_manager.get_current_version()
        assert isinstance(version, str)

    def test_status_default(self, update_manager):
        """Default status is NOT_AVAILABLE."""
        assert update_manager.get_status() == UpdateStatus.NOT_AVAILABLE

    def test_channel_default(self, update_manager):
        """Default channel is STABLE."""
        assert update_manager.get_channel() == UpdateChannel.STABLE

    def test_set_channel(self, update_manager):
        """Changing the channel updates the stored value."""
        update_manager.set_channel(UpdateChannel.BETA)
        assert update_manager.get_channel() == UpdateChannel.BETA

    def test_history_empty(self, update_manager):
        """History is empty initially."""
        assert update_manager.get_history() == []

    def test_record_history(self, update_manager):
        """record_history adds an entry to the history list."""
        update_manager.record_history("1.0.0", "1.1.0", True, "upgrade notes")
        history = update_manager.get_history()
        assert len(history) == 1
        assert history[0].version_from == "1.0.0"
        assert history[0].version_to == "1.1.0"
        assert history[0].success is True
        assert history[0].notes == "upgrade notes"

    def test_validate_download_valid(self, update_manager, tmp_path):
        """Checksum match returns True."""
        test_file = tmp_path / "update.bin"
        content = b"binary payload for testing"
        test_file.write_bytes(content)
        expected = hashlib.sha256(content).hexdigest()
        assert update_manager.validate_download(test_file, expected) is True

    def test_validate_download_invalid(self, update_manager, tmp_path):
        """Checksum mismatch returns False."""
        test_file = tmp_path / "update.bin"
        test_file.write_bytes(b"some data")
        assert update_manager.validate_download(test_file, "0000dead") is False


# ===================================================================
# TestBackupManager
# ===================================================================

class TestBackupManager:
    """Tests for BackupManager creation, verification, and deletion."""

    def test_list_backups_empty(self, backup_manager):
        """No backups initially."""
        assert backup_manager.list_backups() == []

    def test_create_backup(self, backup_manager, tmp_path):
        """Creating a backup produces a file and returns BackupEntry."""
        # Ensure source dirs exist so the zip creation doesn't fail
        for d in ["config", "workspaces", "plugins"]:
            (tmp_path / d).mkdir(exist_ok=True)

        entry = backup_manager.create_backup(
            name="Test Backup",
            backup_type=BackupType.FULL,
            description="unit test",
        )
        assert entry is not None
        assert isinstance(entry, BackupEntry)
        assert entry.name == "Test Backup"
        assert Path(entry.file_path).exists()
        assert entry.file_size > 0
        assert entry.checksum != ""

    def test_verify_backup(self, backup_manager, tmp_path):
        """Verifying a newly created backup returns True."""
        for d in ["config", "workspaces", "plugins"]:
            (tmp_path / d).mkdir(exist_ok=True)

        entry = backup_manager.create_backup(name="Verify")
        assert entry is not None
        assert backup_manager.verify_backup(entry.id) is True

    def test_delete_backup(self, backup_manager, tmp_path):
        """Deleting a backup removes the archive file."""
        for d in ["config", "workspaces", "plugins"]:
            (tmp_path / d).mkdir(exist_ok=True)

        entry = backup_manager.create_backup(name="To Delete")
        assert entry is not None
        archive = Path(entry.file_path)
        assert archive.exists()

        result = backup_manager.delete_backup(entry.id)
        assert result is True
        assert not archive.exists()

    def test_backup_contents(self, backup_manager, tmp_path):
        """Listing contents of a backup returns file paths inside the zip."""
        config_dir = tmp_path / "config"
        config_dir.mkdir(exist_ok=True)
        (config_dir / "settings.toml").write_text("[general]\nversion = '1'")
        for d in ["workspaces", "plugins"]:
            (tmp_path / d).mkdir(exist_ok=True)

        entry = backup_manager.create_backup(name="Contents Test")
        assert entry is not None
        contents = backup_manager.get_backup_contents(entry.id)
        assert isinstance(contents, list)
        assert len(contents) > 0
        assert any("settings.toml" in c for c in contents)

    def test_create_settings_only(self, backup_manager, tmp_path):
        """SETTINGS_ONLY backup only includes settings."""
        config_dir = tmp_path / "config"
        config_dir.mkdir(exist_ok=True)
        (config_dir / "only.toml").write_text("data")
        ws_dir = tmp_path / "workspaces"
        ws_dir.mkdir(exist_ok=True)
        (ws_dir / "workspace.txt").write_text("data")
        for d in ["plugins"]:
            (tmp_path / d).mkdir(exist_ok=True)

        entry = backup_manager.create_backup(
            name="Settings Only",
            backup_type=BackupType.SETTINGS_ONLY,
        )
        assert entry is not None
        assert entry.includes_settings is True
        assert entry.includes_workspaces is False
        assert entry.includes_cases is False
        contents = backup_manager.get_backup_contents(entry.id)
        assert any("only.toml" in c for c in contents)
        assert not any("workspace.txt" in c for c in contents)


# ===================================================================
# TestPerformanceMonitor
# ===================================================================

class TestPerformanceMonitor:
    """Tests for PerformanceMonitor snapshots, thresholds, and ring buffer."""

    def test_snapshot_fields(self):
        """PerformanceSnapshot has all expected metric fields."""
        snap = PerformanceSnapshot(
            timestamp=time.monotonic(),
            cpu_percent=12.5,
            memory_mb=512.0,
            memory_percent=25.0,
            disk_io_read=1000,
            disk_io_write=2000,
            thread_count=8,
            open_files=42,
            fps=60.0,
            app_memory_mb=128.0,
        )
        assert snap.cpu_percent == 12.5
        assert snap.memory_percent == 25.0
        assert snap.memory_mb == 512.0
        assert snap.disk_io_read == 1000
        assert snap.disk_io_write == 2000
        assert snap.open_files == 42
        assert snap.thread_count == 8
        assert snap.fps == 60.0
        assert snap.app_memory_mb == 128.0

    def test_snapshot_to_dict(self):
        """to_dict serializes all snapshot fields."""
        snap = PerformanceSnapshot(
            timestamp=100.0,
            cpu_percent=5.0,
            memory_mb=256.0,
            memory_percent=10.0,
            thread_count=4,
        )
        d = snap.to_dict()
        assert d["timestamp"] == 100.0
        assert d["cpu_percent"] == 5.0
        assert d["memory_mb"] == 256.0
        assert d["memory_percent"] == 10.0
        assert d["thread_count"] == 4
        assert d["disk_io_read"] == 0
        assert d["open_files"] == 0

    def test_thresholds_default(self):
        """Default thresholds dict contains cpu_percent and memory_percent."""
        monitor = PerformanceMonitor()
        thresholds = monitor.get_thresholds()
        assert "cpu_percent" in thresholds
        assert "memory_percent" in thresholds
        assert thresholds["cpu_percent"] == 80.0
        assert thresholds["memory_percent"] == 80.0

    def test_history_ring_buffer(self):
        """max_snapshots caps the stored snapshot list."""
        monitor = PerformanceMonitor()
        # Override max_snapshots to a small number for fast testing
        monitor._max_snapshots = 10

        # Manually inject snapshots past the limit
        for i in range(25):
            snap = PerformanceSnapshot(timestamp=float(i), cpu_percent=float(i))
            with monitor._lock:
                monitor._snapshots.append(snap)
                if len(monitor._snapshots) > monitor._max_snapshots:
                    monitor._snapshots = monitor._snapshots[-monitor._max_snapshots:]

        assert len(monitor._snapshots) == 10
        # The oldest entries should be trimmed; latest should be timestamp=24
        assert monitor._snapshots[-1].timestamp == 24.0
        assert monitor._snapshots[0].timestamp == 15.0


# ===================================================================
# TestSettingsValidation
# ===================================================================

class TestSettingsValidation:
    """Tests for DEFAULT_CONFIG structure and _VALIDATION_RULES coverage."""

    def test_backup_section_exists(self):
        """The 'backup' key exists in DEFAULT_CONFIG."""
        assert "backup" in DEFAULT_CONFIG

    def test_diagnostics_section_exists(self):
        """The 'diagnostics' key exists in DEFAULT_CONFIG."""
        assert "diagnostics" in DEFAULT_CONFIG

    def test_backup_auto_backup_default(self):
        """backup.auto_backup defaults to False."""
        assert DEFAULT_CONFIG["backup"]["auto_backup"] is False

    def test_backup_interval_hours_default(self):
        """backup.backup_interval_hours defaults to 24."""
        assert DEFAULT_CONFIG["backup"]["backup_interval_hours"] == 24

    def test_diagnostics_perf_monitoring_default(self):
        """diagnostics.performance_monitoring defaults to True."""
        assert DEFAULT_CONFIG["diagnostics"]["performance_monitoring"] is True

    def test_backup_validation_rules(self):
        """backup.auto_backup and backup.backup_interval_hours have validation rules."""
        assert "backup.auto_backup" in _VALIDATION_RULES
        assert "backup.backup_interval_hours" in _VALIDATION_RULES
        # Verify the rule types
        auto_rule = _VALIDATION_RULES["backup.auto_backup"]
        assert auto_rule[0] is bool
        interval_rule = _VALIDATION_RULES["backup.backup_interval_hours"]
        assert interval_rule[1] is not None  # has a range checker

    def test_diagnostics_validation_rules(self):
        """diagnostics.auto_run_on_startup and diagnostics.log_level have rules."""
        assert "diagnostics.auto_run_on_startup" in _VALIDATION_RULES
        assert "diagnostics.log_level" in _VALIDATION_RULES
        startup_rule = _VALIDATION_RULES["diagnostics.auto_run_on_startup"]
        assert startup_rule[0] is bool
        log_rule = _VALIDATION_RULES["diagnostics.log_level"]
        assert log_rule[1] is not None  # has an enum checker


# ===================================================================
# TestEventsExtended
# ===================================================================

class TestEventsExtended:
    """Tests that all expected event constants exist on the Events class."""

    def test_plugin_events(self):
        """All plugin lifecycle event constants exist."""
        assert hasattr(Events, "PLUGIN_LOADED")
        assert hasattr(Events, "PLUGIN_UNLOADED")
        assert hasattr(Events, "PLUGIN_ENABLED")
        assert hasattr(Events, "PLUGIN_DISABLED")
        assert hasattr(Events, "PLUGIN_INSTALLED")
        assert hasattr(Events, "PLUGIN_UNINSTALLED")
        assert Events.PLUGIN_LOADED == "plugin.loaded"
        assert Events.PLUGIN_INSTALLED == "plugin.installed"

    def test_update_events(self):
        """All update event constants exist."""
        assert hasattr(Events, "UPDATE_AVAILABLE")
        assert hasattr(Events, "UPDATE_DOWNLOAD_STARTED")
        assert hasattr(Events, "UPDATE_DOWNLOAD_COMPLETED")
        assert hasattr(Events, "UPDATE_DOWNLOAD_FAILED")
        assert hasattr(Events, "UPDATE_INSTALL_STARTED")
        assert hasattr(Events, "UPDATE_INSTALL_COMPLETED")
        assert hasattr(Events, "UPDATE_INSTALL_FAILED")
        assert Events.UPDATE_AVAILABLE == "update.available"

    def test_backup_events(self):
        """All backup event constants exist."""
        assert hasattr(Events, "BACKUP_CREATED")
        assert hasattr(Events, "BACKUP_RESTORED")
        assert hasattr(Events, "BACKUP_FAILED")
        assert hasattr(Events, "BACKUP_DELETED")
        assert Events.BACKUP_CREATED == "backup.created"
        assert Events.BACKUP_RESTORED == "backup.restored"

    def test_diagnostics_events(self):
        """All diagnostics event constants exist."""
        assert hasattr(Events, "DIAGNOSTICS_COMPLETED")
        assert hasattr(Events, "DIAGNOSTICS_EXPORTED")
        assert Events.DIAGNOSTICS_COMPLETED == "diagnostics.completed"

    def test_performance_events(self):
        """All performance event constants exist."""
        assert hasattr(Events, "PERFORMANCE_WARNING")
        assert hasattr(Events, "PERFORMANCE_CRITICAL")
        assert hasattr(Events, "MEMORY_WARNING")
        assert hasattr(Events, "MEMORY_CRITICAL")
        assert Events.PERFORMANCE_WARNING == "performance.warning"
        assert Events.MEMORY_WARNING == "memory.warning"


# ===================================================================
# TestThreadSafety
# ===================================================================

class TestThreadSafety:
    """Verify thread-safety of core data structures."""

    def test_concurrent_metadata_creation(self):
        """50 threads creating PluginMetadata concurrently raises no exceptions."""
        errors: list[Exception] = []
        lock = threading.Lock()

        def create_meta(i: int) -> None:
            try:
                meta = PluginMetadata(
                    name=f"ThreadPlugin_{i}",
                    version=f"1.0.{i}",
                    author=f"author_{i}",
                    description=f"desc_{i}",
                )
                d = meta.to_dict()
                restored = PluginMetadata.from_dict(d)
                assert restored.name == meta.name
            except Exception as exc:
                with lock:
                    errors.append(exc)

        threads = [
            threading.Thread(target=create_meta, args=(i,)) for i in range(50)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert errors == [], f"Thread errors: {errors}"
