"""
Hyperliquid Native API Client.

Hyperliquid is a decentralized perpetual exchange that uses:
- REST API for public data
- Signed requests (EIP-712) for trading operations

API Documentation: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api
"""

import asyncio
import hashlib
import json
import time
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

import aiohttp
from eth_account import Account
from eth_account.messages import encode_typed_data

from shared.utils.logging import get_logger

logger = get_logger(__name__)

# Hyperliquid API endpoints
HYPERLIQUID_API = "https://api.hyperliquid.xyz"
HYPERLIQUID_MAINNET_CHAIN_ID = 42161  # Arbitrum


class HyperliquidClient:
    """
    Hyperliquid trading client for balance, orders, and positions.

    Supports:
    - Balance fetching
    - Position management
    - Order placement and cancellation
    - Funding rate queries
    """

    def __init__(
        self,
        wallet_address: Optional[str] = None,
        private_key: Optional[str] = None,
        testnet: bool = False,
    ):
        self.wallet_address = wallet_address
        self.private_key = private_key
        self.testnet = testnet
        self._session: Optional[aiohttp.ClientSession] = None
        self._meta: Optional[dict] = None
        self._asset_map: dict[str, int] = {}  # symbol -> asset index

    async def connect(self) -> bool:
        """Initialize connection and fetch metadata."""
        try:
            self._session = aiohttp.ClientSession()

            # Fetch exchange metadata
            self._meta = await self._post_info({"type": "meta"})

            # Build asset index map
            universe = self._meta.get("universe", [])
            for i, asset in enumerate(universe):
                self._asset_map[asset["name"]] = i

            logger.info(
                "Hyperliquid client connected",
                assets=len(self._asset_map),
                wallet=self.wallet_address[:10] + "..." if self.wallet_address else None,
            )
            return True

        except Exception as e:
            logger.error("Failed to connect to Hyperliquid", error=str(e))
            return False

    async def disconnect(self) -> None:
        """Close the client connection."""
        if self._session:
            await self._session.close()
            self._session = None

    async def _post_info(self, payload: dict) -> Any:
        """Make a POST request to the info endpoint."""
        if not self._session:
            raise RuntimeError("Client not connected")

        async with self._session.post(
            f"{HYPERLIQUID_API}/info",
            json=payload,
            headers={"Content-Type": "application/json"},
        ) as response:
            return await response.json()

    async def _post_exchange(self, action: dict) -> Any:
        """Make a signed POST request to the exchange endpoint."""
        if not self._session or not self.private_key:
            raise RuntimeError("Client not connected or no private key")

        nonce = int(time.time() * 1000)

        # Create the signature
        signature = self._sign_action(action, nonce)

        payload = {
            "action": action,
            "nonce": nonce,
            "signature": signature,
        }

        async with self._session.post(
            f"{HYPERLIQUID_API}/exchange",
            json=payload,
            headers={"Content-Type": "application/json"},
        ) as response:
            # Handle both JSON and text responses
            content_type = response.headers.get("Content-Type", "")

            if response.status >= 400:
                # Try to get error text
                try:
                    if "application/json" in content_type:
                        error_data = await response.json()
                        error_msg = error_data.get("error", str(error_data))
                    else:
                        error_msg = await response.text()
                except Exception:
                    error_msg = f"HTTP {response.status}"

                logger.error(
                    "Hyperliquid API error",
                    status=response.status,
                    error=error_msg,
                    action_type=action.get("type"),
                )
                return {"status": "error", "error": error_msg, "http_status": response.status}

            # Parse successful response
            if "application/json" in content_type:
                return await response.json()
            else:
                # Handle text responses (shouldn't happen for successful requests)
                text = await response.text()
                logger.warning(
                    "Unexpected text response from Hyperliquid",
                    content_type=content_type,
                    text=text[:200],
                )
                # Try to parse as JSON anyway
                try:
                    import json as json_lib
                    return json_lib.loads(text)
                except Exception:
                    return {"status": "error", "error": f"Unexpected response format: {text[:100]}"}

    def _sign_action(self, action: dict, nonce: int) -> dict:
        """Sign an action using EIP-712."""
        if not self.private_key:
            raise RuntimeError("No private key configured")

        # EIP-712 typed data for Hyperliquid
        domain = {
            "name": "HyperliquidSignTransaction",
            "version": "1",
            "chainId": HYPERLIQUID_MAINNET_CHAIN_ID,
            "verifyingContract": "0x0000000000000000000000000000000000000000",
        }

        # Create the message hash
        action_hash = self._action_hash(action, nonce)

        types = {
            "HyperliquidTransaction:Approve": [
                {"name": "hyperliquidChain", "type": "string"},
                {"name": "signatureChainId", "type": "uint64"},
                {"name": "nonce", "type": "uint64"},
            ],
        }

        message = {
            "hyperliquidChain": "Mainnet" if not self.testnet else "Testnet",
            "signatureChainId": HYPERLIQUID_MAINNET_CHAIN_ID,
            "nonce": nonce,
        }

        # Sign with eth_account
        account = Account.from_key(self.private_key)
        signed = account.sign_typed_data(domain, types, message)

        return {
            "r": hex(signed.r),
            "s": hex(signed.s),
            "v": signed.v,
        }

    def _action_hash(self, action: dict, nonce: int) -> str:
        """Create action hash for signing."""
        action_str = json.dumps(action, separators=(",", ":"), sort_keys=True)
        return hashlib.sha256(f"{action_str}{nonce}".encode()).hexdigest()

    # ==================== Balance Operations ====================

    async def get_balance(self) -> dict[str, Any]:
        """Fetch account balance and margin info."""
        if not self.wallet_address:
            return {"total_usd": 0, "balances": {}, "error": "No wallet address"}

        try:
            # Get clearinghouse state
            state = await self._post_info({
                "type": "clearinghouseState",
                "user": self.wallet_address,
            })

            margin_summary = state.get("marginSummary", {})
            account_value = float(margin_summary.get("accountValue", 0))
            total_margin_used = float(margin_summary.get("totalMarginUsed", 0))

            # Cross margin info
            cross_margin = state.get("crossMarginSummary", {})

            # Hyperliquid uses USDC as the settlement currency
            balances = {
                "USDC": {
                    "free": account_value - total_margin_used,
                    "used": total_margin_used,
                    "total": account_value,
                }
            }

            return {
                "total_usd": account_value,
                "balances": balances,
                "margin_used": total_margin_used,
                "margin_available": account_value - total_margin_used,
                "withdrawable": float(state.get("withdrawable", 0)),
            }

        except Exception as e:
            logger.error("Failed to get Hyperliquid balance", error=str(e))
            return {"total_usd": 0, "balances": {}, "error": str(e)}

    # ==================== Position Operations ====================

    async def get_positions(self) -> list[dict[str, Any]]:
        """Fetch all open positions."""
        if not self.wallet_address:
            return []

        try:
            state = await self._post_info({
                "type": "clearinghouseState",
                "user": self.wallet_address,
            })

            positions = []
            for pos in state.get("assetPositions", []):
                position = pos.get("position", {})
                if not position:
                    continue

                size = float(position.get("szi", 0))
                if size == 0:
                    continue

                entry_price = float(position.get("entryPx", 0))

                # Get current mark price
                coin = position.get("coin", "")

                positions.append({
                    "symbol": f"{coin}/USD:USD",
                    "side": "long" if size > 0 else "short",
                    "size": abs(size),
                    "notional": abs(size) * entry_price,
                    "entry_price": entry_price,
                    "mark_price": float(position.get("markPx", entry_price)),
                    "unrealized_pnl": float(position.get("unrealizedPnl", 0)),
                    "leverage": float(position.get("leverage", {}).get("value", 1)),
                    "liquidation_price": float(position.get("liquidationPx", 0)) or None,
                    "margin_mode": position.get("leverage", {}).get("type", "cross"),
                    "funding_pnl": float(position.get("cumFunding", {}).get("sinceOpen", 0)),
                })

            return positions

        except Exception as e:
            logger.error("Failed to get Hyperliquid positions", error=str(e))
            return []

    # ==================== Order Operations ====================

    async def place_order(
        self,
        symbol: str,
        side: str,  # "buy" or "sell"
        size: float,
        price: Optional[float] = None,
        order_type: str = "limit",  # "limit" or "market"
        reduce_only: bool = False,
        time_in_force: str = "Gtc",  # "Gtc", "Ioc", "Alo"
    ) -> dict[str, Any]:
        """Place an order on Hyperliquid."""
        if not self.private_key:
            return {"success": False, "error": "No private key configured"}

        # Get asset index
        coin = symbol.split("/")[0]
        asset_idx = self._asset_map.get(coin)
        if asset_idx is None:
            return {"success": False, "error": f"Unknown asset: {coin}"}

        try:
            # Build order action
            is_buy = side.lower() == "buy"

            order = {
                "a": asset_idx,  # asset index
                "b": is_buy,  # is buy
                "p": str(price) if price else "0",  # price (0 for market)
                "s": str(size),  # size
                "r": reduce_only,
                "t": {
                    "limit": {"tif": time_in_force},
                } if order_type == "limit" else {
                    "trigger": {
                        "isMarket": True,
                        "triggerPx": str(price) if price else "0",
                        "tpsl": "tp",
                    }
                },
            }

            action = {
                "type": "order",
                "orders": [order],
                "grouping": "na",
            }

            result = await self._post_exchange(action)

            if result.get("status") == "ok":
                response = result.get("response", {})
                statuses = response.get("data", {}).get("statuses", [])
                if statuses and "resting" in statuses[0]:
                    order_id = statuses[0]["resting"]["oid"]
                    return {
                        "success": True,
                        "order_id": order_id,
                        "symbol": symbol,
                        "side": side,
                        "size": size,
                        "price": price,
                    }
                elif statuses and "filled" in statuses[0]:
                    return {
                        "success": True,
                        "order_id": statuses[0]["filled"]["oid"],
                        "symbol": symbol,
                        "side": side,
                        "size": size,
                        "filled": True,
                    }

            return {"success": False, "error": result}

        except Exception as e:
            logger.error("Failed to place Hyperliquid order", error=str(e))
            return {"success": False, "error": str(e)}

    async def cancel_order(self, symbol: str, order_id: int) -> dict[str, Any]:
        """Cancel an order."""
        if not self.private_key:
            return {"success": False, "error": "No private key configured"}

        coin = symbol.split("/")[0]
        asset_idx = self._asset_map.get(coin)
        if asset_idx is None:
            return {"success": False, "error": f"Unknown asset: {coin}"}

        try:
            action = {
                "type": "cancel",
                "cancels": [{"a": asset_idx, "o": order_id}],
            }

            result = await self._post_exchange(action)

            if result.get("status") == "ok":
                return {"success": True, "order_id": order_id}

            return {"success": False, "error": result}

        except Exception as e:
            logger.error("Failed to cancel Hyperliquid order", error=str(e))
            return {"success": False, "error": str(e)}

    async def get_open_orders(self, symbol: Optional[str] = None) -> list[dict[str, Any]]:
        """Fetch open orders."""
        if not self.wallet_address:
            return []

        try:
            orders = await self._post_info({
                "type": "openOrders",
                "user": self.wallet_address,
            })

            result = []
            for order in orders:
                order_symbol = f"{order.get('coin', '')}/USD:USD"
                if symbol and order_symbol != symbol:
                    continue

                result.append({
                    "id": order.get("oid"),
                    "symbol": order_symbol,
                    "side": "buy" if order.get("side") == "B" else "sell",
                    "type": "limit",
                    "price": float(order.get("limitPx", 0)),
                    "amount": float(order.get("sz", 0)),
                    "filled": float(order.get("sz", 0)) - float(order.get("origSz", 0)),
                    "remaining": float(order.get("origSz", 0)),
                    "status": "open",
                    "created_at": order.get("timestamp"),
                })

            return result

        except Exception as e:
            logger.error("Failed to get Hyperliquid open orders", error=str(e))
            return []

    async def get_fills(self, limit: int = 100) -> list[dict[str, Any]]:
        """Fetch recent fills/trades from the account."""
        if not self.wallet_address:
            return []

        try:
            fills = await self._post_info({
                "type": "userFills",
                "user": self.wallet_address,
            })

            result = []
            for fill in fills[:limit]:
                result.append({
                    "id": fill.get("tid", ""),
                    "order_id": fill.get("oid"),
                    "symbol": f"{fill.get('coin', '')}/USD:USD",
                    "side": "buy" if fill.get("side") == "B" else "sell",
                    "price": float(fill.get("px", 0)),
                    "amount": float(fill.get("sz", 0)),
                    "cost": float(fill.get("px", 0)) * float(fill.get("sz", 0)),
                    "fee": float(fill.get("fee", 0)),
                    "fee_currency": "USDC",
                    "timestamp": fill.get("time"),
                    "datetime": datetime.utcfromtimestamp(fill.get("time", 0) / 1000).isoformat() if fill.get("time") else None,
                })

            return result

        except Exception as e:
            logger.error("Failed to get Hyperliquid fills", error=str(e))
            return []

    async def get_order_history(self, limit: int = 100) -> list[dict[str, Any]]:
        """Fetch order history (filled/cancelled orders)."""
        if not self.wallet_address:
            return []

        try:
            # Hyperliquid uses userFills for trade history
            fills = await self.get_fills(limit)

            # Convert fills to order history format
            return [
                {
                    "id": fill["order_id"],
                    "symbol": fill["symbol"],
                    "side": fill["side"],
                    "type": "limit",
                    "price": fill["price"],
                    "amount": fill["amount"],
                    "filled": fill["amount"],
                    "cost": fill["cost"],
                    "fee": fill["fee"],
                    "fee_currency": fill["fee_currency"],
                    "status": "closed",
                    "timestamp": fill["timestamp"],
                    "datetime": fill["datetime"],
                }
                for fill in fills
            ]

        except Exception as e:
            logger.error("Failed to get Hyperliquid order history", error=str(e))
            return []

    # ==================== Funding Rate Operations ====================

    async def get_funding_rates(self) -> list[dict[str, Any]]:
        """Fetch current funding rates for all assets."""
        try:
            data = await self._post_info({"type": "metaAndAssetCtxs"})

            meta = data[0] if len(data) > 0 else {}
            asset_ctxs = data[1] if len(data) > 1 else []
            universe = meta.get("universe", [])

            funding_rates = []
            for i, asset in enumerate(universe):
                if i >= len(asset_ctxs):
                    break

                ctx = asset_ctxs[i]
                symbol = asset["name"]

                funding_rates.append({
                    "symbol": f"{symbol}/USD:USD",
                    "funding_rate": float(ctx.get("funding", 0)),
                    "mark_price": float(ctx.get("markPx", 0)),
                    "open_interest": float(ctx.get("openInterest", 0)),
                    "funding_interval_hours": 1,  # Hyperliquid has 1-hour funding
                })

            return funding_rates

        except Exception as e:
            logger.error("Failed to get Hyperliquid funding rates", error=str(e))
            return []

    # ==================== Market Data ====================

    async def get_all_markets(self) -> list[dict[str, Any]]:
        """Fetch all available markets."""
        if not self._meta:
            self._meta = await self._post_info({"type": "meta"})

        markets = []
        for asset in self._meta.get("universe", []):
            markets.append({
                "symbol": f"{asset['name']}/USD:USD",
                "base": asset["name"],
                "quote": "USD",
                "sz_decimals": asset.get("szDecimals", 0),
                "max_leverage": asset.get("maxLeverage", 50),
            })

        return markets

    async def get_orderbook(self, symbol: str, depth: int = 20) -> dict[str, Any]:
        """Fetch orderbook for a symbol."""
        coin = symbol.split("/")[0]

        try:
            data = await self._post_info({
                "type": "l2Book",
                "coin": coin,
            })

            levels = data.get("levels", [[], []])
            bids = levels[0] if len(levels) > 0 else []
            asks = levels[1] if len(levels) > 1 else []

            return {
                "symbol": symbol,
                "bids": [
                    {"price": float(b["px"]), "size": float(b["sz"])}
                    for b in bids[:depth]
                ],
                "asks": [
                    {"price": float(a["px"]), "size": float(a["sz"])}
                    for a in asks[:depth]
                ],
                "timestamp": datetime.utcnow().isoformat(),
            }

        except Exception as e:
            logger.error("Failed to get Hyperliquid orderbook", error=str(e))
            return {"symbol": symbol, "bids": [], "asks": []}

    async def get_ticker(self, symbol: str) -> Optional[dict[str, Any]]:
        """Get current ticker/price for a symbol."""
        coin = symbol.split("/")[0]

        try:
            data = await self._post_info({"type": "metaAndAssetCtxs"})

            meta = data[0] if len(data) > 0 else {}
            asset_ctxs = data[1] if len(data) > 1 else []
            universe = meta.get("universe", [])

            # Find the asset
            for i, asset in enumerate(universe):
                if asset["name"] == coin and i < len(asset_ctxs):
                    ctx = asset_ctxs[i]
                    return {
                        "symbol": f"{coin}/USD:USD",
                        "last": float(ctx.get("markPx", 0)),
                        "bid": float(ctx.get("markPx", 0)),  # Use mark price as approx
                        "ask": float(ctx.get("markPx", 0)),
                        "high": 0,  # Not available from this endpoint
                        "low": 0,
                        "volume": float(ctx.get("dayNtlVlm", 0)),
                        "timestamp": int(datetime.utcnow().timestamp() * 1000),
                    }

            return None

        except Exception as e:
            logger.error("Failed to get Hyperliquid ticker", error=str(e))
            return None

    async def get_min_order_size(self, symbol: str) -> Optional[float]:
        """Get minimum order size for a symbol."""
        coin = symbol.split("/")[0]

        try:
            if not self._meta:
                self._meta = await self._post_info({"type": "meta"})

            universe = self._meta.get("universe", [])

            for asset in universe:
                if asset["name"] == coin:
                    # Hyperliquid minimum is typically 10 USD notional
                    # The actual minimum size depends on szDecimals
                    sz_decimals = asset.get("szDecimals", 0)
                    # Minimum size is 1 unit at the smallest decimal
                    min_size = 10 ** (-sz_decimals) if sz_decimals > 0 else 1
                    return min_size

            return None

        except Exception as e:
            logger.warning("Failed to get Hyperliquid min order size", error=str(e))
            return None

    async def is_symbol_valid(self, symbol: str) -> bool:
        """Check if a symbol is valid and tradeable on Hyperliquid."""
        coin = symbol.split("/")[0]

        try:
            if not self._meta:
                self._meta = await self._post_info({"type": "meta"})

            universe = self._meta.get("universe", [])

            for asset in universe:
                if asset["name"] == coin:
                    # Check if the asset is not marked as inactive/delisted
                    # Hyperliquid doesn't have an explicit status field,
                    # but presence in universe means it's tradeable
                    return True

            return False

        except Exception as e:
            logger.warning("Failed to check Hyperliquid symbol validity", error=str(e))
            return False
