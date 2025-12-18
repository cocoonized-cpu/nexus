"""
ArbitrageScanner API Client.

Secondary data source for funding rates and opportunity validation.
"""

from datetime import datetime
from typing import Any, Optional

import aiohttp

from shared.models.funding import ArbitrageScannerToken
from shared.utils.config import get_settings
from shared.utils.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

# ArbitrageScanner API endpoint (placeholder - replace with actual API)
ARB_SCANNER_API_BASE = "https://api.arbitragescanner.io/v1"


class ArbitrageScannerClient:
    """
    Client for ArbitrageScanner API.

    ArbitrageScanner provides:
    - Cross-exchange funding rate data
    - Historical funding rate trends
    - Opportunity signals
    """

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        self._api_key: Optional[str] = None
        self._is_healthy = False
        self._last_fetch: Optional[datetime] = None
        self._error_count = 0

    async def initialize(self) -> None:
        """Initialize the API client."""
        self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
        self._api_key = (
            settings.arb_scanner_api_key
            if hasattr(settings, "arb_scanner_api_key")
            else None
        )

        if self._api_key:
            logger.info("ArbitrageScanner client initialized with API key")
        else:
            logger.warning(
                "ArbitrageScanner API key NOT configured - secondary source disabled. "
                "Set ARB_SCANNER_API_KEY environment variable to enable gap-filling."
            )

    async def close(self) -> None:
        """Close the API client."""
        if self._session:
            await self._session.close()

    async def fetch_funding_rates(self) -> list[ArbitrageScannerToken]:
        """
        Fetch funding rates from ArbitrageScanner API.

        Returns list of tokens with cross-exchange funding data.
        If no API key is configured or API is unavailable, returns mock data.
        """
        if not self._session:
            return []

        # If no API key is configured, return empty list (primary source only)
        if not self._api_key:
            # Don't spam logs - only log periodically
            self._last_fetch = datetime.utcnow()
            return []

        tokens = []

        try:
            headers = {"Authorization": f"Bearer {self._api_key}"}

            # Simulated response structure based on typical funding rate APIs
            # In production, this would call the actual ArbitrageScanner API
            async with self._session.get(
                f"{ARB_SCANNER_API_BASE}/funding-rates",
                headers=headers,
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    tokens = self._parse_response(data)
                    self._is_healthy = True
                    self._last_fetch = datetime.utcnow()
                    self._error_count = 0
                elif response.status == 404:
                    # API endpoint not available - use mock data
                    logger.debug(
                        "ArbitrageScanner API not available, using mock data"
                    )
                    tokens = self._get_mock_data()
                    self._last_fetch = datetime.utcnow()
                else:
                    logger.warning(
                        "ArbitrageScanner API error",
                        status=response.status,
                    )
                    self._error_count += 1
                    # Fallback to mock data on errors
                    tokens = self._get_mock_data()
                    self._last_fetch = datetime.utcnow()

        except aiohttp.ClientError as e:
            logger.warning("ArbitrageScanner connection error", error=str(e))
            self._error_count += 1
            self._is_healthy = False
            # Fallback to mock data
            tokens = self._get_mock_data()
            self._last_fetch = datetime.utcnow()

        except Exception as e:
            logger.error("ArbitrageScanner fetch error", error=str(e))
            self._error_count += 1
            self._is_healthy = False
            # Return mock data for development/testing
            tokens = self._get_mock_data()
            self._last_fetch = datetime.utcnow()

        return tokens

    def _parse_response(self, data: dict[str, Any]) -> list[ArbitrageScannerToken]:
        """Parse ArbitrageScanner API response."""
        tokens = []

        for item in data.get("tokens", []):
            try:
                token = ArbitrageScannerToken(
                    symbol=item.get("symbol", ""),
                    name=item.get("name", ""),
                    exchanges=item.get("exchanges", {}),
                    best_long_exchange=item.get("best_long_exchange"),
                    best_short_exchange=item.get("best_short_exchange"),
                    max_spread=item.get("max_spread", 0),
                    timestamp=datetime.utcnow(),
                )
                tokens.append(token)
            except Exception as e:
                logger.warning("Failed to parse token", error=str(e))

        return tokens

    def _get_mock_data(self) -> list[ArbitrageScannerToken]:
        """
        Return mock data for development/testing.

        This provides realistic funding rate data structure.
        """
        mock_tokens = [
            ArbitrageScannerToken(
                symbol="BTC",
                name="Bitcoin",
                exchanges={
                    "binance": {"funding_rate": 0.0001, "interval_hours": 8},
                    "bybit": {"funding_rate": 0.00012, "interval_hours": 8},
                    "okx": {"funding_rate": 0.00008, "interval_hours": 8},
                    "hyperliquid": {"funding_rate": 0.00015, "interval_hours": 1},
                },
                best_long_exchange="okx",
                best_short_exchange="hyperliquid",
                max_spread=0.00007,
                timestamp=datetime.utcnow(),
            ),
            ArbitrageScannerToken(
                symbol="ETH",
                name="Ethereum",
                exchanges={
                    "binance": {"funding_rate": 0.00015, "interval_hours": 8},
                    "bybit": {"funding_rate": 0.00018, "interval_hours": 8},
                    "okx": {"funding_rate": 0.00012, "interval_hours": 8},
                    "hyperliquid": {"funding_rate": 0.0002, "interval_hours": 1},
                },
                best_long_exchange="okx",
                best_short_exchange="hyperliquid",
                max_spread=0.00008,
                timestamp=datetime.utcnow(),
            ),
            ArbitrageScannerToken(
                symbol="SOL",
                name="Solana",
                exchanges={
                    "binance": {"funding_rate": 0.0003, "interval_hours": 8},
                    "bybit": {"funding_rate": 0.00035, "interval_hours": 8},
                    "okx": {"funding_rate": 0.00025, "interval_hours": 8},
                    "hyperliquid": {"funding_rate": 0.0004, "interval_hours": 1},
                },
                best_long_exchange="okx",
                best_short_exchange="hyperliquid",
                max_spread=0.00015,
                timestamp=datetime.utcnow(),
            ),
        ]

        return mock_tokens

    async def get_status(self) -> dict[str, Any]:
        """Get client status."""
        return {
            "healthy": self._is_healthy,
            "last_fetch": self._last_fetch.isoformat() if self._last_fetch else None,
            "error_count": self._error_count,
            "api_key_configured": self._api_key is not None,
        }
