from __future__ import annotations

"""
Pytest configuration helpers.

Ensures the repository root is importable regardless of how pytest was invoked.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
