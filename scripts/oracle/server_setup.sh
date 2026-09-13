#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# AI-Teaching-Assistant — one-shot server setup (Oracle free VM / any Ubuntu)
#
# Run automatically by scripts/oracle/deploy_windows.ps1, or manually:
#     sudo bash server_setup.sh [--domain api.example.com]
#                                 [--app-dir /opt/ai-teaching-assistant]
#
# Expects (already staged by the Windows script, or via git clone):
#     $APP_DIR/{docker-compose.yml, .env, backend/, frontend/}
# -----------------------------------------------------------------------------
set -euo pipefail

DOMAIN=""
APP_DIR="/opt/ai-teaching-assistant"
while [ $# -gt 0 ]; do
    case "$1" in
        --domain)  DOMAIN="${2:-}";  shift 2 ;;
        --app-dir) APP_DIR="${2:-}"; shift 2 ;;
        *) echo "Unknown argument: $1"; exit 1 ;;
    esac
done

SUDO=""
if [ "$(id -u)" != "0" ]; then SUDO="sudo"; fi
export DEBIAN_FRONTEND=noninteractive

log() { echo; echo "==> $*"; }

# ---------------------------------------------------------------- 1/8 swap
log "[1/8] Ensure 4 GB swap (protects Docker builds on small RAM)"
if ! swapon --show | grep -q swapfile; then
    $SUDO fallocate -l 4G /swapfile 2>/dev/null \
        || $SUDO dd if=/dev/zero of=/swapfile bs=1M count=4096
    $SUDO chmod 600 /swapfile
    $SUDO mkswap /swapfile >/dev/null
    $SUDO swapon /swapfile
    grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' | $SUDO tee -a /etc/fstab >/dev/null
fi
swapok=$(free -h | awk '/Swap:/{print $2}')
echo "      swap: $swapok"

# --------------------------------------------------------- 2/8 grow to 200 GB
log "[2/8] Grow root filesystem into the free 200 GB (best effort)"
# Requires the boot volume to already be resized in the Oracle console.
for part in 1 3 2; do
    if [ -b "/dev/sda$part" ]; then
        $SUDO growpart /dev/sda "$part" >/dev/null 2>&1 || true
        $SUDO resize2fs "/dev/sda$part" >/dev/null 2>&1 || true
        break
    fi
done
$SUDO xfs_growfs / >/dev/null 2>&1 || true
df -h / | tail -1
echo "      (if still small: Oracle Console -> Boot volume -> Resize to 200 GB, then rerun this script)"

# -------------------------------------------------- 3/8 Docker + Compose v2
log "[3/8] Install Docker Engine + Compose (if missing)"
if ! command -v docker >/dev/null 2>&1; then
    curl -fsSL https://get.docker.com | $SUDO sh
fi
# Wait for the daemon to be ready
for i in $(seq 1 30); do docker info >/dev/null 2>&1 && break; sleep 2; done
docker --version
$SUDO docker compose version

# --------------------------------------------------------- 4/8 firewall 80/443
log "[4/8] Open ports 80/443 in the OS firewall"
log "      (ALSO required, done once in the console: Networking -> VCN -> Security List -> add Ingress TCP 80 & 443)"
$SUDO apt-get update -qq >/dev/null
$SUDO apt-get install -y -qq iptables-persistent >/dev/null 2>&1 || true
$SUDO iptables -I INPUT -p tcp --dport 80  -j ACCEPT 2>/dev/null || true
$SUDO iptables -I INPUT -p tcp --dport 443 -j ACCEPT 2>/dev/null || true
$SUDO netfilter-persistent save >/dev/null 2>&1 || echo "      (note: iptables persistence unavailable; re-run this script after reboot if ports stop working)"

# ----------------------------------------------------- 5/8 app dir + .env
log "[5/8] Validate app directory + .env"
$SUDO mkdir -p "$APP_DIR"
if [ ! -f "$APP_DIR/.env" ]; then
    echo "ERROR: $APP_DIR/.env not found. The Windows deploy script creates it." >&2
    exit 1
