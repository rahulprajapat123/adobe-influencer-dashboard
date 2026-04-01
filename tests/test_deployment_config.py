from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from adobe_influencer.core.config import ROOT_DIR, AppSettings


def make_temp_dir(test_name: str) -> Path:
    temp_dir = ROOT_DIR / "data" / "test_tmp" / f"{test_name}_{uuid4().hex}"
    temp_dir.mkdir(parents=True, exist_ok=True)
    return temp_dir


def test_app_settings_derives_runtime_paths_from_data_dir() -> None:
    temp_dir = make_temp_dir("deployment_config")
    settings = AppSettings(**{"DATA_DIR": temp_dir, "DATABASE_URL": None})

    assert settings.sample_dir == temp_dir / "sample"
    assert settings.imports_dir == temp_dir / "imports"
    assert settings.raw_lake_dir == temp_dir / "raw_lake"
    assert settings.output_dir == temp_dir / "outputs"
    assert settings.vector_store_path == temp_dir / "chroma"
    assert settings.database_url == f"sqlite:///{(temp_dir / 'adobe_influencer.db').as_posix()}"


def test_app_settings_builds_cloudsql_socket_url() -> None:
    settings = AppSettings(
        **{
            "ENVIRONMENT": "production",
            "DATABASE_URL": None,
            "CLOUDSQL_INSTANCE_CONNECTION_NAME": "demo-project:us-central1:adobe-db",
            "POSTGRES_DB": "adobe_influencer",
            "POSTGRES_USER": "adobe",
            "POSTGRES_PASSWORD": "s3cret!",
        }
    )

    assert settings.database_url == (
        "postgresql+psycopg2://adobe:s3cret%21@/adobe_influencer"
        "?host=%2Fcloudsql%2Fdemo-project%3Aus-central1%3Aadobe-db"
    )


def test_app_settings_resolves_relative_sqlite_url_against_repo_root() -> None:
    settings = AppSettings(**{"DATABASE_URL": "sqlite:///./data/test.db"})

    assert settings.database_url == f"sqlite:///{(ROOT_DIR / 'data' / 'test.db').resolve().as_posix()}"


def test_app_settings_parses_cors_origins_csv() -> None:
    settings = AppSettings(**{"CORS_ALLOWED_ORIGINS": "https://dashboard.run.app, https://admin.example.com"})

    assert settings.cors_origins == ["https://dashboard.run.app", "https://admin.example.com"]
