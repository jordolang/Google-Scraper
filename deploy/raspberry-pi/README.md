# Running the licence service on a Raspberry Pi

One script. It installs the service, generates your signing key, and stops
short of starting anything — because the server refuses to run without Stripe
credentials, and it would rather tell you that than crash-loop.

```bash
git clone https://github.com/jordolang/Google-Scraper.git
cd Google-Scraper/deploy/raspberry-pi
sudo ./install-licence-server.sh
```

Or, without cloning first:

```bash
curl -fsSLO https://raw.githubusercontent.com/jordolang/Google-Scraper/main/deploy/raspberry-pi/install-licence-server.sh
chmod +x install-licence-server.sh
sudo ./install-licence-server.sh
```

Needs Raspberry Pi OS (or any Debian-based system) with systemd and Python
3.9+. Bookworm and Bullseye both qualify. 64-bit is preferable but 32-bit
works — see *Architecture* below.

---

## What it puts where

| Path | What |
|---|---|
| `/opt/llsp-licence` | the checkout and its virtualenv, owned by the `llsp` user |
| `/etc/llsp-licence/licence.env` | configuration **including the signing key**, `0640 root:llsp` |
| `/var/lib/llsp-licence/licences.db` | the SQLite store |
| `/var/lib/llsp-licence/backups/` | nightly snapshots, 14 kept |
| `/usr/local/bin/llsp-licence` | the operator CLI |
| `/etc/systemd/system/llsp-licence.service` | the service |

It runs as a dedicated `llsp` system user with no shell, bound to
`127.0.0.1` only, under a systemd sandbox that gives it the network, its own
database directory, and nothing else.

## After the install

1. **Save the public key.** The script prints it twice. It goes in the GitHub
   repository variable `LLSP_LICENSE_PUBKEY` (Settings → Secrets and variables
   → Actions → Variables) so release builds can verify licences.

2. **Back up `/etc/llsp-licence/licence.env` somewhere offline.** It holds the
   signing key. Lose it and no licence can ever be re-signed — every customer
   ages out at the end of their offline grace window. Leak it and anyone can
   mint Agency licences. It is the one irreplaceable thing on the Pi.

3. **Create the nine prices in Stripe.** `sudo llsp-licence pricing` lists the
   SKUs; each one needs a price id pasted into the env file.

4. **Fill in the Stripe secret and webhook secret**, then start it:

   ```bash
   sudo nano /etc/llsp-licence/licence.env
   sudo systemctl enable --now llsp-licence
   curl http://127.0.0.1:8787/healthz
   ```

## Letting Stripe reach the Pi

The service listens on localhost only, which is right: a home router should
not be forwarding ports to a Pi. But Stripe has to deliver webhooks, and the
webhook is the only thing that turns a payment into a licence.

A Cloudflare tunnel is the least painful answer — no port forwarding, no
dynamic-DNS, TLS included:

```bash
sudo ./install-licence-server.sh --with-tunnel     # installs cloudflared
cloudflared tunnel login
cloudflared tunnel create llsp-licence
cloudflared tunnel route dns llsp-licence licence.yourdomain.com
sudo cloudflared service install                    # survives reboots
```

Then set `LLSP_PUBLIC_URL=https://licence.yourdomain.com` in the env file, and
point a Stripe webhook at `https://licence.yourdomain.com/v1/stripe/webhook`
subscribed to:

```
checkout.session.completed     invoice.paid       invoice.payment_failed
customer.subscription.deleted  charge.refunded    charge.dispute.created
```

Copy the webhook's signing secret into `LLSP_STRIPE_WEBHOOK_SECRET` and
restart. Stripe's dashboard will show delivery attempts and their responses,
which is the fastest way to confirm the tunnel works.

## Day to day

```bash
sudo llsp-licence list                              # recent licences
sudo llsp-licence show LLSP-XXXXX-XXXXX-XXXXX-XXXXX # seats, events, history
sudo llsp-licence grant --sku pro-perpetual-once --email someone@example.com
sudo llsp-licence revoke LLSP-… --reason refunded
sudo llsp-licence release LLSP-… --machine <id>     # free a stuck seat

journalctl -u llsp-licence -f                       # live log
sudo systemctl restart llsp-licence                 # after editing the env file
sudo ./install-licence-server.sh --update           # pull new code and restart
```

## Architecture

On 64-bit Pi OS (`aarch64`) `cryptography` installs as a wheel and signs
licences in microseconds.

On 32-bit (`armv7l`) there is no wheel, and building it needs a Rust
toolchain and the better part of an hour. The script does not try: it falls
back to the vendored RFC 8032 implementation in `licensing/_ed25519.py`,
which signs in about 10 ms. That is supported, correct, and tested against
the RFC's own vectors — this service will never notice the difference.

## The database

SQLite on an SD card, which is the one part of this that will eventually fail.
Hence the nightly backup timer, and hence `sqlite3`'s online backup API rather
than a file copy — a snapshot taken mid-write is still consistent.

```bash
sudo systemctl list-timers llsp-licence-backup      # when it next runs
sudo /usr/local/bin/llsp-licence-backup             # run one now
```

Copy those off the Pi periodically. A backup that only exists on the failing
disk is not a backup.

## Uninstalling

```bash
sudo ./install-licence-server.sh --uninstall
```

Removes the service and the checkout. Deliberately keeps
`/var/lib/llsp-licence` and `/etc/llsp-licence` — the database and the signing
key — because deleting either is unrecoverable and should be a decision, not a
side effect.
