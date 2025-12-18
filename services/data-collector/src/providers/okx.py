"""
OKX Exchange Provider.

OKX is a Tier 1 exchange with 8-hour funding intervals.
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


class OKXProvider(ExchangeProvider):
    """OKX perpetual futures data provider."""

    def __init__(self):
        super().__init__()
        self._client: Optional[ccxt.okx] = None
        self._symbols: list[str] = []
        self._rate_limiter = asyncio.Semaphore(8)

    @property
    def exchange_id(self) -> str:
        return "okx"

    @property
    def display_name(self) -> str:
        return "OKX"

    async def initialize(self) -> None:
        """Initialize the OKX client."""
        self._client = ccxt.okx(
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

        logger.info(f"OKX provider initialized", symbols=len(self._symbols))

    async def close(self) -> None:
        """Close the OKX client."""
        if self._client:
            await self._client.close()

    async def get_funding_rates(self) -> list[FundingRateData]:
        """Fetch funding rates from OKX."""
        if not self._client:
            return []

        funding_rates = []

        try:
            # OKX has a dedicated funding rate endpoint
            for symbol in self._symbols[:100]:  # Limit to top 100
                try:
                    async with self._rate_limiter:
                        funding_info = await self._client.fetch_funding_rate(symbol)

                    funding_rates.append(
                        FundingRateData(
                            exchange="okx",
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
                        f"Failed to fetch OKX funding rate", symbol=symbol, error=str(e)
                    )
                    self._record_error(str(e))

                await asyncio.sleep(0.05)

        except Exception as e:
            logger.error("Failed to fetch OKX funding rates", error=str(e))
            self._record_error(str(e))

        return funding_rates

    async def get_prices(self) -> list[PriceData]:
        """Fetch prices from OKX."""
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
                        exchange="okx",
                        symbol=symbol,
                        mark_price=float(
                            info.get("markPx", 0) or ticker.get("last", 0)
                        ),
                        index_price=float(info.get("indexPx", 0) or 0) or None,
                        bid=ticker.get("bid"),
                        ask=ticker.get("ask"),
                        volume_24h=ticker.get("quoteVolume", 0),
                        open_interest=float(info.get("openInterest", 0) or 0) or None,
                        timestamp=datetime.utcnow(),
                    )
                )

            self._record_success()

        except Exception as e:
            logger.error("Failed to fetch OKX prices", error=str(e))
            self._record_error(str(e))

        return prices

    async def get_liquidity(self) -> list[LiquidityData]:
        """Fetch order book liquidity from OKX."""
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
                        exchange="okx",
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
                    f"Failed to fetch OKX orderbook", symbol=symbol, error=str(e)
                )
                self._record_error(str(e))

            await asyncio.sleep(0.1)

        return liquidity_data
