"""Common fixtures for Dreame Vacuum tests."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_dreame_vacuum_protocol() -> Generator[MagicMock, None, None]:
    """Mock DreameVacuumProtocol."""
    with patch("custom_components.dreame_vacuum.config_flow.DreameVacuumProtocol") as mock_protocol:
        protocol = MagicMock()
        protocol.cloud = MagicMock()
        protocol.cloud.logged_in = True
        protocol.cloud.captcha_img = None
        protocol.cloud.verification_url = None
        protocol.cloud.auth_key = "test_auth_key"
        protocol.cloud.get_supported_devices = MagicMock(
            return_value=(
                {
                    "test_device": {
                        "mac": "AA:BB:CC:DD:EE:FF",
                        "model": "dreame.vacuum.test",
                        "name": "Test Vacuum",
                        "did": "123456789",
                        "bindDomain": "192.168.1.100",
                        "customName": "My Vacuum",
                        "deviceInfo": {"displayName": "Dreame Test"},
                    }
                },
                {},
            )
        )
        mock_protocol.return_value = protocol
        yield mock_protocol
