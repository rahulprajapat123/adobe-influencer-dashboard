from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse

from adobe_influencer.core.models import CreatorSeed, SourcePlatform


def load_creator_seeds(path: Path) -> list[CreatorSeed]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [CreatorSeed(**item) for item in payload]


def save_creator_seeds(path: Path, seeds: list[CreatorSeed]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [seed.model_dump(mode="json") for seed in seeds]
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def build_creator_seeds_from_urls(urls: list[str]) -> list[CreatorSeed]:
    merged: dict[str, CreatorSeed] = {}
    for raw_url in urls:
        url = raw_url.strip()
        if not url:
            continue
        candidate = _seed_from_url(url)
        if not candidate:
            continue
        existing = merged.get(candidate.creator_id)
        merged[candidate.creator_id] = _merge_seed(existing, candidate) if existing else candidate
    return list(merged.values())


def _seed_from_url(url: str) -> CreatorSeed | None:
    parsed = urlparse(url if "://" in url else f"https://{url}")
    normalized_url = parsed.geturl()
    domain = parsed.netloc.lower().replace("www.", "")
    path_parts = [part for part in parsed.path.split("/") if part]

    if "instagram.com" in domain:
        handle = _extract_instagram_handle(path_parts)
        if not handle:
            return None
        creator_id = f"creator_{_slugify(handle)}"
        return CreatorSeed(
            creator_id=creator_id,
            handle=handle,
            display_name=_display_name_from_handle(handle),
            profile_url=f"https://www.instagram.com/{handle}/",
            primary_platform=SourcePlatform.instagram,
            niche="Creator analysis pending live ingestion",
            bio="Creator discovered from submitted Instagram URL.",
            audience_persona=[],
        )

    if "youtube.com" in domain or "youtu.be" in domain:
        handle = _extract_youtube_handle(domain, path_parts, parsed.query)
        if not handle:
            handle = _slugify(normalized_url)[:40] or "youtube_creator"
        creator_id = f"creator_{_slugify(handle)}"
        channel_url = _canonical_youtube_channel_url(domain, path_parts, parsed.query, normalized_url)
        return CreatorSeed(
            creator_id=creator_id,
            handle=handle,
            display_name=_display_name_from_handle(handle),
            profile_url=channel_url,
            youtube_channel_url=channel_url,
            primary_platform=SourcePlatform.youtube,
            niche="Creator analysis pending live ingestion",
            bio="Creator discovered from submitted YouTube URL.",
            audience_persona=[],
        )

    if domain:
        handle = _slugify(path_parts[0] if path_parts else domain.split(".")[0]) or "creator"
        creator_id = f"creator_{handle}"
        website_url = normalized_url
        return CreatorSeed(
            creator_id=creator_id,
            handle=handle,
            display_name=_display_name_from_handle(handle),
            profile_url=website_url,
            website_url=website_url,
            primary_platform=SourcePlatform.website,
            niche="Creator analysis pending live ingestion",
            bio="Creator discovered from submitted website URL.",
            audience_persona=[],
        )

    return None


def _merge_seed(existing: CreatorSeed, incoming: CreatorSeed) -> CreatorSeed:
    payload = existing.model_dump()
    if incoming.primary_platform == SourcePlatform.instagram:
        payload["profile_url"] = incoming.profile_url
        payload["primary_platform"] = SourcePlatform.instagram
    if incoming.youtube_channel_url:
        payload["youtube_channel_url"] = incoming.youtube_channel_url
    if incoming.website_url and not payload.get("website_url"):
        payload["website_url"] = incoming.website_url
    if payload.get("bio", "").startswith("Creator discovered") and incoming.bio:
        payload["bio"] = incoming.bio
    if payload.get("niche", "").startswith("Creator analysis pending") and incoming.niche:
        payload["niche"] = incoming.niche
    return CreatorSeed(**payload)


def _extract_instagram_handle(path_parts: list[str]) -> str | None:
    if not path_parts:
        return None
    candidate = path_parts[0].strip("@")
    if candidate.lower() in {"p", "reel", "reels", "stories", "tv", "explore"}:
        return None
    return candidate


def _extract_youtube_handle(domain: str, path_parts: list[str], query: str) -> str | None:
    if "youtu.be" in domain and path_parts:
        return path_parts[0]
    if not path_parts:
        return None
    if path_parts[0].startswith("@"):
        return path_parts[0][1:]
    if path_parts[0] in {"channel", "c", "user", "shorts", "watch"} and len(path_parts) > 1:
        return path_parts[1]
    match = re.search(r"[?&]v=([A-Za-z0-9_-]{11})", f"?{query}")
    if match:
        return match.group(1)
    return path_parts[-1]


def _canonical_youtube_channel_url(domain: str, path_parts: list[str], query: str, fallback: str) -> str:
    if path_parts and path_parts[0].startswith("@"):
        return f"https://www.youtube.com/{path_parts[0]}"
    if path_parts[:1] and path_parts[0] in {"channel", "c", "user"} and len(path_parts) > 1:
        return f"https://www.youtube.com/{path_parts[0]}/{path_parts[1]}"
    match = re.search(r"[?&]v=([A-Za-z0-9_-]{11})", f"?{query}")
    if match:
        return f"https://www.youtube.com/watch?v={match.group(1)}"
    if "youtu.be" in domain and path_parts:
        return f"https://youtu.be/{path_parts[0]}"
    return fallback


def _display_name_from_handle(handle: str) -> str:
    clean = re.sub(r"[_\-.]+", " ", handle).strip()
    return clean.title() if clean else "Creator"


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()
    return slug or "creator"
