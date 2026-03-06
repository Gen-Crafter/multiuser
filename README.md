# LinkedIn Campaign Automation Platform

A production-ready, scalable multi-user LinkedIn Campaign Automation Platform supporting AI-generated posting, automated connection growth, AI-driven sales outreach, follow-up automation, and profile/session management for 2000+ concurrent users.

## Architecture

```
┌─────────────┐     ┌──────────┐     ┌────────────────┐
│   Nginx     │────▶│ Next.js  │     │  PostgreSQL    │
│   Reverse   │     │ Frontend │     │  (Primary DB)  │
│   Proxy     │     └──────────┘     └────────────────┘
│             │                             ▲
│             │     ┌──────────┐            │
│             │────▶│ FastAPI  │────────────┘
│             │     │ Backend  │────┐
└─────────────┘     └──────────┘    │  ┌──────────┐
                         │          └─▶│  Redis   │
                    ┌────┴─────┐       └──────────┘
                    │  Celery  │            ▲
                    │ Workers  │────────────┘
                    └────┬─────┘
                         │
                    ┌────┴─────┐    ┌──────────┐
                    │Playwright│    │  Ollama   │
                    │ Browsers │    │ Local LLM │
                    └──────────┘    └──────────┘
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3.12, FastAPI, SQLAlchemy (async), Pydantic |
| **Frontend** | Next.js 14, React 18, TailwindCSS, TypeScript |
| **Database** | PostgreSQL 16 |
| **Cache/Queue** | Redis 7 |
| **Task Queue** | Celery with Redis broker |
| **Browser Automation** | Playwright (Chromium) |
| **LLM** | Ollama (llama3 + nomic-embed-text) |
| **Vector DB** | FAISS (in-process) |
| **Reverse Proxy** | Nginx |
| **Containers** | Docker, Docker Compose |
| **Orchestration** | Kubernetes (manifests included) |

## Features

- **AI Post Generator** — Schedule AI-written LinkedIn posts with configurable tone, topic, and audience
- **Connection Growth** — Auto-discover, scrape, and send personalized connection requests
- **Sales Outreach** — Multi-stage pipeline with LLM-driven first messages and objection handling
- **Follow-up Automation** — Intelligent follow-up scheduling based on conversation intent
- **Conversation Intelligence** — Intent detection, sentiment analysis, memory store per lead
- **Rate Limiting** — Adaptive throttling with risk scoring and cooldown detection
- **Anti-Detection** — Human-like delays, fingerprint randomization, proxy rotation, warm-up mode
- **Real-Time Logs** — WebSocket-powered live event stream
- **Analytics Dashboard** — Daily metrics, campaign performance, risk gauges
- **Multi-Account** — Multiple LinkedIn accounts per user with encrypted credential storage

## Quick Start (Docker Compose)

### 1. Clone and configure

```bash
git clone <repo-url> && cd multiuser
cp .env.example .env
# Edit .env with your values (especially SECRET_KEY, ENCRYPTION_KEY)
```

### 2. Generate encryption key

```python
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 3. Start all services

```bash
docker compose up -d
```

### 4. Run database migrations

```bash
docker compose exec backend alembic upgrade head
```

### 5. Access the platform

- **Frontend**: http://localhost (via Nginx)
- **Backend API**: http://localhost/api/v1
- **API Docs**: http://localhost:8000/docs

## Ubuntu 24.04 Setup (Bare Metal)

```bash
chmod +x setup-ubuntu.sh install-ollama.sh
sudo ./setup-ubuntu.sh
./install-ollama.sh
```

## Project Structure

