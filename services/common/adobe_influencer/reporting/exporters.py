from __future__ import annotations

import json
from pathlib import Path

from adobe_influencer.core.models import RecommendationResult


def export_markdown(results: list[RecommendationResult], output_path: Path) -> Path:
    lines = ["# Adobe Influencer Intelligence Report", ""]
    for index, item in enumerate(results, start=1):
        lines.extend(
            [
                f"## {index}. {item.creator_name} ({item.handle})",
                f"- Overall brand-fit: {item.overall_brand_fit}",
                f"- Adobe Acrobat fit: {item.acrobat_fit}",
                f"- Adobe Creative Cloud fit: {item.creative_cloud_fit}",
                f"- Audience sentiment: {item.audience_sentiment_summary}",
                f"- Campaign angle: {item.recommended_campaign_angle}",
                f"- Risk flags: {', '.join(item.risk_flags) if item.risk_flags else 'None'}",
                "- Recurring audience questions:",
            ]
        )
        for question in item.recurring_audience_questions:
            lines.append(f"  - {question}")
        lines.append("- Evidence snippets:")
        for snippet in item.evidence_snippets:
            lines.append(f"  - {snippet}")
        lines.append("")
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def export_json(results: list[RecommendationResult], output_path: Path) -> Path:
    output_path.write_text(json.dumps([item.model_dump() for item in results], indent=2), encoding="utf-8")
    return output_path
