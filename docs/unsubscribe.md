# Unsubscribe links

Every outreach email gets its own unsubscribe link, in the footer and in the
`List-Unsubscribe` header that powers the Unsubscribe button Gmail, Outlook and
Apple Mail show at the top of a message. One click marks the address, and the
app skips it on every later send, including dry runs.

It runs on the same Supabase project as image hosting, so if
**Settings → Image Hosting** is filled in, there is nothing else to set in the
app.

## How it works

- `supabase/migrations/…_outreach_recipients.sql` creates the
  `outreach_recipients` table: one row per address the app has emailed, with a
  random token and, once they use it, `unsubscribed_at`. Row level security is
  on with no policies, so only the secret key can read or write it.
- `supabase/functions/unsubscribe` is the link itself:
  `https://<project>.supabase.co/functions/v1/unsubscribe?t=<token>`.
  `POST` is the inbox's one-click button (RFC 8058); `GET` is the footer link.
  Supabase serves function pages as plain text, so the confirmation is plain
  text.
- `opt_outs.py` is the app side. Composing an email creates the recipient's
  row (or reuses it), and sending checks the list first. If the list can't be
  reached, the send stops rather than risk emailing someone who opted out.
- Without Supabase, emails fall back to the **Unsubscribe Page** setting, or a
  "reply Unsubscribe" mailto link.

## Setting it up on a new Supabase project

The `lead-scraper-images` project already has both pieces. For any other
project:

1. Install the Supabase CLI: `brew install supabase/tap/supabase` on a Mac, or
   `scoop bucket add supabase https://github.com/supabase/scoop-bucket.git` then
   `scoop install supabase` on Windows.
2. In this repository folder, run `supabase login`, then
   `supabase link --project-ref <your project ref>` (the ref is the
   `abcdxyz` part of `https://abcdxyz.supabase.co`).
3. Run `supabase db push` to create the table.
4. Run `supabase functions deploy unsubscribe --no-verify-jwt`.

Or, without the CLI: paste the migration file into the dashboard's
**SQL Editor** and click **Run**, then open **Edge Functions → Deploy a new
function → Via Editor**, name it `unsubscribe`, paste `index.ts`, turn off
**Enforce JWT verification**, and deploy.

## Who has unsubscribed

In the Supabase dashboard, open **Table Editor → outreach_recipients** and sort
by `unsubscribed_at`. `unsubscribe_method` says whether they used the inbox
button (`one-click`) or the footer link (`link`).

People who reply "Unsubscribe" instead still need adding by hand: set
`unsubscribed_at` on their row to the current time.
