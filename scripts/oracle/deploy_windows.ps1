<#
  deploy_windows.ps1 - ONE-command deploy of AI-Teaching-Assistant to an
  Oracle Cloud free VM (or any Ubuntu 22.04/24.04 server).

  You only do 3 things:
    1. Sign up at https://signup.cloud.oracle.com (free tier, Always Free)
    2. First run of this script prints an SSH public key -> paste it when
       creating the VM (Ubuntu 24.04, Ampere A1 ARM, 1 OCPU / 4 GB),
       then write down the Public IP.
    3. Run this script again with that IP. It uploads everything, sets up
       Docker, firewall, HTTPS (if -Domain), copies your Neon data, and
       starts the stack.

  Usage (from the repo root, in PowerShell):
    powershell -ExecutionPolicy Bypass -File scripts\oracle\deploy_windows.ps1
    powershell -ExecutionPolicy Bypass -File scripts\oracle\deploy_windows.ps1 -Ip 1.2.3.4
    powershell -ExecutionPolicy Bypass -File scripts\oracle\deploy_windows.ps1 -Ip 1.2.3.4 -Domain api.example.com
    powershell -ExecutionPolicy Bypass -File scripts\oracle\deploy_windows.ps1 -DryRun

  Requires: backend\.env with your keys (it already exists in this repo),
  Windows 10/11 (has ssh, scp and tar built in).
