#!/usr/bin/env bash
#
# Install the Local Lead Scraper Pro licence service on a Raspberry Pi.
#
#     sudo ./install-licence-server.sh
#
# Sets up a dedicated system user, a virtualenv, a signing keypair, a systemd
# service, and a nightly database backup. It does NOT start the service: the
# server refuses to run without Stripe credentials, so the last thing this
# prints is the short list of values you still have to paste in.
#
# Safe to re-run. The one thing it will never do twice is generate a signing
# key — every licence already issued verifies against that key's public half,
# so a second one would silently invalidate all of them.
#
# Options:
#   --repo URL      where to clone from (default: the public GitHub repo)
#   --ref REF       branch or tag to check out (default: main)
#   --port PORT     port the service listens on, localhost only (default: 8787)
#   --with-tunnel   also install cloudflared, for exposing the Pi to Stripe
#   --update        pull the latest code and restart, skipping the rest
#   --uninstall     remove the service (keeps the database and the key)

set -euo pipefail

REPO_URL="https://github.com/jordolang/Google-Scraper.git"
REPO_REF="main"
PORT="8787"
WITH_TUNNEL="no"
MODE="install"

APP_DIR="/opt/llsp-licence"
VENV_DIR="${APP_DIR}/venv"
DATA_DIR="/var/lib/llsp-licence"
BACKUP_DIR="${DATA_DIR}/backups"
CONF_DIR="/etc/llsp-licence"
ENV_FILE="${CONF_DIR}/licence.env"
SERVICE_USER="llsp"
SERVICE_NAME="llsp-licence"
DB_PATH="${DATA_DIR}/licences.db"
BACKUP_KEEP_DAYS=14

# -- output helpers -------------------------------------------------------
if [ -t 1 ]; then
    BOLD=$(printf '\033[1m'); DIM=$(printf '\033[2m')
    RED=$(printf '\033[31m'); GREEN=$(printf '\033[32m')
    YELLOW=$(printf '\033[33m'); OFF=$(printf '\033[0m')
else
    BOLD=""; DIM=""; RED=""; GREEN=""; YELLOW=""; OFF=""
fi

say()  { printf '%s==>%s %s\n' "${GREEN}${BOLD}" "${OFF}" "$*"; }
note() { printf '    %s%s%s\n' "${DIM}" "$*" "${OFF}"; }
warn() { printf '%s !! %s %s\n' "${YELLOW}${BOLD}" "${OFF}" "$*" >&2; }
# _died marks a failure this script diagnosed itself, so the exit handler can
# stay quiet rather than appending "FAILED at line ?" to an explanation that is
# already clear.
_died=""
die()  { _died=1; printf '%sERROR%s %s\n' "${RED}${BOLD}" "${OFF}" "$*" >&2; exit 1; }

# LINENO has to be captured by an ERR trap: read inside the EXIT trap it gives
# the trap's own line, which points at this file's plumbing rather than at
# whatever actually broke.
_failed_line="?"
_on_err() { _failed_line="$1"; }
_on_exit() {
    exit_status=$?
    [ "${exit_status}" -eq 0 ] && return 0
    [ -n "${_died}" ] && return 0
    printf '\n%sFAILED%s at line %s (exit %s).\n' \
        "${RED}${BOLD}" "${OFF}" "${_failed_line}" "${exit_status}" >&2
    printf 'Nothing was started. Re-run once the cause is fixed; this script is\n' >&2
    printf 'safe to run again and will not regenerate the signing key.\n' >&2
    return 0
}
trap '_on_err "${LINENO}"' ERR
trap _on_exit EXIT

# -- arguments ------------------------------------------------------------
while [ $# -gt 0 ]; do
    case "$1" in
        --repo)        REPO_URL="${2:?--repo needs a URL}"; shift 2 ;;
        --ref)         REPO_REF="${2:?--ref needs a branch or tag}"; shift 2 ;;
        --port)        PORT="${2:?--port needs a number}"; shift 2 ;;
        --with-tunnel) WITH_TUNNEL="yes"; shift ;;
        --update)      MODE="update"; shift ;;
        --uninstall)   MODE="uninstall"; shift ;;
        -h|--help)     sed -n '2,26p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *)             die "unknown option: $1 (try --help)" ;;
    esac
