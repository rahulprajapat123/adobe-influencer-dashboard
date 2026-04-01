# Adobe Influencer Intelligence System

Adobe Influencer Intelligence System is a production-oriented MVP that turns raw public creator content into ranked partnership recommendations for Adobe Acrobat and Adobe Creative Cloud. The repo is designed as a modular monorepo with pluggable ingestion adapters, a typed Python service layer, a FastAPI API, a Streamlit dashboard, relational and analytical storage, semantic search, demo fixtures, Docker support, and unit tests.

## What the MVP does

Input sources:
- Influencer handles
- Profile URLs
- YouTube channel URLs
- Website URLs
- Optional CSV exports from tools such as HypeAuditor, Modash, SocialBlade, SparkToro, or Not Just Analytics

Output per creator:
- Overall brand-fit score
- Adobe Acrobat fit score
- Adobe Creative Cloud fit score
- Audience sentiment summary
- Recurring audience questions
- Content theme map
- Evidence snippets from comments, captions, and transcripts
- Risk flags
- Recommended campaign angle

The default local demo uses three mock creators so the entire workflow runs without API keys. In live mode, the pipeline now runs the full configured Apify Instagram actor set and stores each raw actor payload under `data/apify_scraped data/<creator_id>/`.

## Architecture

Monorepo layout:
- `apps/api`: FastAPI service exposing pipeline, creator, and search endpoints
- `apps/dashboard`: Streamlit dashboard for ranked creators and creator detail views
- `services/common/adobe_influencer/core`: configuration, logging, shared models, and text helpers
- `services/common/adobe_influencer/ingestion`: source adapters, seed loading, and external CSV import hooks
- `services/common/adobe_influencer/transcription`: transcription interfaces and mock faster-whisper hook
- `services/common/adobe_influencer/nlp`: corpus cleaning, theme detection, comment intent analysis, and Adobe signal detection
- `services/common/adobe_influencer/scoring`: audience overlap framework and weighted recommendation engine
- `services/common/adobe_influencer/storage`: PostgreSQL/SQLite persistence, DuckDB analytics, and ChromaDB semantic retrieval
- `services/common/adobe_influencer/reporting`: JSON and Markdown export helpers
- `data/sample`: local demo fixture set for 3 creators
- `configs`: pipeline and scoring configuration
- `tests`: unit tests for scoring and NLP wrappers

Data flow:
1. Source discovery and ingestion normalize creators, content, comments, and raw payloads.
2. Media processing links transcript segments to content records.
3. Quality analysis computes engagement, comment-to-like ratio, posting consistency, and growth placeholders.
4. NLP normalizes corpus text, maps themes, classifies audience intent, and surfaces product/workflow signals.
5. Scoring combines engagement, theme relevance, sentiment, Adobe fit, uniqueness, and risk into final rankings.
6. Reporting persists structured results to SQL, DuckDB, ChromaDB, JSON, Markdown, API, and dashboard views.

## Storage model

Primary stores:
- PostgreSQL for production relational storage via SQLAlchemy
- SQLite fallback for minimal-friction local runs
- DuckDB for lightweight analytics tables
- ChromaDB for local semantic evidence retrieval

Key logical entities:
- `creators`
- `content`
- `comments`
- `transcripts`
- `creator_scores`

## Tech stack

- Python 3.11+
- FastAPI
- Streamlit
- SQLAlchemy
- PostgreSQL or SQLite fallback
- DuckDB
- ChromaDB
- spaCy, BERTopic, KeyBERT, transformers, VADER, faster-whisper, FFmpeg hooks
- Docker and docker-compose
- `.env` configuration

## Setup

### 1. Install dependencies

```powershell
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

### 2. Run the end-to-end sample workflow

```powershell
$env:PYTHONPATH='services/common'
python run_workflow.py
```

This will:
1. Ingest the 3 sample creators
2. Load transcript segments
3. Run NLP and scoring
4. Persist results to SQLite, DuckDB, and ChromaDB
5. Export reports to `data/outputs/recommendations.json` and `data/outputs/recommendations.md`

### 3. Launch the API

```powershell
$env:PYTHONPATH='services/common'
python serve_api.py
```

Key endpoints:
- `GET /health`
- `POST /pipeline/run`
- `GET /creators/recommendations`
- `GET /creators/{creator_id}`
- `GET /search?query=pdf`

### 4. Launch the dashboard

```powershell
$env:PYTHONPATH='services/common'
python serve_dashboard.py
```

### 5. Run tests

```powershell
$env:PYTHONPATH='services/common'
pytest -q
```

## Docker

Start PostgreSQL, API, and dashboard locally:

```powershell
docker-compose up --build
```

Service URLs:
- API: `http://localhost:8000`
- Dashboard: `http://localhost:8501`
- PostgreSQL: `localhost:5432`

