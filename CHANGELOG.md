# Changelog

All notable changes to SecurePacket Analyzer Pro will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Cross-platform build script (`scripts/build.py`) with PyInstaller support
- Release preparation script (`scripts/release.py`) for versioning and tagging
- GitHub Actions release workflow (`.github/workflows/release.yml`)
- Comprehensive test suite for Part 3C (58 tests)

## [1.0.0] - 2025-07-16

### Added

#### Part 1A — Project Scaffolding
- Complete project architecture and repository structure
- Configuration system with TOML defaults + JSON user overrides and validation
- Centralized logging with rotation, thread safety, and separate security/performance logs
- Security manager with input validation, hashing, safe file access, and encryption stubs
- Workspace management system with JSON persistence and session tracking
- Diagnostics manager for environment validation and formatted reports
- Notification manager for in-app notification system
- Root documentation: README, LICENSE (MIT), SECURITY, CHANGELOG, CONTRIBUTING, CODE_OF_CONDUCT
- pyproject.toml with build configuration and tool settings (black, isort, ruff, mypy, pytest)
- Pre-commit hooks, .editorconfig, .gitignore, CI workflow

#### Part 1B — Accessibility & Themes
- Accessibility framework (WCAG 2.2 AA) with AccessibilityManager
- Keyboard shortcuts system (16 default shortcuts) and focus chain navigation
- Theme engine with dark, light, and high-contrast QSS generation
- Icon system with SVG generation for toolbar/sidebar icons
- Font system with configurable families and scaling

#### Part 1C — Application Infrastructure
- Application lifecycle management and service registry (dependency injection)
- Session management with auto-save and recovery
- Event bus (Qt Signals + Python callbacks) for decoupled communication
- Plugin manager (backend), settings backend, update framework
- Privacy controls, resource manager, file manager, error reporting
- First-run wizard completion flow

#### Part 2A — Capture Engine
- Passive packet capture engine using Scapy
- Capture controller with state machine (IDLE, STARTING, RUNNING, PAUSED, STOPPING, ERROR)
- Network interface manager with detection, testing, and permission checks
- Npcap/libpcap dependency detection
- Capture buffer with configurable size and performance optimization
- Background capture threads, health monitor, statistics engine
- UI capture page with controls and interface selector

#### Part 2B — Protocol Analysis
- Packet parser with protocol decoder (L2/L3/L4/L7)
- Metadata extraction for common protocols
- Live packet viewer with table model
- Protocol tree view, hex viewer, packet search
- Advanced filter engine with grammar and compiler
- Bookmarks, notes, packet storage, live updates

#### Part 2C — Analytics Dashboard
- Analytics pipeline with background processing
- Live dashboard with tabbed widgets
- Live charts (PyQtGraph) for bandwidth, protocol distribution, connections
- Host discovery, connection tracker, protocol statistics
- Top talkers analyzer, bandwidth analyzer, session analyzer
- Timeline view, network summary, analytics search

#### Part 3A — Security Monitoring
- Passive security monitoring with rule-based detection
- Anomaly detection (port scan, SYN flood, DNS tunneling, brute force, etc.)
- Alert management with severity, lifecycle, and timeline
- Rule engine for custom detection rules
- Baseline learning for normal traffic patterns
- Network health monitoring and evidence collection
- Security dashboard widgets and host/connection security views

#### Part 3B — Reporting & Cases
- Reporting framework with ReportManager (CRUD, search, JSON persistence)
- Report template system with 10 built-in templates (executive, technical, compliance, etc.)
- Report exporter supporting CSV, JSON, HTML, Markdown, TXT, XML, PCAP metadata
- Case management system with lifecycle tracking
- Evidence management with chain of custody
- Analyst notes with search and categorization
- Bookmark management with folders and tagging
- Investigation timeline with event correlation
- Import/export framework for data exchange

#### Part 3C — Ecosystem & Polish
- Plugin ecosystem with base classes, loader, lifecycle manager, health checks
- Plugin metadata with categories, permissions, dependencies, and API versioning
- Auto-update framework with version checking, SHA-256 verification, and rollback
- Backup and restore system with per-category inclusion, compression, and checksums
- Performance monitor with background thread, psutil metrics, alerts, and ring buffer
- Extended event constants for plugin/update/backup/diagnostics/performance
- New config sections for backup and diagnostics with validation rules
- Build/release scripts and CI/CD release workflow

### Changed
- All components now emit events through the EventBus for loose coupling
- Settings system expanded with backup, diagnostics, and update server configuration
- Events class extended with 30+ event constants across all subsystems

## [0.1.0] - 2025-01-01

### Added
- Initial project structure
- Foundation architecture
