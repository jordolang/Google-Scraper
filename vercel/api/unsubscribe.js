// Unsubscribe endpoint for outreach email.
//
// Every email the desktop app sends links here with the recipient's own id:
//   https://<this-project>.vercel.app/api/unsubscribe?h=<id>&s=<signature>
//
// `h` is the SHA-256 of the recipient's lower-cased address (never the
// address itself) and `s` is an HMAC of it with UNSUBSCRIBE_SECRET, so only
// links the app made are accepted. A valid click stores optouts/<h>.json in
// the Blob store; the app reads that folder before every campaign and skips
// those people.
//
// POST is RFC 8058 one-click: Gmail, Outlook and Apple Mail send it when the
// recipient presses the inbox's own Unsubscribe button. GET is the footer link.
// Both record the unsubscribe.
//
// Environment (Vercel → Project → Settings → Environment Variables):
//   BLOB_READ_WRITE_TOKEN  added for you when the Blob store is connected
//   UNSUBSCRIBE_SECRET     the same value as in the app's Settings
//   SENDER_LINE            optional, e.g. "Jordan Lang (jlang.dev)"

import { createHmac, timingSafeEqual } from "node:crypto";
import { put } from "@vercel/blob";

const FALLBACK = 'Reply to the email with "Unsubscribe" and you will be removed.';
const SIGNATURE_LENGTH = 32;

export function sign(secret, digest) {
  return createHmac("sha256", secret).update(digest).digest("hex").slice(0, SIGNATURE_LENGTH);
}

export function validLink(secret, h, s) {
  if (!secret || !/^[0-9a-f]{64}$/.test(h) || !/^[0-9a-f]+$/.test(s)) return false;
  const expected = Buffer.from(sign(secret, h));
  const given = Buffer.from(s);
  return expected.length === given.length && timingSafeEqual(expected, given);
}

function escapeHtml(text) {
  return text.replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c]);
}

function page(res, status, heading, body) {
  res.statusCode = status;
  res.setHeader("Content-Type", "text/html; charset=utf-8");
  res.end(`<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex"><title>${escapeHtml(heading)}</title>
<style>body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
max-width:32rem;margin:15vh auto;padding:0 1rem;color:#1f2937;line-height:1.5}
h1{font-size:1.4rem}</style></head><body><h1>${escapeHtml(heading)}</h1>
<p>${escapeHtml(body)}</p></body></html>`);
}

export default async function handler(req, res, record = put) {
  if (req.method !== "GET" && req.method !== "POST") {
    res.setHeader("Allow", "GET, POST");
    return page(res, 405, "Not allowed", "This address only accepts unsubscribe links.");
  }
  const url = new URL(req.url, "https://localhost");
  const h = (url.searchParams.get("h") || "").trim().toLowerCase();
  const s = (url.searchParams.get("s") || "").trim().toLowerCase();
  if (!validLink(process.env.UNSUBSCRIBE_SECRET || "", h, s)) {
    return page(res, 400, "Link not recognised",
      `This unsubscribe link is incomplete. ${FALLBACK}`);
  }

  try {
    await record(
      `optouts/${h}.json`,
      JSON.stringify({
        unsubscribed_at: new Date().toISOString(),
        method: req.method === "POST" ? "one-click" : "link",
      }),
      {
        access: "public",
        contentType: "application/json",
        addRandomSuffix: false,
        allowOverwrite: true,
      },
    );
  } catch (error) {
    console.error("could not record unsubscribe", error);
    return page(res, 500, "Something went wrong",
      `Something went wrong on our side. ${FALLBACK}`);
  }

  if (req.method === "POST") {
    res.statusCode = 200;
    res.setHeader("Content-Type", "text/plain; charset=utf-8");
    return res.end("Unsubscribed.\n");
  }
  const sender = process.env.SENDER_LINE || "us";
  return page(res, 200, "You're unsubscribed",
    `You won't get any more emails from ${sender}. ` +
    "Sorry for the interruption, and thanks for letting me know.");
}
