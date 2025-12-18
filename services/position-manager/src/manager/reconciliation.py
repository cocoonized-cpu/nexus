"""
Position Reconciliation Module.

Ensures consistency between local state, database records, and exchange positions.

Features:
- Startup reconciliation to catch orphaned positions
- Periodic sync to detect and correct drift
- Orphan detection and auto-adoption or alerting
- Position state recovery after service restarts
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from shared.utils.config import get_settings
from shared.utils.logging import get_logger
from shared.utils.redis_client import RedisClient

logger = get_logger(__name__)


class ReconciliationAction(str, Enum):
    """Actions taken during reconciliation."""
    ADOPTED = "adopted"  # Orphaned position adopted
    CLOSED = "closed"  # Inconsistent position closed
    UPDATED = "updated"  # Position state updated
    ALERTED = "alerted"  # Manual review required
    NO_ACTION = "no_action"


class DiscrepancyType(str, Enum):
    """Types of discrepancies found."""
    ORPHAN_ON_EXCHANGE = "orphan_on_exchange"  # Position on exchange not in DB
    MISSING_ON_EXCHANGE = "missing_on_exchange"  # Position in DB not on exchange
    SIZE_MISMATCH = "size_mismatch"  # Size differs between DB and exchange
    PRICE_MISMATCH = "price_mismatch"  # Entry price differs significantly
    STATE_MISMATCH = "state_mismatch"  # Status differs (e.g., closed vs active)


@dataclass
class Discrepancy:
    """Represents a discrepancy found during reconciliation."""
    type: DiscrepancyType
    position_id: Optional[str]
    exchange: str
    symbol: str
    db_value: Any
    exchange_value: Any
    severity: str  # "low", "medium", "high", "critical"
    detected_at: datetime = field(default_factory=datetime.utcnow)
    action_taken: Optional[ReconciliationAction] = None
    resolution_notes: Optional[str] = None


@dataclass
class ReconciliationReport:
    """Report from a reconciliation run."""
    started_at: datetime
    completed_at: datetime
    positions_checked: int
    discrepancies_found: int
    discrepancies_resolved: int
    discrepancies_requiring_review: int
    actions_taken: list[dict[str, Any]]
    unresolved: list[Discrepancy]


class PositionReconciliation:
    """
    Reconciles position state across local cache, database, and exchanges.

    Runs:
    - On startup to catch any positions opened while service was down
    - Periodically to detect drift
    - On demand for manual verification
    """

    def __init__(
        self,
        redis: RedisClient,
        db_session_factory: Optional[Callable] = None,
        exchange_clients: Optional[dict] = None,
    ):
        self.redis = redis
        self._db_session_factory = db_session_factory or self._create_db_session_factory()
        self._exchange_clients = exchange_clients or {}

        # Configuration
        self._reconciliation_interval = 300  # 5 minutes
        self._size_tolerance_pct = Decimal("0.01")  # 1% tolerance for size differences
        self._price_tolerance_pct = Decimal("0.02")  # 2% tolerance for price differences
        self._auto_adopt_orphans = True  # Automatically adopt orphaned positions
        self._max_orphan_age_hours = 24  # Only auto-adopt positions < 24 hours old

        # State
        self._running = False
        self._last_reconciliation: Optional[datetime] = None
        self._pending_discrepancies: list[Discrepancy] = []

    def _create_db_session_factory(self) -> Callable:
        """Create database session factory."""
        settings = get_settings()
        engine = create_async_engine(
            settings.database_url,
            pool_size=5,
            max_overflow=10,
        )
        return async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    async def start(self) -> None:
        """Start reconciliation service."""
        self._running = True
        logger.info("Position Reconciliation service started")

    async def stop(self) -> None:
        """Stop reconciliation service."""
        self._running = False
        logger.info("Position Reconciliation service stopped")

    async def run_startup_reconciliation(self) -> ReconciliationReport:
        """
        Run full reconciliation on startup.

        Compares database positions with exchange positions and resolves discrepancies.
        """
        started_at = datetime.utcnow()
        logger.info("Starting startup reconciliation")

        discrepancies: list[Discrepancy] = []
        actions_taken: list[dict[str, Any]] = []
        positions_checked = 0

        try:
            # Get positions from database
            db_positions = await self._get_db_positions()
            positions_checked = len(db_positions)

            # Get positions from each exchange
            exchange_positions = await self._get_all_exchange_positions()

            # Compare and find discrepancies
            discrepancies = await self._compare_positions(db_positions, exchange_positions)

            # Resolve discrepancies
            for discrepancy in discrepancies:
                action = await self._resolve_discrepancy(discrepancy)
                if action:
                    actions_taken.append(action)

            # Store unresolved discrepancies
            self._pending_discrepancies = [
                d for d in discrepancies
                if d.action_taken in [None, ReconciliationAction.ALERTED]
            ]

        except Exception as e:
            logger.error("Startup reconciliation failed", error=str(e))

        completed_at = datetime.utcnow()
        self._last_reconciliation = completed_at

        report = ReconciliationReport(
            started_at=started_at,
            completed_at=completed_at,
            positions_checked=positions_checked,
            discrepancies_found=len(discrepancies),
            discrepancies_resolved=len([d for d in discrepancies if d.action_taken not in [None, ReconciliationAction.ALERTED]]),
            discrepancies_requiring_review=len(self._pending_discrepancies),
            actions_taken=actions_taken,
            unresolved=self._pending_discrepancies,
        )

        logger.info(
            "Startup reconciliation completed",
            positions_checked=positions_checked,
            discrepancies_found=len(discrepancies),
            discrepancies_resolved=report.discrepancies_resolved,
            requiring_review=report.discrepancies_requiring_review,
        )

        # Publish report
        await self._publish_reconciliation_report(report)

        return report

    async def run_periodic_sync(self) -> ReconciliationReport:
        """
        Run periodic sync to detect drift.

        Lighter-weight than full reconciliation - focuses on active positions.
        """
        started_at = datetime.utcnow()
        discrepancies: list[Discrepancy] = []
        actions_taken: list[dict[str, Any]] = []
        positions_checked = 0

        try:
            # Get only active positions from database
            async with self._db_session_factory() as db:
                result = await db.execute(text("""
                    SELECT id, symbol, long_exchange, short_exchange, size,
                           entry_price, status
                    FROM positions.active
                    WHERE status IN ('active', 'opening')
                """))
                db_positions = [dict(row._mapping) for row in result.fetchall()]
                positions_checked = len(db_positions)

            # Quick check against exchange positions
            for pos in db_positions:
                exchange_discrepancies = await self._check_position_on_exchanges(pos)
                discrepancies.extend(exchange_discrepancies)

            # Resolve any critical discrepancies
            for discrepancy in discrepancies:
                if discrepancy.severity in ["high", "critical"]:
                    action = await self._resolve_discrepancy(discrepancy)
                    if action:
                        actions_taken.append(action)

        except Exception as e:
            logger.error("Periodic sync failed", error=str(e))

        completed_at = datetime.utcnow()
        self._last_reconciliation = completed_at

        return ReconciliationReport(
            started_at=started_at,
            completed_at=completed_at,
            positions_checked=positions_checked,
            discrepancies_found=len(discrepancies),
            discrepancies_resolved=len(actions_taken),
            discrepancies_requiring_review=len([d for d in discrepancies if d.severity in ["high", "critical"] and d.action_taken is None]),
            actions_taken=actions_taken,
            unresolved=[d for d in discrepancies if d.action_taken is None],
        )

    async def _get_db_positions(self) -> list[dict[str, Any]]:
        """Get all active positions from database."""
        try:
            async with self._db_session_factory() as db:
                result = await db.execute(text("""
                    SELECT
                        id, symbol, opportunity_id, long_exchange, short_exchange,
                        size, entry_price, status, opened_at,
                        total_capital_deployed
                    FROM positions.active
                    WHERE status IN ('pending', 'opening', 'active', 'closing')
                """))
                return [dict(row._mapping) for row in result.fetchall()]
        except Exception as e:
            logger.error("Failed to get DB positions", error=str(e))
            return []

    async def _get_all_exchange_positions(self) -> dict[str, list[dict[str, Any]]]:
        """Get positions from all connected exchanges."""
        exchange_positions: dict[str, list[dict[str, Any]]] = {}

        for exchange_name, client in self._exchange_clients.items():
            try:
                positions = await client.get_positions()
                exchange_positions[exchange_name] = positions
            except Exception as e:
                logger.warning(
                    "Failed to get positions from exchange",
                    exchange=exchange_name,
                    error=str(e),
                )
                exchange_positions[exchange_name] = []

        return exchange_positions

    async def _compare_positions(
        self,
        db_positions: list[dict[str, Any]],
        exchange_positions: dict[str, list[dict[str, Any]]],
    ) -> list[Discrepancy]:
        """Compare database positions with exchange positions."""
        discrepancies: list[Discrepancy] = []

        # Index DB positions by exchange and symbol
        db_by_exchange: dict[str, dict[str, dict]] = {}
        for pos in db_positions:
            for exchange_type in ["long_exchange", "short_exchange"]:
                exchange = pos.get(exchange_type)
                if exchange:
                    if exchange not in db_by_exchange:
                        db_by_exchange[exchange] = {}
                    db_by_exchange[exchange][pos["symbol"]] = pos

        # Check for orphans on exchange (positions on exchange not in DB)
        for exchange, positions in exchange_positions.items():
            db_symbols = set(db_by_exchange.get(exchange, {}).keys())

            for ex_pos in positions:
                symbol = ex_pos.get("symbol", "")
                size = Decimal(str(ex_pos.get("size", 0)))

                if abs(size) < Decimal("0.0001"):
                    continue  # Skip dust positions

                if symbol not in db_symbols:
                    discrepancies.append(Discrepancy(
                        type=DiscrepancyType.ORPHAN_ON_EXCHANGE,
                        position_id=None,
                        exchange=exchange,
                        symbol=symbol,
                        db_value=None,
                        exchange_value={
                            "size": float(size),
                            "entry_price": ex_pos.get("entry_price"),
                            "unrealized_pnl": ex_pos.get("unrealized_pnl"),
                        },
                        severity="high",
                    ))

        # Check for missing on exchange (DB positions not found on exchange)
        for pos in db_positions:
            if pos.get("status") not in ["active", "opening"]:
                continue

            for exchange_type in ["long_exchange", "short_exchange"]:
                exchange = pos.get(exchange_type)
                if not exchange:
                    continue

                ex_positions = exchange_positions.get(exchange, [])
                symbol = pos["symbol"]

                found = any(
                    ep.get("symbol") == symbol and abs(Decimal(str(ep.get("size", 0)))) > Decimal("0.0001")
                    for ep in ex_positions
                )

                if not found and pos.get("status") == "active":
                    discrepancies.append(Discrepancy(
                        type=DiscrepancyType.MISSING_ON_EXCHANGE,
                        position_id=str(pos["id"]),
                        exchange=exchange,
                        symbol=symbol,
                        db_value={
                            "size": float(pos.get("size", 0)),
                            "status": pos.get("status"),
                        },
                        exchange_value=None,
                        severity="critical",
                    ))

        # Check for size mismatches
        for pos in db_positions:
            if pos.get("status") != "active":
                continue

            for exchange_type, side in [("long_exchange", "long"), ("short_exchange", "short")]:
                exchange = pos.get(exchange_type)
                if not exchange:
                    continue

                ex_positions = exchange_positions.get(exchange, [])
                symbol = pos["symbol"]
                db_size = Decimal(str(pos.get("size", 0)))

                for ex_pos in ex_positions:
                    if ex_pos.get("symbol") != symbol:
                        continue

                    ex_size = abs(Decimal(str(ex_pos.get("size", 0))))

                    # Check for size mismatch
                    if db_size > 0:
                        size_diff_pct = abs(db_size - ex_size) / db_size
                        if size_diff_pct > self._size_tolerance_pct:
                            discrepancies.append(Discrepancy(
                                type=DiscrepancyType.SIZE_MISMATCH,
                                position_id=str(pos["id"]),
                                exchange=exchange,
                                symbol=symbol,
                                db_value=float(db_size),
                                exchange_value=float(ex_size),
                                severity="medium" if size_diff_pct < Decimal("0.1") else "high",
                            ))

        return discrepancies

    async def _check_position_on_exchanges(
        self,
        position: dict[str, Any],
    ) -> list[Discrepancy]:
        """Check a single position against exchanges."""
        discrepancies: list[Discrepancy] = []

        for exchange_type in ["long_exchange", "short_exchange"]:
            exchange = position.get(exchange_type)
            if not exchange or exchange not in self._exchange_clients:
                continue

            try:
                client = self._exchange_clients[exchange]
                ex_positions = await client.get_positions()

                symbol = position["symbol"]
                db_size = Decimal(str(position.get("size", 0)))

                found = False
                for ex_pos in ex_positions:
                    if ex_pos.get("symbol") != symbol:
                        continue

                    found = True
                    ex_size = abs(Decimal(str(ex_pos.get("size", 0))))

                    if db_size > 0:
                        size_diff_pct = abs(db_size - ex_size) / db_size
                        if size_diff_pct > self._size_tolerance_pct:
                            discrepancies.append(Discrepancy(
                                type=DiscrepancyType.SIZE_MISMATCH,
                                position_id=str(position["id"]),
                                exchange=exchange,
                                symbol=symbol,
                                db_value=float(db_size),
                                exchange_value=float(ex_size),
                                severity="medium" if size_diff_pct < Decimal("0.1") else "high",
                            ))
                    break

                if not found and position.get("status") == "active":
                    discrepancies.append(Discrepancy(
                        type=DiscrepancyType.MISSING_ON_EXCHANGE,
                        position_id=str(position["id"]),
                        exchange=exchange,
                        symbol=symbol,
                        db_value={"status": position.get("status")},
                        exchange_value=None,
                        severity="critical",
                    ))

            except Exception as e:
                logger.warning(
                    "Failed to check position on exchange",
                    exchange=exchange,
                    position_id=position.get("id"),
                    error=str(e),
                )

        return discrepancies

    async def _resolve_discrepancy(self, discrepancy: Discrepancy) -> Optional[dict[str, Any]]:
        """Attempt to automatically resolve a discrepancy."""
        action_result = {
            "discrepancy_type": discrepancy.type.value,
            "exchange": discrepancy.exchange,
            "symbol": discrepancy.symbol,
            "action": None,
            "success": False,
            "notes": "",
        }

        try:
            if discrepancy.type == DiscrepancyType.ORPHAN_ON_EXCHANGE:
                # Handle orphaned position
                if self._auto_adopt_orphans:
                    adopted = await self._adopt_orphan_position(discrepancy)
                    if adopted:
                        discrepancy.action_taken = ReconciliationAction.ADOPTED
                        action_result["action"] = "adopted"
                        action_result["success"] = True
                        action_result["notes"] = "Orphaned position adopted into tracking"
                    else:
                        discrepancy.action_taken = ReconciliationAction.ALERTED
                        action_result["action"] = "alerted"
                        action_result["notes"] = "Could not auto-adopt, requires manual review"
                else:
                    discrepancy.action_taken = ReconciliationAction.ALERTED
                    action_result["action"] = "alerted"
                    action_result["notes"] = "Auto-adopt disabled, requires manual review"

            elif discrepancy.type == DiscrepancyType.MISSING_ON_EXCHANGE:
                # Position in DB but not on exchange - likely already closed
                updated = await self._mark_position_closed(discrepancy)
                if updated:
                    discrepancy.action_taken = ReconciliationAction.UPDATED
                    action_result["action"] = "updated"
                    action_result["success"] = True
                    action_result["notes"] = "Position marked as closed in database"
                else:
                    discrepancy.action_taken = ReconciliationAction.ALERTED
                    action_result["action"] = "alerted"
                    action_result["notes"] = "Could not update, requires manual review"

            elif discrepancy.type == DiscrepancyType.SIZE_MISMATCH:
                # Size mismatch - update DB to match exchange
                if discrepancy.severity != "critical":
                    updated = await self._update_position_size(discrepancy)
                    if updated:
                        discrepancy.action_taken = ReconciliationAction.UPDATED
                        action_result["action"] = "updated"
                        action_result["success"] = True
                        action_result["notes"] = f"Size updated from {discrepancy.db_value} to {discrepancy.exchange_value}"
                    else:
                        discrepancy.action_taken = ReconciliationAction.ALERTED
                        action_result["action"] = "alerted"
                else:
                    discrepancy.action_taken = ReconciliationAction.ALERTED
                    action_result["action"] = "alerted"
                    action_result["notes"] = "Critical size mismatch requires manual review"

            else:
                discrepancy.action_taken = ReconciliationAction.ALERTED
                action_result["action"] = "alerted"
                action_result["notes"] = "Unknown discrepancy type"

        except Exception as e:
            logger.error(
                "Failed to resolve discrepancy",
                discrepancy_type=discrepancy.type.value,
                error=str(e),
            )
            discrepancy.action_taken = ReconciliationAction.ALERTED
            action_result["action"] = "error"
            action_result["notes"] = str(e)

        return action_result

    async def _adopt_orphan_position(self, discrepancy: Discrepancy) -> bool:
        """Adopt an orphaned position found on exchange."""
        try:
            exchange_data = discrepancy.exchange_value
            if not exchange_data:
                return False

            async with self._db_session_factory() as db:
                # Create new position record
                await db.execute(text("""
                    INSERT INTO positions.active (
                        symbol, long_exchange, short_exchange, size,
                        entry_price, status, opened_at, notes
                    ) VALUES (
                        :symbol, :exchange, '', :size,
                        :price, 'active', NOW(), 'Adopted from exchange during reconciliation'
                    )
                """), {
                    "symbol": discrepancy.symbol,
                    "exchange": discrepancy.exchange,
                    "size": exchange_data.get("size", 0),
                    "price": exchange_data.get("entry_price", 0),
                })
                await db.commit()

            logger.info(
                "Adopted orphan position",
                exchange=discrepancy.exchange,
                symbol=discrepancy.symbol,
            )
            return True

        except Exception as e:
            logger.error("Failed to adopt orphan position", error=str(e))
            return False

    async def _mark_position_closed(self, discrepancy: Discrepancy) -> bool:
        """Mark a position as closed in the database."""
        try:
            if not discrepancy.position_id:
                return False

            async with self._db_session_factory() as db:
                await db.execute(text("""
                    UPDATE positions.active
                    SET status = 'closed',
                        closed_at = NOW(),
                        exit_reason = 'reconciliation_missing_on_exchange'
                    WHERE id = :position_id
                """), {"position_id": discrepancy.position_id})
                await db.commit()

            logger.info(
                "Marked position as closed",
                position_id=discrepancy.position_id,
                reason="missing_on_exchange",
            )
            return True

        except Exception as e:
            logger.error("Failed to mark position closed", error=str(e))
            return False

    async def _update_position_size(self, discrepancy: Discrepancy) -> bool:
        """Update position size in database to match exchange."""
        try:
            if not discrepancy.position_id:
                return False

            async with self._db_session_factory() as db:
                await db.execute(text("""
                    UPDATE positions.active
                    SET size = :new_size,
                        notes = COALESCE(notes, '') || ' Size corrected during reconciliation.'
                    WHERE id = :position_id
                """), {
                    "position_id": discrepancy.position_id,
                    "new_size": discrepancy.exchange_value,
                })
                await db.commit()

            logger.info(
                "Updated position size",
                position_id=discrepancy.position_id,
                old_size=discrepancy.db_value,
                new_size=discrepancy.exchange_value,
            )
            return True

        except Exception as e:
            logger.error("Failed to update position size", error=str(e))
            return False

    async def _publish_reconciliation_report(self, report: ReconciliationReport) -> None:
        """Publish reconciliation report to Redis."""
        import json

        report_data = {
            "started_at": report.started_at.isoformat(),
            "completed_at": report.completed_at.isoformat(),
            "positions_checked": report.positions_checked,
            "discrepancies_found": report.discrepancies_found,
            "discrepancies_resolved": report.discrepancies_resolved,
            "discrepancies_requiring_review": report.discrepancies_requiring_review,
            "actions_taken": report.actions_taken,
        }

        await self.redis.set(
            "nexus:reconciliation:last_report",
            json.dumps(report_data),
        )

        if report.discrepancies_requiring_review > 0:
            # Publish alert
            await self.redis.publish(
                "nexus:reconciliation:alert",
                json.dumps({
                    "type": "reconciliation_discrepancies",
                    "count": report.discrepancies_requiring_review,
                    "severity": "warning",
                    "message": f"Reconciliation found {report.discrepancies_requiring_review} discrepancies requiring review",
                }),
            )

    def get_pending_discrepancies(self) -> list[dict[str, Any]]:
        """Get pending discrepancies for API."""
        return [
            {
                "type": d.type.value,
                "position_id": d.position_id,
                "exchange": d.exchange,
                "symbol": d.symbol,
                "db_value": d.db_value,
                "exchange_value": d.exchange_value,
                "severity": d.severity,
                "detected_at": d.detected_at.isoformat(),
            }
            for d in self._pending_discrepancies
        ]

    def get_last_reconciliation(self) -> Optional[str]:
        """Get timestamp of last reconciliation."""
        return self._last_reconciliation.isoformat() if self._last_reconciliation else None
