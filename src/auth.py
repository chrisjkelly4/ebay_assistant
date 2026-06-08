"""OAuth 2.0 authorization code flow for eBay user tokens."""
import os
import webbrowser
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

EBAY_AUTHORIZE_URL = "https://auth.ebay.com/oauth2/authorize"

SCOPES = " ".join([
    "https://api.ebay.com/oauth/api_scope/sell.inventory",
    "https://api.ebay.com/oauth/api_scope/sell.account",
])


def _build_auth_url() -> str:
    params = {
        "client_id": os.environ["EBAY_APP_ID"],
        "redirect_uri": os.environ["EBAY_RUNAME"],
        "response_type": "code",
        "scope": SCOPES,
    }
    return f"{EBAY_AUTHORIZE_URL}?{urlencode(params)}"


def _exchange_code(code: str) -> dict:
    from src.ebay_client import EBAY_AUTH_URL
    resp = httpx.post(
        EBAY_AUTH_URL,
        auth=(os.environ["EBAY_APP_ID"], os.environ["EBAY_CERT_ID"]),
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": os.environ["EBAY_RUNAME"],
        },
    )
    resp.raise_for_status()
    return resp.json()


def run_oauth_flow() -> str:
    """
    Open browser to eBay auth page. After authorizing, eBay redirects to a page
    whose URL contains ?code=xxx — the user copies that URL and pastes it back.
    Returns the refresh token.
    """
    auth_url = _build_auth_url()
    print("\nOpening browser for eBay authorization...")
    print("If the browser doesn't open, visit this URL manually:\n")
    print(f"  {auth_url}\n")
    webbrowser.open(auth_url)

    print("After you click 'Agree' in the browser, eBay will redirect you to a page.")
    print("Copy the full URL from your browser's address bar and paste it here.\n")
    redirected_url = input("Paste the redirect URL: ").strip()

    # Extract code from wherever it appears — full URL or bare code
    if "code=" in redirected_url:
        params = parse_qs(urlparse(redirected_url).query)
        code = params["code"][0]
    else:
        code = redirected_url  # user pasted just the code

    tokens = _exchange_code(code)
    return tokens["refresh_token"]
