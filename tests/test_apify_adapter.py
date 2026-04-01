from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from adobe_influencer.core.models import CreatorSeed, SourcePlatform
from adobe_influencer.ingestion.adapters import ApifyAdapter


TEST_ROOT = Path("data/test_tmp")


def build_adapter(test_name: str) -> ApifyAdapter:
    base = TEST_ROOT / f"{test_name}_{uuid4().hex}"
    (base / "raw_lake").mkdir(parents=True, exist_ok=True)
    (base / "apify_scraped data").mkdir(parents=True, exist_ok=True)
    return ApifyAdapter(
        token="test-token",
        raw_lake_dir=base / "raw_lake",
        apify_scraped_dir=base / "apify_scraped data",
        instagram_scraper_actor="apify/instagram-scraper",
        instagram_post_actor="apify/instagram-post-scraper",
        instagram_comment_actor="apify/instagram-comment-scraper",
        instagram_profile_actor="apify/instagram-profile-scraper",
        instagram_hashtag_actor="apify/instagram-hashtag-scraper",
        instagram_reel_actor="apify/instagram-reel-scraper",
        instagram_api_actor="apify/instagram-api-scraper",
        instagram_profile_api_actor="coderx/instagram-profile-scraper-api",
        posts_limit=8,
        comments_per_post=5,
        hashtags_limit=3,
    )


def test_apify_adapter_merges_posts_and_extracts_hashtags() -> None:
    adapter = build_adapter("merge")
    actor_runs = [
        (
            "instagram_post",
            [
                {
                    "id": "123",
                    "shortCode": "ABC123",
                    "caption": "Testing #acrobat and #design workflows",
                    "likesCount": 25,
                    "commentsCount": 4,
                    "timestamp": "2026-03-20T10:00:00Z",
                    "url": "https://www.instagram.com/p/ABC123/",
                }
            ],
            adapter.apify_scraped_dir / "posts.json",
        ),
        (
            "instagram_api",
            [
                {
                    "id": "123",
                    "videoViewCount": 900,
                    "commentsCount": 6,
                    "timestamp": "2026-03-20T10:00:00Z",
                    "url": "https://www.instagram.com/p/ABC123/",
                }
            ],
            adapter.apify_scraped_dir / "api.json",
        ),
        (
            "instagram_hashtag",
            [
                {
                    "id": "456",
                    "shortCode": "XYZ789",
                    "caption": "Another post for #pdf #creativecloud",
                    "likesCount": 12,
                    "commentsCount": 2,
                    "timestamp": "2026-03-19T10:00:00Z",
                    "url": "https://www.instagram.com/p/XYZ789/",
                }
            ],
            adapter.apify_scraped_dir / "hashtag.json",
        ),
    ]

    merged = adapter._merge_posts(actor_runs)

    assert len(merged) == 2
    assert merged[0]["videoViewCount"] == 900
    assert merged[0]["commentsCount"] == 4
    assert adapter._extract_hashtags(merged) == ["acrobat", "design", "pdf"]


def test_apify_adapter_normalizes_comment_actor_output() -> None:
    adapter = build_adapter("comments")
    seed = CreatorSeed(
        creator_id="real_test_creator",
        handle="testcreator",
        display_name="Test Creator",
        profile_url="https://www.instagram.com/testcreator/",
        primary_platform=SourcePlatform.instagram,
        niche="Design",
        bio="Bio",
        audience_persona=["designers"],
    )
    post = {
        "id": "123",
        "shortCode": "ABC123",
        "url": "https://www.instagram.com/p/ABC123/",
        "timestamp": "2026-03-20T10:00:00Z",
    }
    post_lookup = {
        "ig_123": post,
        "123": post,
    }
    comment_items = [
        {
            "id": "c-1",
            "postId": "123",
            "postUrl": "https://www.instagram.com/p/ABC123/",
            "text": "Can you show the Acrobat export settings?",
            "ownerUsername": "viewer1",
            "likesCount": 3,
            "timestamp": "2026-03-21T10:00:00Z",
        }
    ]

    records = adapter._normalize_actor_comments(seed, comment_items, post_lookup)

    assert len(records) == 1
    assert records[0].content_id == "ig_123"
    assert records[0].author_name == "viewer1"
    assert "Acrobat export settings" in records[0].text


def test_apify_adapter_filters_hashtag_posts_from_other_creators() -> None:
    adapter = build_adapter("hashtag_scope")
    seed = CreatorSeed(
        creator_id="real_test_creator",
        handle="testcreator",
        display_name="Test Creator",
        profile_url="https://www.instagram.com/testcreator/",
        primary_platform=SourcePlatform.instagram,
        niche="Design",
        bio="Bio",
        audience_persona=["designers"],
    )
    actor_runs = [
        (
            "instagram_post",
            [
                {
                    "id": "123",
                    "shortCode": "ABC123",
                    "caption": "Testing #acrobat and #design workflows",
                    "timestamp": "2026-03-20T10:00:00Z",
                    "url": "https://www.instagram.com/p/ABC123/",
                }
            ],
            adapter.apify_scraped_dir / "posts.json",
        ),
        (
            "instagram_hashtag",
            [
                {
                    "id": "456",
                    "shortCode": "XYZ789",
                    "caption": "Other creator talking about #pdf",
                    "timestamp": "2026-03-19T10:00:00Z",
                    "url": "https://www.instagram.com/p/XYZ789/",
                    "ownerUsername": "othercreator",
                }
            ],
            adapter.apify_scraped_dir / "hashtag.json",
        ),
    ]

    merged = adapter._merge_posts(actor_runs)
    filtered = adapter._filter_creator_owned_posts(seed, merged)

    assert len(filtered) == 1
    assert filtered[0]["url"] == "https://www.instagram.com/p/ABC123/"
