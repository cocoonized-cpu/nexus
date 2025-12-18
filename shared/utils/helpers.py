"""
Helper utilities for NEXUS.
"""

import re
from decimal import Decimal, InvalidOperation
from typing import Optional, Tuple
from uuid import uuid4


def generate_id() -> str:
    """Generate a unique ID string."""
    return str(uuid4())


def normalize_symbol(symbol: str, exchange: Optional[str] = None) -> str:
    """
    Normalize a trading symbol to standard format.

    Args:
        symbol: Exchange-specific symbol (e.g., "BTCUSDT", "BTC-USDT", "BTC/USDT")
        exchange: Exchange slug for exchange-specific handling

    Returns:
        Normalized symbol (e.g., "BTCUSDT")
    """
    # Remove common separators
    normalized = symbol.upper().replace("-", "").replace("/", "").replace("_", "")

    # Handle exchange-specific suffixes
    if exchange == "kucoin_futures":
        normalized = normalized.replace("M", "")  # KuCoin uses XBTUSDTM

    # Handle perpetual markers
    for suffix in ["PERP", "-PERP", "_PERP", "SWAP", "-SWAP"]:
        if normalized.endswith(suffix.replace("-", "").replace("_", "")):
            normalized = normalized[: -len(suffix.replace("-", "").replace("_", ""))]

    return normalized


def parse_symbol(symbol: str) -> Tuple[str, str]:
    """
    Parse a symbol into base and quote assets.

    Args:
        symbol: Trading symbol (e.g., "BTCUSDT")

    Returns:
        Tuple of (base_asset, quote_asset)
    """
    # Common quote assets
    quote_assets = ["USDT", "USDC", "USD", "BUSD", "TUSD", "DAI", "BTC", "ETH"]

    normalized = normalize_symbol(symbol)

    for quote in quote_assets:
        if normalized.endswith(quote):
            base = normalized[: -len(quote)]
            if base:
                return base, quote

    # Fallback: assume last 4 chars are quote
    if len(normalized) > 4:
        return normalized[:-4], normalized[-4:]

    return normalized, "USD"


def decimal_to_str(value: Decimal, precision: int = 8) -> str:
    """
    Convert Decimal to string with specified precision.

    Args:
        value: Decimal value
        precision: Number of decimal places

    Returns:
        Formatted string
    """
    if value is None:
        return "0"
    return f"{value:.{precision}f}".rstrip("0").rstrip(".")


def str_to_decimal(
    value: str | float | int | None, default: Decimal = Decimal("0")
) -> Decimal:
    """
    Convert string/float/int to Decimal safely.

    Args:
        value: Value to convert
        default: Default if conversion fails

    Returns:
        Decimal value
    """
    if value is None:
        return default

    try:
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return default


def calculate_slippage(
    size_usd: Decimal,
    order_book: list[Tuple[Decimal, Decimal]],
    side: str = "buy",
) -> Decimal:
    """
    Calculate expected slippage for a given order size.

    Args:
        size_usd: Order size in USD
        order_book: List of (price, quantity) tuples
        side: "buy" or "sell"

    Returns:
        Expected slippage as percentage
    """
    if not order_book:
        return Decimal("100")  # No liquidity

    remaining = size_usd
    weighted_price = Decimal("0")
    total_filled = Decimal("0")

    for price, qty in order_book:
        level_value = price * qty
        if remaining <= level_value:
            weighted_price += price * remaining
            total_filled += remaining
            break
        weighted_price += price * level_value
        total_filled += level_value
        remaining -= level_value

    if total_filled == 0:
        return Decimal("100")

    avg_price = weighted_price / total_filled
    best_price = order_book[0][0]

    if side == "buy":
        slippage = (avg_price - best_price) / best_price * 100
    else:
        slippage = (best_price - avg_price) / best_price * 100

    return abs(slippage)


def format_funding_rate(rate: Decimal, annualize: bool = False) -> str:
    """
    Format a funding rate for display.

    Args:
        rate: Funding rate as percentage
        annualize: Whether to show annualized rate

    Returns:
        Formatted string
    """
    if annualize:
        # Assume 8-hour funding
        annualized = rate * 3 * 365
        return f"{annualized:.2f}% APR"
    return f"{rate:.4f}%"


def format_currency(value: Decimal, currency: str = "USD") -> str:
    """
    Format a currency value for display.

    Args:
        value: Value to format
        currency: Currency code

    Returns:
        Formatted string
    """
    if currency == "USD":
        return f"${value:,.2f}"
    return f"{value:,.2f} {currency}"


def format_percentage(value: Decimal, precision: int = 2) -> str:
    """
    Format a percentage value for display.

    Args:
        value: Percentage value
        precision: Decimal places

    Returns:
        Formatted string
    """
    return f"{value:.{precision}f}%"


def truncate_string(s: str, max_length: int = 50, suffix: str = "...") -> str:
    """
    Truncate a string to maximum length.

    Args:
        s: String to truncate
        max_length: Maximum length
        suffix: Suffix to add if truncated

    Returns:
        Truncated string
    """
    if len(s) <= max_length:
        return s
    return s[: max_length - len(suffix)] + suffix


def is_valid_exchange_slug(slug: str) -> bool:
    """
    Validate an exchange slug format.

    Args:
        slug: Exchange slug to validate

    Returns:
        True if valid
    """
    pattern = r"^[a-z][a-z0-9_]*_futures$"
    return bool(re.match(pattern, slug))


def get_funding_period_hours(exchange: str) -> int:
    """
    Get funding period in hours for an exchange.

    Args:
        exchange: Exchange slug

    Returns:
        Hours between funding settlements
    """
    # DEX typically have 1-hour funding
    dex_exchanges = ["hyperliquid_futures", "dydx_futures", "gmx_futures"]
    if exchange in dex_exchanges:
        return 1
    return 8  # Default 8-hour for CEX
