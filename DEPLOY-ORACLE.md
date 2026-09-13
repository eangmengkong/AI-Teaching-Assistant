# 🟠 Deploy to Oracle Cloud — free 200 GB database + 24/7 backend

One-time setup guide to run **this project's PostgreSQL + backend** on Oracle Cloud's
**Always Free** tier, verified against `oracle.com/cloud/free` on **2026-09-13**.

| What you get (free, forever) | Limit |
|---|---|
| Block volume storage (your database disk) | **2 volumes / 200 GB total** |
| Managed Oracle Autonomous DB (not used here) | 2 instances |
| Arm Ampere A1 compute | up to 2 VMs — **1,500 OCPU-hrs + 9,000 GB-hrs / month** |
| Object storage (optional, e.g. backups) | 20 GB + 50,000 API reqs/month |
| Public IP + network egress | 10 TB/month |
| Signup requirement | valid card for identity check (no charge), 1 free account per person |

Your app is already `docker-compose`-ready, so this is basically:
**create a free VM → install Docker → clone repo → fill `.env` → `docker compose up`**.

## Fast path (recommended): two commands from Windows

Steps 1–16 below are automated by two scripts shipped in this repo:

| Script | Runs on | Does |
|---|---|---|
| `scripts/oracle/deploy_windows.ps1` | your Windows PC | generates the SSH key (and prints it for you), builds the server `.env` from `backend\.env` (points the DB URLs at the bundled postgres and remembers your old Neon URL), packs + uploads the app, runs the setup remotely |
| `scripts/oracle/server_setup.sh` | the VM | swap, 200 GB disk grow, Docker, OS firewall, Caddy HTTPS, **one-time data migration from Neon**, build, health check, nightly `pg_dump` cron |

```powershell
# 1st run — you don't have a VM yet. Prints the SSH public key to paste into
# Oracle + step-by-step instructions. Takes ~1 minute.
powershell -ExecutionPolicy Bypass -File scripts\oracle\deploy_windows.ps1

# 2nd run — VM created, you know its Public IP. Does everything else.
# -Domain is optional (skip it and Telegram still works over http://IP:8000).
powershell -ExecutionPolicy Bypass -File scripts\oracle\deploy_windows.ps1 -Ip 1.2.3.4 -Domain api.example.com
```

What stays **manual** (the scripts print exact values for each):
Oracle signup (Step 0), creating the VM with the printed key (Step 1), the DNS
A record (Step 2/Step 7, only with `-Domain`), Google OAuth redirect URI
(Step 13), Vercel `NEXT_PUBLIC_API_URL` + redeploy (Step 13), and pausing the
old Render backend after one good day (Cutover). The sections below explain
what the scripts do, and how to fix things by hand when needed.

---

## Architecture we end up with

```
[ Vercel / your browser ]  ──HTTPS──▶  [ Caddy (Let's Encrypt)  :443 ]
                                                │ reverse_proxy
                                          [ backend :8000 ]
                                                │ (asyncpg, pool_pre_ping)
                                          [ postgres 15 :5432 ]  ← 200 GB disk
```

- **Frontend stays on Vercel** (already deployed) — zero changes needed there.
- **Backend moves to the Oracle VM** with Postgres on the same machine: no
  network hop, no row/transfer quotas, and the **server-side worker lives inside
  the backend process** (Telegram reminders, daily digest, Google Calendar sync),
  so it runs 24/7 exactly like on Render.
- **Uploaded PDFs stay in Cloudflare R2** — the DB only stores metadata/pages.

> ⚠️ **One-instance rule**: the Telegram bot uses **long-polling**, so only ONE
> backend may use your bot token at a time. After you verify the Oracle backend,
> **stop (or delete) the Render backend** — see *Cutover* below.

---

## Step 0 — Oracle Cloud Free Tier signup

1. Go to <https://signup.cloud.oracle.com> → enter details → **Verify address**.
   - Pick the **closest home region** (your public IP decides the region list).
   - Enter a real card; Oracle places a small hold to verify, then releases it.
     Prepaid/debt cards often fail — a normal credit/debit card works.
