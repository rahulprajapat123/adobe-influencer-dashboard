from __future__ import annotations

import json
import re
import subprocess
import time
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from adobe_influencer.core.logging import get_logger
from adobe_influencer.core.models import CommentRecord, ContentRecord, ContentType, CreatorProfile, CreatorSeed, SourcePlatform

logger = get_logger(__name__)


class CreatorIngestionAdapter(ABC):
    @abstractmethod
    def ingest(self, seeds: list[CreatorSeed]) -> tuple[list[CreatorProfile], list[ContentRecord], list[CommentRecord]]:
        raise NotImplementedError


class MockSeedAdapter(CreatorIngestionAdapter):
    def __init__(self, sample_dir: Path, raw_lake_dir: Path) -> None:
        self.sample_dir = sample_dir
        self.raw_lake_dir = raw_lake_dir

    def ingest(self, seeds: list[CreatorSeed]) -> tuple[list[CreatorProfile], list[ContentRecord], list[CommentRecord]]:
        creators_payload = self._load_json("creators.json")
        content_payload = self._load_json("content.json")
        comments_payload = self._load_json("comments.json")

        creator_ids = {seed.creator_id for seed in seeds}
        creators = [CreatorProfile(**payload) for payload in creators_payload if payload["creator_id"] in creator_ids]
        contents = [ContentRecord(**payload) for payload in content_payload if payload["creator_id"] in creator_ids]
        comments = [CommentRecord(**payload) for payload in comments_payload if payload["creator_id"] in creator_ids]

        self.raw_lake_dir.mkdir(parents=True, exist_ok=True)
        for file_name, payload in {
            "creators_raw.json": creators_payload,
            "content_raw.json": content_payload,
            "comments_raw.json": comments_payload,
        }.items():
            output_path = self.raw_lake_dir / file_name
            output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        logger.info("Mock ingestion completed for %s creators", len(creators))
        return creators, contents, comments

    def _load_json(self, file_name: str) -> list[dict[str, Any]]:
        path = self.sample_dir / file_name
        return json.loads(path.read_text(encoding="utf-8"))


