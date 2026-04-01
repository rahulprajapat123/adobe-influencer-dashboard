from __future__ import annotations

from adobe_influencer.ingestion.seeds import build_creator_seeds_from_urls


def test_build_creator_seeds_from_urls_merges_instagram_and_youtube_handles() -> None:
    seeds = build_creator_seeds_from_urls(
        [
            "https://www.instagram.com/designcourse/",
            "https://www.youtube.com/@designcourse",
        ]
    )

    assert len(seeds) == 1
    seed = seeds[0]
    assert seed.creator_id == "creator_designcourse"
    assert seed.handle == "designcourse"
    assert str(seed.profile_url) == "https://www.instagram.com/designcourse/"
    assert str(seed.youtube_channel_url) == "https://www.youtube.com/@designcourse"


def test_build_creator_seeds_from_urls_supports_youtube_watch_links() -> None:
    seeds = build_creator_seeds_from_urls(["https://www.youtube.com/watch?v=dQw4w9WgXcQ"])

    assert len(seeds) == 1
    assert seeds[0].handle == "dQw4w9WgXcQ"
    assert str(seeds[0].youtube_channel_url) == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