2. Verification can take **~10–30 minutes** ("pending" email, then approval).
3. Sign in to the console: <https://cloud.oracle.com>.

---

## Step 1 — Create the Always-Free VM (from your Windows PC)

1. Generate an SSH key once on **Windows PowerShell** (simple, no passphrase is fine):

   ```powershell
   ssh-keygen -t ed25519 -f "$env:USERPROFILE\.ssh\id_ed25519" -C "oracle-ubuntu"
   type "$env:USERPROFILE\.ssh\id_ed25519.pub"   # copy this output
   ```

2. Oracle Console → **Compute → Instances → Create instance**:
   - **Name**: `ai-teaching`
   - **Image**: `Ubuntu 24.04` (Minimal starts up faster; either works)
   - **Shape**: `Ampere A1 (ARM)` — Ampere A1.Flex
   - **OCPU count**: `1`, **Memory**: `4 GB` ← stays safely inside the free
     OCPU-hours / GB-hours monthly allowance (see *Costs & limits*)
   - **SSH keys**: paste the public key from step 1
   - **Boot volume**: keep the default 47–50 GB for now; the full **200 GB free**
     allocation is made in *Step 3*
   - Click **Create**. Note the **Public IP address**.

> Tip: an AMD VM is also fine, but the free AMD shape (1/8 OCPU) is too weak for
> this stack + Docker builds. Stick with Ampere A1.

---

## Step 2 — SSH in

```powershell
ssh -i "$env:USERPROFILE\.ssh\id_ed25519" ubuntu@<PUBLIC_IP>
```

Then update the OS once:

```bash
sudo apt-get update && sudo apt-get upgrade -y && sudo reboot
# wait ~30s, reconnect:
ssh -i "$env:USERPROFILE\.ssh\id_ed25519" ubuntu@<PUBLIC_IP>
```
---

## Step 3 — Claim the full 200 GB free disk

1. Oracle Console → **Compute → Instances → `ai-teaching`** → your **Boot volume**
   → **⋮** menu → **Resize** → set it to **200 GB** (the Always-Free allowance is
   up to 200 GB total across 2 block volumes), then **Save**.
2. Back in SSH, grow the filesystem into the new space:

   ```bash
   sudo growpart /dev/sda 1        # or /dev/sda3 on some images
   sudo resize2fs /dev/sda1        # ext4. If XFS: sudo xfs_growfs /
   df -h /                         # confirm ~200G now available
   ```

3. Add **swap** so Docker builds never OOM-kill on a 4 GB VM:

   ```bash
   sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile
   sudo mkswap /swapfile && sudo swapon /swapfile
   echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
   free -h                         # check Swap: 4.0Gi
   ```

---

## Step 4 — Install Docker + Compose

```bash
curl -fsSL https://get.docker.com | sh      # installs Docker Engine + Compose v2
sudo usermod -aG docker $USER
# reconnect so the docker group applies:
exit
ssh -i "$env:USERPROFILE\.ssh\id_ed25519" ubuntu@<PUBLIC_IP>
docker compose version    # expect: Docker Compose version v2.x
```

---

## Step 5 — Clone the repo & create secrets

```bash
cd /opt
sudo git clone https://github.com/eangmengkong/AI-Teaching-Assistant.git
sudo chown -R ubuntu:ubuntu AI-Teaching-Assistant
cd AI-Teaching-Assistant
nano .env      # create the file below (works on Windows WSL / via the SSH session)
```

> If your repo is private, use SSH: `git clone git@github.com:eangmengkong/AI-Teaching-Assistant.git`
> (add a deploy key in GitHub → Settings → Deploy keys).

`.env` — `docker compose` reads this file automatically from the repo root and
forwards every `VAR` into the container (`docker-compose.yml` was updated so all
settings pass through):