```
multiuser/
├── .env.example              # Environment template
├── docker-compose.yml        # Multi-service orchestration
├── setup-ubuntu.sh           # Ubuntu 24.04 setup script
├── install-ollama.sh         # Ollama + model installer
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── alembic.ini
│   ├── alembic/              # DB migrations
│   │   ├── env.py
│   │   └── versions/
│   └── app/
│       ├── main.py           # FastAPI entry point
│       ├── config.py         # Pydantic settings
│       ├── database.py       # Async SQLAlchemy
│       ├── security.py       # JWT, bcrypt, Fernet
│       ├── models/           # SQLAlchemy ORM models
│       ├── schemas/          # Pydantic request/response
│       ├── api/              # FastAPI route handlers
│       │   ├── auth.py
│       │   ├── users.py
│       │   ├── linkedin_accounts.py
│       │   ├── campaigns.py
│       │   ├── leads.py
│       │   ├── analytics.py
│       │   └── websocket.py
│       ├── services/         # Business logic
│       │   ├── llm_service.py
│       │   ├── rate_guard.py
│       │   ├── campaign_engine.py
│       │   ├── conversation_intelligence.py
│       │   └── analytics_service.py
│       ├── automation/       # Browser automation
│       │   ├── browser_manager.py
│       │   ├── linkedin_actions.py
│       │   ├── anti_detection.py
│       │   └── proxy_manager.py
│       └── tasks/            # Celery distributed tasks
│           ├── celery_app.py
│           ├── campaign_tasks.py
│           ├── posting_tasks.py
│           ├── connection_tasks.py
│           ├── sales_tasks.py
│           └── followup_tasks.py
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   ├── next.config.js
│   ├── tailwind.config.js
│   └── src/
│       ├── types/index.ts
│       ├── lib/
│       │   ├── api.ts        # API client
│       │   └── websocket.ts  # WebSocket client
│       ├── components/
│       │   ├── Sidebar.tsx
│       │   ├── Header.tsx
│       │   └── RealTimeLogs.tsx
│       └── app/
│           ├── layout.tsx
│           ├── page.tsx
│           ├── login/page.tsx
│           └── dashboard/
│               ├── layout.tsx
│               ├── page.tsx
│               ├── campaigns/page.tsx
│               ├── leads/page.tsx
│               ├── analytics/page.tsx
│               └── accounts/page.tsx
├── nginx/
│   ├── Dockerfile
│   └── nginx.conf
└── k8s/                      # Kubernetes manifests
    ├── namespace.yaml
    ├── postgres.yaml
    ├── redis.yaml
    ├── backend.yaml
    ├── celery-worker.yaml
    ├── celery-beat.yaml
    ├── frontend.yaml
    └── ingress.yaml
```

## Kubernetes Deployment

```bash
# Create namespace and secrets
kubectl apply -f k8s/namespace.yaml
kubectl create secret generic platform-secrets \
  --from-env-file=.env \
  -n linkedin-platform

# Deploy infrastructure
kubectl apply -f k8s/postgres.yaml
kubectl apply -f k8s/redis.yaml

# Deploy application
kubectl apply -f k8s/backend.yaml
kubectl apply -f k8s/celery-worker.yaml
kubectl apply -f k8s/celery-beat.yaml
kubectl apply -f k8s/frontend.yaml
kubectl apply -f k8s/ingress.yaml
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/auth/register` | Register user |
| POST | `/api/v1/auth/login` | Login |
| GET | `/api/v1/users/me` | Current user profile |
| GET/POST | `/api/v1/linkedin-accounts/` | List/add LinkedIn accounts |
| POST | `/api/v1/linkedin-accounts/{id}/login` | Trigger Playwright login |
| GET/POST | `/api/v1/campaigns/` | List/create campaigns |
| POST | `/api/v1/campaigns/{id}/start` | Start campaign |
| POST | `/api/v1/campaigns/{id}/pause` | Pause campaign |
| GET | `/api/v1/leads/` | List leads |
| GET | `/api/v1/analytics/dashboard` | Dashboard summary |
| GET | `/api/v1/analytics/daily` | Daily analytics |
| WS | `/ws?token=...` | Real-time event stream |

## Configuration

All configuration is via environment variables. See `.env.example` for the full list. Key settings:

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection string |
| `JWT_SECRET_KEY` | Secret for JWT signing |
| `ENCRYPTION_KEY` | Fernet key for credential encryption |
| `OLLAMA_BASE_URL` | Ollama API endpoint |
| `OLLAMA_MODEL` | LLM model name (default: llama3) |
| `BROWSER_POOL_SIZE` | Max concurrent browser sessions |

## Safety & Anti-Detection

- Randomized delays between all actions (human-like distribution)
- Human-like typing simulation with variable speed
- Browser fingerprint randomization (viewport, user-agent, WebGL, etc.)
- Proxy rotation with sticky sessions per account
- Activity distribution aligned to business hours
- Shadow-ban detection via page signal analysis
- 7-day warm-up progression for new accounts
- Adaptive rate limiting with risk scoring

## License

Proprietary — All rights reserved.
