from __future__ import annotations

from adobe_influencer.core.config import AppSettings
from adobe_influencer.core.logging import configure_logging, get_logger
from adobe_influencer.core.models import AudienceInsight, CreatorSeed
from adobe_influencer.ingestion.adapters import AnalyticsImportDirectory, ApifyAdapter, CsvAnalyticsImporter, MockSeedAdapter, UnifiedLiveAdapter, YouTubeAPIAdapter
from adobe_influencer.ingestion.seeds import build_creator_seeds_from_urls, load_creator_seeds, save_creator_seeds
from adobe_influencer.nlp.pipeline import build_quality_scorecard, classify_comments, detect_product_signals, detect_themes
from adobe_influencer.reporting.exporters import export_json, export_markdown
from adobe_influencer.scoring.engine import PersonaAnalyzer, RecommendationScorer
from adobe_influencer.storage.analytics import AnalyticsStore
from adobe_influencer.storage.database import DatabaseManager
from adobe_influencer.storage.repositories import Repository
from adobe_influencer.storage.vector_store import VectorStore
from adobe_influencer.transcription.service import MockTranscriptAdapter

logger = get_logger(__name__)


class PipelineRunner:
    def __init__(self, settings: AppSettings | None = None) -> None:
        self.settings = settings or AppSettings()
        self.settings.ensure_paths()
        configure_logging(self.settings.log_level)
        self.db = DatabaseManager(self.settings.database_url)
        self.db.create_all()
        self.repo = Repository(self.db)
        self.analytics_store = AnalyticsStore(self.settings.duckdb_path)
        self.vector_store = VectorStore(str(self.settings.vector_store_path), self.settings.chroma_collection)

    def close(self) -> None:
        """Close all database connections to prevent lock issues"""
        if hasattr(self, 'analytics_store') and self.analytics_store:
            self.analytics_store.connection.close()
        if hasattr(self, 'db') and self.db:
            self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def run(self, creator_urls: list[str] | None = None, creator_seeds: list[CreatorSeed] | None = None) -> list:
        seeds, adapter, transcripts, analytics_rows = self._prepare_sources(creator_urls=creator_urls, creator_seeds=creator_seeds)
        creators, content, comments = adapter.ingest(seeds)
        self.repo.upsert_creators(creators)
        self.repo.upsert_content(content)
        self.repo.upsert_comments(comments)
        
        # Media pipeline: Download videos and transcribe if enabled
        if self.settings.enable_media_pipeline:
            logger.info("Media pipeline enabled - downloading and transcribing videos...")
            try:
                from adobe_influencer.transcription.media_pipeline import MediaPipeline
                
                media_pipeline = MediaPipeline(
                    download_dir=self.settings.media_download_dir,
                    audio_dir=self.settings.media_audio_dir,
                    transcript_dir=self.settings.media_transcript_dir,
                    whisper_model=self.settings.whisper_model,
                    max_videos_per_creator=self.settings.max_videos_per_creator,
                    skip_existing=True
                )
                
                # Group content by creator
                content_by_creator = {}
                for item in content:
                    if item.creator_id not in content_by_creator:
                        content_by_creator[item.creator_id] = []
                    content_by_creator[item.creator_id].append(item)
                
                # Process media for all creators
                media_transcripts_by_creator = media_pipeline.process_batch(creators, content_by_creator)
                
                # Combine with existing transcripts
                all_media_transcripts = []
                for creator_transcripts in media_transcripts_by_creator.values():
                    all_media_transcripts.extend(creator_transcripts)
                
                if all_media_transcripts:
                    logger.info(f"Media pipeline generated {len(all_media_transcripts)} transcript segments")
                    transcripts.extend(all_media_transcripts)
                
                # Show statistics
                stats = media_pipeline.get_statistics()
                logger.info(
                    f"Media pipeline stats: {stats['videos_downloaded']} videos, "
                    f"{stats['audio_extracted']} audio, {stats['transcripts_created']} transcripts"
                )
                
            except Exception as e:
                logger.error(f"Media pipeline failed: {e}")
                logger.warning("Continuing pipeline without media transcripts")
        
        self.repo.upsert_transcripts(transcripts)

        quality = build_quality_scorecard(creators, content, analytics_rows)
        themes = detect_themes(creators, content, transcripts)
        audience = classify_comments(comments)
        for creator in creators:
            audience.setdefault(
                creator.creator_id,
                AudienceInsight(
                    creator_id=creator.creator_id,
                    sentiment_summary="No audience comments were retrieved in this run.",
                    sentiment_distribution={"positive": 0, "neutral": 0, "negative": 0},
                    intents={
                        "question": 0,
                        "tutorial_request": 0,
                        "tool_comparison": 0,
                        "workflow_pain_point": 0,
                        "unmet_need": 0,
                    },
                    recurring_questions=[],
                ),
            )
        product = detect_product_signals(creators, content, comments, transcripts)
        personas = PersonaAnalyzer().analyze({creator.creator_id: creator.audience_persona for creator in creators})
        scorer = RecommendationScorer(self.settings.configs_dir / "scoring_weights.yaml")
        recommendations = scorer.score(
            creator_lookup={creator.creator_id: {"display_name": creator.display_name, "handle": creator.handle} for creator in creators},
            quality=quality,
            themes=themes,
            audience=audience,
            product=product,
            personas=personas,
        )
        self.repo.replace_recommendations(recommendations)
        self.analytics_store.persist_recommendations(recommendations)
        self._index_evidence(recommendations)
        self._write_outputs(recommendations)
        logger.info("Pipeline complete with %s ranked creators", len(recommendations))
        return recommendations

    def _prepare_sources(self, creator_urls: list[str] | None = None, creator_seeds: list[CreatorSeed] | None = None):
        requested_live_seeds = creator_seeds or build_creator_seeds_from_urls(creator_urls or [])

        if requested_live_seeds:
            seeds = requested_live_seeds
            save_creator_seeds(self.settings.imports_dir / "live_creator_seeds.json", seeds)
            return seeds, self._build_live_adapter(), [], AnalyticsImportDirectory(self.settings.imports_dir).load()

        if self.settings.use_mock_data:
            seeds = load_creator_seeds(self.settings.sample_dir / "creator_seeds.json")
            adapter = MockSeedAdapter(self.settings.sample_dir, self.settings.raw_lake_dir)
            _, content, _ = adapter.ingest(seeds)
            transcripts = MockTranscriptAdapter(self.settings.sample_dir).transcribe(content)
            analytics_rows = CsvAnalyticsImporter(self.settings.sample_dir / "analytics_import.csv").load()
            adapter = MockSeedAdapter(self.settings.sample_dir, self.settings.raw_lake_dir)
            return seeds, adapter, transcripts, analytics_rows

        live_seed_path = self.settings.imports_dir / "live_creator_seeds.json"
        seeds = load_creator_seeds(live_seed_path)
        adapter = self._build_live_adapter()
        transcripts = []
        analytics_rows = AnalyticsImportDirectory(self.settings.imports_dir).load()
        return seeds, adapter, transcripts, analytics_rows

    def _build_live_adapter(self) -> UnifiedLiveAdapter:
        instagram_adapter = None
        youtube_adapter = None

        if self.settings.apify_token:
            instagram_adapter = ApifyAdapter(
                token=self.settings.apify_token,
                raw_lake_dir=self.settings.raw_lake_dir,
                apify_scraped_dir=self.settings.apify_scraped_dir,
                instagram_scraper_actor=self.settings.instagram_scraper_actor,
                instagram_post_actor=self.settings.instagram_post_actor,
                instagram_comment_actor=self.settings.instagram_comment_actor,
                instagram_profile_actor=self.settings.instagram_profile_actor,
                instagram_hashtag_actor=self.settings.instagram_hashtag_actor,
                instagram_reel_actor=self.settings.instagram_reel_actor,
                instagram_api_actor=self.settings.instagram_api_actor,
                instagram_profile_api_actor=self.settings.instagram_profile_api_actor,
                posts_limit=self.settings.instagram_posts_limit,
                comments_per_post=self.settings.instagram_comments_per_post,
                hashtags_limit=self.settings.instagram_hashtags_limit,
            )
        else:
            logger.warning("APIFY_TOKEN not configured. Instagram live ingestion is disabled.")

        if self.settings.youtube_api_key:
            youtube_adapter = YouTubeAPIAdapter(
                api_key=self.settings.youtube_api_key,
                raw_lake_dir=self.settings.raw_lake_dir,
                videos_per_channel=self.settings.max_videos_per_creator,
                comments_per_video=self.settings.instagram_comments_per_post,
            )
        else:
            logger.warning("YOUTUBE_API_KEY not configured. YouTube live ingestion is disabled.")

        if not instagram_adapter and not youtube_adapter:
            raise ValueError("No live ingestion providers are configured. Set APIFY_TOKEN and/or YOUTUBE_API_KEY.")

        return UnifiedLiveAdapter(instagram_adapter=instagram_adapter, youtube_adapter=youtube_adapter)

    def _index_evidence(self, recommendations: list) -> None:
        ids: list[str] = []
        documents: list[str] = []
        metadatas: list[dict] = []
        for recommendation in recommendations:
            for idx, snippet in enumerate(recommendation.evidence_snippets):
                ids.append(f"{recommendation.creator_id}-{idx}")
                documents.append(snippet)
                metadatas.append({
                    "creator_id": recommendation.creator_id,
                    "creator_name": recommendation.creator_name,
                    "handle": recommendation.handle,
                })
        self.vector_store.upsert(ids=ids, documents=documents, metadatas=metadatas)

    def _write_outputs(self, recommendations: list) -> None:
        output_dir = self.settings.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        export_json(recommendations, output_dir / "recommendations.json")
        export_markdown(recommendations, output_dir / "recommendations.md")


def run_pipeline() -> list:
    return PipelineRunner().run()