```env
# ---------- Database (docker-compose 'postgres' service) ----------
DATABASE_URL=postgresql+asyncpg://postgres:postgrespassword@postgres:5432/ai_teaching_assistant
SYNC_DATABASE_URL=postgresql://postgres:postgrespassword@postgres:5432/ai_teaching_assistant

# ---------- Security ----------
# Generate one:  openssl rand -hex 32   (run in PowerShell/WSL on your PC)
SECRET_KEY=change-me-to-a-64-char-hex-string

# ---------- AI (any OpenAI-compatible provider; Gemini free tier example) ----------
OPENAI_API_KEY=AIza...your-key
OPENAI_MODEL=gemini-3.6-flash
OPENAI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
# Optional fallbacks (same names as on Render):
# AI_FALLBACK_1_BASE_URL=... / AI_FALLBACK_1_API_KEY=... / AI_FALLBACK_1_MODEL=...

# ---------- Telegram (long-polling, no webhook needed) ----------
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyZ

# ---------- Google Calendar ----------
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REDIRECT_URI=https://api.yourdomain.com/api/v1/calendar/oauth2callback
#   ↑ must be EXACTLY what you add in Google Cloud Console, with HTTPS.

# ---------- Daily automation ----------
DAILY_DIGEST_ENABLED=true
DAILY_DIGEST_HOUR=7
GOOGLE_CALENDAR_SYNC_ENABLED=true

# ---------- Frontend (keep the Vercel URL for password-reset links) ----------
FRONTEND_URL=https://ai-teaching-assistant-eight.vercel.app

# ---------- Uploads ----------
MAX_UPLOAD_SIZE_MB=500
UPLOAD_DIR=/tmp/ai_teaching_uploads

# ---------- Cloudflare R2 (PDF bytes — keep your existing bucket) ----------
R2_ACCOUNT_ID=your-account-id
R2_ACCESS_KEY_ID=your-token-access-key
R2_SECRET_ACCESS_KEY=your-token-secret
R2_BUCKET=your-bucket-name
```

Then set file permissions so only root can read it:

```bash
chmod 600 .env
# sanity check (no secrets should be echoed back wrong):
grep -c "TOKEN" .env
```

---

## Step 6 — Firewall (open only 80 & 443)

Oracle VMs have **two** firewalls — open the ports in BOTH, and never open 5432.

**A. Cloud console (Security List):** *Networking → Virtual Cloud Networks →
your VCN → Security Lists → Default Security List → Add Ingress Rules*:

| Source CIDR | IP Protocol | Destination Port |
|---|---|---|
| `0.0.0.0/0` | TCP | `80` |
| `0.0.0.0/0` | TCP | `443` |

**B. Inside the OS (Ubuntu images ship with iptables blocking inbound):**

```bash
sudo iptables -I INPUT -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save 2>/dev/null || sudo apt-get -y install iptables-persistent && sudo netfilter-persistent save
```

> Port 8000 stays **closed** to the internet — Caddy is the only thing that talks
> to it, via `127.0.0.1`. PostgreSQL (5432) stays closed too.

---

## Step 7 — Free HTTPS with Caddy (auto Let's Encrypt)

1. **Point a domain at your VM's public IP.**

   - **Have a domain?** Add an `A` record: `api.yourdomain.com → <PUBLIC_IP>`.
   - **No domain?** Use free dynamic DNS: create a subdomain at
     <https://duckdns.org> (e.g. `api-abc123.duckdns.org`) and set it to your
     public IP. Caddy auto-renews Let's Encrypt for it as well.

2. Install Caddy and configure:

   ```bash
   sudo apt-get update && sudo apt-get install -y caddy
   sudo tee /etc/caddy/Caddyfile > /dev/null <<'EOF'
   https://api.yourdomain.com {
       reverse_proxy 127.0.0.1:8000
   }
   EOF
   # duckdns example instead:
   # https://api-abc123.duckdns.org { reverse_proxy 127.0.0.1:8000 }
   sudo systemctl reload caddy
   ```

3. Confirm a certificate appears (takes seconds):

   ```bash
   sudo journalctl -u caddy --no-pager | tail -20   # look for "certificate obtained"
   ```

> **Alternative: Cloudflare Tunnel** (you already have a CF account — no open
> ports at all): install `cloudflared`, run
> `cloudflared tunnel --url http://127.0.0.1:8000`, and use the
> `https://<random>.trycloudflare.com` URL as your `GOOGLE_REDIRECT_URI` and
> `NEXT_PUBLIC_API_URL`. Use a *named* tunnel (with your `.duckdns.org`/custom
> hostname) so the URL never changes. Caddy above is the recommended, stable
> option.
---

