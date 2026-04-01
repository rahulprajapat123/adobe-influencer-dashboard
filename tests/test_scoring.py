from __future__ import annotations

from pathlib import Path

from adobe_influencer.core.models import AudienceInsight, ProductSignalResult, QualityScorecard, RecommendationResult, ThemeResult
from adobe_influencer.scoring.engine import PersonaAnalyzer, RecommendationScorer


def test_recommendation_scorer_orders_highest_fit_first() -> None:
    scorer = RecommendationScorer(Path("configs/scoring_weights.yaml"))
    creator_lookup = {
        "c1": {"display_name": "Creator One", "handle": "@one"},
        "c2": {"display_name": "Creator Two", "handle": "@two"},
    }
    quality = {
        "c1": QualityScorecard(creator_id="c1", engagement_rate=9.0, comment_like_ratio=0.08, posting_consistency=0.9, growth_trend=0.8),
        "c2": QualityScorecard(creator_id="c2", engagement_rate=4.0, comment_like_ratio=0.04, posting_consistency=0.5, growth_trend=0.4),
    }
    themes = {
        "c1": ThemeResult(creator_id="c1", themes=[{"theme": "design_education", "share": 0.8, "evidence_terms": ["photoshop"]}], keywords=["photoshop"]),
        "c2": ThemeResult(creator_id="c2", themes=[{"theme": "productivity_docs", "share": 0.3, "evidence_terms": ["pdf"]}], keywords=["pdf"]),
    }
    audience = {
        "c1": AudienceInsight(creator_id="c1", sentiment_summary="Mostly positive", sentiment_distribution={"positive": 8, "neutral": 2, "negative": 0}, intents={"question": 3}, recurring_questions=["How do you export?"]),
        "c2": AudienceInsight(creator_id="c2", sentiment_summary="Mostly neutral", sentiment_distribution={"positive": 2, "neutral": 5, "negative": 2}, intents={"question": 1}, recurring_questions=[]),
    }
    product = {
        "c1": ProductSignalResult(creator_id="c1", acrobat_fit=70, creative_cloud_fit=91, adobe_mentions={}, competitor_mentions={}, evidence_snippets=["photoshop to pdf flow"], risk_flags=[], recommended_campaign_angle="Creative Cloud angle"),
        "c2": ProductSignalResult(creator_id="c2", acrobat_fit=54, creative_cloud_fit=49, adobe_mentions={}, competitor_mentions={}, evidence_snippets=["pdf review"], risk_flags=["Some risk"], recommended_campaign_angle="Acrobat angle"),
    }
    personas = PersonaAnalyzer().analyze({"c1": ["designers", "educators"], "c2": ["operators"]})

    results = scorer.score(creator_lookup, quality, themes, audience, product, personas)

    assert results[0].creator_id == "c1"
    assert results[0].overall_brand_fit > results[1].overall_brand_fit
