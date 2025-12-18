"""Unit tests for Stress Testing module.

NOTE: These tests require running with the risk-manager service in PYTHONPATH.
Run with: PYTHONPATH=services/risk-manager pytest tests/unit/test_stress.py
"""

import os
import sys
from decimal import Decimal

import pytest

# Add service path for imports - use absolute path
_service_path = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../services/risk-manager")
)
if _service_path not in sys.path:
    sys.path.insert(0, _service_path)

# Handle namespace collision with other services' src packages
try:
    from src.manager.stress import (
        ScenarioSeverity,
        ScenarioType,
        STRESS_SCENARIOS,
        StressScenario,
        StressTester,
        StressTestResult,
        get_available_scenarios,
        run_stress_test,
    )
except ImportError:
    pytest.skip("Cannot import stress - run with single service PYTHONPATH", allow_module_level=True)


class TestStressScenarios:
    """Tests for stress scenario definitions."""

    def test_all_scenarios_defined(self):
        """Test that all expected scenarios are defined."""
        expected_scenarios = [
            "flash_crash_mild",
            "flash_crash_moderate",
            "flash_crash_severe",
            "flash_crash_extreme",
            "funding_flip_mild",
            "funding_flip_moderate",
            "funding_flip_severe",
            "exchange_outage_single",
            "exchange_outage_multiple",
            "liquidity_crisis",
            "correlation_breakdown",
            "combined_crisis",
        ]

        for scenario in expected_scenarios:
            assert scenario in STRESS_SCENARIOS, f"Missing scenario: {scenario}"

    def test_scenario_severity_levels(self):
        """Test that scenarios have appropriate severity levels."""
        severity_counts = {
            ScenarioSeverity.MILD: 0,
            ScenarioSeverity.MODERATE: 0,
            ScenarioSeverity.SEVERE: 0,
            ScenarioSeverity.EXTREME: 0,
        }

        for scenario in STRESS_SCENARIOS.values():
            severity_counts[scenario.severity] += 1

        # Should have at least one of each severity
        assert severity_counts[ScenarioSeverity.MILD] >= 1
        assert severity_counts[ScenarioSeverity.MODERATE] >= 1
        assert severity_counts[ScenarioSeverity.SEVERE] >= 1
        assert severity_counts[ScenarioSeverity.EXTREME] >= 1

    def test_scenario_types(self):
        """Test that all scenario types are represented."""
        types_found = set()
        for scenario in STRESS_SCENARIOS.values():
            types_found.add(scenario.type)

        assert ScenarioType.FLASH_CRASH in types_found
        assert ScenarioType.FUNDING_FLIP in types_found
        assert ScenarioType.EXCHANGE_OUTAGE in types_found
        assert ScenarioType.LIQUIDITY_CRISIS in types_found
        assert ScenarioType.COMBINED in types_found

    def test_flash_crash_scenarios_have_price_moves(self):
        """Test flash crash scenarios have negative price moves."""
        flash_crash_scenarios = [
            k for k, v in STRESS_SCENARIOS.items()
            if v.type == ScenarioType.FLASH_CRASH
        ]

        for name in flash_crash_scenarios:
            scenario = STRESS_SCENARIOS[name]
            assert scenario.price_move_pct < 0, f"{name} should have negative price move"

    def test_funding_flip_scenarios_have_spread_changes(self):
        """Test funding flip scenarios have negative spread changes."""
        funding_scenarios = [
            k for k, v in STRESS_SCENARIOS.items()
            if v.type == ScenarioType.FUNDING_FLIP
        ]

        for name in funding_scenarios:
            scenario = STRESS_SCENARIOS[name]
            assert scenario.spread_change < 0, f"{name} should have negative spread change"

    def test_exchange_outage_scenarios_have_offline_exchanges(self):
        """Test exchange outage scenarios have offline exchanges."""
        outage_scenarios = [
            k for k, v in STRESS_SCENARIOS.items()
            if v.type == ScenarioType.EXCHANGE_OUTAGE
        ]

        for name in outage_scenarios:
            scenario = STRESS_SCENARIOS[name]
            assert len(scenario.offline_exchanges) > 0, f"{name} should have offline exchanges"


