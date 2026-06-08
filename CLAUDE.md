# eBay Assistant

## What this is

A local CLI tool that turns folders of item photos into live eBay listings, fully autonomous. Photos in, listings live. The user retains an approval gate for the first batch, then disables it once the output is trusted.

The user is a recent CS graduate selling items on eBay. The goal is to remove all manual listing work: titles, descriptions, categories, pricing, and the actual publishing. Unlike the parallel Vinted project (which is assisted only due to ToS), eBay has a legitimate API for programmatic listing, so full autonomy is achievable here.

This is an MVP. Ship something that publishes 5 real items end-to-end before adding features.

## Architecture

Pipeline, one item at a time:

1. Read photos from `ebay_items/item_XX/`
2. Vision pass: send photos to Claude (multimodal), get draft JSON with title, description, category, condition, brand, item specifics, confidence flags. **Reuse the existing vision code from the Vinted project — same logic, may need minor tweaks for eBay's item specifics format.**
3. Pricing: fetch sold comps via eBay's Marketplace Insights API (if approved) or fall back to Browse API active listings (median price minus a small discount)
4. Create inventory item via Sell Inventory API
5. Create offer with the computed price
6. Publish offer — gated by an `--approve` flag for first batch, off by default once user trusts it

Local SQLite tracks status per item: `drafted`, `priced`, `created`, `published`, `sold`.

## Folder structure

```
ebay_assistant/
  CLAUDE.md              <- this file
  ebay_items/
    item_01/
      photo_01.jpg
      photo_02.jpg
      ...
    item_02/
      ...
  src/
    vision.py            <- ported from Vinted project
    ebay_client.py       <- Sell API wrapper
    pricing.py           <- sold comps / Browse fallback
    publish.py           <- create + publish flow
    cli.py
  data/
    items.db
    drafts/
  .env                   <- API keys, never commit
```

## Tech choices

- Python 3.11+
- Anthropic SDK for vision (same as Vinted project)
- `requests` or `httpx` for eBay API calls
- SQLite via stdlib
- Click or Typer for the CLI

Minimal dependencies. No web framework, no Docker.

## eBay API specifics

- Use the **Sell Inventory API** for listings (not the legacy Trading API)
- Auth: OAuth 2.0 with user token (NOT application token — listings are user-scoped)
- Endpoints needed: `createOrReplaceInventoryItem`, `createOffer`, `publishOffer`
- Pricing: `Marketplace Insights API` is gated/Limited Release — application required, approval is not guaranteed. Apply day one.
- Fallback pricing: `Browse API` (open, no approval), use median active listing price minus 10-15% as a proxy until Marketplace Insights comes through

## One-time setup (user does this manually, agent guides)

The agent should walk the user through these steps in order, since they involve external accounts:

1. Register at developer.ebay.com, create an app, get production App ID, Cert ID, Dev ID
2. Complete OAuth user consent flow to get a refresh token for the seller account
3. In eBay seller account: opt into Business Policies
4. Create payment policy, return policy, fulfillment (shipping) policy
5. Create an inventory location
6. Apply for Marketplace Insights API access (separate clock, days to weeks)
7. Store all keys and policy IDs in `.env`

## Non-goals (for MVP)

- Vinted integration (separate project)
- Relisting unsold items
- Sold-event webhooks
- Multi-account
- GUI of any kind
- Image editing / background removal
- Auction-style listings (fixed price only for MVP)

## Key constraints

- **Don't publish without the approval gate on first runs.** Default the CLI to dry-run / approval-required. The user explicitly flips a flag to allow auto-publish.
- **Never invent item specifics.** eBay rejects listings with invalid aspects. If brand/size/etc. isn't visible in photos, leave it blank or use eBay's "Unbranded" / "Does Not Apply" values where allowed.
- **Pace API calls.** eBay has rate limits. One item at a time, no parallel publishing.
- **Validate before publishing.** Use eBay's validation responses to catch bad listings before they go live.
- **Idempotency.** If the agent crashes mid-publish, re-running shouldn't create duplicates. Use SKU as the dedup key.

## Build order

The longest pole is OAuth and policies setup because it depends on the user clicking through eBay's developer portal and seller settings. Start there.

1. **OAuth and policies walkthrough.** Agent guides user through developer.ebay.com signup, OAuth consent, business policy creation. Output: a working `.env` with all required IDs and a refresh token that actually fetches a user access token.
2. **API client wrapper** (`ebay_client.py`). Thin layer over the Sell Inventory API endpoints. Handles auth token refresh, error responses.
3. **Pricing module** (`pricing.py`). Browse API lookup with median calculation. Stub for Marketplace Insights to swap in later.
4. **Vision integration** (`vision.py`). Port from Vinted project. Adjust output schema to match eBay's item specifics format.
5. **Publish flow** (`publish.py`). create inventory item → create offer → publish, with approval gate.
6. **CLI glue** (`cli.py`). Commands: `setup`, `draft <item>`, `price <item>`, `publish <item>`, `run <item>` (full pipeline).
7. **Test on 5 real items.** Expect to iterate on category guessing and item specifics.

## How to work with the user

- CS grad, learning Claude Code. Explain non-obvious decisions briefly, no lecturing.
- Direct, concise, no fluff, no emojis. Mirror message length.
- Push back when something's a bad idea, with reasons.
- Flag uncertainty rather than guessing — especially around eBay's API quirks (category IDs, aspect requirements, policy IDs are all error-prone).
- When the user says "do X," do X. Don't expand scope unprompted.
- Before any destructive or production action (publishing, deleting drafts), confirm with the user.

## Current status

Full pipeline built and ready for first live run. All credentials configured.

- All 6 source modules complete: vision, db, pricing, images, publish, auth
- CLI commands: setup, draft, price, publish, run, all, show, list, policies, location
- Cloudflare webhook deployed and verified with eBay
- OAuth refresh token obtained, all .env keys populated
- Business policies created (payment, return, small postage, large postage)
- Inventory location created
- Marketplace Insights API application submitted (pending approval)
- 4 items in items/ folder, ready to list

## Decision log

- **Browse API as pricing fallback**: Active listings only. Using median × 0.82 discount to approximate sold prices. Swap for Marketplace Insights API + 0.95 factor when approval comes through.
- **Approval gate default ON**: First runs are gated with `--approve` flag. User flips to auto-publish after trusting the output (estimated after 10-20 successful items).
- **Upper quartile pricing tried and reverted**: Median × 0.82 chosen over upper quartile (75th pct) after prices came out too high for varied items (mugs, Akai). 65th percentile option left commented in pricing.py.
- **Tiered shipping policies**: Small (clothing/accessories) and large (sewing machine/bulky) — vision auto-assigns based on item bulk.
- **eBay EPS for image hosting**: Trading API UploadSiteHostedPictures used instead of imgur — images stay on eBay's servers permanently.
- **items/ folder name**: CLAUDE.md says ebay_items/ but actual folder is items/. Code uses items/.
