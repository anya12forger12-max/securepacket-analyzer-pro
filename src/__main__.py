"""Module runner for ``python -m src``."""

from __future__ import annotations

import sys

from src.core.app import main

if __name__ == "__main__":
    sys.exit(main())