## Step 8 — Build & run (Postgres + backend)

```bash
cd /opt/AI-Teaching-Assistant
docker compose up -d --build postgres backend
```

On first boot the backend automatically:

- creates every table (`app.main` → `Base.metadata.create_all`, retried 3×),
- runs the idempotent schema migrations (`run_schema_migrations()`),
- starts the built-in worker — reminders, daily digest, Google Calendar sync and
  the **Telegram long-polling bot** (all inside the uvicorn process).

Watch it come alive:

```bash
docker compose logs -f backend
# look for these lines:
#   [Startup] Database schema initialized successfully
#   [Server-Side Reminder, Daily Digest & Scheduler Background Worker Started]
#   [Telegram Bot Polling Started for token ...
docker compose ps          # both containers "Up" (postgres + backend)
```

> Exactly **one** backend replica — the compose file already runs a single
> instance; never `--scale backend=2` (double polling = double messages).

---

## Step 9 — Verify publicly

```bash
curl -s https://api.yourdomain.com/          # {"message":"AI Teaching Assistant API active", ...}
curl -sI https://api.yourdomain.com/docs     # HTTP/2 200
```

Open <https://api.yourdomain.com/docs> in the browser — the full Swagger UI should load.

---

## Step 10 — Point everything at the new URL

1. **Google Calendar OAuth** (required — Google needs the exact HTTPS redirect):
   - Google Cloud Console → *Credentials → your OAuth client* → **Authorized
     redirect URIs** → add `https://api.yourdomain.com/api/v1/calendar/oauth2callback`,
     and remove the old Render URI once cut over.
   - Your server `.env` `GOOGLE_REDIRECT_URI` must be that **exact** string, then
     `docker compose up -d backend` to re-apply it.
   - Re-authorize **once**: Web dashboard → *Calendar → Connect*.
2. **Vercel** (frontend): Project → *Settings → Environment Variables* →
   `NEXT_PUBLIC_API_URL=https://api.yourdomain.com/api/v1` → Save → **Redeploy**
   (it is baked into the JS at build time).
3. **Telegram**: send `/start` to the bot again so your `chat_id` is registered
   on the new backend (user accounts/credentials migrate with the data in Step 12).

---

## Step 11 — Cutover (stop the old backend)

- Your Render backend is still polling the **same bot token** → two live backends
  means duplicated reminders and double replies. Avoid that window.
- After the Oracle backend has run verified for a day or two:
  **Render dashboard → your backend service → Settings → Pause** (or Delete).
- Optional cleanup: repoint `.github/workflows/keep-alive.yml` at the new URL.

---

## Step 12 — Move data from Neon

**If you do this BEFORE the backend's first boot** (tables don't exist yet):

```bash
pg_dump --no-owner --no-privileges "postgresql://USER:PASS@NEON_HOST:5432/DB?sslmode=require" \
  | docker compose exec -T postgres psql -U postgres -d ai_teaching_assistant
```

**If the backend already booted** (tables exist), dump only the data:

```bash
pg_dump --data-only --no-owner --disable-triggers "postgresql://USER:PASS@NEON_HOST:5432/DB?sslmode=require" \
  | docker compose exec -T postgres psql -U postgres -d ai_teaching_assistant
```

- **Uploads**: file bytes already live in Cloudflare R2 (`file_path = "r2://..."`),
  so nothing else to move; R2 config in `.env` keeps them served.
- Sanity check: `docker compose exec -T postgres psql -U postgres -d ai_teaching_assistant -c "\dt"`

---

## Step 13 — Keep-alive & monitoring

- Oracle only reclaims accounts that are **idle 30+ days**. Yours is never idle:
  the worker wakes every ~5 s and Telegram `getUpdates` long-polls continuously —
  that real activity keeps the account alive.
- Optional external heartbeat: **UptimeRobot** (free) — add a monitor for
  `https://api.yourdomain.com/` every 5 min with email/Telegram alerts.