done

case "${PORT}" in
    ''|*[!0-9]*) die "--port must be a number, got '${PORT}'" ;;
esac

[ "$(id -u)" -eq 0 ] || die "run this with sudo: sudo $0 $*"

# -- uninstall ------------------------------------------------------------
if [ "${MODE}" = "uninstall" ]; then
    say "Removing the ${SERVICE_NAME} service"
    systemctl disable --now "${SERVICE_NAME}.service" 2>/dev/null || true
    systemctl disable --now "${SERVICE_NAME}-backup.timer" 2>/dev/null || true
    rm -f "/etc/systemd/system/${SERVICE_NAME}.service" \
          "/etc/systemd/system/${SERVICE_NAME}-backup.service" \
          "/etc/systemd/system/${SERVICE_NAME}-backup.timer"
    systemctl daemon-reload
    rm -rf "${APP_DIR}"
    say "Done."
    note "Kept ${DATA_DIR} (database + backups) and ${CONF_DIR} (signing key)."
    note "Delete those by hand only if you are certain — the signing key cannot"
    note "be recovered, and without it no previously issued licence can be re-signed."
    trap - EXIT ERR
    exit 0
fi

# -- sanity ---------------------------------------------------------------
command -v apt-get >/dev/null 2>&1 \
    || die "this expects Raspberry Pi OS or another Debian-based system (no apt-get found)"
# Checked before anything is written: the service is a systemd unit, and
# finding that out at the end would leave a half-finished install behind.
systemctl is-system-running >/dev/null 2>&1 || [ -d /run/systemd/system ] \
    || die "systemd is not running here; this installs a systemd service"

ARCH="$(uname -m)"
say "Installing the licence service"
note "architecture: ${ARCH}"
note "target:       ${APP_DIR}"
note "listening on: 127.0.0.1:${PORT}"

# -- update mode ----------------------------------------------------------
if [ "${MODE}" = "update" ]; then
    [ -d "${APP_DIR}/.git" ] || die "no checkout at ${APP_DIR}; run without --update first"
    say "Updating the code"
    sudo -u "${SERVICE_USER}" git -C "${APP_DIR}" fetch --quiet origin "${REPO_REF}"
    sudo -u "${SERVICE_USER}" git -C "${APP_DIR}" checkout --quiet -B "${REPO_REF}" "origin/${REPO_REF}"
    note "now at $(sudo -u "${SERVICE_USER}" git -C "${APP_DIR}" rev-parse --short HEAD)"
    say "Reinstalling dependencies"
    "${VENV_DIR}/bin/pip" install --quiet --upgrade pip
    "${VENV_DIR}/bin/pip" install --quiet gunicorn || die "could not install gunicorn"
    "${VENV_DIR}/bin/pip" install --quiet cryptography 2>/dev/null \
        || note "cryptography unavailable for ${ARCH}; the vendored signer will be used"
    systemctl restart "${SERVICE_NAME}.service"
    say "Restarted. Recent log:"
    sleep 2
    journalctl -u "${SERVICE_NAME}.service" -n 15 --no-pager || true
    trap - EXIT ERR
    exit 0
fi

# -- packages -------------------------------------------------------------
say "Installing system packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git python3 python3-venv python3-pip curl ca-certificates >/dev/null
note "git, python3, python3-venv, curl"

PY_VERSION="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
PY_OK="$(python3 -c 'import sys; print(1 if sys.version_info >= (3, 9) else 0)')"
[ "${PY_OK}" = "1" ] || die "Python 3.9 or newer is required; this system has ${PY_VERSION}"
note "python ${PY_VERSION}"

# -- service user ---------------------------------------------------------
if id -u "${SERVICE_USER}" >/dev/null 2>&1; then
    note "user ${SERVICE_USER} already exists"
else
    say "Creating the ${SERVICE_USER} service user"
    useradd --system --home-dir "${APP_DIR}" --shell /usr/sbin/nologin "${SERVICE_USER}"
fi

