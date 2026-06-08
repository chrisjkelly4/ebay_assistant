"""create inventory item → create offer → publish, with approval gate."""
import json
import os
from pathlib import Path

from src import ebay_client, db
from src.images import upload_photos

DRAFTS_DIR = Path(__file__).parent.parent / "data" / "drafts"
ITEMS_DIR = Path(__file__).parent.parent / "items"

CONDITION_MAP = {
    "NEW": "NEW",
    "USED_EXCELLENT": "USED_EXCELLENT",
    "USED_VERY_GOOD": "USED_VERY_GOOD",
    "USED_GOOD": "USED_GOOD",
    "USED_ACCEPTABLE": "USED_ACCEPTABLE",
    "FOR_PARTS_OR_NOT_WORKING": "FOR_PARTS_OR_NOT_WORKING",
}


def _load_draft(item_id: str) -> dict:
    path = DRAFTS_DIR / f"{item_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"No draft for {item_id}. Run 'draft' first.")
    return json.loads(path.read_text())


def _build_inventory_payload(draft: dict, image_urls: list[str]) -> dict:
    condition = CONDITION_MAP.get(draft["condition"], "USED_GOOD")
    aspects = {k: [v] for k, v in draft.get("item_specifics", {}).items() if v}
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
            "fulfillmentPolicyId": os.environ["EBAY_FULFILLMENT_POLICY_ID"],
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

    inventory_payload = _build_inventory_payload(draft, image_urls)
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
