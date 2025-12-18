"""
Gate.io Exchange Provider.

Gate.io is a Tier 2 exchange with 8-hour funding intervals.
"""

import asyncio
from datetime import datetime
from typing import Optional

import ccxt.async_support as ccxt
from src.providers.base import ExchangeProvider

from shared.models.exchange import LiquidityData, PriceData
from shared.models.funding import FundingRateData
from shared.utils.logging import get_logger

logger = get_logger(__name__)


class GateProvider(ExchangeProvider):
    """Gate.io perpetual futures data provider."""

    def __init__(self):
        super().__init__()
        self._client: Optional[ccxt.gate] = None
        self._symbols: list[str] = []
        self._rate_limiter = asyncio.Semaphore(5)

    @property
    def exchange_id(self) -> str:
        return "gate"

    @property
    def display_name(self) -> str:
        return "Gate.io"

    async def initialize(self) -> None:
        """Initialize the Gate.io client."""
        self._client = ccxt.gate(
            {
                "enableRateLimit": True,
                "options": {
                    "defaultType": "swap",
                },
            }
        )

        await self._client.load_markets()

        self._symbols = [
            symbol
            for symbol in self._client.symbols
            if symbol.endswith(":USDT") and self._client.markets[symbol].get("swap")
        ]

        logger.info(f"Gate.io provider initialized", symbols=len(self._symbols))

    async def close(self) -> None:
        """Close the Gate.io client."""
        if self._client:
            await self._client.close()

    async def get_funding_rates(self) -> list[FundingRateData]:
        """Fetch funding rates from Gate.io."""
        if not self._client:
            return []

        funding_rates = []

        try:
            for symbol in self._symbols[:80]:  # Limit to top 80
                try:
                    async with self._rate_limiter:
                        funding_info = await self._client.fetch_funding_rate(symbol)

                    funding_rates.append(
                        FundingRateData(
                            exchange="gate",
                            symbol=symbol,
                            funding_rate=funding_info.get("fundingRate", 0),
                            predicted_rate=funding_info.get("fundingRatePredicted"),
                            next_funding_time=(
                                datetime.fromtimestamp(
                                    funding_info.get("fundingTimestamp", 0) / 1000
                                )
                                if funding_info.get("fundingTimestamp")
                                else None
                            ),
                            funding_interval_hours=8,
                            timestamp=datetime.utcnow(),
                        )
                    )

                    self._record_success()

                except Exception as e:
                    logger.warning(
                        f"Failed to fetch Gate funding rate",
                        symbol=symbol,
                        error=str(e),
                    )
                    self._record_error(str(e))

                await asyncio.sleep(0.1)

        except Exception as e:
            logger.error("Failed to fetch Gate.io funding rates", error=str(e))
            self._record_error(str(e))

        return funding_rates

    async def get_prices(self) -> list[PriceData]:
        """Fetch prices from Gate.io."""
        if not self._client:
            return []

        prices = []

        try:
            async with self._rate_limiter:
                tickers = await self._client.fetch_tickers()

            for symbol, ticker in tickers.items():
                if not symbol.endswith(":USDT"):
                    continue

                prices.append(
                    PriceData(
                        exchange="gate",
                        symbol=symbol,
                        mark_price=ticker.get("last", 0),
                        index_price=None,
                        bid=ticker.get("bid"),
                        ask=ticker.get("ask"),
                        volume_24h=ticker.get("quoteVolume", 0),
                        open_interest=None,
                        timestamp=datetime.utcnow(),
                    )
                )

            self._record_success()

        except Exception as e:
            logger.error("Failed to fetch Gate.io prices", error=str(e))
            self._record_error(str(e))

        return prices

    async def get_liquidity(self) -> list[LiquidityData]:
        """Fetch order book liquidity from Gate.io."""
        if not self._client:
            return []

        liquidity_data = []
        top_symbols = self._symbols[:30]

        for symbol in top_symbols:
            try:
                async with self._rate_limiter:
                    orderbook = await self._client.fetch_order_book(symbol, limit=20)

                bid_liquidity = sum(bid[1] * bid[0] for bid in orderbook["bids"][:5])
                ask_liquidity = sum(ask[1] * ask[0] for ask in orderbook["asks"][:5])

                spread = 0
                if orderbook["bids"] and orderbook["asks"]:
                    best_bid = orderbook["bids"][0][0]
                    best_ask = orderbook["asks"][0][0]
                    spread = (best_ask - best_bid) / best_bid * 100

                liquidity_data.append(
                    LiquidityData(
                        exchange="gate",
                        symbol=symbol,
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
                    f"Failed to fetch Gate.io orderbook", symbol=symbol, error=str(e)
                )
                self._record_error(str(e))

            await asyncio.sleep(0.15)

        return liquidity_data