install -d -o "${SERVICE_USER}" -g "${SERVICE_USER}" -m 0750 "${DATA_DIR}" "${BACKUP_DIR}"
install -d -o root -g "${SERVICE_USER}" -m 0750 "${CONF_DIR}"

# -- code -----------------------------------------------------------------
if [ -d "${APP_DIR}/.git" ]; then
    say "Updating the existing checkout"
    sudo -u "${SERVICE_USER}" git -C "${APP_DIR}" fetch --quiet origin "${REPO_REF}"
    sudo -u "${SERVICE_USER}" git -C "${APP_DIR}" checkout --quiet -B "${REPO_REF}" "origin/${REPO_REF}"
else
    say "Cloning ${REPO_URL} (${REPO_REF})"
    install -d -o "${SERVICE_USER}" -g "${SERVICE_USER}" -m 0755 "${APP_DIR}"
    sudo -u "${SERVICE_USER}" git clone --quiet --branch "${REPO_REF}" \
        --single-branch "${REPO_URL}" "${APP_DIR}" \
        || die "clone failed — check the URL and that the Pi has network access"
fi
# As the owner, not as root: the checkout belongs to ${SERVICE_USER}, and git
# refuses to read a repository owned by somebody else ("dubious ownership").
note "at $(sudo -u "${SERVICE_USER}" git -C "${APP_DIR}" rev-parse --short HEAD)"

# -- virtualenv -----------------------------------------------------------
say "Building the virtualenv"
# Debian marks the system Python as externally managed (PEP 668), so a venv is
# not optional here — pip would refuse to install into the system site-packages.
if [ ! -x "${VENV_DIR}/bin/python" ]; then
    sudo -u "${SERVICE_USER}" python3 -m venv "${VENV_DIR}"
fi
"${VENV_DIR}/bin/pip" install --quiet --upgrade pip
"${VENV_DIR}/bin/pip" install --quiet gunicorn || die "could not install gunicorn"
note "gunicorn installed"

# cryptography is the fast signer. On 64-bit Pi OS it arrives as a wheel; on
# 32-bit armv7l there is none, and building it needs a Rust toolchain. That is
# not worth an hour of compiling: licensing/crypto.py falls back to the
# vendored RFC 8032 implementation, which signs in about 10ms — far more than
# this service will ever need.
if "${VENV_DIR}/bin/pip" install --quiet cryptography 2>/dev/null; then
    note "cryptography installed (fast signer)"
else
    warn "no cryptography wheel for ${ARCH}; using the vendored pure-Python signer"
    note "that is supported and correct, just slower. Nothing else changes."
fi

chown -R "${SERVICE_USER}:${SERVICE_USER}" "${VENV_DIR}"

# -- signing key ----------------------------------------------------------
PUBLIC_KEY=""
if [ -f "${ENV_FILE}" ] && grep -q '^LLSP_SIGNING_KEY=.\+' "${ENV_FILE}"; then
    say "Keeping the existing signing key"
    note "a second key would invalidate every licence already issued"
    SEED="$(grep '^LLSP_SIGNING_KEY=' "${ENV_FILE}" | head -1 | cut -d= -f2-)"
    PUBLIC_KEY="$(cd "${APP_DIR}" && LLSP_SEED="${SEED}" "${VENV_DIR}/bin/python" - <<'PY'
import os
from licensing import crypto
print(crypto.b64encode(crypto.public_key(crypto.b64decode(os.environ["LLSP_SEED"]))))
PY
)" || die "the stored signing key could not be read — do not overwrite it, restore a backup"
else
    say "Generating the signing keypair"
    KEYGEN_OUT="$(cd "${APP_DIR}" && "${VENV_DIR}/bin/python" -m payments.cli keygen)" \
        || die "keygen failed"
    SEED="$(printf '%s\n' "${KEYGEN_OUT}" | grep -o 'LLSP_SIGNING_KEY=[A-Za-z0-9_-]\+' | head -1 | cut -d= -f2)"
    PUBLIC_KEY="$(printf '%s\n' "${KEYGEN_OUT}" | grep -o 'LLSP_LICENSE_PUBKEY=[A-Za-z0-9_-]\+' | head -1 | cut -d= -f2)"
    [ -n "${SEED}" ] && [ -n "${PUBLIC_KEY}" ] || die "could not read the generated keypair"
    note "done — the private half never leaves ${ENV_FILE}"