---

## Step 14 — Backups (do this — it's a free-tier box)

Add a daily `pg_dump` via `crontab -e`:

```bash
0 3 * * * mkdir -p /opt/backups && cd /opt/AI-Teaching-Assistant && docker compose exec -T postgres pg_dump -U postgres ai_teaching_assistant | gzip -9 > /opt/backups/ata_$(date +\%F).sql.gz && find /opt/backups -name '*.sql.gz' -mtime +14 -delete
```

Restore:

```bash
gunzip -c /opt/backups/ata_YYYY-MM-DD.sql.gz | docker compose exec -T postgres psql -U postgres -d ai_teaching_assistant
```

Off-box copies (free): Oracle Console → *Storage → Block Volumes → Create
Snapshot* (up to 5 free), and/or copy the `.sql.gz` to **Backblaze B2**
(10 GB free) or your R2 bucket with `rclone`.

---

## Step 15 — Costs & limits recap

| Item | Free allowance | What this project uses |
|---|---|---|
| Compute | 1,500 OCPU-hrs / mo | ~720 hr (1 OCPU always-on) ✅ |
| Memory | 9,000 GB-hrs / mo | ~2,880 (4 GB always-on) ✅ |
| Disk | 200 GB | metadata + pages only; PDFs in R2 |
| Egress | 10 TB / mo | pages + PDF streamed from R2 |
| Object storage | 20 GB / 50k API reqs | optional backups |

**$0/month**, no surprises, as long as the VM stays at 1 OCPU / 4 GB.

---

## Step 16 — Troubleshooting

| Symptom | Fix |
|---|---|
| Docker build killed (OOM) | swap from Step 3; confirm with `free -h` |
| First build slow on ARM | normal — `psycopg2` compiles from source on ARM the first time; later builds are cached |
| Port 8000 unreachable from browser | correct — Caddy proxies it; never open 8000 in the firewall |
| `redirect_uri_mismatch` on Calendar | `GOOGLE_REDIRECT_URI` in `.env` must EXACTLY match the Authorized redirect URI |
| Telegram bot silent | exactly one backend running; `docker compose logs backend | grep -i telegram`; send `/start` |
| `could not connect to server` on boot | `docker compose logs backend`; ensure postgres container is `healthy` (`docker compose ps`) |
| Changed `.env` but nothing happened | `docker compose up -d backend` to re-apply env to the container |

---

## Option B — everything on one free VM (no Vercel)

Run the Next.js dashboard on the same box to remove Vercel from the picture.

```bash
cd /opt/AI-Teaching-Assistant
NEXT_PUBLIC_API_URL=https://api.yourdomain.com/api/v1 docker compose up -d --build
```

Then serve both sites through Caddy (`sudo nano /etc/caddy/Caddyfile`):

```
https://api.yourdomain.com {
    reverse_proxy 127.0.0.1:8000
}
https://app.yourdomain.com {
    reverse_proxy 127.0.0.1:3000
}
```

And set `FRONTEND_URL=https://app.yourdomain.com` in `.env` (password-reset links
will point there), add `app.yourdomain.com` to `CORS_ORIGINS`, then reload Caddy
and `docker compose up -d backend`.

---

## Final checklist

- [ ] Free VM created (Ampere A1, Ubuntu 24.04), SSH working
- [ ] Boot volume ≥ 200 GB, swap 4 GB
- [ ] Ports 80/443 open (console + iptables); 5432/8000 stay closed
- [ ] `.env` complete (DB URLs → `postgres` host, secrets, R2, Google)
- [ ] Caddy serving `https://api.yourdomain.com` (certificate obtained)
- [ ] `docker compose up -d --build postgres backend` → logs show schema + worker + Telegram polling
- [ ] Google redirect URI updated + re-authorized once
- [ ] Vercel `NEXT_PUBLIC_API_URL` updated + redeployed
- [ ] Render backend **paused/deleted** (never two pollers)
- [ ] Data moved from Neon, counts verified
- [ ] Daily `pg_dump` cron installed + one restore tested