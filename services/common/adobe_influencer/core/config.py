from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[4]


class AppSettings(BaseSettings):
    app_name: str = Field(default="Adobe Influencer Intelligence System", alias="APP_NAME")
    environment: str = Field(default="local", alias="ENVIRONMENT")
    data_dir: Path = Field(default=ROOT_DIR / "data", alias="DATA_DIR")
    configs_dir: Path = Field(default=ROOT_DIR / "configs", alias="CONFIGS_DIR")
    sample_dir: Path = Field(default=ROOT_DIR / "data" / "sample", alias="SAMPLE_DIR")
    imports_dir: Path = Field(default=ROOT_DIR / "data" / "imports", alias="IMPORTS_DIR")
    raw_lake_dir: Path = Field(default=ROOT_DIR / "data" / "raw_lake", alias="RAW_LAKE_DIR")
    apify_scraped_dir: Path = Field(default=ROOT_DIR / "data" / "apify_scraped data", alias="APIFY_SCRAPED_DIR")
    output_dir: Path = Field(default=ROOT_DIR / "data" / "outputs", alias="OUTPUT_DIR")
    media_download_dir: Path = Field(default=ROOT_DIR / "data" / "media" / "downloads", alias="MEDIA_DOWNLOAD_DIR")
    media_audio_dir: Path = Field(default=ROOT_DIR / "data" / "media" / "audio", alias="MEDIA_AUDIO_DIR")
    media_transcript_dir: Path = Field(default=ROOT_DIR / "data" / "media" / "transcripts", alias="MEDIA_TRANSCRIPT_DIR")

    database_url: str | None = Field(default=None, alias="DATABASE_URL")
    duckdb_path: Path = Field(default=ROOT_DIR / "data" / "analytics.duckdb", alias="DUCKDB_PATH")
    vector_store_path: Path = Field(default=ROOT_DIR / "data" / "chroma", alias="VECTOR_STORE_PATH")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    use_mock_data: bool = Field(default=True, alias="USE_MOCK_DATA")

    enable_media_pipeline: bool = Field(default=False, alias="ENABLE_MEDIA_PIPELINE")
    whisper_model: str = Field(default="base", alias="WHISPER_MODEL")
    max_videos_per_creator: int = Field(default=5, alias="MAX_VIDEOS_PER_CREATOR")

    youtube_api_key: str | None = Field(default=None, alias="YOUTUBE_API_KEY")
    apify_token: str | None = Field(default=None, alias="APIFY_TOKEN")
    instagram_scraper_actor: str = Field(default="apify/instagram-scraper", alias="INSTAGRAM_SCRAPER_ACTOR")
    instagram_post_actor: str = Field(default="apify/instagram-post-scraper", alias="INSTAGRAM_POST_ACTOR")
    instagram_comment_actor: str = Field(default="apify/instagram-comment-scraper", alias="INSTAGRAM_COMMENT_ACTOR")
    instagram_profile_actor: str = Field(default="apify/instagram-profile-scraper", alias="INSTAGRAM_PROFILE_ACTOR")
    instagram_hashtag_actor: str = Field(default="apify/instagram-hashtag-scraper", alias="INSTAGRAM_HASHTAG_ACTOR")
    instagram_reel_actor: str = Field(default="apify/instagram-reel-scraper", alias="INSTAGRAM_REEL_ACTOR")
    instagram_api_actor: str = Field(default="apify/instagram-api-scraper", alias="INSTAGRAM_API_ACTOR")
    instagram_profile_api_actor: str = Field(default="coderx/instagram-profile-scraper-api", alias="INSTAGRAM_PROFILE_API_ACTOR")
    instagram_posts_limit: int = Field(default=8, alias="INSTAGRAM_POSTS_LIMIT")
    instagram_comments_per_post: int = Field(default=10, alias="INSTAGRAM_COMMENTS_PER_POST")
    instagram_hashtags_limit: int = Field(default=3, alias="INSTAGRAM_HASHTAGS_LIMIT")
    cloudsql_instance_connection_name: str | None = Field(default=None, alias="CLOUDSQL_INSTANCE_CONNECTION_NAME")
    postgres_host: str = Field(default="postgres", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    postgres_db: str = Field(default="adobe_influencer", alias="POSTGRES_DB")
    postgres_user: str = Field(default="adobe", alias="POSTGRES_USER")
    postgres_password: str = Field(default="adobe", alias="POSTGRES_PASSWORD")
    cors_allowed_origins: str = Field(default="*", alias="CORS_ALLOWED_ORIGINS")
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")
    streamlit_host: str = Field(default="0.0.0.0", alias="STREAMLIT_HOST")
    streamlit_port: int = Field(default=8501, alias="STREAMLIT_PORT")
    chroma_collection: str = "creator_evidence"

    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    def model_post_init(self, __context: Any) -> None:
        self.data_dir = self._resolve_path(self.data_dir)
        self.configs_dir = self._resolve_path(self.configs_dir)

        derived_dirs = {
            "sample_dir": Path("sample"),
            "imports_dir": Path("imports"),
            "raw_lake_dir": Path("raw_lake"),
            "apify_scraped_dir": Path("apify_scraped data"),
            "output_dir": Path("outputs"),
            "media_download_dir": Path("media") / "downloads",
            "media_audio_dir": Path("media") / "audio",
            "media_transcript_dir": Path("media") / "transcripts",
        }
        for field_name, relative_path in derived_dirs.items():
            current_value = getattr(self, field_name)
            default_value = self.__class__.model_fields[field_name].default
            resolved_current_value = self._resolve_path(current_value)
            resolved_default_value = self._resolve_path(default_value)
            if field_name not in self.model_fields_set or (
                "data_dir" in self.model_fields_set and resolved_current_value == resolved_default_value
            ):
                setattr(self, field_name, self.data_dir / relative_path)
            else:
                setattr(self, field_name, resolved_current_value)

        default_duckdb_path = self.__class__.model_fields["duckdb_path"].default
        resolved_duckdb_path = self._resolve_path(self.duckdb_path)
        resolved_default_duckdb_path = self._resolve_path(default_duckdb_path)
        if "duckdb_path" not in self.model_fields_set or (
            "data_dir" in self.model_fields_set and resolved_duckdb_path == resolved_default_duckdb_path
        ):
            self.duckdb_path = self.data_dir / "analytics.duckdb"
        else:
            self.duckdb_path = resolved_duckdb_path

        default_vector_store_path = self.__class__.model_fields["vector_store_path"].default
        resolved_vector_store_path = self._resolve_path(self.vector_store_path)
        resolved_default_vector_store_path = self._resolve_path(default_vector_store_path)
        if "vector_store_path" not in self.model_fields_set or (
            "data_dir" in self.model_fields_set and resolved_vector_store_path == resolved_default_vector_store_path
        ):
            self.vector_store_path = self.data_dir / "chroma"
        else:
            self.vector_store_path = resolved_vector_store_path

        if not self.database_url:
            self.database_url = self._build_database_url()
        else:
            self.database_url = self._resolve_database_url(self.database_url)

    def ensure_paths(self) -> None:
        for path in (
            self.data_dir,
            self.sample_dir,
            self.imports_dir,
            self.raw_lake_dir,
            self.apify_scraped_dir,
            self.output_dir,
            self.vector_store_path,
            self.media_download_dir,
            self.media_audio_dir,
            self.media_transcript_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

    @property
    def cors_origins(self) -> list[str]:
        raw_value = self.cors_allowed_origins.strip()
        if not raw_value:
            return []
        if raw_value.startswith("["):
            parsed = json.loads(raw_value)
            return [str(item).strip() for item in parsed if str(item).strip()]
        return [item.strip() for item in raw_value.split(",") if item.strip()]

    def _resolve_path(self, path: Path) -> Path:
        if path.is_absolute():
            return path
        return (ROOT_DIR / path).resolve()

    def _resolve_database_url(self, database_url: str) -> str:
        if not database_url.startswith("sqlite:///"):
            return database_url

        sqlite_path = database_url.replace("sqlite:///", "", 1)
        if sqlite_path == ":memory:":
            return database_url

        resolved_path = self._resolve_path(Path(sqlite_path))
        return f"sqlite:///{resolved_path.as_posix()}"

    def _build_database_url(self) -> str:
        if self.cloudsql_instance_connection_name:
            user = quote_plus(self.postgres_user)
            password = quote_plus(self.postgres_password)
            database = quote_plus(self.postgres_db)
            socket_path = quote_plus(f"/cloudsql/{self.cloudsql_instance_connection_name}")
            return f"postgresql+psycopg2://{user}:{password}@/{database}?host={socket_path}"

        explicit_postgres_config = {
            "postgres_host",
            "postgres_port",
            "postgres_db",
            "postgres_user",
            "postgres_password",
        } & self.model_fields_set
        if self.environment.lower() != "local" and explicit_postgres_config:
            user = quote_plus(self.postgres_user)
            password = quote_plus(self.postgres_password)
            database = quote_plus(self.postgres_db)
            host = self.postgres_host.strip()
            return f"postgresql+psycopg2://{user}:{password}@{host}:{self.postgres_port}/{database}"

        return f"sqlite:///{(self.data_dir / 'adobe_influencer.db').as_posix()}"


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}
