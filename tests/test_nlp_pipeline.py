from __future__ import annotations

from datetime import UTC, datetime

from adobe_influencer.core.models import CommentRecord, ContentRecord, ContentType, SourcePlatform, TranscriptSegment
from adobe_influencer.nlp.pipeline import _build_evidence_snippets, classify_comments


def test_classify_comments_detects_questions_and_pain_points() -> None:
    comments = [
        CommentRecord(
            comment_id="1",
            content_id="p1",
            creator_id="c1",
            author_name="A",
            text="Love this tutorial. Can you show how to fix messy PDF review loops?",
            likes=1,
            published_at="2026-03-01T10:00:00",
            source_url=None,
        ),
        CommentRecord(
            comment_id="2",
            content_id="p1",
            creator_id="c1",
            author_name="B",
            text="Great walkthrough, the workflow pain is real.",
            likes=1,
            published_at="2026-03-01T10:05:00",
            source_url=None,
        ),
    ]

    result = classify_comments(comments)["c1"]

    assert result.intents["question"] >= 1
    assert result.intents["tutorial_request"] >= 1
    assert result.intents["workflow_pain_point"] >= 1
    assert "Mostly positive" in result.sentiment_summary


def test_evidence_snippets_prefer_canonical_content_source_over_foreign_comment_url() -> None:
    published_at = datetime(2026, 3, 31, tzinfo=UTC)
    content = [
        ContentRecord(
            content_id="yt_1",
            creator_id="creator_1",
            platform=SourcePlatform.youtube,
            content_type=ContentType.video,
            source_url="https://www.youtube.com/watch?v=12345678901",
            title="Acrobat breakdown",
            caption="Acrobat review workflow for client PDFs",
            published_at=published_at,
            likes=10,
            comments_count=1,
            views=100,
            raw_payload_path="raw.json",
        )
    ]
    comments = [
        CommentRecord(
            comment_id="comment_1",
            content_id="yt_1",
            creator_id="creator_1",
            author_name="viewer",
            text="Can you explain the Acrobat review flow again?",
            likes=1,
            published_at=published_at,
            source_url="https://www.youtube.com/watch?v=foreignvideo1",
        )
    ]
    transcripts = [
        TranscriptSegment(
            transcript_id="tx_1",
            content_id="yt_1",
            creator_id="creator_1",
            start_seconds=0,
            end_seconds=5,
            text="This Photoshop to PDF review process is what clients actually approve faster.",
            confidence=0.9,
        )
    ]

    snippets = _build_evidence_snippets(
        "creator_1",
        content,
        comments,
        transcripts,
        {item.content_id: item for item in content},
    )

    assert any("https://www.youtube.com/watch?v=12345678901" in snippet for snippet in snippets)
    assert all("foreignvideo1" not in snippet for snippet in snippets)


def test_evidence_snippets_drop_unsupported_source_urls_without_content_mapping() -> None:
    published_at = datetime(2026, 3, 31, tzinfo=UTC)
    comments = [
        CommentRecord(
            comment_id="comment_2",
            content_id="missing_content",
            creator_id="creator_2",
            author_name="viewer",
            text="This Acrobat workflow is useful.",
            likes=1,
            published_at=published_at,
            source_url="https://example.com/random-page",
        )
    ]

    snippets = _build_evidence_snippets("creator_2", [], comments, [], {})

    assert len(snippets) == 1
    assert "(source:" not in snippets[0]
