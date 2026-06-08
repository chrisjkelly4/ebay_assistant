"""OAuth 2.0 authorization code flow for eBay user tokens."""
import os
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

EBAY_AUTHORIZE_URL = "https://auth.ebay.com/oauth2/authorize"
CALLBACK_PORT = 8080

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


class _CallbackHandler(BaseHTTPRequestHandler):
    code: str | None = None

    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        if "code" in params:
            _CallbackHandler.code = params["code"][0]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"<h2>Authorized! You can close this tab.</h2>")
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"No code received.")

    def log_message(self, *args):
        pass


def run_oauth_flow() -> str:
    """
    Open browser to eBay auth page, capture the callback on localhost,
    exchange auth code for tokens. Returns the refresh token.
    """
    auth_url = _build_auth_url()
    print(f"\nOpening browser for eBay authorization...")
    print(f"If the browser doesn't open, visit:\n{auth_url}\n")
    webbrowser.open(auth_url)

    server = HTTPServer(("localhost", CALLBACK_PORT), _CallbackHandler)
    print(f"Waiting for eBay to redirect to http://localhost:{CALLBACK_PORT} ...")
    while _CallbackHandler.code is None:
        server.handle_request()
    server.server_close()

    tokens = _exchange_code(_CallbackHandler.code)
    return tokens["refresh_token"]
