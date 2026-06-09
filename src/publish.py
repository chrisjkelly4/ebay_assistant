"""create inventory item → create offer → publish, with approval gate."""
import json
import os
from pathlib import Path

from src import ebay_client, db
from src.images import upload_photos

DRAFTS_DIR = Path(__file__).parent.parent / "data" / "drafts"
ITEMS_DIR = Path(__file__).parent.parent / "items"


def _load_draft(item_id: str) -> dict:
    path = DRAFTS_DIR / f"{item_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"No draft for {item_id}. Run 'draft' first.")
    return json.loads(path.read_text())


_CONDITION_HIERARCHY = [
    "NEW", "LIKE_NEW", "NEW_OTHER", "NEW_WITH_DEFECTS",
    "MANUFACTURER_REFURBISHED", "CERTIFIED_REFURBISHED",
    "EXCELLENT_REFURBISHED", "VERY_GOOD_REFURBISHED", "GOOD_REFURBISHED",
    "SELLER_REFURBISHED",
    "USED_EXCELLENT", "USED_VERY_GOOD", "USED_GOOD", "USED_ACCEPTABLE",
    "FOR_PARTS_OR_NOT_WORKING",
]


def _resolve_condition(draft_condition: str, valid_conditions: list[str]) -> str:
    """Pick the nearest valid condition to the draft condition in the quality hierarchy."""
    if not valid_conditions:
        return draft_condition
    if draft_condition in valid_conditions:
        return draft_condition
    try:
        pos = _CONDITION_HIERARCHY.index(draft_condition)
    except ValueError:
        pos = _CONDITION_HIERARCHY.index("USED_GOOD")
    # Search outward from pos in both directions, alternating down then up
    for offset in range(1, len(_CONDITION_HIERARCHY)):
        for idx in (pos + offset, pos - offset):
            if 0 <= idx < len(_CONDITION_HIERARCHY):
                if _CONDITION_HIERARCHY[idx] in valid_conditions:
                    return _CONDITION_HIERARCHY[idx]
    return valid_conditions[-1]


def _build_inventory_payload(draft: dict, image_urls: list[str], valid_conditions: list[str] | None = None) -> dict:
    raw = draft.get("condition", "USED_GOOD")
    condition = _resolve_condition(raw, valid_conditions or [])
    aspects = {k: [v[:65]] for k, v in draft.get("item_specifics", {}).items() if v}
    return {
        "availability": {
            "shipToLocationAvailability": {"quantity": 1}
        },
        "condition": condition,
        "product": {
            "title": draft["title"],
            "description": draft["description"],
            "aspects": aspects,
            "imageUrls": image_urls,
        },
    }


def _fulfillment_policy_id(draft: dict) -> str:
    tier = draft.get("shipping_tier", "small")
    if tier == "large":
        return os.environ["EBAY_FULFILLMENT_POLICY_ID_LARGE"]
    return os.environ["EBAY_FULFILLMENT_POLICY_ID_SMALL"]


def _build_offer_payload(draft: dict, sku: str, price: float, category_id: str) -> dict:
    return {
        "sku": sku,
        "marketplaceId": "EBAY_GB",
        "format": "FIXED_PRICE",
        "listingDescription": draft["description"],
        "pricingSummary": {
            "price": {"value": str(round(price, 2)), "currency": "GBP"}
        },
        "listingPolicies": {
            "fulfillmentPolicyId": _fulfillment_policy_id(draft),
            "paymentPolicyId": os.environ["EBAY_PAYMENT_POLICY_ID"],
            "returnPolicyId": os.environ["EBAY_RETURN_POLICY_ID"],
        },
        "merchantLocationKey": os.environ["EBAY_MERCHANT_LOCATION_KEY"],
        "categoryId": category_id,
    }


def publish_item(item_id: str, price: float, auto_publish: bool = False) -> dict:
    """
    Full pipeline: upload images → resolve category → create inventory item
    → create offer → publish (if auto_publish=True).
    """
    draft = _load_draft(item_id)
    sku = item_id

    print(f"Uploading photos for {item_id}...")
    access_token = ebay_client.get_access_token()
    item_dir = ITEMS_DIR / item_id
    image_urls = upload_photos(item_dir, access_token)
    print(f"Uploaded {len(image_urls)} photo(s).")

    print("Resolving category...")
    category_id = ebay_client.get_category_id(draft["title"], draft.get("category_hint", ""))
    if not category_id:
        raise RuntimeError(
            f"Could not resolve category for '{draft['title']}'. "
            "Set 'category_id' manually in the draft JSON and retry."
        )
    print(f"Category ID: {category_id}")

    valid_conditions = ebay_client.get_valid_conditions(category_id)

    inventory_payload = _build_inventory_payload(draft, image_urls, valid_conditions)
    ebay_client.create_or_replace_inventory_item(sku, inventory_payload)
    db.upsert_item(item_id, "created")

    offer_payload = _build_offer_payload(draft, sku, price, category_id)
    offer_id = ebay_client.create_offer(offer_payload)
    db.upsert_item(item_id, "created", offer_id=offer_id)

    result = {"item_id": item_id, "offer_id": offer_id, "price": price, "category_id": category_id}

    if not auto_publish:
        result["status"] = "pending_approval"
        return result

    listing_id = ebay_client.publish_offer(offer_id)

    db.upsert_item(item_id, "published", listing_id=listing_id)
    result["listing_id"] = listing_id
    result["status"] = "published"
    return result
