# 🧠 AI Research Assistant — Backend

> Production-ready FastAPI backend for an AI-powered research paper management and analysis platform.

---

## ✨ Key Features

| Category | Features |
|---|---|
| **Paper Management** | PDF upload, text extraction (PyMuPDF), metadata parsing, hash deduplication |
| **Semantic Search** | pgvector embeddings (384-dim), cosine similarity, HNSW index |
| **RAG Chat** | Context-aware Q&A over papers with source attribution |
| **Summarization** | Brief / detailed / structured / section-level (BART-large-CNN) |
| **Citations** | Auto-generate APA, MLA, IEEE, Chicago, Harvard, BibTeX |
| **Clustering** | K-Means & HDBSCAN topic discovery with auto-labeling |
| **Research Tools** | Insight extraction, literature reviews, paper comparison, timeline |
| **Collections** | Organize papers, reading lists, annotations |
| **Auth & Security** | JWT access/refresh tokens, bcrypt, rate limiting, security headers |
| **Async Processing** | Celery + Redis workers for heavy AI tasks |
| **Monitoring** | Prometheus metrics, Sentry errors, structured logging |

---

## 🏗️ Architecture

```
┌────────────┐     ┌──────────────┐     ┌───────────┐
│   Client   │────▶│   FastAPI    │────▶│ PostgreSQL│
│  (Frontend)│     │   Backend    │     │ + pgvector│
└────────────┘     └──────┬───────┘     └───────────┘
                          │
                   ┌──────┴───────┐
                   │    Redis     │
                   │ Cache+Broker │
                   └──────┬───────┘
                          │
                   ┌──────┴───────┐
                   │   Celery     │
                   │   Workers    │
                   └──────────────┘
```

### Tech Stack

- **Framework:** FastAPI (Python 3.11) with uvicorn + uvloop
- **Package Manager:** Poetry
- **Database:** PostgreSQL 16 + Prisma ORM + pgvector extension
- **AI Models:** SentenceTransformers (MiniLM-L6-v2), BART-large-CNN, RoBERTa-base-SQuAD2
- **Task Queue:** Celery 5 with Redis broker
- **Caching:** Redis 7
- **Containerisation:** Docker multi-stage builds, Docker Compose
- **Deployment:** GCP Cloud Run / GKE ready

---

## 📁 Project Structure

```
backend/
├── app/
│   ├── main.py                 # FastAPI application factory
│   ├── config.py               # Pydantic settings
│   ├── api/                    # Route handlers
│   │   ├── health_routes.py
│   │   ├── auth_routes.py
│   │   ├── paper_routes.py
│   │   ├── chat_routes.py
│   │   ├── research_routes.py
│   │   ├── notes_routes.py
│   │   ├── collection_routes.py
│   │   └── advanced_routes.py
│   ├── ai_models/              # HuggingFace model wrappers
│   │   ├── embedding_model.py
│   │   ├── summarizer_model.py
│   │   └── qa_model.py
│   ├── database/
│   │   └── prisma_client.py
│   ├── middleware/
│   │   ├── auth.py             # JWT authentication
│   │   ├── rate_limiter.py
│   │   └── security.py
│   ├── schemas/                # Pydantic v2 request/response models
│   │   ├── user_schema.py
│   │   ├── paper_schema.py
│   │   ├── chat_schema.py
│   │   └── note_schema.py
│   ├── services/               # Business logic
│   │   ├── pdf_service.py
│   │   ├── embedding_service.py
│   │   ├── rag_service.py
│   │   ├── summarization_service.py
│   │   ├── citation_service.py
│   │   └── clustering_service.py
│   ├── utils/
│   │   ├── chunking.py
│   │   └── text_cleaning.py
│   └── workers/
│       ├── celery_worker.py
│       └── tasks.py
├── prisma/
│   └── schema.prisma
├── scripts/
│   └── init_db.sql
├── tests/
│   ├── conftest.py
│   ├── unit/
│   └── api/
├── docker-compose.yml
├── Dockerfile
├── Dockerfile.worker
├── Makefile
├── pyproject.toml
├── poetry.lock
├── .env.example
└── README.md
```

