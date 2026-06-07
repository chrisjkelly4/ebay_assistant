"""Pricing: derive a list price from Browse API active listing comps."""
import statistics
from src import ebay_client

DISCOUNT_FACTOR = 0.95  # undercut median active listings by ~5%


def get_suggested_price(query: str) -> float | None:
    """
    Search active fixed-price listings for `query`, take median price, apply discount.
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

    median = statistics.median(prices)
    return round(median * DISCOUNT_FACTOR, 2)
