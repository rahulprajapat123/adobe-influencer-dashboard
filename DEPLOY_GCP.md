# GCP Deployment

This project is ready for Google Cloud Run as two services:

- `dashboard`: Streamlit frontend using the root `Dockerfile`
- `api`: FastAPI backend using `Dockerfile.api`

Do not try to expose both apps from one Cloud Run container. Cloud Run expects one public ingress port per service, and this repo has two independent web entrypoints.

## Recommended Architecture

- Cloud Run service 1: dashboard
- Cloud Run service 2: api
- Cloud SQL for PostgreSQL: primary relational database
- Cloud Storage mount at `/mnt/data`: persistent folder for outputs, raw payloads, imports, and media

## Project Values

- Project name: `My First Project`
- Project number: `494635809653`
- Project ID: `project-ce75d2f4-bdb3-4abe-a10`
- Region: `asia-south1`
- Artifact Registry base: `asia-south1-docker.pkg.dev/project-ce75d2f4-bdb3-4abe-a10/app-images`

## Recommended Naming

- Cloud Run dashboard service: `adobe-dashboard`
- Cloud Run API service: `adobe-api`
- Cloud SQL PostgreSQL instance: `adobe-influencer-pg`
- Database name: `adobe_influencer`
- Database user: `adobe`

## Why this setup

- No service depends on `localhost`
- Both services bind to the Cloud Run `PORT` environment variable automatically
- The API supports explicit CORS origins through `CORS_ALLOWED_ORIGINS`
- The database can use either:
  - `DATABASE_URL`
  - `CLOUDSQL_INSTANCE_CONNECTION_NAME` with `POSTGRES_*` variables

## Required Environment Variables

Reference templates:

- `configs/gcp_dashboard.env.example`
- `configs/gcp_api.env.example`

Use these on both Cloud Run services unless noted otherwise:

```env
ENVIRONMENT=production
USE_MOCK_DATA=false
DATA_DIR=/mnt/data
IMPORTS_DIR=/mnt/data/imports
OUTPUT_DIR=/mnt/data/outputs
RAW_LAKE_DIR=/mnt/data/raw_lake
APIFY_SCRAPED_DIR=/mnt/data/apify_scraped data
MEDIA_DOWNLOAD_DIR=/mnt/data/media/downloads
MEDIA_AUDIO_DIR=/mnt/data/media/audio
MEDIA_TRANSCRIPT_DIR=/mnt/data/media/transcripts
DUCKDB_PATH=/tmp/analytics.duckdb
VECTOR_STORE_PATH=/tmp/chroma
POSTGRES_DB=adobe_influencer
POSTGRES_USER=adobe
POSTGRES_PASSWORD=your-password
CLOUDSQL_INSTANCE_CONNECTION_NAME=project-ce75d2f4-bdb3-4abe-a10:asia-south1:adobe-influencer-pg
```

Set this only on the API service:

```env
CORS_ALLOWED_ORIGINS=https://your-dashboard-service-url
```

If you prefer a single explicit database DSN instead of Cloud SQL socket settings, set:

```env
DATABASE_URL=postgresql+psycopg2://USER:PASSWORD@/DB_NAME?host=/cloudsql/project-ce75d2f4-bdb3-4abe-a10:asia-south1:adobe-influencer-pg
```

## Build Images in GCP

Create two Cloud Build triggers in the Google Cloud console:

1. Dashboard trigger
   - Config file: `cloudbuild.dashboard.yaml`
   - Substitution `_IMAGE`:
     `asia-south1-docker.pkg.dev/project-ce75d2f4-bdb3-4abe-a10/app-images/adobe-dashboard:latest`
2. API trigger
   - Config file: `cloudbuild.api.yaml`
   - Substitution `_IMAGE`:
     `asia-south1-docker.pkg.dev/project-ce75d2f4-bdb3-4abe-a10/app-images/adobe-api:latest`

You can also run the same builds manually with Cloud Build or `gcloud builds submit`.

## Deploy the Dashboard Service

In Cloud Run console:

1. Create a new service named `adobe-dashboard`
2. Select the dashboard image from Artifact Registry
3. Set the container port to `8080`
4. Add the environment variables listed above
5. If using Cloud SQL, add the instance connection on the service
6. If using Cloud Storage persistence, mount the bucket at `/mnt/data`
7. Keep unauthenticated access enabled if this is a public UI
8. Deploy

## Deploy the API Service

In Cloud Run console:

1. Create a new service named `adobe-api`
2. Select the API image from Artifact Registry
3. Set the container port to `8080`
4. Add the shared environment variables
5. Add `CORS_ALLOWED_ORIGINS=https://YOUR_DASHBOARD_URL`
6. Add the same Cloud SQL connection used by the dashboard
7. Mount the same Cloud Storage bucket at `/mnt/data` if you need persistent outputs, media, imports, or raw payloads
8. Decide whether this service should allow unauthenticated access
9. Deploy

## Cloud SQL Setup

Create a new PostgreSQL Cloud SQL instance in `asia-south1` with:

- Instance ID: `adobe-influencer-pg`
- Database version: PostgreSQL 16
- Database: `adobe_influencer`
- User: `adobe`

After creation, use its instance connection name:

`project-ce75d2f4-bdb3-4abe-a10:asia-south1:adobe-influencer-pg`

## Storage Mount Guidance

Use the mounted bucket at `/mnt/data` for:

- outputs
- media files
- raw payload archives
- import files

Do not rely on the mounted bucket for SQLite, DuckDB, or Chroma durability/concurrency. Keep:

- `DATABASE_URL` on Cloud SQL
- `DUCKDB_PATH` on `/tmp`
- `VECTOR_STORE_PATH` on `/tmp`

## Important Notes

- Cloud Run filesystem is ephemeral. Without a mounted bucket, local files under `data/` will not persist across revisions or instance restarts.
- Cloud SQL is the correct production database target. Do not point `DATABASE_URL` at `localhost`.
- Google documents that Cloud Storage FUSE on Cloud Run is not fully POSIX-compliant and does not provide file locking for concurrent writes. That is why this guide keeps Cloud SQL as the database and moves DuckDB/Chroma to `/tmp`. Source: https://cloud.google.com/run/docs/configuring/services/cloud-storage-volume-mounts
- The dashboard does not need to call the API to function, but if you want browser-based API access from the dashboard domain, keep `CORS_ALLOWED_ORIGINS` restricted to the dashboard URL.
- If media transcription is enabled in production, the container already includes `ffmpeg`.
