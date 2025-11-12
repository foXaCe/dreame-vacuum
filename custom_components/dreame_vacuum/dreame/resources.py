"""
Lazy loading wrapper for resources.

This module implements lazy loading of large image resources to improve startup time.
Resources are loaded on-demand when first accessed.

Note: When using 'from .resources import *', all resources will be loaded immediately
to support the star import. For better performance, import specific items or use
'import resources' instead.
"""

import sys


def _load_and_expose_all():
    """Load _resources_data and expose all its attributes to this module's namespace."""
    try:
        from . import _resources_data
    except ImportError:
        import _resources_data

    # Get all public attributes from _resources_data
    _all_attrs = [attr for attr in dir(_resources_data) if not attr.startswith("_")]

    # Expose them in this module's namespace
    current_module = sys.modules[__name__]
    for attr in _all_attrs:
        setattr(current_module, attr, getattr(_resources_data, attr))

    # Set __all__ for star imports
    current_module.__all__ = _all_attrs

    return _resources_data


# Load everything immediately to support 'from .resources import *' used in map.py
_load_and_expose_all()
