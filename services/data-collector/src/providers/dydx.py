"""
dYdX Exchange Provider.

dYdX is a Tier 1 DEX with 1-hour funding intervals.
"""

import asyncio
from datetime import datetime
from typing import Optional

import aiohttp
from src.providers.base import ExchangeProvider

from shared.models.exchange import LiquidityData, PriceData
from shared.models.funding import FundingRateData
from shared.utils.logging import get_logger

logger = get_logger(__name__)

# dYdX v4 API (Cosmos-based)
DYDX_API_BASE = "https://indexer.dydx.trade/v4"


class DYDXProvider(ExchangeProvider):
    """dYdX perpetual futures data provider."""

    def __init__(self):
        super().__init__()
        self._session: Optional[aiohttp.ClientSession] = None
        self._symbols: list[str] = []
        self._rate_limiter = asyncio.Semaphore(5)

    @property
    def exchange_id(self) -> str:
        return "dydx"

    @property
    def display_name(self) -> str:
        return "dYdX"

    async def initialize(self) -> None:
        """Initialize the dYdX client."""
        self._session = aiohttp.ClientSession()

        try:
            async with self._session.get(
                f"{DYDX_API_BASE}/perpetualMarkets"
            ) as response:
                data = await response.json()
                markets = data.get("markets", {})
                self._symbols = list(markets.keys())

            logger.info(f"dYdX provider initialized", symbols=len(self._symbols))

        except Exception as e:
            logger.error("Failed to initialize dYdX", error=str(e))
            self._record_error(str(e))

    async def close(self) -> None:
        """Close the dYdX client."""
        if self._session:
            await self._session.close()

    async def get_funding_rates(self) -> list[FundingRateData]:
        """Fetch funding rates from dYdX."""
        if not self._session:
            return []

        funding_rates = []

        try:
            async with self._rate_limiter:
                async with self._session.get(
                    f"{DYDX_API_BASE}/perpetualMarkets"
                ) as response:
                    data = await response.json()

            markets = data.get("markets", {})

            for ticker, market in markets.items():
                # dYdX provides nextFundingRate
                funding_rate = float(market.get("nextFundingRate", 0))

                funding_rates.append(
                    FundingRateData(
                        exchange="dydx",
                        symbol=f"{ticker}:USD",
                        funding_rate=funding_rate,
                        predicted_rate=None,
                        next_funding_time=None,
                        funding_interval_hours=1,
                        timestamp=datetime.utcnow(),
                    )
                )

            self._record_success()

        except Exception as e:
            logger.error("Failed to fetch dYdX funding rates", error=str(e))
            self._record_error(str(e))

        return funding_rates

    async def get_prices(self) -> list[PriceData]:
        """Fetch prices from dYdX."""
        if not self._session:
            return []

        prices = []

        try:
            async with self._rate_limiter:
                async with self._session.get(
                    f"{DYDX_API_BASE}/perpetualMarkets"
                ) as response:
                    data = await response.json()

            markets = data.get("markets", {})

            for ticker, market in markets.items():
                prices.append(
                    PriceData(
                        exchange="dydx",
                        symbol=f"{ticker}:USD",
                        mark_price=float(market.get("oraclePrice", 0)),
                        index_price=float(market.get("indexPrice", 0)) or None,
                        bid=None,
                        ask=None,
                        volume_24h=float(market.get("volume24H", 0)),
                        open_interest=float(market.get("openInterest", 0)) or None,
                        timestamp=datetime.utcnow(),
                    )
                )

            self._record_success()

        except Exception as e:
            logger.error("Failed to fetch dYdX prices", error=str(e))
            self._record_error(str(e))

        return prices

    async def get_liquidity(self) -> list[LiquidityData]:
        """Fetch order book liquidity from dYdX."""
        if not self._session:
            return []

        liquidity_data = []
        top_symbols = self._symbols[:30]

        for symbol in top_symbols:
            try:
                async with self._rate_limiter:
                    async with self._session.get(
                        f"{DYDX_API_BASE}/orderbooks/perpetualMarket/{symbol}"
                    ) as response:
                        data = await response.json()

                bids = data.get("bids", [])
                asks = data.get("asks", [])

                bid_liquidity = sum(
                    float(level.get("price", 0)) * float(level.get("size", 0))
                    for level in bids[:5]
                )
                ask_liquidity = sum(
                    float(level.get("price", 0)) * float(level.get("size", 0))
                    for level in asks[:5]
                )

                spread = 0
                if bids and asks:
                    best_bid = float(bids[0].get("price", 0))
                    best_ask = float(asks[0].get("price", 0))
                    if best_bid > 0:
                        spread = (best_ask - best_bid) / best_bid * 100

                liquidity_data.append(
                    LiquidityData(
                        exchange="dydx",
                        symbol=f"{symbol}:USD",
                        bid_liquidity_usd=bid_liquidity,
                        ask_liquidity_usd=ask_liquidity,
                        spread_pct=spread,
                        depth_imbalance=(
                            (bid_liquidity - ask_liquidity)
                            / (bid_liquidity + ask_liquidity)
                            if (bid_liquidity + ask_liquidity) > 0
                            else 0
                        ),
                        timestamp=datetime.utcnow(),
                    )
                )

                self._record_success()

            except Exception as e:
                logger.warning(
                    f"Failed to fetch dYdX orderbook", symbol=symbol, error=str(e)
                )
                self._record_error(str(e))

            await asyncio.sleep(0.2)

        return liquidity_data