---

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- [Poetry](https://python-poetry.org/docs/#installation) (v1.8+)
- Docker & Docker Compose
- (Optional) GCP CLI for cloud deployment

### 1. Clone & Configure

```bash
cd backend
cp .env.example .env
# Edit .env with your secrets (SECRET_KEY, DATABASE_URL, etc.)
```

### 2. Start with Docker Compose (Recommended)

```bash
# Start all services (PostgreSQL, Redis, Backend, Workers, Flower)
make docker-up

# View logs
make docker-logs

# API available at http://localhost:8000
# Flower dashboard at http://localhost:5555
# Prisma Studio: make db-studio
```

### 3. Local Development (Without Docker)

```bash
# Install all dependencies (production + dev)
make install-dev

# Generate Prisma client
make db-generate

# Push schema to database
make db-push

# Start dev server
make dev

# In a separate terminal — start Celery worker
make dev-worker
```

---

## 🔌 API Endpoints

### Authentication
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/auth/register` | Register new user |
| POST | `/api/v1/auth/login` | Login, get tokens |
| POST | `/api/v1/auth/refresh` | Refresh access token |
| GET | `/api/v1/auth/profile` | Get current user |
| PUT | `/api/v1/auth/profile` | Update profile |
| PUT | `/api/v1/auth/password` | Change password |

### Papers
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/papers/upload` | Upload PDF |
| GET | `/api/v1/papers` | List papers (paginated) |
| GET | `/api/v1/papers/{id}` | Get paper details |
| PUT | `/api/v1/papers/{id}` | Update paper |
| DELETE | `/api/v1/papers/{id}` | Delete paper |
| POST | `/api/v1/papers/search` | Semantic search |
| GET | `/api/v1/papers/{id}/citations` | Generate citations |
| GET | `/api/v1/papers/{id}/related` | Find related papers |

### Chat (RAG)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/chat/ask` | Ask question about a paper |
| POST | `/api/v1/chat/multi-paper` | Ask across multiple papers |
| GET | `/api/v1/chat/sessions` | List chat sessions |
| GET | `/api/v1/chat/sessions/{id}/history` | Get session history |
| DELETE | `/api/v1/chat/sessions/{id}` | Delete session |

### Research
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/research/summarize/{id}` | Summarize paper |
| POST | `/api/v1/research/insights/{id}` | Extract insights |
| POST | `/api/v1/research/cluster` | Run topic clustering |
| GET | `/api/v1/research/clusters` | List clusters |

### Notes
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/notes` | Create note |
| GET | `/api/v1/notes` | List notes |
| GET | `/api/v1/notes/{id}` | Get note |
| PUT | `/api/v1/notes/{id}` | Update note |
| DELETE | `/api/v1/notes/{id}` | Delete note |
| POST | `/api/v1/notes/generate/{paper_id}` | AI-generate note |

### Collections
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/collections` | Create collection |
| GET | `/api/v1/collections` | List collections |
| POST | `/api/v1/collections/{id}/papers` | Add paper |
| DELETE | `/api/v1/collections/{id}/papers/{pid}` | Remove paper |
| POST | `/api/v1/reading-list` | Add to reading list |
| GET | `/api/v1/reading-list` | Get reading list |

### Advanced
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/advanced/compare` | Compare papers |
| POST | `/api/v1/advanced/literature-review` | Auto literature review |
| GET | `/api/v1/advanced/timeline` | Research timeline |
| GET | `/api/v1/advanced/citation-graph/{id}` | Citation graph |
| GET | `/api/v1/advanced/recommendations` | Personalized recommendations |
| GET | `/api/v1/advanced/dashboard` | Research dashboard |

### Health
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/health` | Liveness check |
| GET | `/api/v1/health/ready` | Readiness probe |

---

## 🧪 Testing

```bash
# Run all tests
make test

# With coverage report
make test-cov

# Only unit tests
make test-unit

# Only API tests
make test-api
```

---

## 🐳 Docker Services

| Service | Port | Description |
|---------|------|-------------|
| `backend` | 8000 | FastAPI application |
| `postgres` | 5432 | PostgreSQL 16 + pgvector |
| `redis` | 6379 | Cache & Celery broker |
| `celery_worker` | — | Background task processor |
| `celery_beat` | — | Periodic task scheduler |
| `flower` | 5555 | Celery monitoring dashboard |

---

## ☁️ GCP Deployment

```bash
# Build & push image
make gcp-build

# Deploy to Cloud Run
make gcp-deploy
```

For production, configure:
- **Cloud SQL** (PostgreSQL + pgvector)
- **Memorystore** (Redis)
- **Cloud Storage** (PDF uploads)
- **Secret Manager** (credentials)
- **Cloud Run** or **GKE** (compute)

---

## 🔒 Security

- JWT-based authentication with access + refresh tokens
- bcrypt password hashing (12 rounds)
- Rate limiting via slowapi + Redis
- Security headers (CSP, HSTS, X-Frame-Options, etc.)
- Input sanitization & validation (Pydantic v2)
- CORS with configurable origins

---

## 📊 Monitoring

- **Prometheus** metrics endpoint at `/metrics`
- **Sentry** error tracking (configure `SENTRY_DSN`)
- **Structured logging** via `structlog`
- **Flower** dashboard for Celery task monitoring

---

## 🔧 Useful Commands

```bash
make help          # Show all available commands
make env-check     # Verify local environment
make docker-up     # Start everything
make docker-logs   # Stream all logs
make db-studio     # Open Prisma Studio (GUI)
make lint          # Run linter
make format        # Format code
make clean         # Clean generated files
```

---

## 📄 License

Private — All rights reserved.
