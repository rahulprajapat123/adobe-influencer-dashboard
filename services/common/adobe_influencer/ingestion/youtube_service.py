from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs, urlparse

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from adobe_influencer.core.logging import get_logger
from adobe_influencer.core.models import CommentRecord, ContentRecord, ContentType, CreatorProfile, SourcePlatform

logger = get_logger(__name__)


class YouTubeAPIService:
    """Service for interacting with YouTube Data API v3"""
    
    def __init__(self, api_key: str):
        """
        Initialize YouTube API service
        
        Args:
            api_key: YouTube Data API v3 key from Google Cloud Console
        """
        if not api_key:
            raise ValueError("YouTube API key is required")
        
        self.youtube = build("youtube", "v3", developerKey=api_key)
        logger.info("YouTube API service initialized")
    
    def extract_channel_id(self, url: str) -> str | None:
        """
        Extract channel ID from various YouTube URL formats
        
        Supports:
        - https://www.youtube.com/channel/UC...
        - https://www.youtube.com/@username
        - https://www.youtube.com/c/channelname
        - https://www.youtube.com/user/username
        """
        parsed = urlparse(url)

        if parsed.netloc.endswith("youtu.be"):
            video_id = parsed.path.strip("/")
            return self._get_channel_id_from_video(video_id) if video_id else None

        if parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [None])[0]
            return self._get_channel_id_from_video(video_id) if video_id else None
        
        # Direct channel ID format
        if "/channel/" in parsed.path:
            return parsed.path.split("/channel/")[1].split("/")[0]
        
        # Handle @username format
        if "/@" in parsed.path:
            username = parsed.path.split("/@")[1].split("/")[0]
            return self._get_channel_id_by_username(username)
        
        # Handle /c/ or /user/ format
        if "/c/" in parsed.path or "/user/" in parsed.path:
            username = parsed.path.split("/")[-1]
            return self._get_channel_id_by_username(username)
        
        return None

    def _get_channel_id_from_video(self, video_id: str | None) -> str | None:
        if not video_id:
            return None
        try:
            request = self.youtube.videos().list(part="snippet", id=video_id)
            response = request.execute()
            items = response.get("items", [])
            if not items:
                return None
            return items[0].get("snippet", {}).get("channelId")
        except HttpError as e:
            logger.error(f"Error resolving channel from video {video_id}: {e}")
            return None
    
    def _get_channel_id_by_username(self, username: str) -> str | None:
        """Get channel ID from username or custom URL"""
        try:
            # Try forUsername first
            request = self.youtube.channels().list(
                part="id",
                forUsername=username
            )
            response = request.execute()
            
            if response.get("items"):
                return response["items"][0]["id"]
            
            # Try search as fallback
            search_request = self.youtube.search().list(
                part="snippet",
                q=username,
                type="channel",
                maxResults=1
            )
            search_response = search_request.execute()
            
            if search_response.get("items"):
                return search_response["items"][0]["snippet"]["channelId"]
            
            return None
        
        except HttpError as e:
            logger.error(f"Error fetching channel ID for username {username}: {e}")
            return None
    
    def get_channel_info(self, channel_id: str) -> dict[str, Any] | None:
        """
        Fetch channel metadata
        
        Returns:
            Dict with channel info including title, description, subscriber count, etc.
        """
        try:
            request = self.youtube.channels().list(
                part="snippet,statistics,brandingSettings",
                id=channel_id
            )
            response = request.execute()
            
            if not response.get("items"):
                logger.warning(f"No channel found for ID: {channel_id}")
                return None
            
            channel = response["items"][0]
            snippet = channel.get("snippet", {})
            stats = channel.get("statistics", {})
            
            return {
                "channel_id": channel_id,
                "title": snippet.get("title"),
                "description": snippet.get("description"),
                "custom_url": snippet.get("customUrl"),
                "published_at": snippet.get("publishedAt"),
                "thumbnail": snippet.get("thumbnails", {}).get("high", {}).get("url"),
                "subscriber_count": int(stats.get("subscriberCount", 0)),
                "video_count": int(stats.get("videoCount", 0)),
                "view_count": int(stats.get("viewCount", 0)),
                "country": snippet.get("country"),
            }
        
        except HttpError as e:
            logger.error(f"Error fetching channel info for {channel_id}: {e}")
            return None
    
    def get_channel_videos(
        self,
        channel_id: str,
        max_results: int = 10,
        order: str = "date"
    ) -> list[dict[str, Any]]:
        """
        Fetch recent videos from a channel
        
        Args:
            channel_id: YouTube channel ID
            max_results: Maximum number of videos to fetch (default 10, max 50)
            order: Sort order - date, viewCount, rating, relevance, title
        
        Returns:
            List of video metadata dicts
        """
        try:
            # First, get video IDs from channel
            search_request = self.youtube.search().list(
                part="id,snippet",
                channelId=channel_id,
                type="video",
                order=order,
                maxResults=min(max_results, 50)
            )
            search_response = search_request.execute()
            
            video_ids = [item["id"]["videoId"] for item in search_response.get("items", [])]
            
            if not video_ids:
                return []
            
            # Get detailed video statistics
            videos_request = self.youtube.videos().list(
                part="snippet,statistics,contentDetails",
                id=",".join(video_ids)
            )
            videos_response = videos_request.execute()
            
            videos = []
            for video in videos_response.get("items", []):
                snippet = video.get("snippet", {})
                stats = video.get("statistics", {})
                details = video.get("contentDetails", {})
                
                videos.append({
                    "video_id": video["id"],
                    "title": snippet.get("title"),
                    "description": snippet.get("description"),
                    "published_at": snippet.get("publishedAt"),
                    "channel_id": snippet.get("channelId"),
                    "channel_title": snippet.get("channelTitle"),
                    "thumbnail": snippet.get("thumbnails", {}).get("high", {}).get("url"),
                    "tags": snippet.get("tags", []),
                    "view_count": int(stats.get("viewCount", 0)),
                    "like_count": int(stats.get("likeCount", 0)),
                    "comment_count": int(stats.get("commentCount", 0)),
                    "duration": self._parse_duration_seconds(details.get("duration")),
                    "video_url": f"https://www.youtube.com/watch?v={video['id']}",
                })
            
            logger.info(f"Fetched {len(videos)} videos from channel {channel_id}")
            return videos
        
        except HttpError as e:
            logger.error(f"Error fetching videos for channel {channel_id}: {e}")
            return []
    
    def get_video_comments(
        self,
        video_id: str,
        max_results: int = 20,
        order: str = "relevance"
    ) -> list[dict[str, Any]]:
        """
        Fetch top comments from a video
        
        Args:
            video_id: YouTube video ID
            max_results: Maximum number of comments to fetch
            order: Sort order - time, relevance
        
        Returns:
            List of comment dicts
        """
        try:
            request = self.youtube.commentThreads().list(
                part="snippet",
                videoId=video_id,
                maxResults=min(max_results, 100),
                order=order,
                textFormat="plainText"
            )
            response = request.execute()
            
            comments = []
            for item in response.get("items", []):
                snippet = item["snippet"]["topLevelComment"]["snippet"]
                
                comments.append({
                    "comment_id": item["id"],
                    "video_id": video_id,
                    "author": snippet.get("authorDisplayName"),
                    "author_channel_id": snippet.get("authorChannelId", {}).get("value"),
                    "text": snippet.get("textDisplay"),
                    "like_count": int(snippet.get("likeCount", 0)),
                    "published_at": snippet.get("publishedAt"),
                    "updated_at": snippet.get("updatedAt"),
                })
            
            logger.info(f"Fetched {len(comments)} comments from video {video_id}")
            return comments
        
        except HttpError as e:
            # Comments might be disabled
            if e.resp.status == 403:
                logger.warning(f"Comments disabled for video {video_id}")
            else:
                logger.error(f"Error fetching comments for video {video_id}: {e}")
            return []
    
    def normalize_to_creator_profile(
        self,
        creator_id: str,
        channel_info: dict[str, Any],
        videos: list[dict[str, Any]],
        niche: str = "YouTube creator",
        audience_persona: list[str] = None
    ) -> CreatorProfile:
        """Convert YouTube channel data to CreatorProfile model"""
        
        # Calculate average engagement from recent videos
        recent_videos = videos[:5] if len(videos) >= 5 else videos
        avg_likes = int(sum(v["like_count"] for v in recent_videos) / max(len(recent_videos), 1))
        avg_comments = int(sum(v["comment_count"] for v in recent_videos) / max(len(recent_videos), 1))
        
        # Count videos from last 30 days
        now = datetime.now(UTC)
        recent_count = 0
        for video in videos:
            pub_date = datetime.fromisoformat(video["published_at"].replace("Z", "+00:00"))
            if (now - pub_date).days <= 30:
                recent_count += 1
        
        return CreatorProfile(
            creator_id=creator_id,
            handle=channel_info.get("custom_url", channel_info["channel_id"]),
            display_name=channel_info["title"],
            primary_platform=SourcePlatform.youtube,
            profile_url=f"https://www.youtube.com/channel/{channel_info['channel_id']}",
            youtube_channel_url=f"https://www.youtube.com/channel/{channel_info['channel_id']}",
            website_url=None,
            niche=niche,
            bio=channel_info.get("description", "")[:500],  # Limit to 500 chars
            followers=channel_info.get("subscriber_count", 0),
            avg_likes=avg_likes,
            avg_comments=avg_comments,
            posts_last_30_days=recent_count,
            audience_persona=audience_persona or ["youtube_viewers"],
        )
    
    def normalize_to_content_records(
        self,
        creator_id: str,
        videos: list[dict[str, Any]]
    ) -> list[ContentRecord]:
        """Convert YouTube videos to ContentRecord models"""
        
        records = []
        for video in videos:
            pub_date = datetime.fromisoformat(video["published_at"].replace("Z", "+00:00"))
            
            records.append(
                ContentRecord(
                    content_id=f"yt_{video['video_id']}",
                    creator_id=creator_id,
                    platform=SourcePlatform.youtube,
                    content_type=ContentType.short_video if self._is_short(video) else ContentType.video,
                    source_url=video["video_url"],
                    title=video["title"],
                    caption=video.get("description", ""),
                    published_at=pub_date,
                    likes=video["like_count"],
                    comments_count=video["comment_count"],
                    views=video["view_count"],
                    raw_payload_path=f"youtube_{video['video_id']}.json",
                )
            )
        
        return records
    
    def normalize_to_comment_records(
        self,
        creator_id: str,
        comments: list[dict[str, Any]]
    ) -> list[CommentRecord]:
        """Convert YouTube comments to CommentRecord models"""
        
        records = []
        for comment in comments:
            pub_date = datetime.fromisoformat(comment["published_at"].replace("Z", "+00:00"))
            
            records.append(
                CommentRecord(
                    comment_id=f"yt_comment_{comment['comment_id']}",
                    content_id=f"yt_{comment['video_id']}",
                    creator_id=creator_id,
                    author_name=comment["author"],
                    text=comment["text"],
                    likes=comment["like_count"],
                    published_at=pub_date,
                    source_url=None,
                )
            )
        
        return records

    def _is_short(self, video: dict[str, Any]) -> bool:
        duration_seconds = int(video.get("duration") or 0)
        return duration_seconds > 0 and duration_seconds <= 90

    def _parse_duration_seconds(self, iso_duration: str | None) -> int:
        if not iso_duration:
            return 0
        match = re.fullmatch(
            r"PT(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?",
            iso_duration,
        )
        if not match:
            return 0
        hours = int(match.group("hours") or 0)
        minutes = int(match.group("minutes") or 0)
        seconds = int(match.group("seconds") or 0)
        return hours * 3600 + minutes * 60 + seconds
