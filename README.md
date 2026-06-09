# eBay Assistant

A local CLI tool that turns folders of item photos into live eBay listings. Photos in, listings live.

Built with Python and Claude's vision API. Targets eBay.co.uk (GBP, EBAY_GB marketplace).

---

## How it works

For each item folder, the pipeline runs:

1. **Vision** — sends photos to Claude, gets title, description, category, condition, item specifics, and suggested price
2. **Pricing** — searches eBay active listings via Browse API, takes the median and applies a discount to approximate sold prices
3. **Images** — uploads photos to eBay's image hosting (EPS) via the Trading API
4. **Publish** — creates an inventory item and offer via the Sell Inventory API, then publishes

An `--approve` flag gates the publish step. Omit it for a dry run.

---

## Setup

### Requirements

- Python 3.11+
- An [Anthropic API key](https://console.anthropic.com)
- An [eBay developer account](https://developer.ebay.com) with a production app

### Install dependencies

```bash
pip install anthropic httpx python-dotenv click pillow pillow-heif
```

### Configure credentials

Create a `.env` file in the project root with the following keys:

```
ANTHROPIC_API_KEY=
EBAY_APP_ID=
EBAY_CERT_ID=
EBAY_DEV_ID=
EBAY_RUNAME=
EBAY_REFRESH_TOKEN=
EBAY_PAYMENT_POLICY_ID=
EBAY_RETURN_POLICY_ID=
EBAY_FULFILLMENT_POLICY_ID_SMALL=
EBAY_FULFILLMENT_POLICY_ID_LARGE=
EBAY_MERCHANT_LOCATION_KEY=
```

### One-time eBay setup

Run the guided setup command — it will walk you through OAuth and verify your credentials:

```bash
python -m src.cli setup
```

This covers:
- OAuth user consent flow to get a refresh token
- Business policies (payment, return, fulfillment)
- Inventory location

---

## Usage

### Add items

Create a folder per item inside `items/`, with photos inside:

```
items/
  item_01/
    photo_1.jpg
    photo_2.HEIC
  item_02/
    ...
```

Supports `.jpg`, `.jpeg`, `.png`, `.heic`.

### Run the full pipeline

**Dry run (preview only, no publishing):**
```bash
python -m src.cli all
```

**Publish live:**
```bash
python -m src.cli all --approve
```

### Single item commands

```bash
python -m src.cli draft item_01             # Vision pass only
python -m src.cli price item_01             # Pricing only
python -m src.cli run item_01               # Full pipeline, dry run
python -m src.cli run item_01 --approve     # Full pipeline, publish live
```

### Utilities

```bash
python -m src.cli show item_01    # Show draft details
python -m src.cli list            # Show all items and their status
python -m src.cli policies        # List your eBay business policies and IDs
python -m src.cli location        # Create an inventory location
```

---

## Sandbox mode

To test against eBay's sandbox environment without creating real listings:

```bash
EBAY_SANDBOX=1 python -m src.cli run item_01 --approve
```

Note: sandbox has no real listing data, so pricing comps will return nothing.

---

## Project structure

```
src/
  vision.py        Claude multimodal vision pass
  pricing.py       Browse API comp search
  images.py        eBay EPS image upload
  publish.py       Full publish pipeline
  ebay_client.py   eBay API wrapper
  db.py            SQLite status tracking
  auth.py          OAuth flow
  cli.py           CLI entry point
data/
  items.db         SQLite database
  drafts/          Draft JSON files per item
items/             Your item photo folders (gitignored)
webhook/
  worker.js        Cloudflare Worker for eBay account deletion compliance
```

---

## Pricing

Active listings are used as comps (eBay's Marketplace Insights API for sold data requires a separate application). The current formula is:

```
price = median(active listing prices) × 0.82
```

The 0.82 discount approximates the gap between active and sold prices. When Marketplace Insights access is approved, swap the Browse API call for the Insights API and change the factor to 0.95.