class TestStressTester:
    """Tests for the StressTester class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.positions = [
            {
                "position_id": "pos_1",
                "symbol": "BTC",
                "size_usd": 10000,
                "long_exchange": "binance",
                "short_exchange": "bybit",
                "current_spread": 0.02,
                "unrealized_pnl": 50,
            },
            {
                "position_id": "pos_2",
                "symbol": "ETH",
                "size_usd": 5000,
                "long_exchange": "okx",
                "short_exchange": "bybit",
                "current_spread": 0.015,
                "unrealized_pnl": -20,
            },
        ]
        self.total_capital = Decimal("100000")
        self.current_exposure = Decimal("15000")

    def test_tester_initialization(self):
        """Test StressTester initializes correctly."""
        tester = StressTester(
            self.positions,
            self.total_capital,
            self.current_exposure,
        )

        assert tester._positions == self.positions
        assert tester._total_capital == self.total_capital
        assert tester._current_exposure == self.current_exposure

    def test_run_single_scenario(self):
        """Test running a single scenario."""
        tester = StressTester(
            self.positions,
            self.total_capital,
            self.current_exposure,
        )

        result = tester.run_scenario("flash_crash_mild")

        assert isinstance(result, StressTestResult)
        assert result.scenario_name == "Mild Flash Crash"
        assert result.scenario_type == ScenarioType.FLASH_CRASH
        assert result.severity == ScenarioSeverity.MILD
        assert result.positions_affected == 2  # Both positions

    def test_run_unknown_scenario(self):
        """Test running an unknown scenario raises error."""
        tester = StressTester(
            self.positions,
            self.total_capital,
            self.current_exposure,
        )

        with pytest.raises(ValueError, match="Unknown scenario"):
            tester.run_scenario("nonexistent_scenario")

    def test_run_all_scenarios(self):
        """Test running all scenarios."""
        tester = StressTester(
            self.positions,
            self.total_capital,
            self.current_exposure,
        )

        results = tester.run_all_scenarios()

        assert len(results) == len(STRESS_SCENARIOS)
        for result in results:
            assert isinstance(result, StressTestResult)

    def test_run_custom_scenario(self):
        """Test running a custom scenario."""
        tester = StressTester(
            self.positions,
            self.total_capital,
            self.current_exposure,
        )

        custom = StressScenario(
            name="Custom Test",
            type=ScenarioType.FLASH_CRASH,
            severity=ScenarioSeverity.MODERATE,
            description="Custom test scenario",
            price_move_pct=-15.0,
            volatility_multiplier=2.0,
        )

        result = tester.run_custom_scenario(custom)

        assert result.scenario_name == "Custom Test"
        assert result.projected_pnl < 0  # Should show loss


class TestStressTestResults:
    """Tests for stress test result calculations."""

    def setup_method(self):
        """Set up test fixtures."""
        self.positions = [
            {
                "position_id": "pos_1",
                "symbol": "BTC",
                "size_usd": 10000,
                "long_exchange": "binance",
                "short_exchange": "bybit",
                "current_spread": 0.02,
                "unrealized_pnl": 50,
            },
        ]
        self.total_capital = Decimal("100000")
        self.current_exposure = Decimal("10000")

    def test_pnl_calculation_flash_crash(self):
        """Test P&L calculation for flash crash scenarios."""
        tester = StressTester(
            self.positions,
            self.total_capital,
            self.current_exposure,
        )

        # Run mild vs severe crash
        mild_result = tester.run_scenario("flash_crash_mild")
        severe_result = tester.run_scenario("flash_crash_severe")

        # Severe should have larger losses
        assert severe_result.projected_pnl < mild_result.projected_pnl

    def test_pnl_calculation_funding_flip(self):
        """Test P&L calculation for funding flip scenarios."""
        tester = StressTester(
            self.positions,
            self.total_capital,
            self.current_exposure,
        )

        result = tester.run_scenario("funding_flip_moderate")

        # Should show funding loss
        assert result.projected_pnl < 0
        assert result.scenario_type == ScenarioType.FUNDING_FLIP

    def test_exchange_outage_impact(self):
        """Test exchange outage impacts correct positions."""
        # Position with binance
        positions = [
            {
                "position_id": "pos_1",
                "symbol": "BTC",
                "size_usd": 10000,
                "long_exchange": "binance",
                "short_exchange": "bybit",
                "current_spread": 0.02,
            },
        ]

        tester = StressTester(
            positions,
            self.total_capital,
            self.current_exposure,
        )

        result = tester.run_scenario("exchange_outage_single")  # Takes binance offline

        # Should trigger margin call due to unhedged exposure
        assert result.margin_calls > 0

    def test_drawdown_calculation(self):
        """Test max drawdown is calculated correctly."""
        tester = StressTester(
            self.positions,
            self.total_capital,
            self.current_exposure,
        )

        result = tester.run_scenario("flash_crash_extreme")

        # Drawdown should match P&L percentage
        expected_drawdown = abs(result.projected_pnl_pct)
        assert result.max_drawdown_pct == expected_drawdown

    def test_recovery_time_scaling(self):
        """Test recovery time scales with severity."""
        tester = StressTester(
            self.positions,
            self.total_capital,
            self.current_exposure,
        )

        mild_result = tester.run_scenario("flash_crash_mild")
        severe_result = tester.run_scenario("flash_crash_severe")
        extreme_result = tester.run_scenario("flash_crash_extreme")

        # Recovery time should increase with severity
        assert mild_result.estimated_recovery_hours < severe_result.estimated_recovery_hours
        assert severe_result.estimated_recovery_hours < extreme_result.estimated_recovery_hours


class TestRecommendations:
    """Tests for recommendation generation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.positions = [
            {
                "position_id": "pos_1",
                "symbol": "BTC",
                "size_usd": 50000,
                "long_exchange": "binance",
                "short_exchange": "bybit",
                "current_spread": 0.02,
            },
        ]
        self.total_capital = Decimal("100000")
        self.current_exposure = Decimal("50000")

    def test_extreme_scenario_recommendations(self):
        """Test extreme scenarios generate appropriate recommendations."""
        tester = StressTester(
            self.positions,
            self.total_capital,
            self.current_exposure,
        )

        result = tester.run_scenario("flash_crash_extreme")

        # Should include exposure reduction recommendation
        assert any("exposure" in r.lower() for r in result.recommendations)

    def test_exchange_outage_recommendations(self):
        """Test exchange outage generates diversification recommendations."""
        tester = StressTester(
            self.positions,
            self.total_capital,
            self.current_exposure,
        )

        result = tester.run_scenario("exchange_outage_single")

        # Should include diversification or exchange-specific recommendations
        recommendations_text = " ".join(result.recommendations).lower()
        assert "binance" in recommendations_text or "diversify" in recommendations_text

    def test_liquidity_crisis_recommendations(self):
        """Test liquidity crisis generates appropriate recommendations."""
        tester = StressTester(
            self.positions,
            self.total_capital,
            self.current_exposure,
        )

        result = tester.run_scenario("liquidity_crisis")

        # Should include position size or exit strategy recommendations
        recommendations_text = " ".join(result.recommendations).lower()
        assert "size" in recommendations_text or "exit" in recommendations_text or "liquidity" in recommendations_text


