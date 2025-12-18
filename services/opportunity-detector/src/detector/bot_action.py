"""
Bot Action Calculator - Determines why an opportunity is/isn't being traded.

Evaluates all rules that affect whether an opportunity will be auto-traded,
can be manually executed, or is blocked entirely.
"""

from decimal import Decimal
from typing import Any, Optional

from shared.models.opportunity import (
    BotAction,
    BotActionDetail,
    BotActionStatus,
    Opportunity,
)
from shared.utils.logging import get_logger
from shared.utils.system_state import SystemStateManager

logger = get_logger(__name__)


class BotActionCalculator:
    """
    Calculates the bot action status for an opportunity.

    Evaluates rules in priority order:
    1. System state (blocking)
    2. Exchange/symbol checks (blocking)
    3. Quality thresholds (blocking)
    4. Auto-execution eligibility (manual only)
    5. Capital/allocation checks (waiting)
    6. Risk limits (waiting)
    """

    def __init__(
        self,
        state_manager: SystemStateManager,
        config: dict[str, Any],
        exchanges_with_credentials: set[str],
        blacklisted_symbols: set[str],
    ):
        """
        Initialize the calculator.

        Args:
            state_manager: System state manager for checking running/auto-execute status
            config: Opportunity detector configuration
            exchanges_with_credentials: Set of exchange slugs with configured credentials
            blacklisted_symbols: Set of blacklisted symbols
        """
        self.state_manager = state_manager
        self.config = config
        self.exchanges_with_credentials = exchanges_with_credentials
        self.blacklisted_symbols = blacklisted_symbols

    def calculate(
        self,
        opportunity: Opportunity,
        active_coins: int = 0,
        max_coins: int = 5,
        available_capital: Decimal = Decimal("0"),
        has_existing_position: bool = False,
    ) -> BotAction:
        """
        Calculate the bot action status for an opportunity.

        Args:
            opportunity: The opportunity to evaluate
            active_coins: Number of currently active coins (symbols with positions)
            max_coins: Maximum concurrent coins allowed
            available_capital: Available capital for new positions
            has_existing_position: Whether a position already exists for this symbol

        Returns:
            BotAction with status, reason, details, and suggested user action
        """
        details: list[BotActionDetail] = []
        blocking_reasons: list[str] = []
        waiting_reasons: list[str] = []
        manual_reasons: list[str] = []
        user_actions: list[str] = []

        # Get opportunity data
        uos_score = opportunity.uos_score
        symbol = opportunity.symbol
        long_exchange = (
            opportunity.long_leg.exchange
            if opportunity.long_leg
            else opportunity.primary_leg.exchange if opportunity.primary_leg else "unknown"
        )
        short_exchange = (
            opportunity.short_leg.exchange
            if opportunity.short_leg
            else opportunity.hedge_leg.exchange if opportunity.hedge_leg else "unknown"
        )
        spread_pct = float(opportunity.funding_spread_pct or opportunity.gross_funding_rate or 0)
        net_apr = float(opportunity.net_apr or opportunity.estimated_net_apr or 0)

        # ==================== Stage 1: System State Checks ====================

        # Check if system is running
        is_running = self.state_manager.is_running
        details.append(BotActionDetail(
            rule="system_running",
            passed=is_running,
            current="Running" if is_running else "Stopped",
            threshold="Running",
            message="System is running" if is_running else "System is stopped",
        ))
        if not is_running:
            blocking_reasons.append("System is stopped")
            user_actions.append("Start the system in Situation Room")

        # Check circuit breaker
        circuit_breaker_active = getattr(self.state_manager, 'circuit_breaker_active', False)
        details.append(BotActionDetail(
            rule="circuit_breaker",
            passed=not circuit_breaker_active,
            current="Inactive" if not circuit_breaker_active else "Active",
            threshold="Inactive",
            message="Circuit breaker inactive" if not circuit_breaker_active else "Circuit breaker is active",
        ))
        if circuit_breaker_active:
            blocking_reasons.append("Circuit breaker is active")
            user_actions.append("Resolve risk alerts and reset circuit breaker")

        # Check system mode
        mode = getattr(self.state_manager, 'mode', 'live')
        is_discovery = mode == "discovery"
        is_emergency = mode == "emergency"
        details.append(BotActionDetail(
            rule="system_mode",
            passed=not is_discovery and not is_emergency,
            current=mode.capitalize(),
            threshold="Live or Standard",
            message=f"System mode: {mode}" if not is_discovery and not is_emergency else f"System in {mode} mode",
        ))
        if is_discovery:
            blocking_reasons.append("System is in discovery mode (info-only)")
            user_actions.append("Switch to standard mode in Situation Room")
        elif is_emergency:
            blocking_reasons.append("System is in emergency mode")
            user_actions.append("Reset emergency mode in Situation Room")

        # ==================== Stage 2: Exchange/Symbol Checks ====================

        # Check exchange credentials
        long_has_creds = self._exchange_has_credentials(long_exchange)
        short_has_creds = self._exchange_has_credentials(short_exchange)
        both_have_creds = long_has_creds and short_has_creds

        if long_has_creds and short_has_creds:
            creds_message = "Both exchanges have credentials configured"
        elif long_has_creds:
            creds_message = f"Missing credentials for {short_exchange}"
        elif short_has_creds:
            creds_message = f"Missing credentials for {long_exchange}"
        else:
            creds_message = f"Missing credentials for {long_exchange} and {short_exchange}"

        details.append(BotActionDetail(
            rule="exchange_credentials",
            passed=both_have_creds,
            current=f"{long_exchange}: {'Yes' if long_has_creds else 'No'}, {short_exchange}: {'Yes' if short_has_creds else 'No'}",
            threshold="Both exchanges configured",
            message=creds_message,
        ))
        if not both_have_creds:
            missing = []
            if not long_has_creds:
                missing.append(long_exchange)
            if not short_has_creds:
                missing.append(short_exchange)
            blocking_reasons.append(f"Missing API credentials for {', '.join(missing)}")
            user_actions.append(f"Configure API credentials for {', '.join(missing)} in Settings")

        # Check symbol blacklist
        is_blacklisted = symbol.upper() in self.blacklisted_symbols or symbol in self.blacklisted_symbols
        details.append(BotActionDetail(
            rule="symbol_blacklist",
            passed=not is_blacklisted,
            current="Not blacklisted" if not is_blacklisted else "Blacklisted",
            threshold="Not blacklisted",
            message=f"{symbol} is allowed" if not is_blacklisted else f"{symbol} is blacklisted",
        ))
        if is_blacklisted:
            blocking_reasons.append(f"{symbol} is blacklisted")
            user_actions.append(f"Remove {symbol} from blacklist in Settings")

        # ==================== Stage 3: Quality Thresholds ====================

        min_uos = self.config.get("min_uos_score", 50)
        uos_passes_min = uos_score >= min_uos
        details.append(BotActionDetail(
            rule="uos_score_minimum",
            passed=uos_passes_min,
            current=str(uos_score),
            threshold=str(min_uos),
            message=f"UOS score {uos_score} {'meets' if uos_passes_min else 'below'} minimum ({min_uos})",
        ))
        if not uos_passes_min:
            blocking_reasons.append(f"UOS score {uos_score} below minimum threshold ({min_uos})")

        min_spread = self.config.get("min_spread_pct", 0.01)
        spread_passes = spread_pct >= min_spread
        details.append(BotActionDetail(
            rule="spread_minimum",
            passed=spread_passes,
            current=f"{spread_pct:.4f}%",
            threshold=f"{min_spread:.4f}%",
            message=f"Spread {spread_pct:.4f}% {'meets' if spread_passes else 'below'} minimum ({min_spread}%)",
        ))
        if not spread_passes:
            blocking_reasons.append(f"Spread {spread_pct:.4f}% below minimum ({min_spread}%)")

        min_apr = self.config.get("min_net_apr_pct", 10.0)
        apr_passes = net_apr >= min_apr
        details.append(BotActionDetail(
            rule="apr_minimum",
            passed=apr_passes,
            current=f"{net_apr:.1f}%",
            threshold=f"{min_apr:.1f}%",
            message=f"Net APR {net_apr:.1f}% {'meets' if apr_passes else 'below'} minimum ({min_apr}%)",
        ))
        if not apr_passes:
            blocking_reasons.append(f"Net APR {net_apr:.1f}% below minimum ({min_apr}%)")

        # ==================== Stage 4: Auto-Execution Eligibility ====================

        auto_execute_enabled = self.state_manager.auto_execute
        details.append(BotActionDetail(
            rule="auto_execute_enabled",
            passed=auto_execute_enabled,
            current="Enabled" if auto_execute_enabled else "Disabled",
            threshold="Enabled",
            message="Auto-execute is enabled" if auto_execute_enabled else "Auto-execute is disabled",
        ))
        if not auto_execute_enabled:
            manual_reasons.append("Auto-execute is disabled")
            user_actions.append("Enable auto-execute in Situation Room for automatic trading")

        min_auto_uos = self.config.get("min_uos_auto_execute", 75)
        uos_passes_auto = uos_score >= min_auto_uos
        details.append(BotActionDetail(
            rule="uos_score_auto_execute",
            passed=uos_passes_auto,
            current=str(uos_score),
            threshold=str(min_auto_uos),
            message=f"UOS score {uos_score} {'meets' if uos_passes_auto else 'below'} auto-execute threshold ({min_auto_uos})",
        ))
        if not uos_passes_auto and auto_execute_enabled:
            manual_reasons.append(f"UOS score {uos_score} below auto-execute threshold ({min_auto_uos})")

        # ==================== Stage 5: Capital/Allocation Checks ====================

        # Check coin limit
        at_coin_limit = active_coins >= max_coins
        details.append(BotActionDetail(
            rule="coin_limit",
            passed=not at_coin_limit,
            current=f"{active_coins}/{max_coins}",
            threshold=f"< {max_coins}",
            message=f"Active coins: {active_coins}/{max_coins}" if not at_coin_limit else f"At coin limit ({active_coins}/{max_coins})",
        ))
        if at_coin_limit:
            waiting_reasons.append(f"At coin limit ({active_coins}/{max_coins})")
            user_actions.append("Close a position or increase max concurrent coins limit")

        # Check existing position
        details.append(BotActionDetail(
            rule="existing_position",
            passed=not has_existing_position,
            current="No position" if not has_existing_position else "Has position",
            threshold="No position",
            message=f"No existing position in {symbol}" if not has_existing_position else f"Already have position in {symbol}",
        ))
        if has_existing_position:
            waiting_reasons.append(f"Already have position in {symbol}")

        # Check available capital
        min_allocation = Decimal(str(self.config.get("min_allocation_usd", 100)))
        has_capital = available_capital >= min_allocation
        details.append(BotActionDetail(
            rule="available_capital",
            passed=has_capital,
            current=f"${float(available_capital):,.0f}",
            threshold=f"${float(min_allocation):,.0f}",
            message=f"Available capital: ${float(available_capital):,.0f}" if has_capital else "Insufficient capital",
        ))
        if not has_capital:
            waiting_reasons.append("Insufficient available capital")
            user_actions.append("Add funds or close existing positions to free capital")

        # ==================== Determine Final Status ====================

        can_execute = True

        if blocking_reasons:
            status = BotActionStatus.BLOCKED
            reason = blocking_reasons[0]
            can_execute = False
        elif waiting_reasons:
            status = BotActionStatus.WAITING
            reason = waiting_reasons[0]
        elif manual_reasons:
            status = BotActionStatus.MANUAL_ONLY
            reason = manual_reasons[0] if manual_reasons else "Manual execution available"
        else:
            status = BotActionStatus.AUTO_TRADE
            reason = "Ready for auto-execution"

        # Build user action string
        user_action = None
        if user_actions:
            user_action = user_actions[0]
            if status == BotActionStatus.MANUAL_ONLY:
                user_action += " or click Execute to trade manually"

        return BotAction(
            status=status,
            reason=reason,
            details=details,
            user_action=user_action,
            can_execute=can_execute,
        )

    def _exchange_has_credentials(self, exchange: str) -> bool:
        """Check if an exchange has configured credentials."""
        # Normalize exchange name
        exchange_lower = exchange.lower()

        # Check direct match
        if exchange_lower in self.exchanges_with_credentials:
            return True

        # Check with _futures suffix
        if f"{exchange_lower}_futures" in self.exchanges_with_credentials:
            return True

        # Check without _futures suffix
        if exchange_lower.endswith("_futures"):
            base_name = exchange_lower[:-8]
            if base_name in self.exchanges_with_credentials:
                return True

        return False
