"""Pricing: derive a list price from Browse API active listing comps."""
import statistics
from src import ebay_client

DISCOUNT_FACTOR = 0.95  # undercut upper quartile by ~5%


def get_suggested_price(query: str) -> float | None:
    """
    Search active fixed-price listings for `query`, take the upper quartile (75th
    percentile) price, apply discount. Upper quartile targets better-condition items.
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

    if len(prices) < 4:
        upper_quartile = max(prices)
    else:
        upper_quartile = statistics.quantiles(prices, n=4)[2]  # Q3 = 75th percentile

    return round(upper_quartile * DISCOUNT_FACTOR, 2)
