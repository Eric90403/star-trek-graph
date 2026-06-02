#!/usr/bin/env python3
"""
src/comic/__init__.py — Comic generation platform for star-trek-graph.

See docs/COMIC_PRODUCTION.md for the design principles this implements.
"""

from .balloons import Balloon, BalloonType, FontRegistry, draw_balloon
from .panels   import to_comic_style

__all__ = [
    "Balloon", "BalloonType", "FontRegistry",
    "draw_balloon", "to_comic_style",
]
