"""
Binance Exchange Provider.

Binance is a Tier 1 exchange with 8-hour funding intervals.
Uses ccxt library for API interactions.
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


class BinanceProvider(ExchangeProvider):
    """Binance perpetual futures data provider."""

    def __init__(self):
        super().__init__()
        self._client: Optional[ccxt.binance] = None
        self._symbols: list[str] = []
        self._rate_limiter = asyncio.Semaphore(10)  # Max 10 concurrent requests

    @property
    def exchange_id(self) -> str:
        return "binance"

    @property
    def display_name(self) -> str:
        return "Binance"

    async def initialize(self) -> None:
        """Initialize the Binance client."""
        self._client = ccxt.binance(
            {
                "enableRateLimit": True,
                "options": {
                    "defaultType": "swap",  # Perpetual futures
                },
            }
        )

        # Load markets
        await self._client.load_markets()

        # Filter USDT perpetual markets
        self._symbols = [
            symbol
            for symbol in self._client.symbols
            if symbol.endswith(":USDT") and self._client.markets[symbol].get("swap")
        ]

        logger.info(
            f"Binance provider initialized",
            symbols=len(self._symbols),
        )

    async def close(self) -> None:
        """Close the Binance client."""
        if self._client:
            await self._client.close()

    async def get_funding_rates(self) -> list[FundingRateData]:
        """Fetch funding rates from Binance."""
        if not self._client:
            return []

        funding_rates = []

        try:
            async with self._rate_limiter:
                # Binance provides funding rates in premium index endpoint
                response = await self._client.fapiPublicGetPremiumIndex()

            for item in response:
                symbol = item.get("symbol", "")
                if not symbol.endswith("USDT"):
                    continue

                # Convert to standardized symbol format
                base = symbol[:-4]  # Remove USDT
                std_symbol = f"{base}/USDT:USDT"

                funding_rate = float(item.get("lastFundingRate", 0))
                predicted_rate = float(item.get("interestRate", 0))
                next_funding_time = int(item.get("nextFundingTime", 0))

                funding_rates.append(
                    FundingRateData(
                        exchange="binance",
                        symbol=std_symbol,
                        funding_rate=funding_rate,
                        predicted_rate=predicted_rate,
                        next_funding_time=(
                            datetime.fromtimestamp(next_funding_time / 1000)
                            if next_funding_time
                            else None
                        ),
                        funding_interval_hours=8,
                        timestamp=datetime.utcnow(),
                    )
                )

            self._record_success()

        except Exception as e:
            logger.error("Failed to fetch Binance funding rates", error=str(e))
            self._record_error(str(e))

        return funding_rates

    async def get_prices(self) -> list[PriceData]:
        """Fetch prices from Binance."""
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
                        exchange="binance",
                        symbol=symbol,
                        mark_price=ticker.get("last", 0),
                        index_price=ticker.get("info", {}).get("indexPrice"),
                        bid=ticker.get("bid"),
                        ask=ticker.get("ask"),
                        volume_24h=ticker.get("quoteVolume", 0),
                        open_interest=None,  # Requires separate call
                        timestamp=datetime.utcnow(),
                    )
                )

            self._record_success()

        except Exception as e:
            logger.error("Failed to fetch Binance prices", error=str(e))
            self._record_error(str(e))

        return prices

    async def get_liquidity(self) -> list[LiquidityData]:
        """Fetch order book liquidity from Binance."""
        if not self._client:
            return []

        liquidity_data = []

        # Only fetch for top symbols to reduce API load
        top_symbols = self._symbols[:50]

        for symbol in top_symbols:
            try:
                async with self._rate_limiter:
                    orderbook = await self._client.fetch_order_book(symbol, limit=20)

                # Calculate liquidity at different price levels
                bid_liquidity_1pct = sum(
                    bid[1] * bid[0] for bid in orderbook["bids"][:5]
                )
                ask_liquidity_1pct = sum(
                    ask[1] * ask[0] for ask in orderbook["asks"][:5]
                )

                spread = 0
                if orderbook["bids"] and orderbook["asks"]:
                    best_bid = orderbook["bids"][0][0]
                    best_ask = orderbook["asks"][0][0]
                    spread = (best_ask - best_bid) / best_bid * 100

                liquidity_data.append(
                    LiquidityData(
                        exchange="binance",
                        symbol=symbol,
                        bid_liquidity_usd=bid_liquidity_1pct,
                        ask_liquidity_usd=ask_liquidity_1pct,
                        spread_pct=spread,
                        depth_imbalance=(
                            (bid_liquidity_1pct - ask_liquidity_1pct)
                            / (bid_liquidity_1pct + ask_liquidity_1pct)
                            if (bid_liquidity_1pct + ask_liquidity_1pct) > 0
                            else 0
                        ),
                        timestamp=datetime.utcnow(),
                    )
                )

                self._record_success()

            except Exception as e:
                logger.warning(
                    f"Failed to fetch Binance orderbook",
                    symbol=symbol,
                    error=str(e),
                )
                self._record_error(str(e))

            # Small delay between orderbook requests
            await asyncio.sleep(0.1)

        return liquidity_data