fi

# Printed here as well as in the summary. It is the single thing this script
# produces that cannot be regenerated, and a failure further down must not be
# what stands between you and it.
printf '\n    %spublic key:%s %s\n\n' "${BOLD}" "${OFF}" "${PUBLIC_KEY}"

# -- configuration --------------------------------------------------------
if [ ! -f "${ENV_FILE}" ]; then
    say "Writing ${ENV_FILE}"
    SKUS="$(cd "${APP_DIR}" && "${VENV_DIR}/bin/python" -m payments.cli pricing \
            | awk '/^[a-z]+-(subscription|perpetual)-/ {print $1}')"
    {
        printf '# Local Lead Scraper Pro — licence service configuration.\n'
        printf '# Read by systemd; plain KEY=value, no quotes, no export.\n\n'
        printf '# The signing key. Back this up somewhere offline and NEVER change it:\n'
        printf '# every licence ever issued verifies against its public half.\n'
        printf 'LLSP_SIGNING_KEY=%s\n\n' "${SEED}"
        printf '# --- Stripe -----------------------------------------------------\n'
        printf '# From the Stripe dashboard. The service refuses to start without\n'
        printf '# both of these: an unverified webhook URL mints free licences.\n'
        printf 'LLSP_STRIPE_SECRET_KEY=\n'
        printf 'LLSP_STRIPE_WEBHOOK_SECRET=\n\n'
        printf '# One price id per SKU, created in Stripe.\n'
        for sku in ${SKUS}; do
            printf 'LLSP_STRIPE_PRICE_%s=\n' \
                "$(printf '%s' "${sku}" | tr '[:lower:]-' '[:upper:]_')"
        done
        printf '\n# --- this service ------------------------------------------------\n'
        printf 'LLSP_LICENSE_DB=%s\n' "${DB_PATH}"
        printf 'LLSP_BIND_HOST=127.0.0.1\n'
        printf 'LLSP_BIND_PORT=%s\n' "${PORT}"
        printf '# The address the desktop app and Stripe reach this on — the\n'
        printf '# tunnel or domain, not the LAN address.\n'
        printf 'LLSP_PUBLIC_URL=https://licence.example.com\n'
        printf 'LLSP_CHECKOUT_SUCCESS_URL=\n'
        printf 'LLSP_CHECKOUT_CANCEL_URL=\n'
        printf 'LLSP_SUPPORT_EMAIL=\n'
    } > "${ENV_FILE}"
else
    say "Keeping the existing ${ENV_FILE}"
fi
chown root:"${SERVICE_USER}" "${ENV_FILE}"
chmod 0640 "${ENV_FILE}"

# -- systemd service ------------------------------------------------------
say "Installing the systemd units"
cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<UNIT
[Unit]
Description=Local Lead Scraper Pro licence service
Documentation=https://github.com/jordolang/Google-Scraper/blob/main/docs/LICENSING.md
After=network-online.target
Wants=network-online.target

[Service]
Type=exec
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${APP_DIR}
EnvironmentFile=${ENV_FILE}
# ProtectSystem=strict makes /opt read-only, so Python cannot cache bytecode
# there. Saying so outright avoids it retrying on every import. Unbuffered so
# that journalctl -f shows a line the moment it is logged rather than when a
# 8KB pipe buffer happens to flush.
Environment=PYTHONDONTWRITEBYTECODE=1
Environment=PYTHONUNBUFFERED=1
# One worker, several threads. The store is SQLite: several worker *processes*
# writing one file invites "database is locked", while threads inside one
# process share a single serialised connection. This service handles a few
# requests per customer per week — one worker is not the bottleneck.
ExecStart=${VENV_DIR}/bin/gunicorn \\
    --bind 127.0.0.1:${PORT} \\
    --workers 1 \\
    --threads 8 \\
    --timeout 60 \\
    --access-logfile - \\
    --error-logfile - \\
    payments.server:application
Restart=on-failure
RestartSec=5