fi
# Normalise line endings (Windows-created files can carry CRLF/BOM)
$SUDO sed -i 's/\r$//' "$APP_DIR/.env"
$SUDO sed -i '1s/^\xEF\xBB\xBF//' "$APP_DIR/.env"
$SUDO chmod 600 "$APP_DIR/.env"
$SUDO chown -R "$(id -un):$(id -gn)" "$APP_DIR" 2>/dev/null || true

missing=""
for k in SECRET_KEY TELEGRAM_BOT_TOKEN OPENAI_API_KEY GOOGLE_CLIENT_ID GOOGLE_CLIENT_SECRET; do
    grep -q "^$k=..*" "$APP_DIR/.env" || missing="$missing $k"
done
[ -n "$missing" ] && echo "      WARN: .env is missing:$missing -> app may start but not fully work. Edit $APP_DIR/.env."

# ------------------------------------------------------ 6/8 Caddy + HTTPS
if [ -z "$DOMAIN" ]; then
    log "[6/8] No --domain given -> skipping Caddy/HTTPS. Telegram + web dashboard on http://IP:8000 still work."
else
    log "[6/8] Caddy + Let's Encrypt for https://$DOMAIN"
    $SUDO apt-get install -y -qq caddy >/dev/null
    $SUDO tee /etc/caddy/Caddyfile >/dev/null <<EOF
https://$DOMAIN {
    reverse_proxy 127.0.0.1:8000
}
EOF
    $SUDO systemctl enable --now caddy >/dev/null 2>&1 || $SUDO systemctl restart caddy
    echo "      DNS check: $(getent hosts "$DOMAIN" | awk '{print $1}' | head -1 || echo 'not resolving yet — Caddy retries automatically')"
fi

# -------------------------------------------- 7/8 database, data, backend
cd "$APP_DIR"
log "[7/8] Start postgres -> migrate old data -> build & start backend"

$SUDO docker compose up -d postgres
log "      Waiting for postgres to accept connections..."
for i in $(seq 1 60); do
    if $SUDO docker compose exec -T postgres pg_isready -U postgres -d ai_teaching_assistant >/dev/null 2>&1; then break; fi
    [ "$i" = 60 ] && echo "      WARN: postgres not ready yet; continuing anyway"
    sleep 2
done

# One-time data migration from the old cloud DB (e.g. Neon). The Windows deploy
# script stores your previous database URL as OLD_DATABASE_URL in .env.
OLD_DATABASE_URL="$(grep -E '^OLD_DATABASE_URL=' "$APP_DIR/.env" | head -1 | cut -d= -f2- | sed -e 's/+asyncpg//' -e 's/ssl=require/sslmode=require/' || true)"
if [ -n "$OLD_DATABASE_URL" ]; then
    has_users="$($SUDO docker compose exec -T postgres psql -U postgres -d ai_teaching_assistant -tAc "SELECT to_regclass('public.users') IS NOT NULL" 2>/dev/null || echo f)"
    if [ "$has_users" = "t" ]; then
        echo "      Local database already has tables -> skipping migration."
        echo "      (To copy data later, see DEPLOY-ORACLE.md section 12.)"
    else
        log "      Copying data from the old database (this can take minutes)..."
        dump_err=/tmp/ata_pgdump.err
        if $SUDO docker compose exec -T postgres pg_dump --no-owner --no-privileges "$OLD_DATABASE_URL" 2>"$dump_err" \
             | $SUDO docker compose exec -T postgres psql -q -U postgres -d ai_teaching_assistant 2>>"$dump_err"; then
            echo "      Data migrated. (Any per-statement notes: $dump_err)"
        elif grep -q "server version mismatch" "$dump_err" 2>/dev/null; then
            ver="$($SUDO docker compose exec -T postgres psql "$OLD_DATABASE_URL" -tAc "SHOW server_version" 2>/dev/null | cut -d. -f1 | tr -cd 0-9)"
            [ -n "$ver" ] || ver=17
            log "      Old server is newer (v$ver) -> dumping with a matching postgres:$ver-alpine image"
            if $SUDO docker run --rm "postgres:$ver-alpine" pg_dump --no-owner --no-privileges "$OLD_DATABASE_URL" 2>"$dump_err" \
                 | $SUDO docker compose exec -T postgres psql -q -U postgres -d ai_teaching_assistant 2>>"$dump_err"; then
                echo "      Data migrated."
            else
                echo "      WARN: migration failed - inspect $dump_err; manual steps in DEPLOY-ORACLE.md section 12." >&2
            fi
        else
            echo "      WARN: migration failed - inspect $dump_err; manual steps in DEPLOY-ORACLE.md section 12." >&2
        fi
        rm -f "$dump_err"
    fi