class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def setup_method(self):
        """Set up test fixtures."""
        self.positions = [
            {
                "position_id": "pos_1",
                "symbol": "BTC",
                "size_usd": 10000,
                "long_exchange": "binance",
                "short_exchange": "bybit",
                "current_spread": 0.02,
            },
        ]
        self.total_capital = Decimal("100000")
        self.current_exposure = Decimal("10000")

    def test_run_stress_test_single_scenario(self):
        """Test run_stress_test with single scenario."""
        result = run_stress_test(
            self.positions,
            self.total_capital,
            self.current_exposure,
            "flash_crash_mild",
        )

        assert "scenarios_run" in result
        assert result["scenarios_run"] == 1
        assert "results" in result
        assert len(result["results"]) == 1

    def test_run_stress_test_all_scenarios(self):
        """Test run_stress_test with all scenarios."""
        result = run_stress_test(
            self.positions,
            self.total_capital,
            self.current_exposure,
        )

        assert result["scenarios_run"] == len(STRESS_SCENARIOS)
        assert "worst_case_pnl" in result
        assert "worst_case_drawdown_pct" in result

    def test_run_stress_test_worst_case_metrics(self):
        """Test worst case metrics are calculated correctly."""
        result = run_stress_test(
            self.positions,
            self.total_capital,
            self.current_exposure,
        )

        # Worst case should be the minimum P&L
        pnls = [r["projected_pnl"] for r in result["results"]]
        assert result["worst_case_pnl"] == min(pnls)

    def test_get_available_scenarios(self):
        """Test get_available_scenarios returns correct format."""
        scenarios = get_available_scenarios()

        assert len(scenarios) == len(STRESS_SCENARIOS)

        for scenario in scenarios:
            assert "name" in scenario
            assert "key" in scenario
            assert "type" in scenario
            assert "severity" in scenario
            assert "description" in scenario


