from __future__ import annotations

from dataclasses import dataclass

from adobe_influencer.core.config import load_yaml
from adobe_influencer.core.models import AudienceInsight, ProductSignalResult, QualityScorecard, RecommendationResult, ThemeResult


@dataclass
class PersonaOverlapResult:
    creator_id: str
    audience_match_score: float
    uniqueness_score: float
    persona_tags: list[str]


class PersonaAnalyzer:
    def analyze(self, creator_personas: dict[str, list[str]]) -> dict[str, PersonaOverlapResult]:
        universe = {persona for personas in creator_personas.values() for persona in personas}
        results: dict[str, PersonaOverlapResult] = {}
        for creator_id, personas in creator_personas.items():
            overlap = len(set(personas)) / max(len(universe), 1)
            uniqueness = 1 - overlap / 2
            results[creator_id] = PersonaOverlapResult(
                creator_id=creator_id,
                audience_match_score=round(min(1.0, 0.55 + overlap), 3),
                uniqueness_score=round(max(0.0, uniqueness), 3),
                persona_tags=personas,
            )
        return results


class RecommendationScorer:
    def __init__(self, weight_config_path) -> None:
        payload = load_yaml(weight_config_path)
        self.weights = payload.get("weights", {})

    def score(
        self,
        creator_lookup: dict[str, dict[str, str]],
        quality: dict[str, QualityScorecard],
        themes: dict[str, ThemeResult],
        audience: dict[str, AudienceInsight],
        product: dict[str, ProductSignalResult],
        personas: dict[str, PersonaOverlapResult],
    ) -> list[RecommendationResult]:
        results: list[RecommendationResult] = []
        for creator_id, creator_meta in creator_lookup.items():
            q = quality[creator_id]
            t = themes[creator_id]
            a = audience[creator_id]
            p = product[creator_id]
            persona = personas[creator_id]
            topic_relevance = min(100.0, sum(theme["share"] for theme in t.themes) * 45)
            audience_sentiment_score = self._sentiment_score(a)
            engagement_quality = min(100.0, q.engagement_rate * 5 + q.posting_consistency * 15 + q.growth_trend * 20)
            uniqueness = persona.uniqueness_score * 100
            overall = (
                engagement_quality * self.weights.get("engagement_quality", 0.2)
                + topic_relevance * self.weights.get("topic_relevance", 0.2)
                + audience_sentiment_score * self.weights.get("audience_sentiment", 0.15)
                + ((p.acrobat_fit + p.creative_cloud_fit) / 2) * self.weights.get("adobe_product_fit", 0.25)
                + uniqueness * self.weights.get("audience_uniqueness", 0.1)
                + self._risk_modifier(p.risk_flags) * self.weights.get("risk_flags", 0.1)
            )
            results.append(
                RecommendationResult(
                    creator_id=creator_id,
                    creator_name=creator_meta["display_name"],
                    handle=creator_meta["handle"],
                    overall_brand_fit=round(overall, 2),
                    acrobat_fit=p.acrobat_fit,
                    creative_cloud_fit=p.creative_cloud_fit,
                    audience_sentiment_summary=a.sentiment_summary,
                    recurring_audience_questions=a.recurring_questions,
                    content_theme_map=t.themes,
                    evidence_snippets=p.evidence_snippets,
                    risk_flags=p.risk_flags,
                    recommended_campaign_angle=p.recommended_campaign_angle,
                    score_breakdown={
                        "engagement_quality": round(engagement_quality, 2),
                        "topic_relevance": round(topic_relevance, 2),
                        "audience_sentiment": round(audience_sentiment_score, 2),
                        "adobe_product_fit": round((p.acrobat_fit + p.creative_cloud_fit) / 2, 2),
                        "audience_uniqueness": round(uniqueness, 2),
                        "risk_modifier": round(self._risk_modifier(p.risk_flags), 2),
                    },
                )
            )
        return sorted(results, key=lambda item: item.overall_brand_fit, reverse=True)

    def _sentiment_score(self, insight: AudienceInsight) -> float:
        total = max(sum(insight.sentiment_distribution.values()), 1)
        positive = insight.sentiment_distribution.get("positive", 0)
        neutral = insight.sentiment_distribution.get("neutral", 0)
        return ((positive * 1.0) + (neutral * 0.6)) / total * 100

    def _risk_modifier(self, risks: list[str]) -> float:
        return max(20.0, 100 - len(risks) * 18)
