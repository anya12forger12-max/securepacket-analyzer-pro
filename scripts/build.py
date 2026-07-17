"""Cross-platform build script for SecurePacket Analyzer Pro.

Supports building:
- Python wheel and sdist
- PyInstaller executable
- Platform-specific packaging

Usage::

    python scripts/build.py --platform auto
    python scripts/build.py --platform windows --format exe
    python scripts/build.py --platform linux --format appimage
    python scripts/build.py --platform macos --format dmg
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

# Project root is one level up from scripts/
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DIST_DIR = PROJECT_ROOT / "dist"
BUILD_DIR = PROJECT_ROOT / "build"
APP_NAME = "SecurePacketAnalyzerPro"
ENTRY_MODULE = "src/__main__.py"


def detect_platform() -> str:
    """Detect the current platform."""
    system = platform.system().lower()
    if system == "linux":
        return "linux"
    if system == "darwin":
        return "macos"
    if system == "windows":
        return "windows"
    return "unknown"


def run_command(cmd: list[str], description: str, cwd: Path | None = None) -> bool:
    """Run a shell command with logging."""
    print(f"\n{'='*60}")
    print(f"  {description}")
    print(f"  Command: {' '.join(cmd)}")
    print(f"{'='*60}")
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd or PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        if result.stdout:
            print(result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"ERROR: {description} failed")
        if e.stdout:
            print(f"STDOUT: {e.stdout[-1000:]}")
        if e.stderr:
            print(f"STDERR: {e.stderr[-1000:]}")
        return False


def clean() -> None:
    """Clean build artifacts."""
    for d in [DIST_DIR, BUILD_DIR]:
        if d.exists():
            shutil.rmtree(d)
            print(f"Cleaned {d}")
    for f in PROJECT_ROOT.glob("*.egg-info"):
        if f.is_dir():
            shutil.rmtree(f)
    print("Clean complete.")


def build_python_packages() -> bool:
    """Build wheel and sdist."""
    return run_command(
        [sys.executable, "-m", "build"],
        "Building Python wheel and sdist",
    )


def build_executable(platform_name: str) -> bool:
    """Build standalone executable with PyInstaller."""
    icon_arg = []
    icon_file = PROJECT_ROOT / "assets" / "icons" / "app.ico"
    if icon_file.exists() and platform_name == "windows":
        icon_arg = ["--icon", str(icon_file)]

    return run_command(
        [
            sys.executable, "-m", "PyInstaller",
            "--onefile",
            "--name", APP_NAME,
            "--clean",
            "--noconfirm",
            "--distpath", str(DIST_DIR / platform_name),
            "--workpath", str(BUILD_DIR / platform_name),
            *icon_arg,
            ENTRY_MODULE,
        ],
        f"Building {platform_name} executable",
    )


def build_windows_installer() -> bool:
    """Build Windows NSIS installer placeholder."""
    print("\n[INFO] Windows installer (NSIS/Inno Setup) requires external tooling.")
    print("       See installers/windows/ for template scripts.")
    return True


def build_linux_packages() -> bool:
    """Build Linux packages."""
    print("\n[INFO] Linux packaging (AppImage, Flatpak, Snap, DEB, RPM)")
    print("       requires external tooling. See installers/linux/.")
    return True


def build_macos_dmg() -> bool:
    """Build macOS DMG."""
    print("\n[INFO] macOS DMG creation requires hdiutil (available on macOS).")
    print("       See installers/macos/ for template scripts.")
    return True


def generate_checksums() -> bool:
    """Generate SHA-256 checksums for all build artifacts."""
    checksum_file = DIST_DIR / "checksums.txt"
    if not DIST_DIR.exists():
        print("No dist/ directory found. Run build first.")
        return False

    lines = []
    for path in sorted(DIST_DIR.rglob("*")):
        if path.is_file() and path.name != "checksums.txt":
            import hashlib
            h = hashlib.sha256()
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    h.update(chunk)
            rel = path.relative_to(DIST_DIR)
            lines.append(f"{h.hexdigest()}  {rel}")

    checksum_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Checksums written to {checksum_file}")
    return True


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Build SecurePacket Analyzer Pro")
    parser.add_argument(
        "--platform",
        choices=["auto", "windows", "linux", "macos"],
        default="auto",
        help="Target platform (default: auto-detect)",
    )
    parser.add_argument(
        "--format",
        choices=["all", "package", "executable"],
        default="all",
        help="Build format (default: all)",
    )
    parser.add_argument("--clean", action="store_true", help="Clean before building")
    args = parser.parse_args()

    platform_name = args.platform if args.platform != "auto" else detect_platform()
    print(f"Building for platform: {platform_name}")
    print(f"Build format: {args.format}")

    if args.clean:
        clean()

    success = True

    if args.format in ("all", "package"):
        success &= build_python_packages()

    if args.format in ("all", "executable"):
        success &= build_executable(platform_name)

        if platform_name == "windows":
            success &= build_windows_installer()
        elif platform_name == "linux":
            success &= build_linux_packages()
        elif platform_name == "macos":
            success &= build_macos_dmg()

    success &= generate_checksums()

    if success:
        print(f"\n{'='*60}")
        print("  Build complete! Artifacts in dist/")
        print(f"{'='*60}")
    else:
        print(f"\n{'='*60}")
        print("  Build completed with errors")
        print(f"{'='*60}")

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
