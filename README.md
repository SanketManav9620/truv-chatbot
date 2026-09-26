# Regulatory Copilot

A compliance and regulatory document analysis copilot featuring an intelligent 6-step RAG pipeline (powered by Google Gemini API and ChromaDB vector store) and an embeddable vanilla JS widget frontend.

---

## Table of Contents

1. [Features](#features)
2. [Directory Structure](#directory-structure)
3. [How to Run (Local Development)](#how-to-run-local-development)
4. [Embedding Widget into truvad.com](#embedding-widget-into-truvadcom)
5. [Production Deployment Guide](#production-deployment-guide)
6. [API Endpoints](#api-endpoints)
7. [Running Tests](#running-tests)

---

## Features

- **6-Step Compliance RAG Pipeline**:
  1. Rewrites user query into multiple search queries targeting regulatory text.
  2. Queries vector database (`chromadb`) and deduplicates retrieved circular chunks.
  3. Synthesizes a draft compliance response via Google Gemini Flash.
  4. Verifies claims against source context, identifying any unverified statements.
  5. Formats structured output containing citations, color-coded effective dates timeline, impacted teams, and unverified claim warnings.
  6. Short-circuits with clear `"not enough indexed data"` message if zero relevant chunks are found (avoiding LLM hallucinations).
- **Embeddable Vanilla JS Widget**: Easily mountable into existing HTML pages via `RegulatoryCopilot.mount('#container')`.
- **Automated Scheduler**: Background process (`scheduler.py`) to periodically fetch and ingest regulator circular index pages.
- **Production Controls**: Rate limiting (10 req/min per IP via `slowapi`) and environment-driven CORS configuration.

---

## Directory Structure

```text
/regulatory-copilot
  /backend
    api.py              # FastAPI endpoints, CORS, Rate Limiting & RAG Pipeline
    prompts.py          # RAG pipeline prompt templates (QUERY_REWRITE, ANSWER, VERIFY, FORMAT)
    llm_client.py       # Thin Google Gemini API client wrapper (call_gemini)
    vectorstore.py      # ChromaDB vector store & chunk search interface
    ingest.py           # Document HTML parser & Gemini notification extractor
    scheduler.py        # 24-hour background regulator index crawler & --once CLI
    sources.json        # Config list of regulator index URLs
    ingested_urls.json  # Tracked ingested URLs persistence
    requirements.txt    # Python dependencies
    test_api.py         # Unit tests for RAG pipeline & API
    test_ingest.py      # Unit tests for parser & ingestion
    test_scheduler.py   # Unit tests for crawler & scheduler
  /frontend
    copilot.html        # Standalone demo page showcasing widget mount
    copilot.css         # Scoped compliance UI design system & tooltips
    copilot.js          # Self-contained RegulatoryCopilot.mount() library
  README.md
```

---

## How to Run (Local Development)

### 1. Backend Setup

1. Navigate to `regulatory-copilot` directory:
   ```bash
   cd regulatory-copilot
   ```

2. Create and activate a Python virtual environment:
   ```bash
   python -m venv venv
   # On Windows:
   venv\Scripts\activate
   # On macOS/Linux:
   source venv/bin/activate
   ```

3. Install backend dependencies:
   ```bash
   pip install -r backend/requirements.txt
   ```

4. Set up environment variables in `backend/.env`:
   ```bash
   cp backend/.env.example backend/.env
   ```
   Add your Gemini API key to `backend/.env`:
   ```env
   GEMINI_API_KEY=your_gemini_api_key_here
   GEMINI_MODEL=gemini-2.5-flash
   ENVIRONMENT=development
   ```

### 2. Running the API Server

Start the FastAPI backend server using Uvicorn:

```bash
uvicorn backend.api:app --reload --host 127.0.0.1 --port 8000
```
The server will run locally at `http://127.0.0.1:8000`.

### 3. Running the Circular Ingestion Scheduler

To run a single manual crawler pass over regulator index pages:
```bash
python backend/scheduler.py --once
```

To run the continuous 24-hour background crawler loop:
```bash
python backend/scheduler.py
```

### 4. Opening the Frontend

Open `frontend/copilot.html` directly in your browser or serve via any local web server (e.g. `python -m http.server 3000` inside `frontend/`).

---

## Embedding Widget into truvad.com

To integrate the Regulatory Copilot into an existing HTML page on `truvad.com` (or inside a GRIP dashboard page):

1. **Add Target `<div>` and Include CSS/JS**:
   ```html
   <!-- 1. Mount container -->
   <div id="regulatory-copilot-widget"></div>

   <!-- 2. Stylesheet and Widget Script -->
   <link rel="stylesheet" href="https://truvad.com/copilot.css">
   <script src="https://truvad.com/copilot.js"></script>

   <!-- 3. Mount Initialization Script -->
   <script>
     document.addEventListener('DOMContentLoaded', () => {
       if (window.RegulatoryCopilot) {
         window.RegulatoryCopilot.mount('#regulatory-copilot-widget', {
           apiBase: 'https://api.truvad.com'
         });
       }
     });
   </script>
   ```

---

## Production Deployment Guide

### 1. Environment Variables & Security

In production, set the following environment variables on your backend host:

```bash
export GEMINI_API_KEY="AIzaSy..."
export ENVIRONMENT="production"
export ALLOWED_ORIGINS="https://truvad.com,https://www.truvad.com"
```
When `ENVIRONMENT=production` is set, `backend/api.py` restricts CORS allowed origins strictly to `https://truvad.com` and `https://www.truvad.com`.

### 2. Running Backend Process Manager (Gunicorn + Uvicorn)

Run the FastAPI application behind Gunicorn with Uvicorn worker processes:

```bash
gunicorn -w 4 -k uvicorn.workers.UvicornWorker backend.api:app --bind 0.0.0.0:8000
```

#### Systemd Service (`/etc/systemd/system/regulatory-copilot.service`)
```ini
[Unit]
Description=Regulatory Copilot API Service
After=network.target

[Service]
User=www-data
WorkingDirectory=/var/www/regulatory-copilot
Environment="GEMINI_API_KEY=AIzaSy..."
Environment="ENVIRONMENT=production"
Environment="ALLOWED_ORIGINS=https://truvad.com,https://www.truvad.com"
ExecStart=/var/www/regulatory-copilot/venv/bin/gunicorn -w 4 -k uvicorn.workers.UvicornWorker backend.api:app --bind 127.0.0.1:8000
Restart=always

[Install]
WantedBy=multi-user.target
```

### 3. Serving Static Frontend Files

Place `copilot.js` and `copilot.css` in your public web root or CDN. Configure Nginx to reverse proxy API requests and serve static assets:

```nginx
server {
    server_name truvad.com www.truvad.com;

    # Static Widget Assets
    location /copilot.js {
        alias /var/www/regulatory-copilot/frontend/copilot.js;
        add_header Cache-Control "public, max-age=3600";
    }

    location /copilot.css {
        alias /var/www/regulatory-copilot/frontend/copilot.css;
        add_header Cache-Control "public, max-age=3600";
    }

    # API Proxy Pass
    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## API Endpoints

- **`GET /api/health`**: Returns HTTP 200 `{"status": "ok"}` for monitoring/liveness checks.
- **`POST /api/query`**: Rate-limited to 10 req/min per IP. Accepts `{"query": "your question"}`. Returns JSON schema:
  ```json
  {
    "answer": "Comprehensive answer text...",
    "citations": [
      {
        "circular_no": "RBI/2026-27/89",
        "section": "Section 1",
        "excerpt": "Quote...",
        "url": "https://..."
      }
    ],
    "effective_dates": [
      {
        "provision": "Liquidity Coverage Ratio maintenance",
        "date": "2026-06-01",
        "status": "in force"
      }
    ],
    "impacted_teams": [
      {
        "name": "Treasury",
        "reason": "Responsible for managing LCR liquidity buffers."
      }
    ],
    "unverified_claims": [],
    "confidence_note": "High confidence"
  }
  ```

---

## Running Tests

Execute pytest from the root directory:

```bash
pytest backend
```
All 11 unit tests across API endpoints, verification pipeline, document ingestion, and scheduler will be executed.