class ApifyHttpClient:
    def __init__(self, token: str, timeout: int = 600, max_retries: int = 3, retry_delay_seconds: float = 2.0) -> None:
        from apify_client import ApifyClient
        
        self.client = ApifyClient(token)
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds

    def run_actor_sync_items(self, actor_name: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
        last_error: str | None = None
        
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(f"Apify actor {actor_name} attempt {attempt}/{self.max_retries} - starting run...")
                
                # Run the actor and wait for it to finish
                run = self.client.actor(actor_name).call(
                    run_input=payload,
                    timeout_secs=self.timeout
                )
                
                # Check if the run succeeded
                if run.get("status") != "SUCCEEDED":
                    last_error = f"Actor run status: {run.get('status')}. Error: {run.get('statusMessage', 'Unknown error')}"
                    logger.warning(f"Apify actor {actor_name} attempt {attempt}/{self.max_retries} failed: {last_error}")
                    if attempt < self.max_retries:
                        time.sleep(self.retry_delay_seconds * attempt)
                    continue
                
                # Get the dataset items
                dataset_id = run.get("defaultDatasetId")
                if not dataset_id:
                    last_error = "No dataset ID returned from actor run"
                    logger.warning(f"Apify actor {actor_name} attempt {attempt}/{self.max_retries} failed: {last_error}")
                    if attempt < self.max_retries:
                        time.sleep(self.retry_delay_seconds * attempt)
                    continue
                
                # Fetch all items from the dataset
                items_iterator = self.client.dataset(dataset_id).iterate_items()
                items = list(items_iterator)
                
                logger.info(f"Apify actor {actor_name} returned {len(items)} items")
                return items
                    
            except Exception as e:
                last_error = f"Unexpected error: {str(e)}"
                logger.warning(f"Apify actor {actor_name} attempt {attempt}/{self.max_retries} failed: {last_error}")
            
            if attempt < self.max_retries:
                time.sleep(self.retry_delay_seconds * attempt)
                
        raise RuntimeError(last_error or f"Apify call failed for {actor_name}")

    def _normalize_output(self, output: Any) -> list[dict[str, Any]]:
        if isinstance(output, list):
            return [item for item in output if isinstance(item, dict)]
        if isinstance(output, dict):
            for key in ("items", "data", "results", "datasetItems"):
                value = output.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
            return [output]
        return []


class ApifyAdapter(CreatorIngestionAdapter):
    def __init__(
        self,
        token: str,
        raw_lake_dir: Path,
        apify_scraped_dir: Path,
        instagram_scraper_actor: str,
        instagram_post_actor: str,
        instagram_comment_actor: str,
        instagram_profile_actor: str,
        instagram_hashtag_actor: str,
        instagram_reel_actor: str,
        instagram_api_actor: str,
        instagram_profile_api_actor: str,
        posts_limit: int = 8,
        comments_per_post: int = 10,
        hashtags_limit: int = 3,
    ) -> None:
        self.client = ApifyHttpClient(token)
        self.raw_lake_dir = raw_lake_dir
        self.apify_scraped_dir = apify_scraped_dir
        self.instagram_scraper_actor = instagram_scraper_actor
        self.instagram_post_actor = instagram_post_actor
        self.instagram_comment_actor = instagram_comment_actor
        self.instagram_profile_actor = instagram_profile_actor
        self.instagram_hashtag_actor = instagram_hashtag_actor
        self.instagram_reel_actor = instagram_reel_actor
        self.instagram_api_actor = instagram_api_actor
        self.instagram_profile_api_actor = instagram_profile_api_actor
        self.posts_limit = posts_limit
        self.comments_per_post = comments_per_post
        self.hashtags_limit = hashtags_limit

    def ingest(self, seeds: list[CreatorSeed]) -> tuple[list[CreatorProfile], list[ContentRecord], list[CommentRecord]]:
        creators: list[CreatorProfile] = []
        content_items: list[ContentRecord] = []
        comments: list[CommentRecord] = []
        self.raw_lake_dir.mkdir(parents=True, exist_ok=True)
        self.apify_scraped_dir.mkdir(parents=True, exist_ok=True)

        for seed in seeds:
            creator_dir = self.apify_scraped_dir / seed.creator_id
            creator_dir.mkdir(parents=True, exist_ok=True)

            actor_runs = self._collect_actor_runs(seed, creator_dir)
            posts = self._filter_creator_owned_posts(seed, self._merge_posts(actor_runs))
            post_lookup = self._build_post_lookup(posts)
            comment_items = self._collect_comment_items(seed, creator_dir, actor_runs, post_lookup)

            profile = self._select_profile_payload(actor_runs)
            hashtags = self._extract_hashtags(posts)
            manifest = {
                "creator_id": seed.creator_id,
                "handle": seed.handle,
                "profile_url": str(seed.profile_url),
                "hashtags_used": hashtags,
                "actors": {name: {"count": len(items), "path": str(path)} for name, items, path in actor_runs},
                "comments_actor": {
                    "count": len(comment_items),
                    "path": str(creator_dir / "instagram_comments.json"),
                },
            }
            (creator_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

            profile_raw_path = self.raw_lake_dir / f"{seed.creator_id}_profile.json"
            posts_raw_path = self.raw_lake_dir / f"{seed.creator_id}_posts.json"
            comments_raw_path = self.raw_lake_dir / f"{seed.creator_id}_comments.json"
            profile_raw_path.write_text(json.dumps(profile, indent=2), encoding="utf-8")
            posts_raw_path.write_text(json.dumps(posts, indent=2), encoding="utf-8")
            comments_raw_path.write_text(json.dumps(comment_items, indent=2), encoding="utf-8")

            creators.append(self._normalize_creator(seed, profile, posts))
            content_items.extend(self._normalize_content(seed, posts, posts_raw_path))
            comments.extend(self._normalize_comments(seed, posts, comment_items, post_lookup))
            logger.info("Apify ingestion completed for %s with %s merged posts across %s actors", seed.handle, len(posts), len(actor_runs))
        return creators, content_items, comments

    def _collect_actor_runs(self, seed: CreatorSeed, creator_dir: Path) -> list[tuple[str, list[dict[str, Any]], Path]]:
        actor_payloads: list[tuple[str, str, dict[str, Any], str]] = [
            (
                "instagram_profile",
                self.instagram_profile_actor,
                {"usernames": [seed.handle]},
                "instagram_profile.json",
            ),
            (
                "instagram_profile_api",
                self.instagram_profile_api_actor,
                {"usernames": [seed.handle]},
                "instagram_profile_api.json",
            ),
            (
                "instagram_scraper",
                self.instagram_scraper_actor,
                {
                    "directUrls": [str(seed.profile_url)],
                    "resultsType": "posts",
                    "resultsLimit": self.posts_limit,
                    "addParentData": True,
                },
                "instagram_scraper.json",
            ),
            (
                "instagram_post",
                self.instagram_post_actor,
                {
                    "username": [str(seed.profile_url)],
                    "usernames": [seed.handle],
                    "resultsLimit": self.posts_limit,
                    "skipPinnedPosts": True,
                },
                "instagram_posts.json",
            ),
            (
                "instagram_reel",
                self.instagram_reel_actor,
                {
                    "username": [str(seed.profile_url)],
                    "usernames": [seed.handle],
                    "resultsLimit": self.posts_limit,
                    "skipPinnedPosts": True,
                },
                "instagram_reels.json",
            ),
            (
                "instagram_api",
                self.instagram_api_actor,
                {
                    "directUrls": [str(seed.profile_url)],
                    "resultsType": "posts",
                    "resultsLimit": self.posts_limit,
                    "addParentData": True,
                },
                "instagram_api.json",
            ),
        ]

        actor_runs: list[tuple[str, list[dict[str, Any]], Path]] = []
        for actor_key, actor_name, payload, file_name in actor_payloads:
            output_path = creator_dir / file_name
            items = self._run_actor(actor_key, actor_name, payload, output_path)
            actor_runs.append((actor_key, items, output_path))

        hashtags = self._extract_hashtags(self._filter_creator_owned_posts(seed, self._merge_posts(actor_runs)))
        hashtag_payload = {
            "hashtags": hashtags,
            "resultsType": "posts",
            "resultsLimit": self.posts_limit,
        }
        hashtag_path = creator_dir / "instagram_hashtags.json"
        hashtag_items = self._run_actor(
            "instagram_hashtag",
            self.instagram_hashtag_actor,
            hashtag_payload,
            hashtag_path,
            skip_if=not hashtags,
            skipped_reason="No hashtags were found in the creator's recent post captions.",
        )
        actor_runs.append(("instagram_hashtag", hashtag_items, hashtag_path))
        return actor_runs

    def _collect_comment_items(
        self,
        seed: CreatorSeed,
        creator_dir: Path,
        actor_runs: list[tuple[str, list[dict[str, Any]], Path]],
        post_lookup: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        post_urls = [self._post_url(post) for post in post_lookup.values()]
        direct_urls = list(dict.fromkeys(url for url in post_urls if url))[: self.posts_limit]
        comment_path = creator_dir / "instagram_comments.json"
        comment_items = self._run_actor(
            "instagram_comment",
            self.instagram_comment_actor,
            {
                "directUrls": direct_urls,
                "resultsLimit": self.comments_per_post,
                "includeNestedComments": True,
            },
            comment_path,
            skip_if=not direct_urls,
            skipped_reason=f"No post URLs were available for {seed.handle}.",
        )
        return comment_items

    def _run_actor(
        self,
        actor_key: str,
        actor_name: str,
        payload: dict[str, Any],
        output_path: Path,
        *,
        skip_if: bool = False,
        skipped_reason: str | None = None,
    ) -> list[dict[str, Any]]:
        if skip_if:
            output_path.write_text(
                json.dumps({"actor": actor_name, "skipped": True, "reason": skipped_reason, "payload": payload}, indent=2),
                encoding="utf-8",
            )
            return []

        try:
            items = self.client.run_actor_sync_items(actor_name, payload)
            output_path.write_text(json.dumps(items, indent=2), encoding="utf-8")
            return items
        except Exception as exc:
            logger.warning("Apify actor %s failed: %s", actor_name, exc)
            output_path.write_text(
                json.dumps({"actor": actor_name, "error": str(exc), "payload": payload}, indent=2),
                encoding="utf-8",
            )
            return []

    def _select_profile_payload(self, actor_runs: list[tuple[str, list[dict[str, Any]], Path]]) -> dict[str, Any]:
        for actor_key in ("instagram_profile", "instagram_profile_api", "instagram_scraper", "instagram_api"):
            items = next((items for name, items, _ in actor_runs if name == actor_key), [])
            if items:
                return items[0]
        return {}

    def _merge_posts(self, actor_runs: list[tuple[str, list[dict[str, Any]], Path]]) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        for actor_key in ("instagram_post", "instagram_reel", "instagram_api", "instagram_scraper", "instagram_hashtag"):
            items = next((items for name, items, _ in actor_runs if name == actor_key), [])
            for item in items:
                key = self._post_key(item)
                if not key:
                    continue
                if key not in merged:
                    enriched = dict(item)
                    enriched.setdefault("_sources", [actor_key])
                    merged[key] = enriched
                    continue
                merged[key].setdefault("_sources", [])
                if actor_key not in merged[key]["_sources"]:
                    merged[key]["_sources"].append(actor_key)
                merged[key] = self._merge_dicts(merged[key], item)
        posts = list(merged.values())
        posts.sort(key=lambda post: self._coerce_datetime(self._post_timestamp(post)), reverse=True)
        return posts[: self.posts_limit]

    def _build_post_lookup(self, posts: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        lookup: dict[str, dict[str, Any]] = {}
        for post in posts:
            for candidate in (self._post_key(post), self._post_id(post), self._post_shortcode(post), self._post_url(post)):
                if candidate:
                    lookup[str(candidate)] = post
        return lookup

    def _filter_creator_owned_posts(self, seed: CreatorSeed, posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        filtered: list[dict[str, Any]] = []
        for post in posts:
            if self._is_creator_owned_post(seed, post):
                filtered.append(post)
                continue
            logger.warning(
                "Skipping Instagram post outside creator scope for %s from sources %s: %s",
                seed.handle,
                ", ".join(post.get("_sources", [])) or "unknown",
                self._post_url(post) or self._post_key(post) or "unknown",
            )
        return filtered

    def _is_creator_owned_post(self, seed: CreatorSeed, post: dict[str, Any]) -> bool:
        sources = {str(source).lower() for source in post.get("_sources", [])}
        trusted_direct_sources = {"instagram_post", "instagram_reel", "instagram_api", "instagram_scraper"}
        if sources & trusted_direct_sources:
            return True

        expected_handle = seed.handle.lower().lstrip("@")
        owner_candidates = {
            str(post.get("username") or "").lower(),
            str(post.get("userName") or "").lower(),
            str(post.get("ownerUsername") or "").lower(),
            str(post.get("owner", {}).get("username") or "").lower(),
            str(post.get("owner", {}).get("userName") or "").lower(),
            str(post.get("authorUsername") or "").lower(),
        }
        owner_candidates = {candidate.lstrip("@") for candidate in owner_candidates if candidate}
        if expected_handle and expected_handle in owner_candidates:
            return True

        profile_candidates = {
            str(post.get("owner", {}).get("url") or ""),
            str(post.get("owner", {}).get("profileUrl") or ""),
            str(post.get("profileUrl") or ""),
        }
        normalized_profile_url = str(seed.profile_url).rstrip("/").lower()
        for candidate in profile_candidates:
            if candidate and candidate.rstrip("/").lower() == normalized_profile_url:
                return True

        return False

    def _normalize_creator(self, seed: CreatorSeed, profile: dict[str, Any], posts: list[dict[str, Any]]) -> CreatorProfile:
        avg_likes = int(sum(self._post_likes(post) for post in posts[:5]) / max(len(posts[:5]), 1))
        avg_comments = int(sum(self._post_comments_count(post) for post in posts[:5]) / max(len(posts[:5]), 1))
        recent_posts = [post for post in posts if self._is_recent(self._post_timestamp(post))]
        return CreatorProfile(
            creator_id=seed.creator_id,
            handle=profile.get("username") or profile.get("userName") or seed.handle,
            display_name=profile.get("full_name") or profile.get("fullName") or profile.get("name") or seed.display_name,
            primary_platform=SourcePlatform.instagram,
            profile_url=str(seed.profile_url),
            youtube_channel_url=str(seed.youtube_channel_url) if seed.youtube_channel_url else None,
            website_url=profile.get("external_url") or profile.get("externalUrl") or profile.get("website") or (str(seed.website_url) if seed.website_url else None),
            niche=seed.niche,
            bio=profile.get("biography") or profile.get("bio") or seed.bio,
            followers=profile.get("followers") or profile.get("followersCount") or profile.get("followers_count") or 0,
            avg_likes=avg_likes,
            avg_comments=avg_comments,
            posts_last_30_days=len(recent_posts),
            audience_persona=seed.audience_persona,
        )

    def _normalize_content(self, seed: CreatorSeed, posts: list[dict[str, Any]], raw_payload_path: Path) -> list[ContentRecord]:
        records: list[ContentRecord] = []
        for post in posts:
            post_id = self._post_key(post) or f"ig_{seed.creator_id}_{len(records)}"
            records.append(
                ContentRecord(
                    content_id=post_id,
                    creator_id=seed.creator_id,
                    platform=SourcePlatform.instagram,
                    content_type=self._content_type(post),
                    source_url=self._post_url(post) or str(seed.profile_url),
                    title=None,
                    caption=self._post_caption(post),
                    published_at=self._coerce_datetime(self._post_timestamp(post)),
                    likes=self._post_likes(post),
                    comments_count=self._post_comments_count(post),
                    views=self._post_views(post),
                    raw_payload_path=str(raw_payload_path),
                )
            )
        return records

    def _normalize_comments(
        self,
        seed: CreatorSeed,
        posts: list[dict[str, Any]],
        comment_items: list[dict[str, Any]],
        post_lookup: dict[str, dict[str, Any]],
    ) -> list[CommentRecord]:
        if comment_items:
            return self._normalize_actor_comments(seed, comment_items, post_lookup)
        return self._normalize_embedded_comments(seed, posts)

    def _normalize_actor_comments(
        self,
        seed: CreatorSeed,
        comment_items: list[dict[str, Any]],
        post_lookup: dict[str, dict[str, Any]],
    ) -> list[CommentRecord]:
        records: list[CommentRecord] = []
        for idx, item in enumerate(comment_items):
            post_ref = item.get("postId") or item.get("post_id") or item.get("ownerPostId") or item.get("shortCode") or item.get("postCode")
            post_url = item.get("postUrl") or item.get("post_url") or item.get("url")
            post = post_lookup.get(str(post_ref)) or post_lookup.get(str(post_url))
            content_id = self._post_key(post) if post else None
            if not content_id and post_ref:
                content_id = f"ig_{post_ref}"
            if not content_id and post_url:
                content_id = self._content_id_from_url(post_url)
            if not content_id:
                content_id = f"ig_{seed.creator_id}_comment_target_{idx}"

            text = item.get("text") or item.get("commentText") or item.get("content") or ""
            if not str(text).strip():
                continue
            records.append(
                CommentRecord(
                    comment_id=f"igc_{item.get('id') or item.get('commentId') or idx}",
                    content_id=content_id,
                    creator_id=seed.creator_id,
                    author_name=item.get("ownerUsername") or item.get("username") or item.get("owner", {}).get("username") or "unknown",
                    text=str(text),
                    likes=item.get("likesCount") or item.get("likes") or 0,
                    published_at=self._coerce_datetime(item.get("timestamp") or item.get("createdAt") or item.get("created_at")),
                    source_url=post_url or (self._post_url(post) if post else None),
                )
            )
        return records

    def _normalize_embedded_comments(self, seed: CreatorSeed, posts: list[dict[str, Any]]) -> list[CommentRecord]:
        records: list[CommentRecord] = []
        for post in posts:
            content_id = self._post_key(post) or f"ig_{seed.creator_id}_{len(records)}"
            for idx, comment in enumerate((post.get("latestComments") or post.get("comments") or [])[: self.comments_per_post]):
                text = comment.get("text") or ""
                if not str(text).strip():
                    continue
                created_at = self._coerce_datetime(comment.get("timestamp") or post.get("timestamp"))
                records.append(
                    CommentRecord(
                        comment_id=f"igc_{comment.get('id') or f'{content_id}_{idx}'}",
                        content_id=content_id,
                        creator_id=seed.creator_id,
                        author_name=comment.get("ownerUsername") or comment.get("owner", {}).get("username") or "unknown",
                        text=text,
                        likes=comment.get("likesCount") or 0,
                        published_at=created_at,
                        source_url=self._post_url(post),
                    )
                )
                for reply_idx, reply in enumerate(comment.get("replies") or []):
                    reply_text = reply.get("text") or ""
                    if not str(reply_text).strip():
                        continue
                    records.append(
                        CommentRecord(
                            comment_id=f"igc_{reply.get('id') or f'{content_id}_{idx}_r{reply_idx}'}",
                            content_id=content_id,
                            creator_id=seed.creator_id,
                            author_name=reply.get("ownerUsername") or reply.get("owner", {}).get("username") or "unknown",
                            text=reply_text,
                            likes=reply.get("likesCount") or 0,
                            published_at=self._coerce_datetime(reply.get("timestamp") or comment.get("timestamp") or post.get("timestamp")),
                            source_url=self._post_url(post),
                        )
                    )
        return records

    def _extract_hashtags(self, posts: list[dict[str, Any]]) -> list[str]:
        seen: list[str] = []
        for post in posts:
            for match in re.findall(r"#([A-Za-z0-9_]+)", self._post_caption(post)):
                normalized = match.lower()
                if normalized not in seen:
                    seen.append(normalized)
                if len(seen) >= self.hashtags_limit:
                    return seen
        return seen

    def _content_type(self, post: dict[str, Any]) -> ContentType:
        product_type = str(post.get("productType") or "").lower()
        post_type = str(post.get("type") or post.get("mediaType") or "").lower()
        url = str(self._post_url(post) or "").lower()
        if product_type in {"clips", "igtv", "reel"} or post_type in {"video", "reel"} or "/reel/" in url:
            return ContentType.short_video
        if post.get("isVideo"):
            return ContentType.video
        return ContentType.post

    def _post_key(self, post: dict[str, Any] | None) -> str | None:
        if not post:
            return None
        post_id = self._post_id(post)
        if post_id:
            return f"ig_{post_id}"
        shortcode = self._post_shortcode(post)
        if shortcode:
            return f"ig_{shortcode}"
        url = self._post_url(post)
        if url:
            return self._content_id_from_url(url)
        return None

    def _post_id(self, post: dict[str, Any]) -> str | None:
        value = post.get("id") or post.get("postId") or post.get("media_id") or post.get("pk")
        return str(value) if value else None

    def _post_shortcode(self, post: dict[str, Any]) -> str | None:
        value = post.get("shortCode") or post.get("shortcode") or post.get("code")
        return str(value) if value else None

    def _post_url(self, post: dict[str, Any] | None) -> str | None:
        if not post:
            return None
        for key in ("url", "postUrl", "post_url", "link", "instagramUrl"):
            value = post.get(key)
            if value:
                return str(value)
        shortcode = self._post_shortcode(post)
        if shortcode:
            prefix = "reel" if self._content_type(post) != ContentType.post else "p"
            return f"https://www.instagram.com/{prefix}/{shortcode}/"
        return None

    def _post_caption(self, post: dict[str, Any]) -> str:
        return str(post.get("caption") or post.get("text") or post.get("title") or "")

    def _post_timestamp(self, post: dict[str, Any]) -> Any:
        return post.get("timestamp") or post.get("takenAt") or post.get("createdAt") or post.get("created_at") or post.get("publishedAt")

    def _post_likes(self, post: dict[str, Any]) -> int:
        return self._to_int(post.get("likesCount") or post.get("likes") or post.get("likes_count"))

    def _post_comments_count(self, post: dict[str, Any]) -> int:
        raw_value = post.get("commentsCount") or post.get("comments_count")
        if raw_value is None and isinstance(post.get("comments"), list):
            raw_value = len(post.get("comments") or [])
        return self._to_int(raw_value)

    def _post_views(self, post: dict[str, Any]) -> int:
        return self._to_int(post.get("videoViewCount") or post.get("videoPlayCount") or post.get("video_view_count") or post.get("views"))

    def _content_id_from_url(self, url: str) -> str:
        match = re.search(r"instagram\.com/(?:p|reel)/([^/?#]+)/?", str(url))
        if match:
            return f"ig_{match.group(1)}"
        digits = re.sub(r"[^A-Za-z0-9]", "_", str(url)).strip("_")
        return f"ig_{digits[:80]}"

    def _to_int(self, value: Any) -> int:
        if value in (None, "", [], {}):
            return 0
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float)):
            return int(value)
        digits = re.sub(r"[^0-9.-]", "", str(value))
        if not digits:
            return 0
        try:
            return int(float(digits))
        except ValueError:
            return 0

    def _merge_dicts(self, base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
        merged = dict(base)
        for key, value in incoming.items():
            if key in {"_sources"}:
                continue
            if merged.get(key) in (None, "", [], {}) and value not in (None, "", [], {}):
                merged[key] = value
        return merged

    def _coerce_datetime(self, value: Any) -> datetime:
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=UTC)
        if isinstance(value, (int, float)):
            timestamp = float(value)
            if timestamp > 1_000_000_000_000:
                timestamp /= 1000
            return datetime.fromtimestamp(timestamp, tz=UTC)
        if isinstance(value, str) and value:
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                pass
        return datetime.now(UTC)

    def _is_recent(self, value: Any) -> bool:
        created = self._coerce_datetime(value)
        return (datetime.now(UTC) - created).days <= 30


class YouTubeAPIAdapter(CreatorIngestionAdapter):
    """Adapter for fetching creator data from YouTube Data API v3"""
    
    def __init__(self, api_key: str, raw_lake_dir: Path, videos_per_channel: int = 10, comments_per_video: int = 20):
        """
        Initialize YouTube API adapter
        
        Args:
            api_key: YouTube Data API v3 key
            raw_lake_dir: Directory to store raw YouTube API responses
            videos_per_channel: Number of videos to fetch per channel (default 10)
            comments_per_video: Number of comments to fetch per video (default 20)
        """
        from adobe_influencer.ingestion.youtube_service import YouTubeAPIService
        
        if not api_key:
            raise ValueError("YouTube API key is required for YouTubeAPIAdapter")
        
        self.youtube_service = YouTubeAPIService(api_key)
        self.raw_lake_dir = raw_lake_dir
        self.videos_per_channel = videos_per_channel
        self.comments_per_video = comments_per_video
    
    def ingest(self, seeds: list[CreatorSeed]) -> tuple[list[CreatorProfile], list[ContentRecord], list[CommentRecord]]:
        """
        Ingest creator data from YouTube channels
        
        Args:
            seeds: List of creator seeds with youtube_channel_url populated
        
        Returns:
            Tuple of (creators, content, comments)
        """
        creators: list[CreatorProfile] = []
        all_content: list[ContentRecord] = []
        all_comments: list[CommentRecord] = []
        
        self.raw_lake_dir.mkdir(parents=True, exist_ok=True)
        
        for seed in seeds:
            # Skip if no YouTube URL
            if not seed.youtube_channel_url:
                logger.warning(f"Skipping {seed.creator_id}: No YouTube channel URL provided")
                continue
            
            # Extract channel ID from URL
            channel_id = self.youtube_service.extract_channel_id(str(seed.youtube_channel_url))
            if not channel_id:
                logger.error(f"Could not extract channel ID from {seed.youtube_channel_url}")
                continue
            
            # Fetch channel info
            channel_info = self.youtube_service.get_channel_info(channel_id)
            if not channel_info:
                logger.error(f"Could not fetch channel info for {channel_id}")
                continue
            
            # Fetch videos
            videos = self.youtube_service.get_channel_videos(
                channel_id,
                max_results=self.videos_per_channel,
                order="date"
            )
            
            if not videos:
                logger.warning(f"No videos found for channel {channel_id}")
            
            # Fetch comments for each video
            all_video_comments = []
            for video in videos[:5]:  # Only get comments from top 5 videos
                video_comments = self.youtube_service.get_video_comments(
                    video["video_id"],
                    max_results=self.comments_per_video,
                    order="relevance"
                )
                all_video_comments.extend(video_comments)
            
            # Save raw data
            youtube_data = {
                "channel": channel_info,
                "videos": videos,
                "comments": all_video_comments,
            }
            raw_path = self.raw_lake_dir / f"{seed.creator_id}_youtube.json"
            raw_path.write_text(json.dumps(youtube_data, indent=2, default=str), encoding="utf-8")
            
            # Normalize to models
            creator = self.youtube_service.normalize_to_creator_profile(
                creator_id=seed.creator_id,
                channel_info=channel_info,
                videos=videos,
                niche=seed.niche,
                audience_persona=seed.audience_persona,
            )
            
            content = self.youtube_service.normalize_to_content_records(
                creator_id=seed.creator_id,
                videos=videos,
            )
            
            comments = self.youtube_service.normalize_to_comment_records(
                creator_id=seed.creator_id,
                comments=all_video_comments,
            )
            
            creators.append(creator)
            all_content.extend(content)
            all_comments.extend(comments)
            
            logger.info(
                f"YouTube ingestion complete for {seed.handle}: "
                f"{len(videos)} videos, {len(all_video_comments)} comments"
            )
        
        return creators, all_content, all_comments


class UnifiedLiveAdapter(CreatorIngestionAdapter):
    def __init__(
        self,
        instagram_adapter: CreatorIngestionAdapter | None,
        youtube_adapter: CreatorIngestionAdapter | None,
    ) -> None:
        self.instagram_adapter = instagram_adapter
        self.youtube_adapter = youtube_adapter

    def ingest(self, seeds: list[CreatorSeed]) -> tuple[list[CreatorProfile], list[ContentRecord], list[CommentRecord]]:
        creators_by_id: dict[str, CreatorProfile] = {}
        content_by_id: dict[str, ContentRecord] = {}
        comments_by_id: dict[str, CommentRecord] = {}
        seed_lookup = {seed.creator_id: seed for seed in seeds}

        instagram_seeds = [seed for seed in seeds if self._supports_instagram(seed)]
        youtube_seeds = [seed for seed in seeds if self._supports_youtube(seed)]

        if instagram_seeds and self.instagram_adapter:
            creators, content, comments = self.instagram_adapter.ingest(instagram_seeds)
            self._merge_results(creators_by_id, content_by_id, comments_by_id, seed_lookup, creators, content, comments)

        if youtube_seeds and self.youtube_adapter:
            creators, content, comments = self.youtube_adapter.ingest(youtube_seeds)
            self._merge_results(creators_by_id, content_by_id, comments_by_id, seed_lookup, creators, content, comments)

        unsupported = [seed.creator_id for seed in seeds if seed.creator_id not in creators_by_id]
        if unsupported:
            logger.warning("No supported live ingestion source resolved for creators: %s", ", ".join(sorted(unsupported)))

        creators = list(creators_by_id.values())
        content = sorted(content_by_id.values(), key=lambda item: item.published_at, reverse=True)
        comments = sorted(comments_by_id.values(), key=lambda item: item.published_at, reverse=True)
        return creators, content, comments

    def _merge_results(
        self,
        creators_by_id: dict[str, CreatorProfile],
        content_by_id: dict[str, ContentRecord],
        comments_by_id: dict[str, CommentRecord],
        seed_lookup: dict[str, CreatorSeed],
        creators: list[CreatorProfile],
        content: list[ContentRecord],
        comments: list[CommentRecord],
    ) -> None:
        for creator in creators:
            existing = creators_by_id.get(creator.creator_id)
            creators_by_id[creator.creator_id] = self._merge_creator(existing, creator, seed_lookup.get(creator.creator_id))
        for item in content:
            content_by_id[item.content_id] = item
        for comment in comments:
            comments_by_id[comment.comment_id] = comment

    def _merge_creator(
        self,
        existing: CreatorProfile | None,
        incoming: CreatorProfile,
        seed: CreatorSeed | None,
    ) -> CreatorProfile:
        if not existing:
            payload = incoming.model_dump()
            if seed and seed.website_url and not payload.get("website_url"):
                payload["website_url"] = str(seed.website_url)
            return CreatorProfile(**payload)

        payload = existing.model_dump()
        incoming_payload = incoming.model_dump()
        preferred_platform = seed.primary_platform if seed else existing.primary_platform

        for key in ("profile_url", "youtube_channel_url", "website_url", "niche"):
            if incoming_payload.get(key) and not payload.get(key):
                payload[key] = incoming_payload[key]

        if incoming_payload.get("bio") and len(incoming_payload["bio"]) > len(payload.get("bio", "")):
            payload["bio"] = incoming_payload["bio"]
        if incoming_payload.get("display_name") and len(incoming_payload["display_name"]) > len(payload.get("display_name", "")):
            payload["display_name"] = incoming_payload["display_name"]

        payload["followers"] = max(payload.get("followers", 0), incoming_payload.get("followers", 0))
        payload["avg_likes"] = max(payload.get("avg_likes", 0), incoming_payload.get("avg_likes", 0))
        payload["avg_comments"] = max(payload.get("avg_comments", 0), incoming_payload.get("avg_comments", 0))
        payload["posts_last_30_days"] = max(payload.get("posts_last_30_days", 0), incoming_payload.get("posts_last_30_days", 0))
        payload["primary_platform"] = preferred_platform
        payload["audience_persona"] = list(dict.fromkeys((payload.get("audience_persona") or []) + (incoming_payload.get("audience_persona") or [])))
        return CreatorProfile(**payload)

    def _supports_instagram(self, seed: CreatorSeed) -> bool:
        return "instagram.com" in str(seed.profile_url).lower()

    def _supports_youtube(self, seed: CreatorSeed) -> bool:
        return bool(seed.youtube_channel_url) or "youtube.com" in str(seed.profile_url).lower() or "youtu.be" in str(seed.profile_url).lower()



class CsvAnalyticsImporter:
    def __init__(self, csv_path: Path) -> None:
        self.csv_path = csv_path

    def load(self) -> list[dict[str, Any]]:
        if not self.csv_path.exists():
            return []
        frame = pd.read_csv(self.csv_path)
        return frame.to_dict(orient="records")


class AnalyticsImportDirectory:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def load(self) -> list[dict[str, Any]]:
        if not self.directory.exists():
            return []
        grouped: dict[str, dict[str, Any]] = {}
        for path in sorted(self.directory.glob('*.csv')):
            frame = pd.read_csv(path)
            for row in frame.to_dict(orient='records'):
                normalized = self._normalize_row(path.name, row)
                if not normalized:
                    continue
                bucket = grouped.setdefault(
                    normalized['creator_id'],
                    {'creator_id': normalized['creator_id'], 'growth_values': [], 'sources': set()},
                )
                bucket['growth_values'].append(normalized['growth_trend'])
                bucket['sources'].add(normalized['source'])
        rows: list[dict[str, Any]] = []
        for creator_id, bucket in grouped.items():
            growth_values = bucket['growth_values']
            rows.append(
                {
                    'creator_id': creator_id,
                    'growth_trend': round(sum(growth_values) / max(len(growth_values), 1), 2),
                    'source': ', '.join(sorted(bucket['sources'])),
                }
            )
        return rows

    def _normalize_row(self, file_name: str, row: dict[str, Any]) -> dict[str, Any] | None:
        lower_name = file_name.lower()
        if 'anik' in lower_name:
            creator_id = 'real_anikjaindesign'
        elif 'saptarshi' in lower_name:
            creator_id = 'real_saptarshiux'
        elif 'wanderwithsky' in lower_name:
            creator_id = 'real_wanderwithsky'
        else:
            return None

        source = 'manual_csv'
        growth_trend = 0.55
        data3 = str(row.get('data3', '')).lower()
        start_url = str(row.get('web_scraper_start_url', ''))
        if 'modash' in start_url:
            source = 'Modash CSV'
            match = re.search(r'([0-9.]+)\s*%', data3)
            if match:
                growth_trend = min(1.0, float(match.group(1)) / 5)
        elif 'socialblade' in start_url:
            source = 'SocialBlade CSV'
            rank_value = self._parse_rank_value(str(row.get('data', '')))
            if rank_value:
                growth_trend = max(0.3, min(0.9, 1 - (rank_value / 300000)))
        return {'creator_id': creator_id, 'source': source, 'growth_trend': round(growth_trend, 2)}

    def _parse_rank_value(self, text: str) -> int | None:
        digits = re.sub(r'[^0-9]', '', text)
        return int(digits) if digits else None
