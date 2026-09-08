# 🎓 AI Teaching Assistant System

Production-ready **AI Teaching Assistant System** designed to manage a complete 1-month course plan using an uploaded textbook and workbook.

Architected around **ONE Central AI Agent** providing complete synchronization between:

$$\text{AI Agent} \iff \text{Database} \iff \text{Google Calendar} \iff \text{Telegram Bot}$$

---

## 🌟 Key Capabilities & Requirements

1. **ONE Central AI Agent**: Single intelligence controlling lesson planning, exercise generation, homework, quizzes, reviews, exams, rescheduling, and communications.
2. **Primary Source of Truth**: Uploaded Textbook and Workbook are treated as strict source of truth with page-level reference tracking.
3. **Strict Anti-Hallucination**: The system NEVER invents textbook/workbook content. Answers retain page numbers. If missing, replies: `"I could not find this information in the uploaded textbook/workbook."`
4. **Clear Content Labeling**:
   - `📖 Textbook Content`
   - `✏️ Workbook Content`
   - `🤖 AI Additional Practice`
5. **Automatic 1-Month Schedule**: Generates a teaching schedule balancing workload across available sessions, reserving days for quizzes, reviews, and exams.
6. **Automatic Intelligent Rescheduling**: When a lesson is skipped or partially completed, unfinished content is redistributed across remaining teaching sessions without breaking quiz or final exam dates.
7. **Google Calendar Synchronization**: Lessons are automatically created/updated with formatted objectives, activities, textbook/workbook pages, and reminders.
8. **Telegram Interface**: Complete natural control via Telegram (`/today`, `/tomorrow`, `/week`, `/lesson`, `/exercise`, `/quiz`, `/homework`, `/review`, `/exam`, `/progress`, `/complete`, `/skip`, `/reschedule`, `/score`).
9. **Offline Reminder Reliability**: Built-in server-side scheduler checks pending reminders and dispatches them even if the teacher's phone or browser is offline.
10. **Completed Content Enforcement**: Quizzes and Final Exams test **ONLY** content from completed lessons.

---

## 🚀 1. Installation Instructions

### Prerequisites
- Python 3.11+
- Node.js 18+
- PostgreSQL 15+
- Docker & Docker Compose (Optional)

### Clone & Install Backend
```bash
cd ai-teaching-assistant/backend
python -m venv venv
# On Windows:
.\venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
```

### Install Frontend
```bash
cd ../frontend
npm install
```

---

## 🔑 2. Environment Variables Configuration

Copy `.env.example` to `.env`:

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgrespassword@localhost:5432/ai_teaching_assistant
SYNC_DATABASE_URL=postgresql://postgres:postgrespassword@localhost:5432/ai_teaching_assistant

SECRET_KEY=super-secret-production-key-2026

OPENAI_API_KEY=sk-proj-your-openai-key
OPENAI_MODEL=gpt-4o

TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyZ
TELEGRAM_WEBHOOK_URL=https://yourdomain.com/api/v1/telegram/webhook

GOOGLE_CLIENT_ID=your-google-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-google-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8000/api/v1/calendar/oauth2callback
```

### 🆓 Free AI Provider (no OpenAI key needed)

The agent works with **any OpenAI-compatible API** — just set `OPENAI_API_KEY`, `OPENAI_MODEL` and `OPENAI_BASE_URL` in `backend/.env`:

| Provider | Free tier (approx.) | `OPENAI_BASE_URL` | `OPENAI_MODEL` | Get key |
|---|---|---|---|---|
| **Google Gemini** ⭐ recommended | Free tier on AI Studio, function calling supported | `https://generativelanguage.googleapis.com/v1beta/openai/` | `gemini-3.6-flash` | https://aistudio.google.com/apikey |
| **Groq** | ~30 RPM / ~1,000 req/day (gpt-oss-120b), very fast | `https://api.groq.com/openai/v1` | `openai/gpt-oss-120b` | https://console.groq.com/keys |
| **OpenRouter** | `:free` models, ~50–1,000 req/day | `https://openrouter.ai/api/v1` | `minimax/minimax-m3:free` | https://openrouter.ai/keys |
| **Ollama** (local) | Unlimited, runs on your PC | `http://localhost:11434/v1` | `qwen2.5:7b` | `ollama pull qwen2.5:7b` |

Example for Gemini:
```env
OPENAI_API_KEY=AIza...your-free-gemini-key
OPENAI_MODEL=gemini-3.6-flash
OPENAI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
```

### 🔄 Automatic AI Fallback (keep working when one runs out)

Providers are tried **in order**: primary (`OPENAI_*`) first, then `AI_FALLBACK_1`, `AI_FALLBACK_2`, … (up to 9). If a provider is rate-limited, out of quota, or erroring, the **next one answers automatically**; the failed one is skipped for `AI_PROVIDER_COOLDOWN_SECONDS` (default 300 s) before being retried.

