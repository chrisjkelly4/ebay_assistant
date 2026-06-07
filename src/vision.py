"""Vision step: send item photos to Claude, get back a draft listing JSON."""
import base64
import json
import os
from pathlib import Path

import anthropic
from PIL import Image
import pillow_heif

pillow_heif.register_heif_opener()

SYSTEM_PROMPT = """You are helping list second-hand items on eBay.

Given photos of an item, return a JSON object with these fields:
- title: short, searchable listing title (max 80 chars, no ALL CAPS, no *, $, !)
- description: plain text, 2-4 sentences. State what the item is, its condition, and any visible flaws. No marketing language.
- category_hint: the most specific eBay category path as a string, e.g. "Clothing > Men > Shirts" or "Electronics > Cameras > Digital Cameras"
- condition: one of "NEW", "USED_EXCELLENT", "USED_VERY_GOOD", "USED_GOOD", "USED_ACCEPTABLE", "FOR_PARTS_OR_NOT_WORKING"
- item_specifics: a flat dict of visible attributes. Always include Brand, Color. Add Size, Material, Style, Type, and any other clearly visible attributes. Use "Unbranded" for Brand only if it is definitely unbranded. Use empty string for attributes not visible.
- suggested_price_gbp: a competitive second-hand price in GBP as a number
- low_confidence_fields: list of field names you are uncertain about

Rules:
- NEVER invent brand, size, or material. If a label isn't visible, use empty string and add to low_confidence_fields.
- Title should include brand + item type + key attributes (size, color) if visible.
- For condition: when in doubt between two adjacent grades, choose the better one. Items on this platform are well-maintained. Only drop to USED_GOOD or below if there are clearly visible flaws.
- Return only valid JSON, no extra text."""

MAX_SIDE = 1568


def load_image_as_base64(path: Path) -> tuple[str, str]:
    """Convert any image (including HEIC) to a resized JPEG base64 for the API."""
    from io import BytesIO
    img = Image.open(path).convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=85)
    data = base64.standard_b64encode(buf.getvalue()).decode()
    return data, "image/jpeg"


def draft_item(item_dir: Path) -> dict:
    """Run the vision step for one item folder. Returns the draft dict."""
    photos = (
        sorted(item_dir.glob("*.HEIC"))
        + sorted(item_dir.glob("*.heic"))
        + sorted(item_dir.glob("*.jpg"))
        + sorted(item_dir.glob("*.jpeg"))
        + sorted(item_dir.glob("*.png"))
    )
    if not photos:
        raise ValueError(f"No photos found in {item_dir}")

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    content = []
    for photo in photos:
        data, media_type = load_image_as_base64(photo)
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": data},
        })
    content.append({"type": "text", "text": "Analyse these photos and return the listing JSON."})

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
    )

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    draft = json.loads(raw)
    draft["item_id"] = item_dir.name
    return draft
