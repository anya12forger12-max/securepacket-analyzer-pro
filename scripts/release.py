"""Release preparation script for SecurePacket Analyzer Pro.

Handles version bumping, changelog generation, tagging, and release notes.

Usage::

    python scripts/release.py bump 1.1.0
    python scripts/release.py prepare
    python scripts/release.py notes 1.1.0
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = PROJECT_ROOT / "pyproject.toml"
INIT_FILE = PROJECT_ROOT / "src" / "__init__.py"
CHANGELOG = PROJECT_ROOT / "CHANGELOG.md"
DEFAULTS_TOML = PROJECT_ROOT / "src" / "config" / "defaults.toml"


def get_current_version() -> str:
    """Extract current version from __init__.py."""
    content = INIT_FILE.read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*"([^"]+)"', content)
    if match:
        return match.group(1)
    return "0.0.0"


def set_version(version: str) -> None:
    """Update version in all relevant files."""
    # Update __init__.py
    content = INIT_FILE.read_text(encoding="utf-8")
    content = re.sub(r'__version__\s*=\s*"[^"]+"', f'__version__ = "{version}"', content)
    INIT_FILE.write_text(content, encoding="utf-8")
    print(f"Updated __init__.py -> {version}")

    # Update pyproject.toml
    content = PYPROJECT.read_text(encoding="utf-8")
    content = re.sub(r'version\s*=\s*"[^"]+"', f'version = "{version}"', content)
    PYPROJECT.write_text(content, encoding="utf-8")
    print(f"Updated pyproject.toml -> {version}")

    # Update defaults.toml
    content = DEFAULTS_TOML.read_text(encoding="utf-8")
    content = re.sub(r'version\s*=\s*"[^"]+"', f'version = "{version}"', content)
    DEFAULTS_TOML.write_text(content, encoding="utf-8")
    print(f"Updated defaults.toml -> {version}")


def generate_changelog_entry(version: str) -> str:
    """Generate a changelog entry for the new version."""
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"\n## [{version}] - {date}\n\n### Added\n\n- \n\n### Changed\n\n- \n\n### Fixed\n\n- \n\n"


def prepare_release() -> None:
    """Prepare a release: validate, generate changelog entry."""
    version = get_current_version()
    print(f"Preparing release: v{version}")

    # Check for uncommitted changes
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True, text=True, cwd=PROJECT_ROOT
    )
    if result.stdout.strip():
        print("WARNING: Uncommitted changes detected:")
        print(result.stdout[:500])

    # Run tests
    print("\nRunning tests...")
    subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short"],
        cwd=PROJECT_ROOT
    )

    # Generate changelog entry
    entry = generate_changelog_entry(version)
    print(f"\nSuggested changelog entry for v{version}:")
    print(entry)


def create_git_tag(version: str) -> None:
    """Create and push a git tag."""
    tag = f"v{version}"
    print(f"Creating git tag: {tag}")

    subprocess.run(["git", "tag", "-a", tag, "-m", f"Release {tag}"], cwd=PROJECT_ROOT)
    print(f"Tag {tag} created. Push with: git push origin {tag}")


def show_release_notes(version: str) -> None:
    """Display release notes template."""
    print(f"""
====================================
  Release Notes Template
  Version: {version}
====================================

# SecurePacket Analyzer Pro v{version}

## Highlights

- 

## New Features

- 

## Improvements

- 

## Bug Fixes

- 

## Breaking Changes

- None

## Dependencies

- Python >= 3.12
- PySide6 >= 6.6.0
- Scapy >= 2.5.0
- SQLAlchemy >= 2.0.0
- PyQtGraph >= 0.13.0

## Installation

### Windows
Download `SecurePacketAnalyzerPro-{version}-setup.exe`

### Linux
Download the AppImage, DEB, or RPM package

### macOS
Download `SecurePacketAnalyzerPro-{version}.dmg`

### From Source
```
git clone https://github.com/your-org/SecurePacket-Analyzer-Pro.git
cd SecurePacket Analyzer-Pro
pip install -r requirements.txt
python -m src
```

## SHA-256 Checksums

See checksums.txt
""")


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Release management")
    sub = parser.add_subparsers(dest="command")

    bump_cmd = sub.add_parser("bump", help="Bump version")
    bump_cmd.add_argument("version", help="New version (e.g., 1.1.0)")

    sub.add_parser("prepare", help="Prepare release")

    notes_cmd = sub.add_parser("notes", help="Show release notes template")
    notes_cmd.add_argument("version", help="Version number")

    tag_cmd = sub.add_parser("tag", help="Create git tag")
    tag_cmd.add_argument("version", help="Version to tag")

    args = parser.parse_args()

    if args.command == "bump":
        set_version(args.version)
    elif args.command == "prepare":
        prepare_release()
    elif args.command == "notes":
        show_release_notes(args.version)
    elif args.command == "tag":
        create_git_tag(args.version)
    else:
        parser.print_help()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
