"""Compatibility facade for the former ``vacuum_types`` god module.

This module re-exports everything from the ``types_*`` submodules so that
every existing import site (in this package, the HA layer, and tests) keeps
working unchanged. New types should be added to the appropriate
``types_*.py`` submodule, not here.
"""

from __future__ import annotations

from .types_attributes import *
from .types_capability import *
from .types_enums import *
from .types_map import *
from .types_properties import *
from .types_renderer import *