# Hardening. The service needs the network, its database and nothing else.
NoNewPrivileges=yes
PrivateTmp=yes
PrivateDevices=yes
ProtectSystem=strict
ProtectHome=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
RestrictNamespaces=yes
RestrictSUIDSGID=yes
LockPersonality=yes
SystemCallArchitectures=native
ReadWritePaths=${DATA_DIR}

[Install]
WantedBy=multi-user.target
UNIT

# -- backups --------------------------------------------------------------
# SD cards fail, and this database is the only record of who bought what and
# which machines they activated. sqlite3's own backup API is used rather than
# copying the file, so a backup taken mid-write is still consistent.
cat > /usr/local/bin/llsp-licence-backup <<BACKUP
#!/bin/sh
set -eu
stamp="\$(date -u +%Y%m%d-%H%M%S)"
out="${BACKUP_DIR}/licences-\${stamp}.db"
[ -f "${DB_PATH}" ] || { echo "no database at ${DB_PATH} yet"; exit 0; }
"${VENV_DIR}/bin/python" - "${DB_PATH}" "\${out}" <<'PY'
import sqlite3, sys
source = sqlite3.connect(sys.argv[1])
target = sqlite3.connect(sys.argv[2])
with target:
    source.backup(target)
target.close()
source.close()
PY
find "${BACKUP_DIR}" -name 'licences-*.db' -mtime +${BACKUP_KEEP_DAYS} -delete
echo "backed up to \${out}"
BACKUP
chmod 0755 /usr/local/bin/llsp-licence-backup

cat > "/etc/systemd/system/${SERVICE_NAME}-backup.service" <<UNIT
[Unit]
Description=Back up the licence database

[Service]
Type=oneshot
User=${SERVICE_USER}
Group=${SERVICE_USER}
ExecStart=/usr/local/bin/llsp-licence-backup
ProtectSystem=strict
ReadWritePaths=${DATA_DIR}
UNIT

cat > "/etc/systemd/system/${SERVICE_NAME}-backup.timer" <<UNIT
[Unit]
Description=Nightly licence database backup

[Timer]
OnCalendar=daily
Persistent=yes
RandomizedDelaySec=30m

[Install]
WantedBy=timers.target
UNIT

# -- admin wrapper --------------------------------------------------------
cat > /usr/local/bin/llsp-licence <<WRAPPER
#!/bin/sh
# Operator CLI: grants, revocations, seat releases, support lookups.
#   llsp-licence list
#   llsp-licence grant --sku pro-perpetual-once --email someone@example.com
#   llsp-licence show LLSP-XXXXX-XXXXX-XXXXX-XXXXX
#   llsp-licence revoke LLSP-… --reason refunded
set -eu
if [ "\$(id -u)" -ne 0 ]; then
    echo "run this with sudo (the database is only readable by ${SERVICE_USER})" >&2
    exit 1
fi
set -a
. "${ENV_FILE}"
set +a
cd "${APP_DIR}"
exec sudo -u "${SERVICE_USER}" --preserve-env=LLSP_SIGNING_KEY,LLSP_LICENSE_DB \\
    "${VENV_DIR}/bin/python" -m payments.cli --database "${DB_PATH}" "\$@"
WRAPPER
chmod 0755 /usr/local/bin/llsp-licence

systemctl daemon-reload
systemctl enable --now "${SERVICE_NAME}-backup.timer" >/dev/null 2>&1 || true

# -- cloudflared ----------------------------------------------------------
if [ "${WITH_TUNNEL}" = "yes" ]; then
    say "Installing cloudflared"
    if command -v cloudflared >/dev/null 2>&1; then
        note "already installed"
    else
        case "${ARCH}" in
            aarch64|arm64) CF_ARCH="arm64" ;;
            armv7l|armv6l) CF_ARCH="arm" ;;
            x86_64)        CF_ARCH="amd64" ;;
            *)             CF_ARCH="" ;;
        esac
        if [ -n "${CF_ARCH}" ]; then
            curl -fsSL -o /tmp/cloudflared.deb \
                "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${CF_ARCH}.deb" \
                && dpkg -i /tmp/cloudflared.deb >/dev/null \
                && rm -f /tmp/cloudflared.deb \
                && note "installed" \
                || warn "cloudflared install failed; set the tunnel up by hand"
        else
            warn "no cloudflared build for ${ARCH}; set the tunnel up by hand"
        fi
    fi
