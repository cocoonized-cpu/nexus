"""
Stress Testing Module for Risk Manager.

Provides scenario-based stress testing to evaluate portfolio resilience
under various adverse market conditions.

Scenarios include:
- Flash crashes (rapid price movements)
- Funding rate flips (spread inversion)
- Exchange outages (loss of one or more venues)
- Liquidity crises (reduced market depth)
- Correlation breakdown (hedges become ineffective)
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from shared.utils.logging import get_logger

logger = get_logger(__name__)


class ScenarioSeverity(str, Enum):
    """Severity level of stress scenario."""
    MILD = "mild"
    MODERATE = "moderate"
    SEVERE = "severe"
    EXTREME = "extreme"


class ScenarioType(str, Enum):
    """Type of stress scenario."""
    FLASH_CRASH = "flash_crash"
    FUNDING_FLIP = "funding_flip"
    EXCHANGE_OUTAGE = "exchange_outage"
    LIQUIDITY_CRISIS = "liquidity_crisis"
    CORRELATION_BREAKDOWN = "correlation_breakdown"
    COMBINED = "combined"


@dataclass
class StressScenario:
    """Definition of a stress test scenario."""
    name: str
    type: ScenarioType
    severity: ScenarioSeverity
    description: str

    # Market impact parameters
    price_move_pct: float = 0.0  # Instantaneous price move (e.g., -20 for 20% drop)
    volatility_multiplier: float = 1.0  # Multiply current volatility
    spread_change: float = 0.0  # Change in funding spread (e.g., -0.02 for 2% flip)
    liquidity_reduction: float = 0.0  # Reduce liquidity (0.5 = 50% reduction)

    # Exchange impact
    offline_exchanges: list[str] = field(default_factory=list)

    # Duration
    duration_hours: float = 1.0  # How long the stress lasts


@dataclass
class StressTestResult:
    """Result of a stress test simulation."""
    scenario_name: str
    scenario_type: ScenarioType
    severity: ScenarioSeverity

    # Portfolio impact
    projected_pnl: Decimal
    projected_pnl_pct: Decimal
    max_drawdown_pct: Decimal

    # Position impacts
    positions_affected: int
    positions_liquidated: int  # Estimated liquidations
    margin_calls: int  # Positions requiring additional margin

    # Recovery estimate
    estimated_recovery_hours: float

    # Recommendations
    recommendations: list[str]

    # Metadata
    run_at: datetime = field(default_factory=datetime.utcnow)


# Predefined stress scenarios
STRESS_SCENARIOS: dict[str, StressScenario] = {
    "flash_crash_mild": StressScenario(
        name="Mild Flash Crash",
        type=ScenarioType.FLASH_CRASH,
        severity=ScenarioSeverity.MILD,
        description="5% price drop across all assets",
        price_move_pct=-5.0,
        volatility_multiplier=2.0,
        duration_hours=0.5,
    ),
    "flash_crash_moderate": StressScenario(
        name="Moderate Flash Crash",
        type=ScenarioType.FLASH_CRASH,
        severity=ScenarioSeverity.MODERATE,
        description="10% price drop with increased volatility",
        price_move_pct=-10.0,
        volatility_multiplier=3.0,
        duration_hours=1.0,
    ),
    "flash_crash_severe": StressScenario(
        name="Severe Flash Crash",
        type=ScenarioType.FLASH_CRASH,
        severity=ScenarioSeverity.SEVERE,
        description="20% price drop, liquidity crisis",
        price_move_pct=-20.0,
        volatility_multiplier=5.0,
        liquidity_reduction=0.5,
        duration_hours=2.0,
    ),
    "flash_crash_extreme": StressScenario(
        name="Extreme Flash Crash (Black Swan)",
        type=ScenarioType.FLASH_CRASH,
        severity=ScenarioSeverity.EXTREME,
        description="40% price collapse, complete liquidity evaporation",
        price_move_pct=-40.0,
        volatility_multiplier=10.0,
        liquidity_reduction=0.9,
        duration_hours=4.0,
    ),
    "funding_flip_mild": StressScenario(
        name="Mild Funding Flip",
        type=ScenarioType.FUNDING_FLIP,
        severity=ScenarioSeverity.MILD,
        description="Spread reduces by 50%",
        spread_change=-0.005,  # -0.5%
        duration_hours=8.0,
    ),
    "funding_flip_moderate": StressScenario(
        name="Moderate Funding Flip",
        type=ScenarioType.FUNDING_FLIP,
        severity=ScenarioSeverity.MODERATE,
        description="Spread flips negative",
        spread_change=-0.015,  # -1.5%
        duration_hours=16.0,
    ),
    "funding_flip_severe": StressScenario(
        name="Severe Funding Flip",
        type=ScenarioType.FUNDING_FLIP,
        severity=ScenarioSeverity.SEVERE,
        description="Large negative spread",
        spread_change=-0.03,  # -3%
        duration_hours=24.0,
    ),
    "exchange_outage_single": StressScenario(
        name="Single Exchange Outage",
        type=ScenarioType.EXCHANGE_OUTAGE,
        severity=ScenarioSeverity.MODERATE,
        description="One major exchange goes offline",
        offline_exchanges=["binance"],
        duration_hours=2.0,
    ),
    "exchange_outage_multiple": StressScenario(
        name="Multiple Exchange Outages",
        type=ScenarioType.EXCHANGE_OUTAGE,
        severity=ScenarioSeverity.SEVERE,
        description="Two exchanges go offline simultaneously",
        offline_exchanges=["binance", "bybit"],
        duration_hours=4.0,
    ),
    "liquidity_crisis": StressScenario(
        name="Liquidity Crisis",
        type=ScenarioType.LIQUIDITY_CRISIS,
        severity=ScenarioSeverity.SEVERE,
        description="Market-wide liquidity drops 80%",
        liquidity_reduction=0.8,
        volatility_multiplier=4.0,
        duration_hours=6.0,
    ),
    "correlation_breakdown": StressScenario(
        name="Correlation Breakdown",
        type=ScenarioType.CORRELATION_BREAKDOWN,
        severity=ScenarioSeverity.SEVERE,
        description="Exchange prices diverge significantly",
        price_move_pct=-5.0,
        volatility_multiplier=3.0,
        duration_hours=4.0,
    ),
    "combined_crisis": StressScenario(
        name="Combined Market Crisis",
        type=ScenarioType.COMBINED,
        severity=ScenarioSeverity.EXTREME,
        description="Flash crash + funding flip + liquidity crisis",
        price_move_pct=-25.0,
        spread_change=-0.02,
        liquidity_reduction=0.7,
        volatility_multiplier=6.0,
        offline_exchanges=["dydx"],
        duration_hours=8.0,
    ),
}


class StressTester:
    """
    Runs stress tests on the portfolio to evaluate resilience.

    Uses Monte Carlo simulation and scenario analysis to project
    potential losses under adverse conditions.
    """

    def __init__(
        self,
        positions: list[dict],
        total_capital: Decimal,
        current_exposure: Decimal,
    ):
        """
        Initialize stress tester.

        Args:
            positions: List of position dictionaries with keys:
                       position_id, symbol, size_usd, long_exchange, short_exchange,
                       current_spread, unrealized_pnl
            total_capital: Total portfolio capital
            current_exposure: Current total exposure
        """
        self._positions = positions
        self._total_capital = total_capital
        self._current_exposure = current_exposure

    def run_scenario(self, scenario_name: str) -> StressTestResult:
        """
        Run a single stress test scenario.

        Args:
            scenario_name: Name of predefined scenario to run

        Returns:
            StressTestResult with projected impacts
        """
        if scenario_name not in STRESS_SCENARIOS:
            raise ValueError(f"Unknown scenario: {scenario_name}")

        scenario = STRESS_SCENARIOS[scenario_name]
        return self._simulate_scenario(scenario)

    def run_all_scenarios(self) -> list[StressTestResult]:
        """Run all predefined stress scenarios."""
        results = []
        for name in STRESS_SCENARIOS:
            try:
                result = self.run_scenario(name)
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to run scenario {name}", error=str(e))
        return results

    def run_custom_scenario(self, scenario: StressScenario) -> StressTestResult:
        """Run a custom stress scenario."""
        return self._simulate_scenario(scenario)

    def _simulate_scenario(self, scenario: StressScenario) -> StressTestResult:
        """Simulate the impact of a stress scenario on the portfolio."""
        total_pnl_impact = Decimal("0")
        positions_affected = 0
        positions_liquidated = 0
        margin_calls = 0

        for position in self._positions:
            position_size = Decimal(str(position.get("size_usd", 0)))
            current_spread = Decimal(str(position.get("current_spread", 0.01)))
            long_exchange = position.get("long_exchange", "")
            short_exchange = position.get("short_exchange", "")

            if position_size <= 0:
                continue

            positions_affected += 1

            # Calculate P&L impact based on scenario type
            pnl_impact = Decimal("0")

            # Price movement impact (should be hedged, but not perfectly)
            if scenario.price_move_pct != 0:
                # Assume 1-2% of price move affects delta-neutral position
                # due to timing differences and funding
                delta_exposure_pct = Decimal("0.02")
                price_impact = position_size * Decimal(str(abs(scenario.price_move_pct) / 100)) * delta_exposure_pct
                pnl_impact -= price_impact

            # Spread change impact
            if scenario.spread_change != 0:
                new_spread = current_spread + Decimal(str(scenario.spread_change))
                # Spread deterioration affects funding P&L
                spread_impact = position_size * Decimal(str(abs(scenario.spread_change)))
                if new_spread < current_spread:
                    pnl_impact -= spread_impact

            # Exchange outage impact
            if scenario.offline_exchanges:
                if long_exchange in scenario.offline_exchanges or short_exchange in scenario.offline_exchanges:
                    # Can't close one leg - delta exposure increases significantly
                    outage_impact = position_size * Decimal("0.05")  # 5% potential loss
                    pnl_impact -= outage_impact
                    margin_calls += 1

            # Liquidity crisis impact
            if scenario.liquidity_reduction > 0:
                # Exit slippage increases
                slippage_multiplier = Decimal(str(1 + scenario.liquidity_reduction * 2))
                base_slippage = Decimal("0.001")  # 0.1% base slippage
                liquidity_impact = position_size * base_slippage * slippage_multiplier
                pnl_impact -= liquidity_impact

            # Check for potential liquidation
            if position_size > 0:
                loss_pct = abs(pnl_impact) / position_size * 100
                if loss_pct > Decimal("15"):  # 15% loss = likely liquidation with 5x leverage
                    positions_liquidated += 1

            total_pnl_impact += pnl_impact

        # Calculate portfolio-level metrics
        pnl_pct = (
            total_pnl_impact / self._total_capital * 100
            if self._total_capital > 0
            else Decimal("0")
        )

        max_drawdown = abs(pnl_pct)

        # Estimate recovery time
        recovery_hours = self._estimate_recovery_time(scenario, max_drawdown)

        # Generate recommendations
        recommendations = self._generate_recommendations(
            scenario, total_pnl_impact, positions_liquidated, margin_calls
        )

        return StressTestResult(
            scenario_name=scenario.name,
            scenario_type=scenario.type,
            severity=scenario.severity,
            projected_pnl=total_pnl_impact.quantize(Decimal("0.01")),
            projected_pnl_pct=pnl_pct.quantize(Decimal("0.01")),
            max_drawdown_pct=max_drawdown.quantize(Decimal("0.01")),
            positions_affected=positions_affected,
            positions_liquidated=positions_liquidated,
            margin_calls=margin_calls,
            estimated_recovery_hours=recovery_hours,
            recommendations=recommendations,
        )

    def _estimate_recovery_time(
        self,
        scenario: StressScenario,
        max_drawdown: Decimal,
    ) -> float:
        """Estimate time to recover from stress scenario."""
        base_recovery = scenario.duration_hours

        # Recovery time scales with severity
        severity_multiplier = {
            ScenarioSeverity.MILD: 1.0,
            ScenarioSeverity.MODERATE: 2.0,
            ScenarioSeverity.SEVERE: 4.0,
            ScenarioSeverity.EXTREME: 8.0,
        }

        multiplier = severity_multiplier.get(scenario.severity, 2.0)

        # Larger drawdowns take longer to recover
        drawdown_factor = 1 + float(max_drawdown) / 10

        return base_recovery * multiplier * drawdown_factor

    def _generate_recommendations(
        self,
        scenario: StressScenario,
        total_pnl_impact: Decimal,
        positions_liquidated: int,
        margin_calls: int,
    ) -> list[str]:
        """Generate actionable recommendations based on stress test results."""
        recommendations = []

        # Severity-based recommendations
        if scenario.severity == ScenarioSeverity.EXTREME:
            recommendations.append("Consider reducing overall exposure by 50%")
            recommendations.append("Implement emergency position unwinding procedures")

        if scenario.severity in [ScenarioSeverity.SEVERE, ScenarioSeverity.EXTREME]:
            recommendations.append("Review and potentially tighten stop-loss levels")

        # Scenario-specific recommendations
        if scenario.type == ScenarioType.FLASH_CRASH:
            recommendations.append("Ensure adequate margin buffers on all exchanges")
            if scenario.price_move_pct <= -20:
                recommendations.append("Consider reducing leverage to minimize liquidation risk")

        if scenario.type == ScenarioType.FUNDING_FLIP:
            recommendations.append("Monitor funding rate trends more frequently")
            recommendations.append("Reduce position hold times during volatile periods")

        if scenario.type == ScenarioType.EXCHANGE_OUTAGE:
            recommendations.append("Diversify positions across more exchanges")
            recommendations.append("Maintain reserve capital for emergency rebalancing")
            for exchange in scenario.offline_exchanges:
                recommendations.append(f"Review {exchange} dependency and concentration")

        if scenario.type == ScenarioType.LIQUIDITY_CRISIS:
            recommendations.append("Reduce position sizes to improve exit liquidity")
            recommendations.append("Implement gradual exit strategies instead of market orders")

        # Impact-based recommendations
        if positions_liquidated > 0:
            recommendations.append(
                f"Reduce leverage to prevent {positions_liquidated} potential liquidations"
            )

        if margin_calls > 0:
            recommendations.append(
                f"Increase margin reserves to cover {margin_calls} potential margin calls"
            )

        pnl_pct = float(abs(total_pnl_impact / self._total_capital * 100)) if self._total_capital > 0 else 0
        if pnl_pct > 10:
            recommendations.append(f"Consider portfolio hedging to limit {pnl_pct:.1f}% potential loss")

        return recommendations


def run_stress_test(
    positions: list[dict],
    total_capital: Decimal,
    current_exposure: Decimal,
    scenario_name: Optional[str] = None,
) -> dict[str, Any]:
    """
    Convenience function to run stress tests.

    Args:
        positions: List of position dictionaries
        total_capital: Total portfolio capital
        current_exposure: Current total exposure
        scenario_name: Specific scenario to run, or None for all

    Returns:
        Dict with stress test results
    """
    tester = StressTester(positions, total_capital, current_exposure)

    if scenario_name:
        result = tester.run_scenario(scenario_name)
        results = [result]
    else:
        results = tester.run_all_scenarios()

    return {
        "scenarios_run": len(results),
        "worst_case_pnl": float(min(r.projected_pnl for r in results)),
        "worst_case_drawdown_pct": float(max(r.max_drawdown_pct for r in results)),
        "total_liquidations_risk": sum(r.positions_liquidated for r in results),
        "results": [
            {
                "scenario": r.scenario_name,
                "type": r.scenario_type.value,
                "severity": r.severity.value,
                "projected_pnl": float(r.projected_pnl),
                "projected_pnl_pct": float(r.projected_pnl_pct),
                "max_drawdown_pct": float(r.max_drawdown_pct),
                "positions_affected": r.positions_affected,
                "positions_liquidated": r.positions_liquidated,
                "margin_calls": r.margin_calls,
                "recovery_hours": r.estimated_recovery_hours,
                "recommendations": r.recommendations,
            }
            for r in results
        ],
        "run_at": datetime.utcnow().isoformat(),
    }


def get_available_scenarios() -> list[dict[str, Any]]:
    """Get list of available stress test scenarios."""
    return [
        {
            "name": scenario.name,
            "key": key,
            "type": scenario.type.value,
            "severity": scenario.severity.value,
            "description": scenario.description,
        }
        for key, scenario in STRESS_SCENARIOS.items()
    ]
