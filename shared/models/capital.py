"""
Capital allocation and management models for NEXUS.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from pydantic import Field, computed_field

from shared.models.base import BaseModel


class CapitalPoolType(str, Enum):
    """Type of capital pool."""

    RESERVE = "reserve"  # Emergency margin, float
    ACTIVE = "active"  # Deployed in positions
    PENDING = "pending"  # Allocated to pending opportunities
    TRANSIT = "transit"  # In transit between venues


class AllocationStatus(str, Enum):
    """Status of a capital allocation."""

    RESERVED = "reserved"  # Capital reserved
    DEPLOYED = "deployed"  # Capital in active position
    RELEASING = "releasing"  # Being released from position
    RELEASED = "released"  # Returned to available pool


class CapitalPool(BaseModel):
    """
    A segment of total capital.

    Capital is divided into pools for different purposes.
    """

    pool_type: CapitalPoolType
    total_value_usd: Decimal = Decimal("0")
    allocations: dict[str, Decimal] = Field(
        default_factory=dict, description="Venue -> amount mapping"
    )
    min_required: Decimal = Decimal("0")
    max_allowed: Optional[Decimal] = None

    def get_available(self, venue: Optional[str] = None) -> Decimal:
        """
        Get available capital in this pool.

        Args:
            venue: Optional venue filter

        Returns:
            Available capital
        """
        if venue:
            return self.allocations.get(venue, Decimal("0"))
        return self.total_value_usd

    def allocate(self, venue: str, amount: Decimal) -> bool:
        """
        Allocate capital to a venue.

        Args:
            venue: Venue slug
            amount: Amount to allocate

        Returns:
            True if successful
        """
        if amount > self.total_value_usd:
            return False

        current = self.allocations.get(venue, Decimal("0"))
        self.allocations[venue] = current + amount
        self.total_value_usd -= amount
        return True

    def deallocate(self, venue: str, amount: Decimal) -> bool:
        """
        Deallocate capital from a venue.

        Args:
            venue: Venue slug
            amount: Amount to deallocate

        Returns:
            True if successful
        """
        current = self.allocations.get(venue, Decimal("0"))
        if amount > current:
            return False

        self.allocations[venue] = current - amount
        self.total_value_usd += amount

        # Clean up zero allocations
        if self.allocations[venue] == 0:
            del self.allocations[venue]

        return True


class CapitalAllocation(BaseModel):
    """Record of a capital allocation to an opportunity/position."""

    id: UUID = Field(default_factory=uuid4)
    opportunity_id: Optional[UUID] = None
    position_id: Optional[UUID] = None
    amount_usd: Decimal
    venue: str
    status: AllocationStatus = AllocationStatus.RESERVED
    allocated_at: datetime = Field(default_factory=datetime.utcnow)
    deployed_at: Optional[datetime] = None
    released_at: Optional[datetime] = None
    expiry: Optional[datetime] = None  # For pending allocations

    @property
    def is_expired(self) -> bool:
        """Check if allocation has expired."""
        if self.expiry is None:
            return False
        return (
            datetime.utcnow() > self.expiry and self.status == AllocationStatus.RESERVED
        )


class CapitalTransfer(BaseModel):
    """Record of a capital transfer between venues."""

    id: UUID = Field(default_factory=uuid4)
    from_venue: str
    to_venue: str
    asset: str = "USDT"
    amount: Decimal
    status: str = "pending"  # pending, in_transit, completed, failed
    initiated_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    tx_hash: Optional[str] = None
    fee: Decimal = Decimal("0")
    error_message: Optional[str] = None


class VenueBalance(BaseModel):
    """Balance information for a single venue."""

    venue: str
    balances: dict[str, Decimal] = Field(
        default_factory=dict, description="Asset -> balance mapping"
    )
    total_usd: Decimal = Decimal("0")
    margin_used: Decimal = Decimal("0")
    margin_available: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    last_updated: datetime = Field(default_factory=datetime.utcnow)

    @computed_field
    @property
    def margin_utilization(self) -> Decimal:
        """Calculate margin utilization percentage."""
        total_margin = self.margin_used + self.margin_available
        if total_margin == 0:
            return Decimal("0")
        return self.margin_used / total_margin * 100


class CapitalState(BaseModel):
    """
    Global view of capital across all pools and venues.

    This is the master state for capital allocation decisions.
    """

    # Total Capital
    total_capital_usd: Decimal = Decimal("0")

    # Pools
    reserve_pool: CapitalPool = Field(
        default_factory=lambda: CapitalPool(pool_type=CapitalPoolType.RESERVE)
    )
    active_pool: CapitalPool = Field(
        default_factory=lambda: CapitalPool(pool_type=CapitalPoolType.ACTIVE)
    )
    pending_pool: CapitalPool = Field(
        default_factory=lambda: CapitalPool(pool_type=CapitalPoolType.PENDING)
    )
    transit_pool: CapitalPool = Field(
        default_factory=lambda: CapitalPool(pool_type=CapitalPoolType.TRANSIT)
    )

    # Per-Venue Tracking
    venue_balances: dict[str, VenueBalance] = Field(default_factory=dict)

    # Allocations
    active_allocations: list[CapitalAllocation] = Field(default_factory=list)
    pending_transfers: list[CapitalTransfer] = Field(default_factory=list)

    # Utilization Metrics
    total_utilization_pct: Decimal = Decimal("0")
    venue_utilization: dict[str, Decimal] = Field(default_factory=dict)

    # Configuration
    reserve_pool_target_pct: Decimal = Decimal("20")  # Target 20% in reserve
    max_utilization_pct: Decimal = Decimal("80")  # Max 80% deployed

    # Last Update
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    @computed_field
    @property
    def available_for_allocation(self) -> Decimal:
        """Calculate total capital available for new allocations."""
        # Available = Total - Reserve minimum - Active - Pending - Transit
        reserve_min = self.total_capital_usd * self.reserve_pool_target_pct / 100
        used = (
            self.active_pool.total_value_usd
            + self.pending_pool.total_value_usd
            + self.transit_pool.total_value_usd
        )
        return max(Decimal("0"), self.total_capital_usd - reserve_min - used)

    @computed_field
    @property
    def reserve_pool_health(self) -> str:
        """Check if reserve pool is adequately funded."""
        target = self.total_capital_usd * self.reserve_pool_target_pct / 100
        if self.reserve_pool.total_value_usd >= target:
            return "healthy"
        if self.reserve_pool.total_value_usd >= target * Decimal("0.7"):
            return "low"
        return "critical"

    def refresh_from_venues(self) -> None:
        """Refresh total capital from venue balances."""
        total = Decimal("0")
        for balance in self.venue_balances.values():
            total += balance.total_usd
        self.total_capital_usd = total

        # Update utilization
        if self.total_capital_usd > 0:
            self.total_utilization_pct = (
                self.active_pool.total_value_usd / self.total_capital_usd * 100
            )
        else:
            self.total_utilization_pct = Decimal("0")

    def get_allocatable_for_venue(
        self, venue: str, max_venue_exposure_pct: Decimal
    ) -> Decimal:
        """
        Get maximum allocatable capital for a specific venue.

        Args:
            venue: Venue slug
            max_venue_exposure_pct: Maximum venue exposure limit

        Returns:
            Maximum allocatable amount
        """
        # Overall available
        available = self.available_for_allocation

        # Venue-specific limit
        venue_limit = self.total_capital_usd * max_venue_exposure_pct / 100
        current_venue_exposure = self.venue_utilization.get(venue, Decimal("0"))
        venue_remaining = venue_limit - current_venue_exposure

        return min(available, max(Decimal("0"), venue_remaining))

    def reserve_for_opportunity(
        self,
        opportunity_id: UUID,
        venue: str,
        amount: Decimal,
        expiry_seconds: int = 300,
    ) -> Optional[CapitalAllocation]:
        """
        Reserve capital for a pending opportunity.

        Args:
            opportunity_id: Opportunity ID
            venue: Target venue
            amount: Amount to reserve
            expiry_seconds: Seconds until reservation expires

        Returns:
            Allocation record or None if insufficient capital
        """
        if amount > self.available_for_allocation:
            return None

        allocation = CapitalAllocation(
            opportunity_id=opportunity_id,
            amount_usd=amount,
            venue=venue,
            status=AllocationStatus.RESERVED,
            expiry=datetime.utcnow() + timedelta(seconds=expiry_seconds),
        )

        self.pending_pool.allocate(venue, amount)
        self.active_allocations.append(allocation)

        return allocation

    def confirm_allocation(self, allocation_id: UUID, position_id: UUID) -> bool:
        """
        Confirm a pending allocation and mark it as deployed.

        Args:
            allocation_id: Allocation ID
            position_id: Position that used the capital

        Returns:
            True if successful
        """
        for allocation in self.active_allocations:
            if allocation.id == allocation_id:
                if allocation.status != AllocationStatus.RESERVED:
                    return False

                # Move from pending to active pool
                self.pending_pool.deallocate(allocation.venue, allocation.amount_usd)
                self.active_pool.allocate(allocation.venue, allocation.amount_usd)

                allocation.status = AllocationStatus.DEPLOYED
                allocation.position_id = position_id
                allocation.deployed_at = datetime.utcnow()

                return True

        return False

    def release_allocation(self, allocation_id: UUID) -> bool:
        """
        Release a capital allocation back to available.

        Args:
            allocation_id: Allocation ID

        Returns:
            True if successful
        """
        for allocation in self.active_allocations:
            if allocation.id == allocation_id:
                if allocation.status == AllocationStatus.RESERVED:
                    self.pending_pool.deallocate(
                        allocation.venue, allocation.amount_usd
                    )
                elif allocation.status == AllocationStatus.DEPLOYED:
                    self.active_pool.deallocate(allocation.venue, allocation.amount_usd)
                else:
                    return False

                allocation.status = AllocationStatus.RELEASED
                allocation.released_at = datetime.utcnow()

                return True

        return False

    def cleanup_expired_allocations(self) -> list[UUID]:
        """
        Clean up expired pending allocations.

        Returns:
            List of expired allocation IDs
        """
        expired = []
        for allocation in self.active_allocations:
            if allocation.is_expired:
                self.pending_pool.deallocate(allocation.venue, allocation.amount_usd)
                allocation.status = AllocationStatus.RELEASED
                expired.append(allocation.id)

        return expired


# Import at end to avoid circular import
from datetime import timedelta
