from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import duckdb
import pandas as pd

from adobe_influencer.core.models import RecommendationResult


class AnalyticsStore:
    def __init__(self, db_path: Path, read_only: bool = False) -> None:
        try:
            db_path.parent.mkdir(parents=True, exist_ok=True)
        except (OSError, PermissionError):
            # Filesystem is read-only - use in-memory database
            db_path = Path(":memory:")
        self.connection = duckdb.connect(str(db_path), read_only=read_only)

    def persist_recommendations(self, recommendations: Iterable[RecommendationResult]) -> None:
        frame = pd.DataFrame([result.model_dump() for result in recommendations])
        self.connection.register("recommendations_df", frame)
        self.connection.execute("create or replace table recommendations as select * from recommendations_df")

    def top_creators(self, limit: int = 10) -> list[dict]:
        return self.connection.execute(
            "select creator_name, handle, overall_brand_fit, acrobat_fit, creative_cloud_fit from recommendations order by overall_brand_fit desc limit ?",
            [limit],
        ).fetchdf().to_dict(orient="records")
