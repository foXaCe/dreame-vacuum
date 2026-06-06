"""Map module - backward-compatible re-exports.

All classes have been split into submodules for maintainability:
- map_manager: DreameMapVacuumMapManager
- map_editor: DreameMapVacuumMapEditor
- map_decoder: DreameVacuumMapDecoder
- map_data_json_renderer: DreameVacuumMapDataJsonRenderer
- map_renderer: DreameVacuumMapRenderer
- map_optimizer: DreameVacuumMapOptimizer
"""

from __future__ import annotations

from .map_data_json_renderer import DreameVacuumMapDataJsonRenderer  # noqa: F401
from .map_decoder import DreameVacuumMapDecoder  # noqa: F401
from .map_editor import DreameMapVacuumMapEditor  # noqa: F401
from .map_manager import DreameMapVacuumMapManager  # noqa: F401
from .map_optimizer import DreameVacuumMapOptimizer  # noqa: F401
from .map_renderer import DreameVacuumMapRenderer  # noqa: F401
