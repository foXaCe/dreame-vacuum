"""
Patch for python-miio to fix Python 3.13 FutureWarning.

This suppresses the FutureWarning about functools.partial in enums
that is emitted by python-miio on Python 3.13.

This patch can be removed once python-miio releases a version including
the fix from PR #1993: https://github.com/rytilahti/python-miio/pull/1993
"""

import logging
import sys
import warnings

_LOGGER = logging.getLogger(__name__)


def apply_miio_patch():
    """
    Apply patch to suppress python-miio Python 3.13 FutureWarning.

    Filters out the specific warning about functools.partial that
    comes from miio/miot_device.py line 23.
    """

    # Only apply patch on Python 3.13+
    if sys.version_info < (3, 13):
        return

    try:
        # Add a filter to suppress the specific FutureWarning from miio
        warnings.filterwarnings(
            "ignore",
            category=FutureWarning,
            message=r".*functools\.partial will be a method descriptor.*",
            module=r"miio\.miot_device",
        )

        _LOGGER.debug("Applied warning filter for python-miio Python 3.13 compatibility")

    except Exception as e:
        _LOGGER.warning(f"Error applying miio warning filter: {e}")