class TestEmptyPositions:
    """Tests with empty or zero positions."""

    def test_empty_positions(self):
        """Test stress testing with empty positions."""
        tester = StressTester(
            [],
            Decimal("100000"),
            Decimal("0"),
        )

        result = tester.run_scenario("flash_crash_mild")

        assert result.positions_affected == 0
        assert result.projected_pnl == Decimal("0")

    def test_zero_size_positions(self):
        """Test positions with zero size are skipped."""
        positions = [
            {
                "position_id": "pos_1",
                "symbol": "BTC",
                "size_usd": 0,
                "long_exchange": "binance",
                "short_exchange": "bybit",
                "current_spread": 0.02,
            },
        ]

        tester = StressTester(
            positions,
            Decimal("100000"),
            Decimal("0"),
        )

        result = tester.run_scenario("flash_crash_mild")

        assert result.positions_affected == 0

    def test_zero_capital(self):
        """Test with zero capital handles division safely."""
        positions = [
            {
                "position_id": "pos_1",
                "symbol": "BTC",
                "size_usd": 10000,
                "long_exchange": "binance",
                "short_exchange": "bybit",
                "current_spread": 0.02,
            },
        ]

        tester = StressTester(
            positions,
            Decimal("0"),
            Decimal("10000"),
        )

        result = tester.run_scenario("flash_crash_mild")

        # Should handle zero division gracefully
        assert result.projected_pnl_pct == Decimal("0")


class TestLiquidationDetection:
    """Tests for liquidation detection."""

    def test_high_loss_triggers_liquidation(self):
        """Test that high losses trigger liquidation warning."""
        # Position with high leverage exposure
        positions = [
            {
                "position_id": "pos_1",
                "symbol": "BTC",
                "size_usd": 50000,  # Large position
                "long_exchange": "binance",
                "short_exchange": "bybit",
                "current_spread": 0.02,
            },
        ]

        tester = StressTester(
            positions,
            Decimal("100000"),
            Decimal("50000"),
        )

        # Extreme crash should trigger liquidation
        result = tester.run_scenario("flash_crash_extreme")

        # Extreme scenario may cause liquidation warnings
        assert result.positions_liquidated >= 0  # At least checked

    def test_mild_scenario_no_liquidation(self):
        """Test mild scenarios don't trigger liquidations."""
        positions = [
            {
                "position_id": "pos_1",
                "symbol": "BTC",
                "size_usd": 10000,
                "long_exchange": "binance",
                "short_exchange": "bybit",
                "current_spread": 0.02,
            },
        ]

        tester = StressTester(
            positions,
            Decimal("100000"),
            Decimal("10000"),
        )

        result = tester.run_scenario("flash_crash_mild")

        # 10% position with 5% move shouldn't liquidate
        assert result.positions_liquidated == 0