fi

# -- what is left ---------------------------------------------------------
MISSING=""
for key in LLSP_STRIPE_SECRET_KEY LLSP_STRIPE_WEBHOOK_SECRET; do
    grep -q "^${key}=.\+" "${ENV_FILE}" || MISSING="${MISSING} ${key}"
done
grep -q '^LLSP_STRIPE_PRICE_[A-Z_]*=.\+' "${ENV_FILE}" \
    || MISSING="${MISSING} LLSP_STRIPE_PRICE_*"

printf '\n'
say "Installed."
printf '\n'
printf '%sThe public key%s — put this in the GitHub repository variable\n' "${BOLD}" "${OFF}"
printf 'LLSP_LICENSE_PUBKEY so release builds can verify licences:\n\n'
printf '    %s%s%s\n\n' "${BOLD}" "${PUBLIC_KEY}" "${OFF}"
printf '    Settings -> Secrets and variables -> Actions -> Variables\n\n'

printf '%sBack up the signing key now%s:\n\n' "${BOLD}" "${OFF}"
printf '    sudo cp %s /somewhere/offline/\n\n' "${ENV_FILE}"
printf '    Lose it and no licence can ever be re-signed; every customer ages\n'
printf '    out at the end of their offline grace window. Leak it and anyone\n'
printf '    can mint Agency licences.\n\n'

if [ -n "${MISSING}" ]; then
    printf '%sStill needed before the service will start%s:\n\n' "${BOLD}" "${OFF}"
    for key in ${MISSING}; do printf '    %s\n' "${key}"; done
    printf '\n    sudo nano %s\n' "${ENV_FILE}"
    printf '    sudo systemctl enable --now %s\n\n' "${SERVICE_NAME}"
    printf '    Run  llsp-licence pricing  for the nine SKUs to create in Stripe.\n\n'
else
    say "Starting the service"
    systemctl enable --now "${SERVICE_NAME}.service"
    sleep 3
    if curl -fsS --max-time 5 "http://127.0.0.1:${PORT}/healthz" >/dev/null 2>&1; then
        printf '    %shealth check passed%s on http://127.0.0.1:%s/healthz\n\n' \
            "${GREEN}" "${OFF}" "${PORT}"
    else
        warn "the service did not answer /healthz — check: journalctl -u ${SERVICE_NAME} -n 40"
    fi
fi

printf '%sReaching it from outside%s — Stripe has to deliver webhooks, and a Pi\n' "${BOLD}" "${OFF}"
printf 'behind a home router is not reachable by default. A Cloudflare tunnel\n'
printf 'avoids port forwarding and gives you TLS:\n\n'
printf '    cloudflared tunnel login\n'
printf '    cloudflared tunnel create llsp-licence\n'
printf '    cloudflared tunnel route dns llsp-licence licence.yourdomain.com\n'
printf '    cloudflared tunnel --url http://127.0.0.1:%s run llsp-licence\n' "${PORT}"
printf '    sudo cloudflared service install   # keep it running across reboots\n\n'
printf 'Then set LLSP_PUBLIC_URL to that hostname, point a Stripe webhook at\n'
printf 'https://licence.yourdomain.com/v1/stripe/webhook, and subscribe it to:\n'
printf '    checkout.session.completed   invoice.paid   invoice.payment_failed\n'
printf '    customer.subscription.deleted   charge.refunded   charge.dispute.created\n\n'

printf '%sDay to day%s\n' "${BOLD}" "${OFF}"
printf '    sudo llsp-licence list                 recent licences\n'
printf '    sudo llsp-licence show LLSP-…          seats, events, history\n'
printf '    sudo llsp-licence grant --sku pro-perpetual-once --email a@b.com\n'
printf '    sudo llsp-licence revoke LLSP-… --reason refunded\n'
printf '    journalctl -u %s -f            live log\n' "${SERVICE_NAME}"
printf '    sudo %s --update    pull new code and restart\n\n' "$0"

trap - EXIT ERR
