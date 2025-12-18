"""
Exchange Client - Unified interface for connecting to exchanges.

Supports:
- CCXT-compatible exchanges (most CEXes)
- Native API exchanges (Hyperliquid, dYdX)
"""

import asyncio
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

import ccxt.async_support as ccxt
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from shared.utils.logging import get_logger
from shared.utils.hyperliquid_client import HyperliquidClient

logger = get_logger(__name__)

# Mapping from our slug to CCXT exchange IDs
EXCHANGE_MAPPING = {
    "binance_futures": "binance",
    "bybit_futures": "bybit",
    "okex_futures": "okx",
    "gate_futures": "gate",
    "kucoin_futures": "kucoinfutures",
    "bitget_futures": "bitget",
    "mexc_futures": "mexc",
    "bingx_futures": "bingx",
}


class ExchangeCredentials:
    """Exchange credential container."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        passphrase: Optional[str] = None,
        wallet_address: Optional[str] = None,
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.wallet_address = wallet_address


class ExchangeClient:
    """Unified exchange client for balance and order operations."""

    def __init__(
        self,
        slug: str,
        credentials: ExchangeCredentials,
        api_type: str = "ccxt",
        sandbox: bool = False,
    ):
        self.slug = slug
        self.credentials = credentials
        self.api_type = api_type
        self.sandbox = sandbox
        self._client: Optional[ccxt.Exchange] = None
        self._hyperliquid: Optional[HyperliquidClient] = None

    async def connect(self) -> bool:
        """Connect to the exchange."""
        try:
            if self.api_type == "ccxt":
                return await self._connect_ccxt()
            elif self.api_type == "native":
                return await self._connect_native()
            else:
                logger.error(f"Unknown API type: {self.api_type}")
                return False
        except Exception as e:
            logger.error(f"Failed to connect to {self.slug}", error=str(e))
            return False

    async def _connect_ccxt(self) -> bool:
        """Connect using CCXT."""
        exchange_id = EXCHANGE_MAPPING.get(self.slug)
        if not exchange_id:
            logger.error(f"No CCXT mapping for {self.slug}")
            return False

        exchange_class = getattr(ccxt, exchange_id, None)
        if not exchange_class:
            logger.error(f"CCXT exchange not found: {exchange_id}")
            return False

        config: dict[str, Any] = {
            "enableRateLimit": True,
            "adjustForTimeDifference": True,  # Auto-sync with exchange server time
            "recvWindow": 20000,  # Increase receive window to 20 seconds for all exchanges
            "options": {
                "defaultType": "swap",  # Use perpetual/futures
                "warnOnFetchOpenOrdersWithoutSymbol": False,  # Suppress warning for fetching all orders
                "recvWindow": 20000,  # Also set in options for exchanges that read from there
                "recv_window": 20000,  # Bybit uses recv_window
                "timeDifference": 0,  # Will be updated by adjustForTimeDifference
                "adjustForTimeDifference": True,
            },
        }

        if self.credentials.api_key:
            config["apiKey"] = self.credentials.api_key
        if self.credentials.api_secret:
            config["secret"] = self.credentials.api_secret
        if self.credentials.passphrase:
            config["password"] = self.credentials.passphrase

        self._client = exchange_class(config)

        if self.sandbox:
            self._client.set_sandbox_mode(True)

        logger.info(f"Connected to {self.slug} via CCXT")
        return True

    async def _connect_native(self) -> bool:
        """Connect using native API (for Hyperliquid, dYdX, etc.)."""
        if "hyperliquid" in self.slug.lower():
            self._hyperliquid = HyperliquidClient(
                wallet_address=self.credentials.wallet_address,
                private_key=self.credentials.api_secret,  # Private key stored as api_secret
                testnet=self.sandbox,
            )
            connected = await self._hyperliquid.connect()
            if connected:
                logger.info(f"Connected to Hyperliquid via native API")
            return connected
        else:
            # Other native exchanges can be added here
            logger.warning(f"Native API not implemented for {self.slug}")
            return False

    async def disconnect(self) -> None:
        """Disconnect from the exchange."""
        if self._client:
            await self._client.close()
            self._client = None
        if self._hyperliquid:
            await self._hyperliquid.disconnect()
            self._hyperliquid = None

    async def get_balance(self) -> dict[str, Any]:
        """Fetch account balance from the exchange."""
        if not self._client and self.api_type == "ccxt":
            raise RuntimeError("Not connected to exchange")

        try:
            if self.api_type == "ccxt":
                return await self._get_ccxt_balance()
            elif self.api_type == "native":
                return await self._get_native_balance()
            else:
                return {"total_usd": 0, "balances": {}}
        except Exception as e:
            logger.error(f"Failed to get balance from {self.slug}", error=str(e))
            return {"total_usd": 0, "balances": {}, "error": str(e)}

    async def _get_ccxt_balance(self) -> dict[str, Any]:
        """Get balance via CCXT."""
        if not self._client:
            return {"total_usd": 0, "balances": {}}

        balance = await self._client.fetch_balance()

        # Extract relevant info - include ALL currencies
        total_usd = Decimal("0")
        balances: dict[str, dict[str, float]] = {}

        for currency, data in balance.get("total", {}).items():
            # Include all currencies, not just ones with balance
            total_val = float(data) if data else 0
            free_val = float(balance.get("free", {}).get(currency, 0) or 0)
            used_val = float(balance.get("used", {}).get(currency, 0) or 0)

            balances[currency] = {
                "free": free_val,
                "used": used_val,
                "total": total_val,
            }

            # Estimate USD value (simplified - assumes stablecoins are 1:1)
            if data and data > 0 and currency in ["USDT", "USDC", "USD", "BUSD"]:
                total_usd += Decimal(str(data))

        # Try to get USD value from exchange if available
        if "USD" in balance:
            total_info = balance.get("info", {})
            if isinstance(total_info, dict):
                total_wallet = total_info.get("totalWalletBalance")
                if total_wallet:
                    total_usd = Decimal(str(total_wallet))

        return {
            "total_usd": float(total_usd),
            "balances": balances,
            "margin_used": float(balance.get("used", {}).get("USDT", 0) or 0),
            "margin_available": float(balance.get("free", {}).get("USDT", 0) or 0),
        }

    async def _get_native_balance(self) -> dict[str, Any]:
        """Get balance via native API."""
        if self._hyperliquid:
            return await self._hyperliquid.get_balance()

        # Other native exchanges
        return {
            "total_usd": 0,
            "balances": {},
            "margin_used": 0,
            "margin_available": 0,
        }

    async def get_positions(self) -> list[dict[str, Any]]:
        """Fetch open positions from the exchange."""
        try:
            if self.api_type == "ccxt":
                if not self._client:
                    return []
                positions = await self._client.fetch_positions()
                return [
                    {
                        "symbol": pos["symbol"],
                        "side": pos["side"],
                        "size": float(pos["contracts"] or 0),
                        "notional": float(pos["notional"] or 0),
                        "entry_price": float(pos["entryPrice"] or 0),
                        "mark_price": float(pos["markPrice"] or 0),
                        "unrealized_pnl": float(pos["unrealizedPnl"] or 0),
                        "leverage": float(pos["leverage"] or 1),
                        "liquidation_price": float(pos["liquidationPrice"] or 0)
                        if pos.get("liquidationPrice")
                        else None,
                        "margin_mode": pos.get("marginMode", "cross"),
                    }
                    for pos in positions
                    if pos.get("contracts") and float(pos["contracts"]) != 0
                ]
            elif self.api_type == "native" and self._hyperliquid:
                return await self._hyperliquid.get_positions()
            else:
                return []
        except Exception as e:
            logger.error(f"Failed to get positions from {self.slug}", error=str(e))
            return []

    async def get_orders(self, symbol: Optional[str] = None) -> list[dict[str, Any]]:
        """Fetch open orders from the exchange."""
        try:
            if self.api_type == "ccxt":
                if not self._client:
                    return []
                orders = await self._client.fetch_open_orders(symbol)
                return [
                    {
                        "id": order["id"],
                        "symbol": order["symbol"],
                        "side": order["side"],
                        "type": order["type"],
                        "price": float(order["price"] or 0),
                        "amount": float(order["amount"] or 0),
                        "filled": float(order["filled"] or 0),
                        "remaining": float(order["remaining"] or 0),
                        "status": order["status"],
                        "created_at": order["datetime"],
                    }
                    for order in orders
                ]
            elif self.api_type == "native" and self._hyperliquid:
                return await self._hyperliquid.get_open_orders(symbol)
            else:
                return []
        except Exception as e:
            logger.error(f"Failed to get orders from {self.slug}", error=str(e))
            return []

    async def get_trades(self, symbol: Optional[str] = None, since: Optional[int] = None, limit: int = 100) -> list[dict[str, Any]]:
        """Fetch recent trades/fills from the exchange."""
        try:
            if self.api_type == "ccxt":
                if not self._client:
                    return []
                # Binance requires a symbol for fetch_my_trades - return empty if no symbol
                if not symbol and self.slug.startswith("binance"):
                    return []
                # Fetch my trades (filled orders)
                trades = await self._client.fetch_my_trades(symbol, since=since, limit=limit)
                if not trades:
                    return []
                result = []
                for trade in trades:
                    if not trade:
                        continue
                    fee_info = trade.get("fee") or {}
                    result.append({
                        "id": trade.get("id", ""),
                        "order_id": trade.get("order"),
                        "symbol": trade.get("symbol", ""),
                        "side": trade.get("side", ""),
                        "price": float(trade.get("price") or 0),
                        "amount": float(trade.get("amount") or 0),
                        "cost": float(trade.get("cost") or 0),
                        "fee": float(fee_info.get("cost") or 0),
                        "fee_currency": fee_info.get("currency"),
                        "timestamp": trade.get("timestamp"),
                        "datetime": trade.get("datetime"),
                    })
                return result
            elif self.api_type == "native" and self._hyperliquid:
                return await self._hyperliquid.get_fills(limit=limit)
            else:
                return []
        except Exception as e:
            import traceback
            logger.error(f"Failed to get trades from {self.slug}", error=str(e), traceback=traceback.format_exc())
            return []

    async def get_closed_orders(self, symbol: Optional[str] = None, since: Optional[int] = None, limit: int = 100) -> list[dict[str, Any]]:
        """Fetch closed/cancelled orders from the exchange."""
        try:
            if self.api_type == "ccxt":
                if not self._client:
                    return []
                # Try fetch_closed_orders if available
                if self._client.has.get("fetchClosedOrders"):
                    orders = await self._client.fetch_closed_orders(symbol, since=since, limit=limit)
                else:
                    # Fallback to fetch_orders with closed status
                    orders = await self._client.fetch_orders(symbol, since=since, limit=limit)
                    orders = [o for o in orders if o["status"] in ("closed", "canceled", "cancelled")]

                return [
                    {
                        "id": order["id"],
                        "symbol": order["symbol"],
                        "side": order["side"],
                        "type": order["type"],
                        "price": float(order["price"] or order.get("average") or 0),
                        "amount": float(order["amount"] or 0),
                        "filled": float(order["filled"] or 0),
                        "cost": float(order["cost"] or 0),
                        "fee": float(order["fee"]["cost"]) if order.get("fee") else 0,
                        "fee_currency": order["fee"]["currency"] if order.get("fee") else None,
                        "status": order["status"],
                        "timestamp": order["timestamp"],
                        "datetime": order["datetime"],
                    }
                    for order in orders
                ]
            elif self.api_type == "native" and self._hyperliquid:
                return await self._hyperliquid.get_order_history(limit=limit)
            else:
                return []
        except Exception as e:
            logger.error(f"Failed to get closed orders from {self.slug}", error=str(e))
            return []

    def _normalize_symbol_for_ccxt(self, symbol: str) -> str:
        """
        Normalize symbol to CCXT perpetual format.

        CCXT expects symbols like "BTC/USDT:USDT" for perpetual futures.
        Input might be "BTC", "BTCUSDT", "BTC/USDT", etc.
        """
        # Already in correct format
        if "/" in symbol and ":" in symbol:
            return symbol

        # Remove common suffixes to get base asset
        base = symbol.upper()
        for suffix in ["USDT", "USD", "PERP", "-PERP", "/USDT", "-USDT"]:
            if base.endswith(suffix):
                base = base[:-len(suffix)]
                break

        # Build the CCXT perpetual format: BASE/USDT:USDT
        return f"{base}/USDT:USDT"

    async def place_order(
        self,
        symbol: str,
        side: str,
        size: float,
        price: Optional[float] = None,
        order_type: str = "limit",
        reduce_only: bool = False,
    ) -> dict[str, Any]:
        """Place an order on the exchange."""
        try:
            if self.api_type == "ccxt":
                if not self._client:
                    return {"success": False, "error": "Not connected"}

                # Normalize symbol to CCXT format (e.g., "BTC" -> "BTC/USDT:USDT")
                ccxt_symbol = self._normalize_symbol_for_ccxt(symbol)

                if order_type == "market":
                    order = await self._client.create_market_order(
                        ccxt_symbol, side, size, params={"reduceOnly": reduce_only}
                    )
                else:
                    order = await self._client.create_limit_order(
                        ccxt_symbol, side, size, price, params={"reduceOnly": reduce_only}
                    )

                return {
                    "success": True,
                    "order_id": order["id"],
                    "symbol": ccxt_symbol,
                    "side": side,
                    "size": size,
                    "price": price,
                }

            elif self.api_type == "native" and self._hyperliquid:
                return await self._hyperliquid.place_order(
                    symbol=symbol,
                    side=side,
                    size=size,
                    price=price,
                    order_type=order_type,
                    reduce_only=reduce_only,
                )
            else:
                return {"success": False, "error": "Not connected"}

        except Exception as e:
            logger.error(f"Failed to place order on {self.slug}", error=str(e))
            return {"success": False, "error": str(e)}

    async def cancel_order(self, symbol: str, order_id: str) -> dict[str, Any]:
        """Cancel an order on the exchange."""
        try:
            if self.api_type == "ccxt":
                if not self._client:
                    return {"success": False, "error": "Not connected"}

                # Normalize symbol to CCXT format
                ccxt_symbol = self._normalize_symbol_for_ccxt(symbol)
                await self._client.cancel_order(order_id, ccxt_symbol)
                return {"success": True, "order_id": order_id}

            elif self.api_type == "native" and self._hyperliquid:
                return await self._hyperliquid.cancel_order(symbol, int(order_id))
            else:
                return {"success": False, "error": "Not connected"}

        except Exception as e:
            logger.error(f"Failed to cancel order on {self.slug}", error=str(e))
            return {"success": False, "error": str(e)}

    async def get_ticker(self, symbol: str) -> Optional[dict[str, Any]]:
        """Get current ticker/price for a symbol."""
        try:
            if self.api_type == "ccxt":
                if not self._client:
                    return None

                # Normalize symbol to CCXT format
                ccxt_symbol = self._normalize_symbol_for_ccxt(symbol)
                ticker = await self._client.fetch_ticker(ccxt_symbol)

                return {
                    "symbol": ticker.get("symbol"),
                    "last": float(ticker.get("last") or 0),
                    "bid": float(ticker.get("bid") or 0),
                    "ask": float(ticker.get("ask") or 0),
                    "high": float(ticker.get("high") or 0),
                    "low": float(ticker.get("low") or 0),
                    "volume": float(ticker.get("baseVolume") or 0),
                    "timestamp": ticker.get("timestamp"),
                }

            elif self.api_type == "native" and self._hyperliquid:
                return await self._hyperliquid.get_ticker(symbol)
            else:
                return None

        except Exception as e:
            logger.error(f"Failed to get ticker from {self.slug}", error=str(e))
            return None

    async def get_min_order_size(self, symbol: str) -> Optional[float]:
        """Get minimum order size for a symbol."""
        try:
            if self.api_type == "ccxt":
                if not self._client:
                    return None

                # Normalize symbol to CCXT format
                ccxt_symbol = self._normalize_symbol_for_ccxt(symbol)

                # Load markets if not loaded
                if not self._client.markets:
                    await self._client.load_markets()

                market = self._client.market(ccxt_symbol)
                if market:
                    # Get minimum amount from market limits
                    limits = market.get("limits", {})
                    amount_limits = limits.get("amount", {})
                    min_amount = amount_limits.get("min")

                    if min_amount:
                        return float(min_amount)

                return None

            elif self.api_type == "native" and self._hyperliquid:
                return await self._hyperliquid.get_min_order_size(symbol)
            else:
                return None

        except Exception as e:
            logger.warning(f"Failed to get min order size from {self.slug}", error=str(e))
            return None


async def get_exchange_credentials(
    db: AsyncSession, slug: str, encryption_key: str = "nexus_secret"
) -> Optional[ExchangeCredentials]:
    """Fetch decrypted credentials for an exchange from the database."""
    query = text("""
        SELECT
            pgp_sym_decrypt(api_key_encrypted, :key)::text as api_key,
            pgp_sym_decrypt(api_secret_encrypted, :key)::text as api_secret,
            pgp_sym_decrypt(passphrase_encrypted, :key)::text as passphrase,
            pgp_sym_decrypt(wallet_address_encrypted, :key)::text as wallet_address
        FROM config.exchanges
        WHERE slug = :slug
          AND (api_key_encrypted IS NOT NULL OR wallet_address_encrypted IS NOT NULL)
    """)

    try:
        result = await db.execute(query, {"slug": slug, "key": encryption_key})
        row = result.fetchone()

        if not row:
            return None

        # Ensure strings are not None (empty string is safer than None for CCXT)
        api_key = row[0] if row[0] else ""
        api_secret = row[1] if row[1] else ""
        passphrase = row[2] if row[2] else ""
        wallet_address = row[3] if row[3] else ""

        # At least one credential type must be present
        if not api_key and not wallet_address:
            logger.warning(f"No valid credentials found for {slug}")
            return None

        return ExchangeCredentials(
            api_key=api_key,
            api_secret=api_secret,
            passphrase=passphrase,
            wallet_address=wallet_address,
        )
    except Exception as e:
        logger.error(f"Failed to fetch credentials for {slug}", error=str(e))
        return None


async def get_enabled_exchanges(db: AsyncSession) -> list[dict[str, Any]]:
    """Fetch all enabled exchanges from the database."""
    query = text("""
        SELECT
            slug, display_name, api_type, exchange_type,
            (api_key_encrypted IS NOT NULL OR wallet_address_encrypted IS NOT NULL) as has_credentials
        FROM config.exchanges
        WHERE enabled = true
        ORDER BY tier, display_name
    """)

    result = await db.execute(query)
    rows = result.fetchall()

    return [
        {
            "slug": row[0],
            "display_name": row[1],
            "api_type": row[2],
            "exchange_type": row[3],
            "has_credentials": row[4],
        }
        for row in rows
    ]
