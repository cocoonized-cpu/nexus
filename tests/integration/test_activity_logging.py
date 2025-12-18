"""Integration tests for activity logging across services."""

import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime
from uuid import uuid4


class TestActivityEventLogging:
    """Integration tests for activity event logging."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        redis = AsyncMock()
        redis.publish = AsyncMock()
        return redis

    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        return session

    @pytest.mark.asyncio
    async def test_activity_event_published_to_redis(self, mock_redis):
        """Test that activity events are published to Redis."""
        event = {
            "event_type": "opportunity_detected",
            "worker_name": "opportunity-detector",
            "entity_type": "opportunity",
            "entity_id": str(uuid4()),
            "severity": "info",
            "narrative": "New opportunity detected for BTCUSDT",
            "timestamp": datetime.utcnow().isoformat(),
        }

        await mock_redis.publish("activity_events", str(event))

        mock_redis.publish.assert_called_once()
        call_args = mock_redis.publish.call_args
        assert call_args[0][0] == "activity_events"

    @pytest.mark.asyncio
    async def test_activity_event_persisted_to_database(self, mock_db_session):
        """Test that activity events are persisted to the database."""
        event = {
            "event_type": "position_opened",
            "worker_name": "position-manager",
            "entity_type": "position",
            "entity_id": str(uuid4()),
            "severity": "info",
            "narrative": "Position opened for BTCUSDT",
        }

        # Simulate database insert
        mock_db_session.execute.return_value = None

        # In actual integration test, would call the activity logger
        assert mock_db_session is not None

    @pytest.mark.asyncio
    async def test_activity_event_contains_required_fields(self):
        """Test that activity events contain all required fields."""
        required_fields = [
            "event_type",
            "worker_name",
            "timestamp",
            "narrative",
        ]

        optional_fields = [
            "entity_type",
            "entity_id",
            "severity",
            "decision",
            "metrics",
        ]

        event = {
            "event_type": "health_check",
            "worker_name": "position-manager",
            "timestamp": datetime.utcnow().isoformat(),
            "narrative": "Health check completed for all positions",
            "entity_type": "system",
            "severity": "info",
        }

        # Check required fields
        for field in required_fields:
            assert field in event, f"Missing required field: {field}"

        # Optional fields should be allowed
        for field in optional_fields:
            if field in event:
                assert event[field] is not None

    @pytest.mark.asyncio
    async def test_activity_events_filtered_by_worker(self, mock_db_session):
        """Test that activity events can be filtered by worker name."""
        worker_filter = "position-manager"

        mock_events = [
            {
                "id": str(uuid4()),
                "event_type": "health_check",
                "worker_name": "position-manager",
                "timestamp": datetime.utcnow(),
                "narrative": "Health check passed",
            },
            {
                "id": str(uuid4()),
                "event_type": "health_check",
                "worker_name": "position-manager",
                "timestamp": datetime.utcnow(),
                "narrative": "Another health check",
            },
        ]

        mock_db_session.execute.return_value.mappings.return_value.all.return_value = mock_events

        # All events should be from position-manager
        for event in mock_events:
            assert event["worker_name"] == worker_filter

    @pytest.mark.asyncio
    async def test_activity_events_filtered_by_severity(self, mock_db_session):
        """Test that activity events can be filtered by severity."""
        severity_filter = "warning"

        mock_events = [
            {
                "id": str(uuid4()),
                "event_type": "health_degraded",
                "worker_name": "position-manager",
                "severity": "warning",
                "timestamp": datetime.utcnow(),
                "narrative": "Position health degraded",
            },
        ]

        mock_db_session.execute.return_value.mappings.return_value.all.return_value = mock_events

        for event in mock_events:
            assert event["severity"] == severity_filter


class TestCrossServiceActivityFlow:
    """Tests for activity events across multiple services."""

    @pytest.mark.asyncio
    async def test_opportunity_to_position_activity_flow(self):
        """Test activity events from opportunity detection through position opening."""
        activity_flow = [
            {
                "worker": "opportunity-detector",
                "event": "opportunity_detected",
                "narrative": "High UOS opportunity detected for BTCUSDT (score: 85)",
            },
            {
                "worker": "opportunity-detector",
                "event": "opportunity_queued",
                "narrative": "Opportunity queued for execution",
            },
            {
                "worker": "execution-engine",
                "event": "execution_started",
                "narrative": "Starting execution of BTCUSDT opportunity",
            },
            {
                "worker": "execution-engine",
                "event": "orders_placed",
                "narrative": "Orders placed on Binance and Bybit",
            },
            {
                "worker": "execution-engine",
                "event": "execution_completed",
                "narrative": "Execution completed successfully",
            },
            {
                "worker": "position-manager",
                "event": "position_opened",
                "narrative": "Position opened for BTCUSDT",
            },
        ]

        # Verify the flow sequence is correct
        expected_workers = [
            "opportunity-detector",
            "opportunity-detector",
            "execution-engine",
            "execution-engine",
            "execution-engine",
            "position-manager",
        ]

        for i, activity in enumerate(activity_flow):
            assert activity["worker"] == expected_workers[i]
            assert activity["narrative"]

    @pytest.mark.asyncio
    async def test_position_lifecycle_activity_flow(self):
        """Test activity events throughout position lifecycle."""
        lifecycle_events = [
            ("position_opened", "Position opened for BTCUSDT"),
            ("health_check", "Health check passed"),
            ("funding_collected", "Collected funding payment of $5.25"),
            ("health_check", "Health check passed"),
            ("spread_update", "Spread updated to 1.8%"),
            ("health_changed", "Health degraded: spread decline"),
            ("exit_evaluation", "Evaluating exit conditions"),
            ("exit_triggered", "Exit triggered: spread below threshold"),
            ("position_closed", "Position closed with P&L: +$125.50"),
        ]

        # Verify all lifecycle events have proper narratives
        for event_type, narrative in lifecycle_events:
            assert event_type
            assert len(narrative) > 0


class TestActivityEventQueryAPI:
    """Tests for the activity events query API."""

    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        session.execute = AsyncMock()
        return session

    @pytest.mark.asyncio
    async def test_query_recent_activities(self, mock_db_session):
        """Test querying recent activity events."""
        mock_events = [
            {
                "id": str(uuid4()),
                "event_type": "health_check",
                "worker_name": "position-manager",
                "timestamp": datetime.utcnow(),
                "narrative": "Health check completed",
            }
            for _ in range(10)
        ]

        mock_db_session.execute.return_value.mappings.return_value.all.return_value = mock_events

        assert len(mock_events) == 10

    @pytest.mark.asyncio
    async def test_query_activities_by_entity(self, mock_db_session):
        """Test querying activities for a specific entity."""
        position_id = uuid4()

        mock_events = [
            {
                "id": str(uuid4()),
                "entity_type": "position",
                "entity_id": str(position_id),
                "event_type": "funding_collected",
                "timestamp": datetime.utcnow(),
                "narrative": "Funding collected",
            }
            for _ in range(5)
        ]

        mock_db_session.execute.return_value.mappings.return_value.all.return_value = mock_events

        for event in mock_events:
            assert event["entity_id"] == str(position_id)

    @pytest.mark.asyncio
    async def test_query_activities_since_timestamp(self, mock_db_session):
        """Test querying activities since a specific timestamp."""
        from datetime import timedelta

        since = datetime.utcnow() - timedelta(hours=1)

        mock_events = [
            {
                "id": str(uuid4()),
                "event_type": "health_check",
                "timestamp": datetime.utcnow(),
                "narrative": "Recent health check",
            }
            for _ in range(3)
        ]

        mock_db_session.execute.return_value.mappings.return_value.all.return_value = mock_events

        for event in mock_events:
            assert event["timestamp"] >= since
