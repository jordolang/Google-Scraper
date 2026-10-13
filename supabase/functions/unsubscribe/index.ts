// Unsubscribe endpoint for outreach email.
//
// Every email the desktop app sends links here with the recipient's own token:
//   https://<project>.supabase.co/functions/v1/unsubscribe?t=<token>
//
// POST is RFC 8058 one-click: Gmail, Outlook and Apple Mail send it when the
// recipient presses the inbox's own Unsubscribe button. GET is the footer link.
// Both mark the address unsubscribed, and the app skips it from then on.
//
// Deploy with JWT checks off, since mail clients and browsers carry no key:
//   supabase functions deploy unsubscribe --no-verify-jwt

import { createClient } from "npm:@supabase/supabase-js@2";

function adminKey(): string {
  // Newer projects expose their sb_secret_ keys here; older ones only have the
  // service_role JWT. Either can write the table.
  try {
    const keys = JSON.parse(Deno.env.get("SUPABASE_SECRET_KEYS") ?? "{}");
    if (keys.default) return keys.default;
  } catch {
    // fall through
  }
  return Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
}

const db = createClient(Deno.env.get("SUPABASE_URL") ?? "", adminKey(), {
  auth: { persistSession: false },
});

const FALLBACK = 'Reply to the email with "Unsubscribe" and you will be removed.';

// Supabase serves GET responses from Edge Functions as plain text, so the
// confirmation is written to read well as plain text.
function text(body: string, status = 200): Response {
  return new Response(body + "\n", {
    status,
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": "no-store",
      "X-Robots-Tag": "noindex",
    },
  });
}

Deno.serve(async (req) => {
  if (req.method !== "GET" && req.method !== "POST") {
    return text("Method not allowed.", 405);
  }
  const token = new URL(req.url).searchParams.get("t")?.trim() ?? "";
  if (!/^[A-Za-z0-9_-]{16,64}$/.test(token)) {
    return text(`This unsubscribe link is incomplete. ${FALLBACK}`, 400);
  }

  const { data, error } = await db
    .from("outreach_recipients")
    .select("email, unsubscribed_at")
    .eq("token", token)
    .maybeSingle();
  if (error) {
    console.error("lookup failed", error);
    return text(`Something went wrong on our side. ${FALLBACK}`, 500);
  }
  if (!data) {
    return text(`This unsubscribe link was not recognised. ${FALLBACK}`, 404);
  }

  if (!data.unsubscribed_at) {
    const { error: updateError } = await db
      .from("outreach_recipients")
      .update({
        unsubscribed_at: new Date().toISOString(),
        unsubscribe_method: req.method === "POST" ? "one-click" : "link",
      })
      .eq("token", token);
    if (updateError) {
      console.error("update failed", updateError);
      return text(`Something went wrong on our side. ${FALLBACK}`, 500);
    }
  }

  if (req.method === "POST") return text("Unsubscribed.");
  return text(
    `You're unsubscribed.\n\n${data.email} won't get any more emails from Jordan Lang (jlang.dev).\n\nSorry for the interruption, and thanks for letting me know.`,
  );
});
