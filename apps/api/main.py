from __future__ import annotations

from functools import lru_cache

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from adobe_influencer.core.config import AppSettings
from adobe_influencer.pipelines.runner import PipelineRunner
from adobe_influencer.storage.database import DatabaseManager
from adobe_influencer.storage.repositories import Repository
from adobe_influencer.storage.vector_store import VectorStore


@lru_cache
def get_settings() -> AppSettings:
    settings = AppSettings()
    settings.ensure_paths()
    return settings


@lru_cache
def get_repo() -> Repository:
    settings = get_settings()
    db = DatabaseManager(settings.database_url)
    db.create_all()
    return Repository(db)


@lru_cache
def get_vector_store() -> VectorStore:
    settings = get_settings()
    return VectorStore(str(settings.vector_store_path), settings.chroma_collection)


app = FastAPI(title="Adobe Influencer Intelligence API", version="0.1.0")
cors_origins = get_settings().cors_origins or ["*"]
allow_all_origins = "*" in cors_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=not allow_all_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


class PipelineRunRequest(BaseModel):
    creator_urls: list[str] = Field(default_factory=list)
    use_mock_data: bool | None = None
    enable_media_pipeline: bool | None = None
    max_videos_per_creator: int | None = None


class PipelineRunResponse(BaseModel):
    count: int
    top_creator: str | None = None
    creator_ids: list[str] = Field(default_factory=list)


@app.get("/")
def root() -> dict[str, object]:
    return {
        "name": "Adobe Influencer Intelligence API",
        "version": "0.1.0",
        "status": "running",
        "endpoints": {
            "health": "/health",
            "docs": "/docs",
            "redoc": "/redoc",
            "pipeline_run": "/pipeline/run",
            "recommendations": "/creators/recommendations",
            "creator_detail": "/creators/{creator_id}",
            "search": "/search"
        },
        "message": "API is running. Use /docs for interactive documentation or access the Streamlit dashboard for the UI."
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/pipeline/run", response_model=PipelineRunResponse)
def run_pipeline(request: PipelineRunRequest | None = None) -> PipelineRunResponse:
    request = request or PipelineRunRequest()
    settings = get_settings().model_copy(deep=True)
    if request.use_mock_data is not None:
        settings.use_mock_data = request.use_mock_data
    if request.enable_media_pipeline is not None:
        settings.enable_media_pipeline = request.enable_media_pipeline
    if request.max_videos_per_creator is not None:
        settings.max_videos_per_creator = request.max_videos_per_creator
    with PipelineRunner(settings) as runner:
        results = runner.run(creator_urls=request.creator_urls)
    return PipelineRunResponse(
        count=len(results),
        top_creator=results[0].creator_name if results else None,
        creator_ids=[item.creator_id for item in results],
    )


@app.get("/creators/recommendations")
def list_recommendations() -> list[dict]:
    return [item.model_dump() for item in get_repo().list_recommendations()]


@app.get("/creators/{creator_id}")
def get_creator_detail(creator_id: str) -> dict[str, object]:
    bundle = get_repo().get_creator_bundle(creator_id)
    if not bundle["creator"]:
        raise HTTPException(status_code=404, detail="Creator not found")
    creator = bundle["creator"]
    recommendation = bundle["recommendation"]
    return {
        "creator": {
            "creator_id": creator.creator_id,
            "handle": creator.handle,
            "display_name": creator.display_name,
            "niche": creator.niche,
            "bio": creator.bio,
            "audience_persona": creator.audience_persona,
        },
        "content": [
            {
                "content_id": item.content_id,
                "platform": item.platform,
                "title": item.title,
                "caption": item.caption,
                "source_url": item.source_url,
            }
            for item in bundle["content"]
        ],
        "comments": [{"text": item.text, "author_name": item.author_name} for item in bundle["comments"]],
        "transcripts": [{"text": item.text, "start_seconds": item.start_seconds, "end_seconds": item.end_seconds} for item in bundle["transcripts"]],
        "recommendation": {
            "overall_brand_fit": recommendation.overall_brand_fit,
            "acrobat_fit": recommendation.acrobat_fit,
            "creative_cloud_fit": recommendation.creative_cloud_fit,
            "audience_sentiment_summary": recommendation.audience_sentiment_summary,
            "recurring_audience_questions": recommendation.recurring_audience_questions,
            "content_theme_map": recommendation.content_theme_map,
            "evidence_snippets": recommendation.evidence_snippets,
            "risk_flags": recommendation.risk_flags,
            "recommended_campaign_angle": recommendation.recommended_campaign_angle,
            "score_breakdown": recommendation.score_breakdown,
        }
        if recommendation
        else None,
    }


@app.get("/search")
def search(query: str, limit: int = 5) -> dict[str, object]:
    return {
        "exact": get_repo().exact_search(query, limit=limit),
        "semantic": get_vector_store().semantic_search(query, limit=limit),
    }
