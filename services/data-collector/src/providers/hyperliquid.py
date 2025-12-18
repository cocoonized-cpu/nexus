"""
Hyperliquid Exchange Provider.

Hyperliquid is a Tier 1 DEX with 1-hour funding intervals.
Uses direct API calls as ccxt support may be limited.
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

HYPERLIQUID_API_BASE = "https://api.hyperliquid.xyz"


class HyperliquidProvider(ExchangeProvider):
    """Hyperliquid perpetual futures data provider."""

    def __init__(self):
        super().__init__()
        self._session: Optional[aiohttp.ClientSession] = None
        self._symbols: list[str] = []
        self._rate_limiter = asyncio.Semaphore(5)

    @property
    def exchange_id(self) -> str:
        return "hyperliquid"

    @property
    def display_name(self) -> str:
        return "Hyperliquid"

    async def initialize(self) -> None:
        """Initialize the Hyperliquid client."""
        self._session = aiohttp.ClientSession()

        # Fetch available markets
        try:
            async with self._session.post(
                f"{HYPERLIQUID_API_BASE}/info",
                json={"type": "meta"},
            ) as response:
                data = await response.json()
                universe = data.get("universe", [])
                self._symbols = [asset["name"] for asset in universe]

            logger.info(f"Hyperliquid provider initialized", symbols=len(self._symbols))

        except Exception as e:
            logger.error("Failed to initialize Hyperliquid", error=str(e))
            self._record_error(str(e))

    async def close(self) -> None:
        """Close the Hyperliquid client."""
        if self._session:
            await self._session.close()

    async def get_funding_rates(self) -> list[FundingRateData]:
        """Fetch funding rates from Hyperliquid."""
        if not self._session:
            return []

        funding_rates = []

        try:
            async with self._rate_limiter:
                async with self._session.post(
                    f"{HYPERLIQUID_API_BASE}/info",
                    json={"type": "metaAndAssetCtxs"},
                ) as response:
                    data = await response.json()

            # Parse meta and contexts
            meta = data[0] if len(data) > 0 else {}
            asset_ctxs = data[1] if len(data) > 1 else []
            universe = meta.get("universe", [])

            for i, asset in enumerate(universe):
                if i >= len(asset_ctxs):
                    break

                ctx = asset_ctxs[i]
                symbol = asset["name"]
                funding_rate = float(ctx.get("funding", 0))

                # Hyperliquid has 1-hour funding intervals
                funding_rates.append(
                    FundingRateData(
                        exchange="hyperliquid",
                        symbol=f"{symbol}/USD:USD",
                        funding_rate=funding_rate,
                        predicted_rate=None,
                        next_funding_time=None,  # Continuous funding
                        funding_interval_hours=1,
                        timestamp=datetime.utcnow(),
                    )
                )

            self._record_success()

        except Exception as e:
            logger.error("Failed to fetch Hyperliquid funding rates", error=str(e))
            self._record_error(str(e))

        return funding_rates

    async def get_prices(self) -> list[PriceData]:
        """Fetch prices from Hyperliquid."""
        if not self._session:
            return []

        prices = []

        try:
            async with self._rate_limiter:
                async with self._session.post(
                    f"{HYPERLIQUID_API_BASE}/info",
                    json={"type": "metaAndAssetCtxs"},
                ) as response:
                    data = await response.json()

            meta = data[0] if len(data) > 0 else {}
            asset_ctxs = data[1] if len(data) > 1 else []
            universe = meta.get("universe", [])

            for i, asset in enumerate(universe):
                if i >= len(asset_ctxs):
                    break

                ctx = asset_ctxs[i]
                symbol = asset["name"]

                prices.append(
                    PriceData(
                        exchange="hyperliquid",
                        symbol=f"{symbol}/USD:USD",
                        mark_price=float(ctx.get("markPx", 0)),
                        index_price=float(ctx.get("oraclePx", 0)) or None,
                        bid=None,
                        ask=None,
                        volume_24h=float(ctx.get("dayNtlVlm", 0)),
                        open_interest=float(ctx.get("openInterest", 0)) or None,
                        timestamp=datetime.utcnow(),
                    )
                )

            self._record_success()

        except Exception as e:
            logger.error("Failed to fetch Hyperliquid prices", error=str(e))
            self._record_error(str(e))

        return prices

    async def get_liquidity(self) -> list[LiquidityData]:
        """Fetch order book liquidity from Hyperliquid."""
        if not self._session:
            return []

        liquidity_data = []
        top_symbols = self._symbols[:30]

        for symbol in top_symbols:
            try:
                async with self._rate_limiter:
                    async with self._session.post(
                        f"{HYPERLIQUID_API_BASE}/info",
                        json={"type": "l2Book", "coin": symbol},
                    ) as response:
                        data = await response.json()

                levels = data.get("levels", [[], []])
                bids = levels[0] if len(levels) > 0 else []
                asks = levels[1] if len(levels) > 1 else []

                bid_liquidity = sum(
                    float(level.get("px", 0)) * float(level.get("sz", 0))
                    for level in bids[:5]
                )
                ask_liquidity = sum(
                    float(level.get("px", 0)) * float(level.get("sz", 0))
                    for level in asks[:5]
                )

                spread = 0
                if bids and asks:
                    best_bid = float(bids[0].get("px", 0))
                    best_ask = float(asks[0].get("px", 0))
                    if best_bid > 0:
                        spread = (best_ask - best_bid) / best_bid * 100

                liquidity_data.append(
                    LiquidityData(
                        exchange="hyperliquid",
                        symbol=f"{symbol}/USD:USD",
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
                    f"Failed to fetch Hyperliquid orderbook",
                    symbol=symbol,
                    error=str(e),
                )
                self._record_error(str(e))

            await asyncio.sleep(0.2)

        return liquidity_data
