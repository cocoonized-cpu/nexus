"""
Bybit Exchange Provider.

Bybit is a Tier 1 exchange with 8-hour funding intervals.
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


class BybitProvider(ExchangeProvider):
    """Bybit perpetual futures data provider."""

    def __init__(self):
        super().__init__()
        self._client: Optional[ccxt.bybit] = None
        self._symbols: list[str] = []
        self._rate_limiter = asyncio.Semaphore(10)

    @property
    def exchange_id(self) -> str:
        return "bybit"

    @property
    def display_name(self) -> str:
        return "Bybit"

    async def initialize(self) -> None:
        """Initialize the Bybit client."""
        self._client = ccxt.bybit(
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

        logger.info(f"Bybit provider initialized", symbols=len(self._symbols))

    async def close(self) -> None:
        """Close the Bybit client."""
        if self._client:
            await self._client.close()

    async def get_funding_rates(self) -> list[FundingRateData]:
        """Fetch funding rates from Bybit."""
        if not self._client:
            return []

        funding_rates = []

        try:
            async with self._rate_limiter:
                # Bybit tickers include funding rate info
                tickers = await self._client.fetch_tickers()

            for symbol, ticker in tickers.items():
                if not symbol.endswith(":USDT"):
                    continue

                info = ticker.get("info", {})
                funding_rate = float(info.get("fundingRate", 0) or 0)
                next_funding_time = info.get("nextFundingTime")

                funding_rates.append(
                    FundingRateData(
                        exchange="bybit",
                        symbol=symbol,
                        funding_rate=funding_rate,
                        predicted_rate=None,
                        next_funding_time=(
                            datetime.fromtimestamp(int(next_funding_time) / 1000)
                            if next_funding_time
                            else None
                        ),
                        funding_interval_hours=8,
                        timestamp=datetime.utcnow(),
                    )
                )

            self._record_success()

        except Exception as e:
            logger.error("Failed to fetch Bybit funding rates", error=str(e))
            self._record_error(str(e))

        return funding_rates

    async def get_prices(self) -> list[PriceData]:
        """Fetch prices from Bybit."""
        if not self._client:
            return []

        prices = []

        try:
            async with self._rate_limiter:
                tickers = await self._client.fetch_tickers()

            for symbol, ticker in tickers.items():
                if not symbol.endswith(":USDT"):
                    continue

                info = ticker.get("info", {})
                prices.append(
                    PriceData(
                        exchange="bybit",
                        symbol=symbol,
                        mark_price=float(
                            info.get("markPrice", 0) or ticker.get("last", 0)
                        ),
                        index_price=float(info.get("indexPrice", 0) or 0) or None,
                        bid=ticker.get("bid"),
                        ask=ticker.get("ask"),
                        volume_24h=ticker.get("quoteVolume", 0),
                        open_interest=float(info.get("openInterest", 0) or 0) or None,
                        timestamp=datetime.utcnow(),
                    )
                )

            self._record_success()

        except Exception as e:
            logger.error("Failed to fetch Bybit prices", error=str(e))
            self._record_error(str(e))

        return prices

    async def get_liquidity(self) -> list[LiquidityData]:
        """Fetch order book liquidity from Bybit."""
        if not self._client:
            return []

        liquidity_data = []
        top_symbols = self._symbols[:50]

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
                        exchange="bybit",
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
                    f"Failed to fetch Bybit orderbook", symbol=symbol, error=str(e)
                )
                self._record_error(str(e))

            await asyncio.sleep(0.1)

        return liquidity_data
