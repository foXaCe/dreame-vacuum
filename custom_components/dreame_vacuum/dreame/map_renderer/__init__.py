"""Map renderer package.

Re-exports :class:`DreameVacuumMapRenderer`. The large implementation used
to live in a single ~5000-line ``map_renderer.py`` module; it has been
moved to ``_core.py`` so future work can split it further (by theme:
shapes, objects, resources, helpers) without touching call sites.

Utility stateless helpers that do not depend on the renderer instance
state are exposed from ``_helpers``.
"""

from __future__ import annotations

from ._core import DreameVacuumMapRenderer

__all__ = ["DreameVacuumMapRenderer"]