```env
# Example: Gemini primary + Groq + OpenRouter as backups
OPENAI_API_KEY=AIza...your-free-gemini-key
OPENAI_MODEL=gemini-3.6-flash
OPENAI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/

AI_FALLBACK_1_BASE_URL=https://api.groq.com/openai/v1
AI_FALLBACK_1_API_KEY=gsk...your-groq-key
AI_FALLBACK_1_MODEL=openai/gpt-oss-120b

AI_FALLBACK_2_BASE_URL=https://openrouter.ai/api/v1
AI_FALLBACK_2_API_KEY=sk-or-v1...your-key
AI_FALLBACK_2_MODEL=minimax/minimax-m3:free
```

---

## 🗄️ 3. Database Setup

Ensure PostgreSQL is running:

```bash
# Create database
createdb -U postgres ai_teaching_assistant
```

When backend starts (`app.main`), tables are automatically initialized via SQLAlchemy Async Engine:
- `users`, `courses`, `documents`, `document_pages`, `document_chunks`, `lesson_schedule`, `lesson_progress`, `homework`, `quizzes`, `quiz_questions`, `quiz_results`, `exams`, `exam_questions`, `exam_results`, `calendar_events`, `telegram_messages`, `holidays`, `settings`.

---

## 📅 4. Google OAuth & Calendar API Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/).
2. Create a Project and enable **Google Calendar API**.
3. Configure OAuth Consent Screen (External / Internal).
4. Create **OAuth 2.0 Client ID** credentials (Web Application).
5. Set Authorized Redirect URI: `http://localhost:8000/api/v1/calendar/oauth2callback`.
6. Add `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` to `.env`.

---

## 🤖 5. Telegram Bot Setup

1. Open Telegram and search for `@BotFather`.
2. Send `/newbot` and follow prompts to receive your `TELEGRAM_BOT_TOKEN`.
3. Add the token to `.env`.
4. (Optional) Set Webhook:
   ```bash
   curl -X POST "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook?url=https://yourdomain.com/api/v1/telegram/webhook"
   ```

---

## ⏰ 6. Server-Side Scheduler & Offline Reminders

### How Offline Reminders Work:
1. The backend runs a server-side background worker (`app.worker`) alongside FastAPI.
2. It periodically scans upcoming lessons in `lesson_schedule` and inserts `reminder_24h` and `reminder_1h` records into the `telegram_messages` database table.
3. Every 30 seconds, it queries pending messages due for delivery and sends them via Telegram API.
4. **Phone Offline Behavior**:
   - If the teacher's phone is switched off or disconnected, the server still dispatches the message to Telegram's cloud servers.
   - Telegram buffers the message and delivers it the moment the phone reconnects.
   - Browser / Frontend state is irrelevant; reminders run 100% on the backend.

---

## 📖 7. Uploading Textbook & Workbook

Upload files via the Web Dashboard or API:

```bash
POST /api/v1/documents/upload
Form data:
- course_id: 1
- document_type: "textbook" (or "workbook")
- file: textbook.pdf (or .docx / .txt)
```

The system parses pages, indexes unit/chapter/lesson sections, and creates searchable page chunks.

---

## 🛠️ 8. Creating First Course & Generating 1-Month Plan

1. Submit setup info:
   ```json
   {
     "name": "English 101",
     "student_count": 25,
     "class_days": ["Monday", "Wednesday", "Friday"],
     "start_time": "08:00",
     "end_time": "09:30",
     "start_date": "2026-09-07",
     "end_date": "2026-10-02",
     "holidays": ["2026-09-24"]
   }
   ```
2. Trigger schedule generation: `POST /api/v1/schedule/generate/1`.
3. The AI Agent calculates total teaching hours, reserves sessions for quizzes, reviews, and the final exam, and balances content across lessons.

---

## 🏃 9. How to Run the Application

### First-Time Setup (SQLite)

1. **Backend & Worker:**
   ```bash
   cd backend
   python -m venv venv
   # On Windows PowerShell:
   .\venv\Scripts\activate
   # On Linux/macOS:
   source venv/bin/activate

   pip install -r requirements.txt aiosqlite email-validator
   uvicorn app.main:app --reload --port 8000
   ```

2. **Frontend:**
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

### Re-running the Project (After Closing Terminal)

1. **Start Backend (Terminal 1):**
   ```bash
   cd backend
   .\venv\Scripts\activate
   uvicorn app.main:app --reload --port 8000
   ```

2. **Start Frontend (Terminal 2):**
   ```bash
   cd frontend
   npm run dev
   ```

### Option B: Docker Compose (PostgreSQL)
```bash
docker-compose up --build
```

Access Web Dashboard at `http://localhost:3000` and API docs at `http://localhost:8000/docs`.

