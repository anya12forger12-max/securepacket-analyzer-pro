# SecurePacket Analyzer Pro

<p align="center">
  <img src="assets/icons/app_logo.png" alt="SecurePacket Analyzer Pro Logo" width="128" height="128">
</p>

<p align="center">
  <strong>Professional-Grade Network Packet Analysis Platform</strong>
</p>

<p align="center">
  <a href="#features">Features</a> •
  <a href="#installation">Installation</a> •
  <a href="#building">Building</a> •
  <a href="#running">Running</a> •
  <a href="#documentation">Documentation</a> •
  <a href="#contributing">Contributing</a> •
  <a href="#license">License</a>
</p>

---

## Overview

SecurePacket Analyzer Pro is a modern, cross-platform desktop application for network packet sniffing and traffic analysis. Built with Python and Scapy, it emphasizes defensive network monitoring, protocol analysis, accessibility, maintainability, security, and performance.

> **Disclaimer:** This application is intended only for monitoring networks that you own or are authorized to analyze. Always obtain proper authorization before capturing network traffic.

## Features

- **Real-time Packet Capture** — Passive network sniffing with Scapy, live packet streaming
- **Protocol Analysis** — Deep L2/L3/L4/L7 protocol decoding with protocol tree and hex viewer
- **Analytics Dashboard** — Live charts (bandwidth, protocol distribution, connections), top talkers, session analysis
- **Security Monitoring** — Passive anomaly detection, rule engine, baseline learning, evidence collection
- **Reporting & Cases** — 10 built-in report templates, case management, evidence tracking, 8 export formats
- **Plugin Ecosystem** — Extend with custom protocol decoders and analyzers via plugin API
- **Auto-Update** — Background version checking with SHA-256 verification and rollback
- **Backup & Restore** — Automated backups with per-category inclusion and compression
- **Advanced Filtering** — Grammar-based filter compiler with bookmarks and notes
- **Multi-Workspace Support** — Manage multiple analysis sessions independently
- **Accessibility-First Design** — WCAG 2.2 AA compliant with keyboard navigation, screen readers, high-contrast themes
- **Cross-Platform** — Native experience on Windows, macOS, and Linux with platform-specific installers
- **Highly Configurable** — TOML defaults + JSON user overrides with full validation
- **Secure by Default** — No telemetry, no external connections, encrypted config support, input validation
- **Enterprise-Grade** — Thread-safe, performant, designed for millions of packets

## Screenshots

<p align="center">
  <em>Screenshots will be added in future releases.</em>
</p>

## Installation

### Prerequisites

- Python 3.12 or higher
- pip (Python package manager)
- Administrative/root privileges (required for packet capture)

### From Source

```bash
# Clone the repository
git clone https://github.com/your-org/SecurePacket-Analyzer-Pro.git
cd SecurePacket-Analyzer-Pro

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt

# Run the application
python -m src
```

### From Release

