# Unsubscribe links and image hosting (Vercel)

Every outreach email gets its own unsubscribe link, in the footer and in the
`List-Unsubscribe` header that powers the Unsubscribe button Gmail, Outlook and
Apple Mail show at the top of a message. One click records the address, and the
app skips it on every later send, including dry runs.

Both this and image hosting (website previews, email images) run on **Vercel**:

| Piece | Where it lives | What it does |
| --- | --- | --- |
| Vercel Blob store | Vercel → Storage | Holds email images, and `optouts/<id>.json` for everyone who unsubscribed |
| Unsubscribe site | `vercel/` in this repo, deployed as its own Vercel project | The page each unsubscribe link opens |
| The app | Settings → Image Hosting and Settings → Deliverability | Uploads images, signs links, skips opted-out addresses |

## How it works

- Each link looks like
  `https://<your-site>.vercel.app/api/unsubscribe?h=<id>&s=<signature>`.
  `h` is a SHA-256 fingerprint of the lower-cased address (the address itself
  never appears in a URL). `s` is an HMAC of `h` with your **unsubscribe
  secret**, so nobody can forge links that unsubscribe other people.
- `vercel/api/unsubscribe.js` checks the signature and stores
  `optouts/<h>.json` in the Blob store. `POST` is the inbox's one-click button
  (RFC 8058); `GET` is the footer link and shows a short confirmation page.
- `opt_outs.py` is the app side. Making a link needs no network. Before a
  send, the app lists `optouts/` in the Blob store and skips every match. If the
  list can't be read, the send stops rather than risk emailing someone who
  opted out.
- Test emails (Send Test to Me) carry a link for **your** address, so clicking
  it while checking the email can't unsubscribe the business.
- Until the site, secret and Blob token are all filled in, emails fall back to
  the **Fallback Unsubscribe Page** setting, or a "reply Unsubscribe" mailto
  link.

## Setting it up

### 1. The Blob store (image hosting)

1. In Vercel, open **Storage → Create → Blob**, choose **Public** access, and
   create it. (Email images have to be public so anyone opening the email can
   see them.)
2. On the store's page, copy the **read-write token** (`vercel_blob_rw_…`,
   under the `.env.local` tab).
3. In the app, open **Settings → Image Hosting**, paste it into **Vercel Blob
   Read-Write Token**, and press **Save**. It's saved in the app's own `.env`
   on your computer, never in the repository.

### 2. The unsubscribe site

1. In the app, open **Settings → Deliverability** and press **Generate & Copy**
   next to **Unsubscribe Secret**. This fills in a new secret and copies it.
2. In Vercel, choose **Add New → Project**, import this GitHub repository, set
   **Root Directory** to `vercel`, and before deploying add the environment
   variables:
   - `UNSUBSCRIBE_SECRET` — paste the secret from step 1.
   - `SENDER_LINE` — optional, e.g. `Jordan Lang (jlang.dev)`, shown on the
     "You're unsubscribed" page.
3. Deploy. Then open the project's **Storage** tab and **Connect** the Blob
   store from part 1. That adds `BLOB_READ_WRITE_TOKEN` for you; redeploy once
   so the function picks it up.
4. Copy the project's address (e.g. `https://lead-unsubscribe.vercel.app`) into
   **Unsubscribe Site (Vercel)** in the app, and press **Save**.

To check it, send yourself a test email (Email Campaigns → **Send Test to Me**)
and click its unsubscribe link: you should see "You're unsubscribed", and a
file appears under `optouts/` in the Blob store's browser.

### Changing the secret

Links in emails already sent are signed with the old secret and stop working
once it changes, so only change it if it has leaked. Update it in both the app
and the Vercel project, then redeploy.

## Seeing who unsubscribed

In Vercel, open **Storage → your Blob store → Browser → optouts/**. Each file
is one address, named by its fingerprint, with the time and whether it came from
the footer link or the inbox button. To bring someone back, delete their file.

## Moving from Supabase

Earlier versions used a Supabase project for both jobs. Nothing is copied over:

- People who unsubscribed through the old Supabase links aren't in the new
  list. Before deleting the Supabase project, open its `outreach_recipients`
  table, filter on `unsubscribed_at` not empty, and keep those addresses out of
  future campaigns.
- Website previews already made point at Supabase Storage and stop showing once
  that project is deleted or paused. New previews go to Vercel Blob.
- Old emails' Supabase unsubscribe links stop working once the project is gone;
  recipients can still reply "Unsubscribe".