---

## 🚢 10. Production Deployment (24/7, hands-off)

The backend ships with a **built-in automation worker** (`app/worker.py`) that runs inside the
API process and every 30 seconds:

1. **Sends lesson reminders** – 24h and 1h before every lesson, straight to Telegram.
2. **Sends the morning digest** – one "today's lessons" message per timezone at
   `DAILY_DIGEST_HOUR` (default 07:00 local time).
3. **Auto-syncs Google Calendar** – inserts every planned lesson that is missing from your
   calendar and pushes updates for edited lessons (rolling window: yesterday → +60 days).
4. **Runs the Telegram bot** – long-polling, so `/today`, `/quiz`, `/complete`, `/score` … all
   work from your phone.

> **Golden rule:** anything running only on your laptop stops when the laptop sleeps. To get
> reminders and calendar sync **every day without opening anything**, host the **backend** on an
> always-on service. The database is already cloud-hosted (Neon), so nothing else is needed.

### Option A – Render (easiest; `render.yaml` included)
1. Push this project to a GitHub repo.
2. In Render: **New + → Blueprint**, pick the repo – the backend service is created from
   `render.yaml` (root directory `backend`).
3. Fill in the `sync: false` env vars in the Render dashboard (Neon `DATABASE_URL`,
   `TELEGRAM_BOT_TOKEN`, `OPENAI_API_KEY`, Google OAuth values, …) and deploy.
4. ⚠️ Keep the **Starter plan (always-on)**. Free tiers **sleep** after inactivity and your
   reminders are missed while asleep.

### Option B – Railway / Fly.io / any Docker host
- **Railway**: New Project → Deploy from repo → set *Root Directory* to `backend` (it uses
  `backend/Dockerfile`), then add the same env vars. The Hobby plan is always-on.
- **Fly.io**: `fly launch --dockerfile backend/Dockerfile` then `fly secrets set ...`.

### Option C – Your own VPS (Hetzner / DigitalOcean / ...)
```bash
# on the VPS, after cloning the repo and creating .env from .env.example
docker compose up -d --build
```
`restart: always` keeps all three containers (postgres, backend, frontend) alive across reboots.

### Frontend (Vercel – free)
1. Import the repo in Vercel, set **Root Directory** to `frontend`.
2. Add env var `NEXT_PUBLIC_API_URL=https://<your-backend-domain>/api/v1` – it is baked in at
   **build time** (the included `frontend/Dockerfile` accepts it as a build arg for Docker hosts).
3. Deploy.

### Google Calendar – one-time production setup
1. Google Cloud Console → *Credentials → your OAuth client* → add
   `https://<your-backend-domain>/api/v1/calendar/oauth2callback` as an **Authorized redirect URI**.
2. Set `GOOGLE_REDIRECT_URI` to the exact same URL in the backend's env.
3. Open the web dashboard → *Calendar → Connect* and re-authorize **once** from the production
   domain (the refresh token is bound to the redirect URI used at consent time).
4. Done – `GOOGLE_CALENDAR_SYNC_ENABLED=true` keeps the calendar in sync automatically, every day.

### Telegram – nothing to do
The bot uses long-polling (no webhook needed) and works 24/7 wherever the backend runs.
Two requirements: send `/start` to your bot once so your `chat_id` is registered, and run
**exactly one** backend instance (single replica) – two pollers would compete for updates and
double-send messages (the included `render.yaml` already pins `numInstances: 1`).

### Daily-automation env vars
| Variable | Default | Purpose |
|---|---|---|
| `DAILY_DIGEST_ENABLED` | `true` | Morning "today's lessons" Telegram digest |
| `DAILY_DIGEST_HOUR` | `7` | Local (course timezone) hour to send the digest |
| `GOOGLE_CALENDAR_SYNC_ENABLED` | `true` | Auto insert/update lessons in Google Calendar |

> 🔐 **Security**: never commit real tokens/keys to the repo (`.env`, README, screenshots). If a
> secret ever lands in pushed code, rotate it immediately (Telegram: BotFather `/revoke`; Google:
> Cloud Console; AI providers: their dashboards) – treat the exposed value as compromised.

---

## 🔧 11. Troubleshooting

- **PDF Reading Error**: Ensure `pypdf` is installed. Fallback simple text reader will handle plain text files.
- **Telegram Not Receiving**: Verify `TELEGRAM_BOT_TOKEN` and make sure you've sent `/start` to the bot once from your Telegram account so your `chat_id` is registered.
- **Google Calendar Authentication**: Ensure redirect URI matches exact host in Google Cloud Console.


> 🔐 Never paste real Client IDs, client secrets or tokens in this file – keep them in `.env`
> (and add `.env` to `.gitignore` before pushing to GitHub). Configure the Google OAuth client
> in Google Cloud Console → *APIs & Services → Credentials*.