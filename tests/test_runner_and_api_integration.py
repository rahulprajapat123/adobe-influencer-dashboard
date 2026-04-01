from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adobe_influencer.core.config import AppSettings
from adobe_influencer.core.models import CommentRecord, ContentRecord, ContentType, CreatorProfile, SourcePlatform
from adobe_influencer.pipelines.runner import PipelineRunner
from apps.api import main as api_main

TEST_ROOT = ROOT / "data" / "test_tmp"
pytestmark = pytest.mark.integration


class FakeLiveAdapter:
    def ingest(self, seeds):
        published_at = datetime(2026, 3, 31, tzinfo=UTC)
        creators = [
            CreatorProfile(
                creator_id=seeds[0].creator_id,
                handle=seeds[0].handle,
                display_name=seeds[0].display_name,
                primary_platform=SourcePlatform.instagram,
                profile_url=str(seeds[0].profile_url),
                youtube_channel_url=str(seeds[0].youtube_channel_url) if seeds[0].youtube_channel_url else None,
                niche="Design education",
                bio="Photoshop, Illustrator, Acrobat and client review workflows.",
                followers=120000,
                avg_likes=5000,
                avg_comments=220,
                posts_last_30_days=6,
                audience_persona=["designers", "creatives"],
            )
        ]
        content = [
            ContentRecord(
                content_id="ig_demo_content",
                creator_id=seeds[0].creator_id,
                platform=SourcePlatform.instagram,
                content_type=ContentType.short_video,
                source_url="https://www.instagram.com/reel/ABC123/",
                title="Photoshop reel",
                caption="Photoshop and Acrobat client review workflow",
                published_at=published_at,
                likes=10000,
                comments_count=400,
                views=180000,
                raw_payload_path="raw_demo.json",
            )
        ]
        comments = [
            CommentRecord(
                comment_id="comment_1",
                content_id="ig_demo_content",
                creator_id=seeds[0].creator_id,
                author_name="viewer",
                text="Can you show the Acrobat export and review setup?",
                likes=20,
                published_at=published_at,
                source_url="https://www.youtube.com/watch?v=ZZZZZZZZZZZ",
            )
        ]
        return creators, content, comments


def build_test_settings(base_dir: Path) -> AppSettings:
    settings = AppSettings()
    settings.data_dir = base_dir / "data"
    settings.configs_dir = ROOT / "configs"
    settings.sample_dir = ROOT / "data" / "sample"
    settings.imports_dir = base_dir / "imports"
    settings.raw_lake_dir = base_dir / "raw_lake"
    settings.apify_scraped_dir = base_dir / "apify_scraped"
    settings.output_dir = base_dir / "outputs"
    settings.media_download_dir = base_dir / "media" / "downloads"
    settings.media_audio_dir = base_dir / "media" / "audio"
    settings.media_transcript_dir = base_dir / "media" / "transcripts"
    settings.database_url = f"sqlite:///{(base_dir / 'app.db').as_posix()}"
    settings.duckdb_path = base_dir / "analytics.duckdb"
    settings.vector_store_path = base_dir / "chroma"
    settings.use_mock_data = False
    settings.enable_media_pipeline = False
    settings.ensure_paths()
    return settings


def make_base_dir(test_name: str) -> Path:
    base_dir = TEST_ROOT / f"{test_name}_{uuid4().hex}"
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir


def test_pipeline_runner_accepts_creator_urls_and_writes_outputs(monkeypatch) -> None:
    settings = build_test_settings(make_base_dir("runner"))
    runner = PipelineRunner(settings)
    monkeypatch.setattr(runner, "_build_live_adapter", lambda: FakeLiveAdapter())

    results = runner.run(creator_urls=["https://www.instagram.com/designcourse/"])

    assert len(results) == 1
    assert results[0].overall_brand_fit > 0
    assert any("source: https://www.instagram.com/reel/ABC123/" in snippet for snippet in results[0].evidence_snippets)
    assert all("ZZZZZZZZZZZ" not in snippet for snippet in results[0].evidence_snippets)
    assert (settings.output_dir / "recommendations.json").exists()
    live_seed_path = settings.imports_dir / "live_creator_seeds.json"
    assert live_seed_path.exists()
    assert "designcourse" in live_seed_path.read_text(encoding="utf-8")


def test_pipeline_run_api_accepts_creator_urls(monkeypatch) -> None:
    settings = build_test_settings(make_base_dir("api"))

    api_main.get_settings.cache_clear()
    api_main.get_repo.cache_clear()
    api_main.get_vector_store.cache_clear()
    monkeypatch.setattr(api_main, "get_settings", lambda: settings)

    original_run = PipelineRunner.run

    def fake_run(self, creator_urls=None, creator_seeds=None):
        assert creator_urls == ["https://www.instagram.com/designcourse/"]
        return original_run(self, creator_urls=creator_urls, creator_seeds=creator_seeds)

    monkeypatch.setattr(PipelineRunner, "_build_live_adapter", lambda self: FakeLiveAdapter())
    monkeypatch.setattr(PipelineRunner, "run", fake_run)

    client = TestClient(api_main.app)
    response = client.post(
        "/pipeline/run",
        json={
            "creator_urls": ["https://www.instagram.com/designcourse/"],
            "use_mock_data": False,
            "enable_media_pipeline": False,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["creator_ids"] == ["creator_designcourse"]
