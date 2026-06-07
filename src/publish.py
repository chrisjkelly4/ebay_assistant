"""create inventory item → create offer → publish, with approval gate."""
import json
import os
from pathlib import Path

from src import ebay_client, db

DRAFTS_DIR = Path(__file__).parent.parent / "data" / "drafts"

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


def _build_inventory_payload(draft: dict) -> dict:
    """Map draft JSON to eBay createOrReplaceInventoryItem payload."""
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
        },
    }


def _build_offer_payload(draft: dict, sku: str, price: float) -> dict:
    return {
        "sku": sku,
        "marketplaceId": "EBAY_GB",
        "format": "FIXED_PRICE",
        "listingDescription": draft["description"],
        "pricingSummary": {
            "price": {"value": str(price), "currency": "GBP"}
        },
        "listingPolicies": {
            "fulfillmentPolicyId": os.environ["EBAY_FULFILLMENT_POLICY_ID"],
            "paymentPolicyId": os.environ["EBAY_PAYMENT_POLICY_ID"],
            "returnPolicyId": os.environ["EBAY_RETURN_POLICY_ID"],
        },
        "merchantLocationKey": os.environ["EBAY_MERCHANT_LOCATION_KEY"],
        "categoryId": draft.get("category_id", ""),  # set after category lookup
    }


def publish_item(item_id: str, price: float, auto_publish: bool = False) -> dict:
    """
    Full create → offer → publish flow for one item.
    auto_publish=False (default): stops after creating the offer and returns a preview.
    auto_publish=True: publishes immediately.
    """
    draft = _load_draft(item_id)
    sku = item_id  # use item_id as SKU for dedup

    inventory_payload = _build_inventory_payload(draft)
    ebay_client.create_or_replace_inventory_item(sku, inventory_payload)
    db.upsert_item(item_id, "created")

    offer_payload = _build_offer_payload(draft, sku, price)
    offer_id = ebay_client.create_offer(offer_payload)
    db.upsert_item(item_id, "created", offer_id=offer_id)

    result = {"item_id": item_id, "offer_id": offer_id, "price": price}

    if not auto_publish:
        result["status"] = "pending_approval"
        return result

    listing_id = ebay_client.publish_offer(offer_id)
    db.upsert_item(item_id, "published", listing_id=listing_id)
    result["listing_id"] = listing_id
    result["status"] = "published"
    return result
