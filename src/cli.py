"""CLI: draft | price | publish | run | show | list"""
import json
from pathlib import Path

import click
from dotenv import load_dotenv

load_dotenv()

ITEMS_DIR = Path(__file__).parent.parent / "items"
DRAFTS_DIR = Path(__file__).parent.parent / "data" / "drafts"


@click.group()
def cli():
    pass


@cli.command()
def setup():
    """Run OAuth consent flow to get an eBay refresh token."""
    from src.auth import run_oauth_flow
    refresh_token = run_oauth_flow()
    click.echo("\nSuccess! Add this to your .env:")
    click.echo(f"EBAY_REFRESH_TOKEN={refresh_token}")


@cli.command()
def location():
    """List inventory locations (and create one if none exist)."""
    from src import ebay_client

    locations = ebay_client.list_inventory_locations()

    if locations:
        click.echo("\nExisting inventory locations:")
        click.echo(f"  {'KEY':<30}  NAME")
        for loc in locations:
            click.echo(f"  {loc['merchantLocationKey']:<30}  {loc.get('name', '')}")
        click.echo("\nAdd the key you want to use as EBAY_MERCHANT_LOCATION_KEY in .env")
        return

    click.echo("No inventory locations found.")
    postcode = click.prompt("Enter your postcode (needed by eBay)").strip().upper()
    key = "home"
    ebay_client.create_inventory_location(key, name="Home", postcode=postcode)
    click.echo(f"\nCreated. Add this to .env:")
    click.echo(f"  EBAY_MERCHANT_LOCATION_KEY={key}")


@cli.command()
def policies():
    """List all business policy IDs from your eBay seller account."""
    from src import ebay_client
    data = ebay_client.list_policies()

    id_keys = {
        "fulfillment": "fulfillmentPolicyId",
        "payment": "paymentPolicyId",
        "return": "returnPolicyId",
    }

    for group, id_key in id_keys.items():
        click.echo(f"\n{group.upper()}")
        for p in data.get(group, []):
            click.echo(f"  {p.get('name', ''):<40}  {p.get(id_key, '')}")


@cli.command()
@click.argument("item_id")
def draft(item_id: str):
    """Run vision step for ITEM_ID and save draft JSON."""
    from src.vision import draft_item
    from src import db

    db.init_db()
    item_dir = ITEMS_DIR / item_id
    if not item_dir.exists():
        raise click.ClickException(f"No folder at {item_dir}")

    click.echo(f"Drafting {item_id}...")
    result = draft_item(item_dir)

    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    draft_path = DRAFTS_DIR / f"{item_id}.json"
    draft_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))

    db.upsert_item(item_id, "drafted", draft_path=str(draft_path))
    _print_card(result)


@cli.command()
@click.argument("item_id")
def price(item_id: str):
    """Fetch Browse API comps and write suggested price into draft."""
    from src import pricing, db

    db.init_db()
    draft_path = DRAFTS_DIR / f"{item_id}.json"
    if not draft_path.exists():
        raise click.ClickException(f"No draft for {item_id}. Run 'draft' first.")

    draft = json.loads(draft_path.read_text())
    specifics = draft.get("item_specifics", {})
    brand = specifics.get("Brand", "")
    model = specifics.get("Model", "")
    if brand and model:
        query = f"{brand} {model}"
    elif brand:
        query = f"{brand} {draft['title'].split()[1] if len(draft['title'].split()) > 1 else ''}".strip()
    else:
        query = " ".join(draft["title"].split()[:5])
    click.echo(f"Searching comps for: {query}")

    suggested = pricing.get_suggested_price(query)
    if suggested is None:
        click.echo("No comps found. Set price manually in the draft JSON.")
        return

    draft["price_gbp"] = suggested
    draft_path.write_text(json.dumps(draft, indent=2, ensure_ascii=False))
    db.upsert_item(item_id, "priced")
    click.echo(f"Price set to £{suggested:.2f}")


@cli.command()
@click.argument("item_id")
@click.option("--approve", is_flag=True, default=False, help="Actually publish (default: dry run).")
def publish(item_id: str, approve: bool):
    """Create eBay inventory item and offer. Use --approve to go live."""
    from src import db
    from src.publish import publish_item

    db.init_db()
    draft_path = DRAFTS_DIR / f"{item_id}.json"
    if not draft_path.exists():
        raise click.ClickException(f"No draft for {item_id}. Run 'draft' first.")

    draft = json.loads(draft_path.read_text())
    price_gbp = draft.get("price_gbp") or draft.get("suggested_price_gbp")
    if not price_gbp:
        raise click.ClickException("No price in draft. Run 'price' first or set price_gbp manually.")

    if not approve:
        click.echo(f"Dry run — would publish '{draft['title']}' at £{price_gbp:.2f}")
        click.echo("Re-run with --approve to go live.")
        return

    click.echo(f"Publishing {item_id}...")
    result = publish_item(item_id, price_gbp, auto_publish=True)
    click.echo(f"Listed! listing_id={result['listing_id']}")


@cli.command()
@click.argument("item_id")
@click.option("--approve", is_flag=True, default=False)
def run(item_id: str, approve: bool):
    """Full pipeline: draft → price → publish for ITEM_ID."""
    from click import get_current_context
    ctx = get_current_context()
    ctx.invoke(draft, item_id=item_id)
    ctx.invoke(price, item_id=item_id)
    ctx.invoke(publish, item_id=item_id, approve=approve)


@cli.command()
@click.argument("item_id")
def show(item_id: str):
    """Print saved draft for ITEM_ID."""
    draft_path = DRAFTS_DIR / f"{item_id}.json"
    if not draft_path.exists():
        raise click.ClickException(f"No draft for {item_id}.")
    _print_card(json.loads(draft_path.read_text()))


@cli.command(name="list")
def list_items():
    """List all tracked items and their pipeline status."""
    from src import db

    db.init_db()
    rows = db.list_items()
    if not rows:
        click.echo("No items tracked yet.")
        return
    click.echo(f"{'ITEM':<12}  {'STATUS':<12}  UPDATED")
    for row in rows:
        click.echo(f"{row['item_id']:<12}  {row['status']:<12}  {row['updated_at']}")


def _print_card(d: dict) -> None:
    low = set(d.get("low_confidence_fields", []))

    def field(label: str, key: str, value=None) -> None:
        v = value if value is not None else d.get(key) or "-"
        flag = "  [LOW CONFIDENCE]" if key in low else ""
        click.echo(f"  {label:<16} {v}{flag}")

    click.echo("")
    click.echo(f"  {'ITEM':<16} {d.get('item_id', '')}")
    field("Title", "title")
    field("Category", "category_hint")
    field("Condition", "condition")
    field("Price (GBP)", "price_gbp", d.get("price_gbp") or d.get("suggested_price_gbp") or "-")

    specifics = d.get("item_specifics", {})
    for k, v in specifics.items():
        if v:
            click.echo(f"  {k:<16} {v}")

    click.echo("")
    click.echo(f"  Description:")
    click.echo(f"  {d.get('description', '-')}")
    click.echo("")


if __name__ == "__main__":
    cli()
