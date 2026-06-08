"""Pricing: derive a list price from Browse API active listing comps."""
import statistics
from src import ebay_client

DISCOUNT_FACTOR = 0.95


def get_suggested_price(query: str) -> float | None:
    """
    Search active fixed-price listings for `query`, apply discount, return suggested price.
    Returns None if no comps found.
    """
    items = ebay_client.search_active_listings(query, limit=20)
    prices = []
    for item in items:
        try:
            prices.append(float(item["price"]["value"]))
        except (KeyError, ValueError):
            continue

    if not prices:
        return None

    # Active pricing strategy: median (50th percentile)
    benchmark = statistics.median(prices)

    # Alternative: 65th percentile — above median, below upper quartile.
    # Swap in if median feels too low for well-maintained items.
    # if len(prices) < 7:
    #     benchmark = statistics.median(prices)
    # else:
    #     benchmark = statistics.quantiles(prices, n=20)[12]  # 65th percentile

    # Alternative: upper quartile (75th percentile) — use for premium condition items.
    # if len(prices) < 4:
    #     benchmark = max(prices)
    # else:
    #     benchmark = statistics.quantiles(prices, n=4)[2]  # Q3 = 75th percentile

    return round(benchmark * DISCOUNT_FACTOR, 2)
