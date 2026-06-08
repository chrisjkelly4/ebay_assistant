"""Upload item photos to eBay's EPS (eBay Picture Service) via Trading API."""
import os
import xml.etree.ElementTree as ET
from io import BytesIO
from pathlib import Path

import httpx
import pillow_heif
from PIL import Image

pillow_heif.register_heif_opener()

MAX_SIDE = 1600  # eBay recommends at least 1600px on longest side
TRADING_API_URL = "https://api.ebay.com/ws/api.dll"
TRADING_API_SANDBOX_URL = "https://api.sandbox.ebay.com/ws/api.dll"

_XML_PAYLOAD = """<?xml version="1.0" encoding="utf-8"?>
<UploadSiteHostedPicturesRequest xmlns="urn:ebay:apis:eBLBaseComponents">
  <PictureName>photo</PictureName>
  <PictureSet>Supersize</PictureSet>
</UploadSiteHostedPicturesRequest>"""


def _trading_url() -> str:
    sandbox = os.environ.get("EBAY_SANDBOX", "").lower() in ("1", "true", "yes")
    return TRADING_API_SANDBOX_URL if sandbox else TRADING_API_URL


def _to_jpeg(path: Path) -> bytes:
    img = Image.open(path).convert("RGB")
    if max(img.size) > MAX_SIDE:
        img.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _upload_one(image_bytes: bytes, access_token: str) -> str:
    """Upload a single JPEG to eBay EPS. Returns the hosted URL."""
    resp = httpx.post(
        _trading_url(),
        headers={
            "X-EBAY-API-SITEID": "3",
            "X-EBAY-API-COMPATIBILITY-LEVEL": "967",
            "X-EBAY-API-CALL-NAME": "UploadSiteHostedPictures",
            "X-EBAY-API-IAF-TOKEN": access_token,
        },
        files=[
            ("XML Payload", (None, _XML_PAYLOAD.encode("utf-8"), "text/xml")),
            ("image", ("photo.jpg", image_bytes, "image/jpeg")),
        ],
    )
    resp.raise_for_status()
    root = ET.fromstring(resp.text)
    ns = {"ns": "urn:ebay:apis:eBLBaseComponents"}

    ack = root.findtext("ns:Ack", namespaces=ns)
    if ack not in ("Success", "Warning"):
        errors = root.findall(".//ns:ShortMessage", ns)
        msg = "; ".join(e.text for e in errors if e.text)
        raise RuntimeError(f"UploadSiteHostedPictures failed: {msg}")

    return root.findtext(".//ns:FullURL", namespaces=ns)


def upload_photos(item_dir: Path, access_token: str) -> list[str]:
    """Convert all photos in item_dir to JPEG and upload to eBay EPS. Returns list of URLs."""
    photos = (
        sorted(item_dir.glob("*.HEIC"))
        + sorted(item_dir.glob("*.heic"))
        + sorted(item_dir.glob("*.jpg"))
        + sorted(item_dir.glob("*.jpeg"))
        + sorted(item_dir.glob("*.png"))
    )
    if not photos:
        raise ValueError(f"No photos found in {item_dir}")

    urls = []
    for photo in photos:
        print(f"  Uploading {photo.name}...")
        jpeg = _to_jpeg(photo)
        url = _upload_one(jpeg, access_token)
        urls.append(url)
    return urls
