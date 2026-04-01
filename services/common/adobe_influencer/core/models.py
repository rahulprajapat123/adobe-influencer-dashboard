from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, HttpUrl


class SourcePlatform(str, Enum):
    instagram = "instagram"
    youtube = "youtube"
    website = "website"
    manual = "manual"


class ContentType(str, Enum):
    video = "video"
    short_video = "short_video"
    post = "post"
    article = "article"
    comment = "comment"


class CreatorSeed(BaseModel):
    creator_id: str
    handle: str
    display_name: str
    profile_url: HttpUrl
    youtube_channel_url: HttpUrl | None = None
    website_url: HttpUrl | None = None
    primary_platform: SourcePlatform
    niche: str
    bio: str
    audience_persona: list[str] = Field(default_factory=list)


class CreatorProfile(BaseModel):
    creator_id: str
    handle: str
    display_name: str
    primary_platform: SourcePlatform
    profile_url: str
    youtube_channel_url: str | None = None
    website_url: str | None = None
    niche: str
    bio: str
    followers: int = 0
    avg_likes: int = 0
    avg_comments: int = 0
    posts_last_30_days: int = 0
    audience_persona: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ContentRecord(BaseModel):
    content_id: str
    creator_id: str
    platform: SourcePlatform
    content_type: ContentType
    source_url: str
    title: str | None = None
    caption: str = ""
    published_at: datetime
    likes: int = 0
    comments_count: int = 0
    views: int = 0
    raw_payload_path: str


class CommentRecord(BaseModel):
    comment_id: str
    content_id: str
    creator_id: str
    author_name: str
    text: str
    likes: int = 0
    published_at: datetime
    source_url: str | None = None


class TranscriptSegment(BaseModel):
    transcript_id: str
    content_id: str
    creator_id: str
    start_seconds: float
    end_seconds: float
    text: str
    confidence: float


class QualityScorecard(BaseModel):
    creator_id: str
    engagement_rate: float
    comment_like_ratio: float
    posting_consistency: float
    growth_trend: float
    imported_analytics_sources: list[str] = Field(default_factory=list)


class ThemeResult(BaseModel):
    creator_id: str
    themes: list[dict[str, Any]]
    keywords: list[str]


class AudienceInsight(BaseModel):
    creator_id: str
    sentiment_summary: str
    sentiment_distribution: dict[str, int]
    intents: dict[str, int]
    recurring_questions: list[str]


class ProductSignalResult(BaseModel):
    creator_id: str
    acrobat_fit: float
    creative_cloud_fit: float
    adobe_mentions: dict[str, int]
    competitor_mentions: dict[str, int]
    evidence_snippets: list[str]
    risk_flags: list[str]
    recommended_campaign_angle: str


class RecommendationResult(BaseModel):
    creator_id: str
    creator_name: str
    handle: str
    overall_brand_fit: float
    acrobat_fit: float
    creative_cloud_fit: float
    audience_sentiment_summary: str
    recurring_audience_questions: list[str]
    content_theme_map: list[dict[str, Any]]
    evidence_snippets: list[str]
    risk_flags: list[str]
    recommended_campaign_angle: str
    score_breakdown: dict[str, float]