Download the latest release for your platform from the [Releases](https://github.com/your-org/SecurePacket-Analyzer-Pro/releases) page.

| Platform | Format |
|----------|--------|
| Windows  | `.exe` installer, `.msi`, Portable ZIP |
| Linux    | AppImage, Flatpak, Snap, `.deb`, `.rpm` |
| macOS    | `.dmg` |

## Building

```bash
# Install development dependencies
pip install -r requirements-dev.txt

# Build platform package
python scripts/build.py --platform auto
```

See [docs/building.md](docs/building.md) for detailed build instructions.

## Running

```bash
# Standard launch
python -m src

# With verbose logging
python -m src --log-level DEBUG

# With a specific config file
python -m src --config /path/to/config.toml
```

## Requirements

### Runtime

| Package | Version |
|---------|---------|
| Python  | >= 3.12 |
| PySide6 | >= 6.6  |
| Scapy   | >= 2.5  |
| SQLAlchemy | >= 2.0 |
| PyQtGraph | >= 0.13 |

### Development

| Package | Purpose |
|---------|---------|
| pytest  | Testing |
| black   | Code formatting |
| isort   | Import sorting |
| ruff    | Linting |
| mypy    | Type checking |
| mkdocs  | Documentation |

## Repository Structure

```
SecurePacket-Analyzer-Pro/
├── src/                    # Main application source
│   ├── core/              # Core application logic
│   ├── capture/           # Packet capture engine
│   ├── analysis/          # Traffic analysis
│   ├── database/          # SQLite + SQLAlchemy
│   ├── gui/               # PySide6 main window
│   ├── widgets/           # Reusable UI widgets
│   ├── dialogs/           # Dialog windows
│   ├── pages/             # Page views
│   ├── models/            # Data models
│   ├── services/          # Business logic services
│   ├── security/          # Security manager
│   ├── plugins/           # Plugin framework
│   ├── reports/           # Report generation
│   ├── exports/           # Export functionality
│   ├── utils/             # Utility functions
│   ├── config/            # Configuration system
│   ├── resources/         # Static resources
│   ├── styles/            # Themes and stylesheets
│   ├── accessibility/     # Accessibility framework
│   ├── logging/           # Logging system
│   ├── diagnostics/       # System diagnostics
│   ├── workspace/         # Workspace management
│   ├── notifications/     # Notification system
│   ├── scheduler/         # Task scheduling
│   └── learning/          # Educational resources
├── tests/                 # Test suite
├── docs/                  # Documentation
├── plugins/               # Plugin directory
├── scripts/               # Build and utility scripts
├── samples/               # Sample captures
├── installers/            # Platform installers
├── assets/                # Static assets
│   ├── themes/           # Theme files
│   ├── icons/            # Application icons
│   ├── fonts/            # Custom fonts
│   └── translations/     # Localization files
├── .github/               # GitHub Actions workflows
├── pyproject.toml         # Project configuration
├── requirements.txt       # Runtime dependencies
└── requirements-dev.txt   # Development dependencies
```

## Roadmap

### Phase 1 — Foundation
- [x] Project architecture and scaffolding
- [x] Configuration system (TOML + JSON with validation)
- [x] Centralized logging with rotation
- [x] Accessibility framework (WCAG 2.2 AA)
- [x] Security manager
- [x] Workspace management
- [x] Plugin framework (backend)
- [x] Diagnostics system
- [x] Notification architecture
- [x] Event bus and service registry
- [x] Session management and auto-save
- [x] Theme engine (dark/light/high-contrast)
- [x] Icon and font systems

### Phase 2 — Core Engine
- [x] Packet capture with Scapy (passive, controller with state machine)
- [x] Network interface detection and management
- [x] Protocol parsing (L2/L3/L4/L7)
- [x] Live packet viewer with table model
- [x] Advanced filter engine with grammar compiler
- [x] Packet bookmarks and notes
- [x] Capture buffer and background threads

### Phase 3 — Analysis
- [x] Live analytics dashboard with tabbed widgets
- [x] Real-time charts (PyQtGraph)
- [x] Host discovery and connection tracking
- [x] Protocol statistics and top talkers
- [x] Bandwidth and session analysis
- [x] Timeline view

### Phase 4 — Security & Reporting
- [x] Passive security monitoring and anomaly detection
- [x] Rule engine and baseline learning
- [x] Network health monitoring and evidence collection
- [x] Report generation (10 templates, 8 export formats)
- [x] Case management and investigation timeline
- [x] Evidence chain of custody
- [x] Analyst notes and bookmarks
- [x] Import/export framework

### Phase 5 — Ecosystem & Polish (Current)
- [x] Plugin ecosystem (base, loader, manager, health checks)
- [x] Auto-update framework with verification and rollback
- [x] Backup and restore system
- [x] Performance monitor with alerts
- [x] Build and release scripts
- [x] CI/CD release workflow
- [x] Comprehensive test suite
- [ ] Full accessibility audit
- [ ] Platform-specific packages (AppImage, DMG, Inno Setup)
- [ ] Documentation site (MkDocs)
- [ ] Localization framework

## Contributing

We welcome contributions! Please read our [Contributing Guide](CONTRIBUTING.md) before submitting a pull request.

## License

This project is licensed under the GNU General Public License v3.0 — see the [LICENSE](LICENSE) file for details.

## FAQ

**Q: Is this legal?**
A: This tool is designed for authorized network monitoring only. You must own the network or have explicit written permission to capture traffic on it.

**Q: Does it support Wi-Fi capture?**
A: Wi-Fi capture support is planned for a future release and may require platform-specific adapters.

**Q: Can I use this commercially?**
A: Yes, under the terms of the GPL v3.0 license.

## Accessibility Statement

SecurePacket Analyzer Pro is committed to ensuring digital accessibility for people with disabilities. We follow WCAG 2.2 AA guidelines and provide:

- Keyboard navigation for all features
- Screen reader compatibility
- High contrast themes
- Adjustable font sizes
- Reduced animation options
- Color-blind friendly palettes

See [docs/accessibility.md](docs/accessibility.md) for details.

## Security Policy

If you discover a security vulnerability, please report it responsibly. See [SECURITY.md](SECURITY.md) for our security policy and reporting instructions.