#>
param(
    [string]$Ip     = "",
    [string]$Domain = "",
    [string]$User   = "ubuntu",
    [string]$Key    = "",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
function Fail($msg) { Write-Host "ERROR: $msg" -ForegroundColor Red; exit 1 }

$repoRoot = (Get-Item (Join-Path $PSScriptRoot "..\..\")).FullName
$compose  = Join-Path $repoRoot "docker-compose.yml"
$setupSh  = Join-Path $PSScriptRoot "server_setup.sh"
$srcEnv   = Join-Path $repoRoot "backend\.env"
if ($Key -eq "") { $Key = Join-Path $env:USERPROFILE ".ssh\id_ed25519" }

Write-Host ""
Write-Host "=============================================================="
Write-Host " AI Teaching Assistant -> Oracle Cloud deploy"
Write-Host "=============================================================="

if (!(Test-Path $compose)) { Fail "docker-compose.yml not found. Run from the repo root." }
if (!(Test-Path $setupSh)) { Fail "server_setup.sh not found next to this script." }
if (!(Test-Path $srcEnv))  { Fail "backend\.env not found - it holds your API tokens and is required." }

# ------------------------------------------------------- 1. SSH key + intro
if (!(Test-Path $Key)) {
    Write-Host "No SSH key at $Key -> generating a fresh key for Oracle..."
    New-Item -ItemType Directory -Force -Path (Split-Path $Key) | Out-Null
    # via cmd so that -N "" is passed as a true empty passphrase (PowerShell 5
    # drops empty native args; with '""' the key would get a bogus passphrase)
    $keygen = (Get-Command ssh-keygen).Source
    cmd /c "`"$keygen`" -t ed25519 -f `"$Key`" -N `"`" -C oracle-ubuntu"
    if ($LASTEXITCODE -ne 0) { Fail "ssh-keygen failed." }
}
if (!(Test-Path "$Key.pub")) { Fail "Missing public key $Key.pub" }

Write-Host ""
Write-Host "=========== PASTE THIS PUBLIC KEY INTO ORACLE (SSH keys) ===========" -ForegroundColor Cyan
Get-Content "$Key.pub" | ForEach-Object { Write-Host $_ -ForegroundColor Cyan }
Write-Host "====================================================================" -ForegroundColor Cyan
Write-Host " 1. Sign up : https://signup.cloud.oracle.com  (credit card needed,"
Write-Host "              never charged - this is the free tier)"
Write-Host " 2. Create  : Compute -> Instances -> Create instance"
Write-Host "              Image : Ubuntu 24.04"
Write-Host "              Shape : Ampere A1 (ARM)  1 OCPU / 4 GB"
Write-Host "              SSH keys: paste the key above"
Write-Host " 3. Deploy  : run this script again with  -Ip <PUBLIC_IP>"
Write-Host "              optional    -Domain api.yourdomain.com  (for HTTPS)"
Write-Host ""

# ------------------------------------------------------------- 2. inputs
if (-not $DryRun) {
    if ($Ip -eq "") { $Ip = (Read-Host "Public IP of your VM (from the Oracle instance page)").Trim() }
    if ($Domain -eq "" ) { $Domain = (Read-Host "Domain for HTTPS (ENTER to skip, Telegram works without it)").Trim() }
    if ($Ip -notmatch '^\d{1,3}(\.\d{1,3}){3}$') { Fail "'$Ip' does not look like an IPv4 address." }
}

# --------------------------------------------- 3. build the server .env
# Compose reads ${VAR} values from the root .env next to docker-compose.yml.
# We copy backend\.env, but:
#   - point DATABASE_URL / SYNC_DATABASE_URL at the bundled postgres
#   - remember the OLD (Neon) url as OLD_DATABASE_URL -> server_setup.sh
#     copies your data once on first boot
#   - set GOOGLE_REDIRECT_URI to the https domain when -Domain is given
$localDbPattern = '://.*@?(postgres|localhost|127\.0\.0\.1)[:/]'
$lines = Get-Content $srcEnv
$serverEnv = New-Object System.Collections.Generic.List[string]
$oldUrl = ""
$rewritten = New-Object System.Collections.Generic.List[string]
foreach ($l in $lines) {
    $t = $l.Trim()
    if ($t -eq "" -or $t.StartsWith("#")) { $serverEnv.Add($l); continue }
    $eq = $l.IndexOf("=")
    if ($eq -lt 1) { $serverEnv.Add($l); continue }
    $k = $l.Substring(0, $eq).Trim()
    $v = $l.Substring($eq + 1).Trim()
    if ($k -eq "DATABASE_URL") {
        if ($v -ne "" -and $v -notmatch $localDbPattern) {
            # Neon URLs arrive as JDBC style (ssl=require); libpq needs sslmode=
            $oldUrl = ($v -replace '\+asyncpg', '') -replace 'ssl=require', 'sslmode=require'
        }
        $serverEnv.Add("DATABASE_URL=postgresql+asyncpg://postgres:postgrespassword@postgres:5432/ai_teaching_assistant")
        $rewritten.Add("DATABASE_URL")
    }
    elseif ($k -eq "SYNC_DATABASE_URL") {
        $serverEnv.Add("SYNC_DATABASE_URL=postgresql://postgres:postgrespassword@postgres:5432/ai_teaching_assistant")
        $rewritten.Add("SYNC_DATABASE_URL")
    }
    elseif ($k -eq "OLD_DATABASE_URL") { }  # never carry an old one over
    elseif ($k -eq "GOOGLE_REDIRECT_URI" -and $Domain -ne "") {
        $serverEnv.Add("GOOGLE_REDIRECT_URI=https://$Domain/api/v1/calendar/oauth2callback")
        $rewritten.Add("GOOGLE_REDIRECT_URI")
    }
    else { $serverEnv.Add($l) }
}
if ($oldUrl -ne "") {
    $serverEnv.Add("OLD_DATABASE_URL=$oldUrl")
    Write-Host "Old database found -> its data will be copied to the VM on first boot."
}

# ------------------------------------------------------- 4. stage bundle
$stamp  = Get-Date -Format "yyyyMMdd_HHmmss"
$stage  = Join-Path ([IO.Path]::GetTempPath()) "ata_stage_$stamp"
$bundle = Join-Path ([IO.Path]::GetTempPath()) "ata_bundle_$stamp.tgz"
New-Item -ItemType Directory -Path $stage | Out-Null

Copy-Item $compose  (Join-Path $stage "docker-compose.yml")
Copy-Item $setupSh  (Join-Path $stage "server_setup.sh")
Copy-Item (Join-Path $repoRoot "backend") (Join-Path $stage "backend") -Recurse
# strip dev junk from the staged backend copy
foreach ($dir in @("__pycache__", ".venv", "venv", ".pytest_cache", ".mypy_cache", ".git")) {
    Get-ChildItem (Join-Path $stage "backend") -Recurse -Force -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -eq $dir } | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
}
Get-ChildItem (Join-Path $stage "backend") -Recurse -Force -File -Include *.pyc -ErrorAction SilentlyContinue |
    Remove-Item -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $stage "backend\ai_teaching_assistant.db") -Force -ErrorAction SilentlyContinue

# write both env files (root one feeds docker compose, backend one is a
# belt-and-braces copy for pydantic's env_file fallback - same values)
$serverEnv | Set-Content -Path (Join-Path $stage ".env") -Encoding ASCII
$serverEnv | Set-Content -Path (Join-Path $stage "backend\.env") -Encoding ASCII

Write-Host ""
Write-Host "Staged for upload:"
Write-Host "  docker-compose.yml, server_setup.sh, backend/ (code only), .env"
if ($rewritten.Count -gt 0) {
    Write-Host ("  DB URLs rewritten to the bundled postgres: " + ($rewritten -join ", "))
}
if ($Domain -ne "") {
    Write-Host "  GOOGLE_REDIRECT_URI set to https://$Domain/api/v1/calendar/oauth2callback"
}
foreach ($need in @("SECRET_KEY", "TELEGRAM_BOT_TOKEN", "OPENAI_API_KEY")) {
    $found = $false
    foreach ($l in $serverEnv) { if ($l -like "$need=*" -and $l -ne "$need=") { $found = $true } }
    if (-not $found) { Write-Host "  WARN: backend\.env has no $need -> that feature will not work until you add it." -ForegroundColor Yellow }
}

# ------------------------------------------------------ 5. pack bundle
Push-Location $stage
try { tar -czf $bundle .; $rc = $LASTEXITCODE } catch { $rc = 99 }
Pop-Location
# Windows bsdtar can exit with a bogus 0xC0000005 code AFTER writing a
# complete archive -> verify the archive instead of trusting the exit code.
$archiveOk = $false
if (Test-Path $bundle) {
    $py = Get-Command python -ErrorAction SilentlyContinue
    if ($py) {
        & python -c "import sys, tarfile; sys.exit(0 if tarfile.is_tarfile(sys.argv[1]) else 1)" $bundle
        $archiveOk = ($LASTEXITCODE -eq 0)
    } else {
        $archiveOk = ((Get-Item $bundle).Length -gt 1024)
    }
}
if (-not $archiveOk) { Fail "tar failed (exit $rc) - could not produce a valid archive. tar.exe (bsdtar) is required (built into Windows 10/11)." }
$mb = [math]::Round((Get-Item $bundle).Length / 1048576, 1)
Write-Host "Bundle ready: $bundle ($mb MB)"

if ($DryRun) {
    Write-Host ""
    Write-Host "DRY-RUN complete. Staged bundle: $bundle"
    Write-Host "Stage folder (inspect the generated .env here): $stage"
    Write-Host "The real run will: scp -> extract to /opt/ai-teaching-assistant -> run server_setup.sh"
    exit 0
}

# ---------------------------------------------------------------- 6. DNS
if ($Domain -ne "") {
    Write-Host ""
    Write-Host "Reminder: add a DNS A record  $Domain -> $Ip  (Caddy needs it for the HTTPS certificate)."
    $dns = (nslookup $Domain 2>$null | Out-String)
    if ($dns -match [regex]::Escape($Ip)) { Write-Host "DNS OK - $Domain already resolves to $Ip." -ForegroundColor Green }
    else { Write-Host "DNS not pointing at $Ip yet - Caddy retries automatically; deploy can continue." -ForegroundColor Yellow }
}

# ---------------------------------------------------- 7. upload + remote
$sshCommon = @("-o", "StrictHostKeyChecking=accept-new", "-i", $Key)
Write-Host ""
Write-Host "Uploading bundle to ${User}@${Ip} ..."
try {
    scp $sshCommon $bundle "${User}@${Ip}:/tmp/ata_bundle.tgz"
    if ($LASTEXITCODE -ne 0) { Fail "scp exited with code $LASTEXITCODE - check the IP and that the VM is running." }
} catch {
    Fail "scp failed - OpenSSH client must be on PATH (built into Windows 10/11)."
}
Remove-Item $bundle -Force -ErrorAction SilentlyContinue

$domainArg = ""
if ($Domain -ne "") { $domainArg = " --domain '$Domain'" }
$remote = "set -e; sudo mkdir -p /opt/ai-teaching-assistant; sudo tar -xzf /tmp/ata_bundle.tgz -C /opt/ai-teaching-assistant; sudo chown -R ${User}:${User} /opt/ai-teaching-assistant; chmod +x /opt/ai-teaching-assistant/server_setup.sh; rm -f /tmp/ata_bundle.tgz; cd /opt/ai-teaching-assistant; sudo bash server_setup.sh$domainArg"

Write-Host "Running server setup (swap, disk, Docker, firewall, HTTPS, data copy, build)..."
try {
    ssh $sshCommon "${User}@${Ip}" $remote
    if ($LASTEXITCODE -ne 0) { Fail "remote setup exited with code $LASTEXITCODE - see the log above." }
} catch {
    Fail "ssh failed - OpenSSH client must be on PATH (built into Windows 10/11)."
}

# ---------------------------------------------------------------- 8. done
$base = "http://${Ip}:8000"
if ($Domain -ne "") { $base = "https://$Domain" }

Write-Host ""
Write-Host "=============================================================="
Write-Host " DEPLOY DONE"
Write-Host "=============================================================="
Write-Host " API docs : $base/docs"
Write-Host ""
Write-Host " 3 manual steps to finish:"
Write-Host " 1) GOOGLE  : Cloud Console -> OAuth client -> add redirect URI:"
Write-Host "              $base/api/v1/calendar/oauth2callback"
Write-Host "              then check GOOGLE_REDIRECT_URI in the server .env matches,"
Write-Host "              ssh -i $Key ${User}@${Ip}"
Write-Host "              cd /opt/ai-teaching-assistant && sudo docker compose up -d backend"
Write-Host " 2) VERCEL  : project env NEXT_PUBLIC_API_URL=$base/api/v1 -> Redeploy"
Write-Host " 3) TELEGRAM: send /start to your bot. NEVER run the old Render backend"
Write-Host "              at the same time (two pollers = duplicate reminders)."
Write-Host "              After one good day: pause/delete the Render service."
Write-Host ""
Write-Host " Backups: nightly pg_dump to /opt/backups on the VM (14 days kept)."


