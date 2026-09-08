FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Default dashboard URL used to build password-reset links sent via Telegram.
# Must match the real Vercel domain (Vercel appends a suffix when the name
# is taken). Override with the FRONTEND_URL env var in production if needed.
ENV FRONTEND_URL=https://ai-teaching-assistant-eight.vercel.app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
