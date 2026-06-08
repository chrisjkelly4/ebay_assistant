/**
 * eBay Marketplace Account Deletion Notification handler.
 *
 * eBay requires all production apps to receive these notifications.
 * We don't store any user data, so deletion notifications are a no-op —
 * but we still need to pass eBay's endpoint verification challenge.
 *
 * Environment variables (set in Cloudflare Worker settings):
 *   EBAY_VERIFICATION_TOKEN  — string you choose when registering in eBay developer portal
 *   EBAY_ENDPOINT_URL        — full URL of this worker, e.g. https://ebay-webhook.yourname.workers.dev
 */
export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // eBay sends a GET with ?challenge_code=xxx to verify you own the endpoint
    if (request.method === "GET") {
      const challengeCode = url.searchParams.get("challenge_code");
      if (!challengeCode) {
        return new Response("Missing challenge_code", { status: 400 });
      }

      const data = challengeCode + env.EBAY_VERIFICATION_TOKEN + env.EBAY_ENDPOINT_URL;
      const hashBuffer = await crypto.subtle.digest(
        "SHA-256",
        new TextEncoder().encode(data)
      );
      const hashHex = Array.from(new Uint8Array(hashBuffer))
        .map((b) => b.toString(16).padStart(2, "0"))
        .join("");

      return new Response(JSON.stringify({ challengeResponse: hashHex }), {
        headers: { "Content-Type": "application/json" },
      });
    }

    // eBay sends a POST for actual deletion notifications — acknowledge and discard
    if (request.method === "POST") {
      return new Response(null, { status: 200 });
    }

    return new Response("Method Not Allowed", { status: 405 });
  },
};