The containers use PostgreSQL. The non-container local workflow defaults to SQLite for easier setup.

## GCP deployment

For Google Cloud Run, deploy the dashboard and API as separate services. The repo includes:
- `Dockerfile` for the Streamlit dashboard
- `Dockerfile.api` for the FastAPI service
- `cloudbuild.dashboard.yaml` and `cloudbuild.api.yaml` for Cloud Build triggers

Use `DEPLOY_GCP.md` for the production deployment checklist, Cloud SQL setup expectations, and environment variables.

## Environment variables

Defined in `.env.example`:
- `DATABASE_URL`: SQLAlchemy connection string
- `DUCKDB_PATH`: DuckDB file location
- `VECTOR_STORE_PATH`: Chroma persistence directory
- `USE_MOCK_DATA`: toggle mock-first demo mode
- `LOG_LEVEL`: logging verbosity
- `YOUTUBE_API_KEY`: optional YouTube Data API credential
- `APIFY_TOKEN`: optional Apify credential for live Instagram ingestion
- `APIFY_SCRAPED_DIR`: folder where raw Apify actor outputs are stored
- `INSTAGRAM_SCRAPER_ACTOR`, `INSTAGRAM_POST_ACTOR`, `INSTAGRAM_COMMENT_ACTOR`, `INSTAGRAM_PROFILE_ACTOR`, `INSTAGRAM_HASHTAG_ACTOR`, `INSTAGRAM_REEL_ACTOR`, `INSTAGRAM_API_ACTOR`, `INSTAGRAM_PROFILE_API_ACTOR`: Apify actor overrides for live mode
- `INSTAGRAM_POSTS_LIMIT`, `INSTAGRAM_COMMENTS_PER_POST`, `INSTAGRAM_HASHTAGS_LIMIT`: live ingestion limits
- `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`: database settings for Docker or production

## How to add new creators

1. Add creator seeds to `data/sample/creator_seeds.json` for a local demo, or update `data/imports/live_creator_seeds.json` for live Apify ingestion.
2. Live runs will fetch profile, post, comment, reel, hashtag, and API/profile datasets through the configured Apify actors and write the raw payloads to `data/apify_scraped data/`.
3. If video/audio is available, populate transcripts through the transcription adapter.
4. Re-run `python run_workflow.py`.
5. Review ranked output in the API, dashboard, or exported report files.

## How to import external analytics CSVs

Built-in CSV/manual import hooks exist for:
- Modash
- SparkToro
- SocialBlade
- HypeAuditor

Current demo path:
- Put CSV exports in `data/sample/`
- Update `analytics_import.csv` or implement source-specific parsing using `services/common/adobe_influencer/ingestion/external_imports.py`
- Re-run the workflow

## Scoring configuration

Weights are stored in `configs/scoring_weights.yaml` and can be tuned without code changes. The engine combines:
- Engagement quality
- Topic relevance
- Audience sentiment
- Adobe product fit
- Audience uniqueness
- Risk modifier

## Mock data and fixtures

The repo includes 3 demo creators representing:
- Brand design and freelance packaging workflows
- Video editing and review workflows
- Consulting documentation and approval workflows

These fixtures include captions, comments, transcripts, and growth placeholders so the pipeline can run with no paid connectors.

## Limitations

- Live Apify ingestion is implemented with configurable actor calls, but successful execution still depends on valid Apify credentials, actor availability, and actor-specific payload compatibility.
- The MVP uses deterministic local fallbacks for semantic embeddings and lightweight rule-based NLP so the demo works without model downloads.
- Audience overlap is a framework plus CSV/manual-import pathway; it is not connected to live Modash or SparkToro APIs.
- The local pipeline defaults to SQLite. Docker uses PostgreSQL for a closer production topology.
- Growth trend and profile quality imports are placeholders unless external analytics CSVs are provided.

## Suggested next production steps

- Replace mock ingestion adapters with authenticated source-specific clients
- Add job orchestration and scheduled backfills
- Swap local deterministic embedding with a production embedding service or approved offline model
- Add richer classifier wrappers using spaCy pipelines or transformers served behind a model abstraction layer
- Add authentication and role-based access control around the API and dashboard


