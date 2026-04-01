from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass
class ExternalAnalyticsAdapter:
    source_name: str

    def import_csv(self, csv_path: Path) -> list[dict]:
        if not csv_path.exists():
            return []
        frame = pd.read_csv(csv_path)
        rows = frame.to_dict(orient="records")
        for row in rows:
            row.setdefault("source", self.source_name)
        return rows


class ModashCsvAdapter(ExternalAnalyticsAdapter):
    def __init__(self) -> None:
        super().__init__(source_name="Modash CSV")


class SparkToroCsvAdapter(ExternalAnalyticsAdapter):
    def __init__(self) -> None:
        super().__init__(source_name="SparkToro CSV")


class SocialBladeCsvAdapter(ExternalAnalyticsAdapter):
    def __init__(self) -> None:
        super().__init__(source_name="SocialBlade CSV")


class HypeAuditorCsvAdapter(ExternalAnalyticsAdapter):
    def __init__(self) -> None:
        super().__init__(source_name="HypeAuditor CSV")
