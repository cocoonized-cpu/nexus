"""Pytest configuration for NEXUS test suite.

This file is loaded by pytest before any test modules are imported.
It sets up the Python path so that service modules can be imported from tests.
"""

import os
import sys
from unittest.mock import MagicMock, patch

# Add service directories to the Python path for imports BEFORE pytest import
# This must happen at the very top of the file before anything else
NEXUS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVICE_DIRS = [
    "services/analytics",
    "services/capital-allocator",
    "services/data-collector",
    "services/execution-engine",
    "services/funding-aggregator",
    "services/gateway",
    "services/notification",
    "services/opportunity-detector",
    "services/position-manager",
    "services/risk-manager",
    "shared",
]

# Perform path manipulation immediately at import time
for service_dir in SERVICE_DIRS:
    service_path = os.path.join(NEXUS_ROOT, service_dir)
    if service_path not in sys.path and os.path.exists(service_path):
        sys.path.insert(0, service_path)

# Also add NEXUS_ROOT itself
if NEXUS_ROOT not in sys.path:
    sys.path.insert(0, NEXUS_ROOT)

import pytest


def pytest_configure(config):
    """Called after command line options have been parsed and all plugins loaded."""
    # Re-add paths in case they got cleared
    for service_dir in SERVICE_DIRS:
        service_path = os.path.join(NEXUS_ROOT, service_dir)
        if service_path not in sys.path and os.path.exists(service_path):
            sys.path.insert(0, service_path)


# Mock database connections to prevent real connections during unit tests
@pytest.fixture(autouse=True)
def mock_db_environment(monkeypatch):
    """Mock database environment variables for testing."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")


# Provide common test fixtures
@pytest.fixture
def mock_async_session():
    """Create a mock async database session."""
    session = MagicMock()
    session.execute = MagicMock()
    session.commit = MagicMock()
    session.rollback = MagicMock()
    session.close = MagicMock()
    return session


@pytest.fixture
def mock_redis_client():
    """Create a mock Redis client."""
    client = MagicMock()
    client.get = MagicMock(return_value=None)
    client.set = MagicMock(return_value=True)
    client.publish = MagicMock(return_value=1)
    client.subscribe = MagicMock()
    return client
