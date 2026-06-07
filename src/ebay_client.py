"""Thin wrapper over eBay Sell Inventory API. Handles token refresh."""
import os
import time
import httpx

EBAY_API_BASE = "https://api.ebay.com"
EBAY_AUTH_URL = "https://api.ebay.com/identity/v1/oauth2/token"

_token_cache: dict = {}  # {"access_token": str, "expires_at": float}


def _get_access_token() -> str:
    """Exchange refresh token for a short-lived access token, caching until expiry."""
    if _token_cache.get("access_token") and time.time() < _token_cache.get("expires_at", 0) - 60:
        return _token_cache["access_token"]

    app_id = os.environ["EBAY_APP_ID"]
    cert_id = os.environ["EBAY_CERT_ID"]
    refresh_token = os.environ["EBAY_REFRESH_TOKEN"]

    resp = httpx.post(
        EBAY_AUTH_URL,
        auth=(app_id, cert_id),
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "scope": "https://api.ebay.com/oauth/api_scope/sell.inventory https://api.ebay.com/oauth/api_scope/sell.account",
        },
    )
    resp.raise_for_status()
    body = resp.json()
    _token_cache["access_token"] = body["access_token"]
    _token_cache["expires_at"] = time.time() + body["expires_in"]
    return _token_cache["access_token"]


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {_get_access_token()}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def create_or_replace_inventory_item(sku: str, payload: dict) -> None:
    """PUT /sell/inventory/v1/inventory_item/{sku}"""
    resp = httpx.put(
        f"{EBAY_API_BASE}/sell/inventory/v1/inventory_item/{sku}",
        headers=_headers(),
        json=payload,
    )
    if resp.status_code not in (200, 204):
        raise RuntimeError(f"createOrReplaceInventoryItem failed {resp.status_code}: {resp.text}")


def create_offer(payload: dict) -> str:
    """POST /sell/inventory/v1/offer. Returns offerId."""
    resp = httpx.post(
        f"{EBAY_API_BASE}/sell/inventory/v1/offer",
        headers=_headers(),
        json=payload,
    )
    resp.raise_for_status()
    return resp.json()["offerId"]


def publish_offer(offer_id: str) -> str:
    """POST /sell/inventory/v1/offer/{offerId}/publish. Returns listingId."""
    resp = httpx.post(
        f"{EBAY_API_BASE}/sell/inventory/v1/offer/{offer_id}/publish",
        headers=_headers(),
    )
    resp.raise_for_status()
    return resp.json()["listingId"]


def search_active_listings(query: str, limit: int = 20) -> list[dict]:
    """Browse API: search active listings to use as pricing comps."""
    resp = httpx.get(
        f"{EBAY_API_BASE}/buy/browse/v1/item_summary/search",
        headers={
            "Authorization": f"Bearer {_get_application_token()}",
            "X-EBAY-C-MARKETPLACE-ID": "EBAY_GB",
        },
        params={"q": query, "limit": limit, "filter": "buyingOptions:{FIXED_PRICE}", "currency": "GBP"},
    )
    resp.raise_for_status()
    return resp.json().get("itemSummaries", [])


def _get_application_token() -> str:
    """Client credentials token for Browse API (no user context needed)."""
    app_id = os.environ["EBAY_APP_ID"]
    cert_id = os.environ["EBAY_CERT_ID"]
    resp = httpx.post(
        EBAY_AUTH_URL,
        auth=(app_id, cert_id),
        data={
            "grant_type": "client_credentials",
            "scope": "https://api.ebay.com/oauth/api_scope",
        },
    )
    resp.raise_for_status()
    return resp.json()["access_token"]
