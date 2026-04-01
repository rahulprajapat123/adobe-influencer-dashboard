from __future__ import annotations

from datetime import UTC, datetime

import pytest

from adobe_influencer.core.models import CommentRecord, ContentRecord, ContentType, CreatorProfile, CreatorSeed, SourcePlatform
from adobe_influencer.ingestion.adapters import CreatorIngestionAdapter, UnifiedLiveAdapter

pytestmark = pytest.mark.integration


class FakeAdapter(CreatorIngestionAdapter):
    def __init__(self, creators, content, comments) -> None:
        self._creators = creators
        self._content = content
        self._comments = comments

    def ingest(self, seeds):
        return self._creators, self._content, self._comments


def test_unified_live_adapter_merges_cross_platform_results() -> None:
    seed = CreatorSeed(
        creator_id="creator_designcourse",
        handle="designcourse",
        display_name="Designcourse",
        profile_url="https://www.instagram.com/designcourse/",
        youtube_channel_url="https://www.youtube.com/@designcourse",
        primary_platform=SourcePlatform.instagram,
        niche="Design",
        bio="Discovered creator",
        audience_persona=["designers"],
    )

    instagram_creator = CreatorProfile(
        creator_id=seed.creator_id,
        handle="designcourse",
        display_name="DesignCourse",
        primary_platform=SourcePlatform.instagram,
        profile_url="https://www.instagram.com/designcourse/",
        niche="Brand design",
        bio="Instagram bio",
        followers=15000,
        avg_likes=900,
        avg_comments=50,
        posts_last_30_days=6,
        audience_persona=["designers"],
    )
    youtube_creator = CreatorProfile(
        creator_id=seed.creator_id,
        handle="designcourse",
        display_name="DesignCourse Official",
        primary_platform=SourcePlatform.youtube,
        profile_url="https://www.youtube.com/channel/abc",
        youtube_channel_url="https://www.youtube.com/@designcourse",
        niche="Design education",
        bio="Longer YouTube bio for the same creator",
        followers=220000,
        avg_likes=12000,
        avg_comments=480,
        posts_last_30_days=8,
        audience_persona=["students", "creatives"],
    )
    published_at = datetime(2026, 3, 31, tzinfo=UTC)
    instagram_content = ContentRecord(
        content_id="ig_1",
        creator_id=seed.creator_id,
        platform=SourcePlatform.instagram,
        content_type=ContentType.short_video,
        source_url="https://www.instagram.com/reel/ABC123/",
        caption="Photoshop reel",
        published_at=published_at,
        likes=500,
        comments_count=10,
        views=10000,
        raw_payload_path="raw_ig.json",
    )
    youtube_content = ContentRecord(
        content_id="yt_1",
        creator_id=seed.creator_id,
        platform=SourcePlatform.youtube,
        content_type=ContentType.video,
        source_url="https://www.youtube.com/watch?v=12345678901",
        title="Illustrator deep dive",
        caption="Illustrator workflow",
        published_at=published_at,
        likes=4000,
        comments_count=200,
        views=80000,
        raw_payload_path="raw_yt.json",
    )
    youtube_comment = CommentRecord(
        comment_id="yt_comment_1",
        content_id="yt_1",
        creator_id=seed.creator_id,
        author_name="viewer",
        text="Great Acrobat review workflow",
        likes=5,
        published_at=published_at,
        source_url="https://www.youtube.com/watch?v=12345678901",
    )

    adapter = UnifiedLiveAdapter(
        instagram_adapter=FakeAdapter([instagram_creator], [instagram_content], []),
        youtube_adapter=FakeAdapter([youtube_creator], [youtube_content], [youtube_comment]),
    )

    creators, content, comments = adapter.ingest([seed])

    assert len(creators) == 1
    creator = creators[0]
    assert creator.primary_platform == SourcePlatform.instagram
    assert creator.followers == 220000
    assert creator.youtube_channel_url == "https://www.youtube.com/@designcourse"
    assert "students" in creator.audience_persona
    assert len(content) == 2
    assert len(comments) == 1