else
    echo "      No OLD_DATABASE_URL in .env -> fresh install (no data to copy)."
fi

log "      Building backend (first build compiles on ARM, several minutes)..."
$SUDO docker compose up -d --build backend

log "      Waiting for the backend on :8000 (up to 10 minutes)..."
ok=0
for i in $(seq 1 120); do
    if curl -sf http://127.0.0.1:8000/ >/dev/null 2>&1; then ok=1; break; fi
    sleep 5
done
if [ "$ok" = 1 ]; then
    echo "      Backend UP: http://127.0.0.1:8000"
else
    echo "      WARN: backend not answering yet. Inspect with:"
    echo "           cd $APP_DIR && sudo docker compose logs -f backend"
fi

# --------------------------------------------- 8/8 daily pg_dump backup
log "[8/8] Install daily pg_dump backup (03:00 UTC, keep 14 days)"
$SUDO mkdir -p /opt/backups
$SUDO tee /etc/cron.d/ata_backup >/dev/null <<'CRONEOF'
SHELL=/bin/bash
0 3 * * * root cd __APP_DIR__ && docker compose exec -T postgres pg_dump -U postgres ai_teaching_assistant | gzip -9 > /opt/backups/ata_$(date +\%F).sql.gz && find /opt/backups -name '*.sql.gz' -mtime +14 -delete
CRONEOF
$SUDO sed -i "s|__APP_DIR__|$APP_DIR|" /etc/cron.d/ata_backup
$SUDO chmod 644 /etc/cron.d/ata_backup

# ------------------------------------------------------------- summary
echo
echo "=============================================================="
echo " DEPLOY FINISHED"
echo "=============================================================="
if [ -n "$DOMAIN" ]; then
    echo " Dashboard API : https://$DOMAIN/docs"
    echo " Root           : https://$DOMAIN/"
else
    echo " API docs       : http://<PUBLIC_IP>:8000/docs  (HTTPS once you add a domain)"
fi
echo
echo " Still manual (3 steps):"
echo "  1. Google Cloud Console -> OAuth client -> add redirect URI:"
echo "       ${DOMAIN:+https://$DOMAIN}$([ -z "$DOMAIN" ] && echo '<your-https-url>')/api/v1/calendar/oauth2callback"
echo "     then set GOOGLE_REDIRECT_URI in $APP_DIR/.env to the SAME string and:"
echo "       cd $APP_DIR && sudo docker compose up -d backend"
echo "  2. Vercel -> project env -> NEXT_PUBLIC_API_URL=${DOMAIN:+https://$DOMAIN}$([ -z "$DOMAIN" ] && echo '<your-https-url>')/api/v1 -> Redeploy"
echo "  3. Telegram -> send /start to the bot; keep EXACTLY ONE backend running (pause/delete the old Render one after a good day)"
echo
echo " Backups: /opt/backups/*.sql.gz every night (keep 14) | Restore: gunzip -c <file> | docker compose exec -T postgres psql -U postgres -d ai_teaching_assistant"