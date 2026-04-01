from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import delete, or_, select

from adobe_influencer.core.models import CommentRecord, ContentRecord, CreatorProfile, RecommendationResult, TranscriptSegment
from adobe_influencer.storage.database import CommentORM, ContentORM, CreatorORM, CreatorScoreORM, DatabaseManager, TranscriptORM


class Repository:
    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    def upsert_creators(self, creators: Iterable[CreatorProfile]) -> None:
        with self.db.session() as session:
            for creator in creators:
                session.merge(CreatorORM(**creator.model_dump()))

    def upsert_content(self, content_items: Iterable[ContentRecord]) -> None:
        with self.db.session() as session:
            for item in content_items:
                session.merge(ContentORM(**item.model_dump()))

    def upsert_comments(self, comments: Iterable[CommentRecord]) -> None:
        with self.db.session() as session:
            for comment in comments:
                session.merge(CommentORM(**comment.model_dump()))

    def upsert_transcripts(self, transcripts: Iterable[TranscriptSegment]) -> None:
        with self.db.session() as session:
            for transcript in transcripts:
                session.merge(TranscriptORM(**transcript.model_dump()))

    def replace_recommendations(self, results: Iterable[RecommendationResult]) -> None:
        with self.db.session() as session:
            session.execute(delete(CreatorScoreORM))
            for result in results:
                payload = result.model_dump(exclude={"creator_name", "handle"})
                session.merge(CreatorScoreORM(**payload))

    def list_recommendations(self) -> list[RecommendationResult]:
        with self.db.session() as session:
            creators = {creator.creator_id: creator for creator in session.scalars(select(CreatorORM)).all()}
            rows = session.scalars(select(CreatorScoreORM).order_by(CreatorScoreORM.overall_brand_fit.desc())).all()
            results: list[RecommendationResult] = []
            for row in rows:
                creator = creators[row.creator_id]
                results.append(
                    RecommendationResult(
                        creator_id=row.creator_id,
                        creator_name=creator.display_name,
                        handle=creator.handle,
                        overall_brand_fit=row.overall_brand_fit,
                        acrobat_fit=row.acrobat_fit,
                        creative_cloud_fit=row.creative_cloud_fit,
                        audience_sentiment_summary=row.audience_sentiment_summary,
                        recurring_audience_questions=row.recurring_audience_questions,
                        content_theme_map=row.content_theme_map,
                        evidence_snippets=row.evidence_snippets,
                        risk_flags=row.risk_flags,
                        recommended_campaign_angle=row.recommended_campaign_angle,
                        score_breakdown=row.score_breakdown,
                    )
                )
            return results

    def get_creator_bundle(self, creator_id: str) -> dict[str, object]:
        with self.db.session() as session:
            creator = session.scalar(select(CreatorORM).where(CreatorORM.creator_id == creator_id))
            content = session.scalars(select(ContentORM).where(ContentORM.creator_id == creator_id)).all()
            comments = session.scalars(select(CommentORM).where(CommentORM.creator_id == creator_id)).all()
            transcripts = session.scalars(select(TranscriptORM).where(TranscriptORM.creator_id == creator_id)).all()
            recommendation = session.scalar(select(CreatorScoreORM).where(CreatorScoreORM.creator_id == creator_id))
            return {
                "creator": creator,
                "content": content,
                "comments": comments,
                "transcripts": transcripts,
                "recommendation": recommendation,
            }

    def exact_search(self, query: str, limit: int = 5) -> list[dict[str, str]]:
        pattern = f"%{query}%"
        with self.db.session() as session:
            content_rows = session.scalars(
                select(ContentORM).where(or_(ContentORM.caption.ilike(pattern), ContentORM.title.ilike(pattern))).limit(limit)
            ).all()
            comment_rows = session.scalars(select(CommentORM).where(CommentORM.text.ilike(pattern)).limit(limit)).all()
        results: list[dict[str, str]] = []
        for row in content_rows:
            results.append({"type": "content", "id": row.content_id, "text": row.caption, "creator_id": row.creator_id})
        for row in comment_rows:
            results.append({"type": "comment", "id": row.comment_id, "text": row.text, "creator_id": row.creator_id})
        return results[:limit]
