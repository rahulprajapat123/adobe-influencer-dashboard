"""
Video Downloader Service

Downloads videos, reels, and shorts from Instagram and YouTube
using instaloader and yt-dlp.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass, asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import instaloader

from adobe_influencer.core.logging import get_logger
from adobe_influencer.core.models import ContentRecord, ContentType, CreatorProfile, SourcePlatform

logger = get_logger(__name__)


@dataclass
class DownloadedMedia:
    """Represents a downloaded video/reel/short with metadata"""
    content_id: str
    creator_id: str
    platform: SourcePlatform
    content_type: ContentType
    source_url: str
    video_path: Path | None = None
    audio_path: Path | None = None
    thumbnail_path: Path | None = None
    metadata_path: Path | None = None
    title: str = ""
    description: str = ""
    duration_seconds: float = 0.0
    views: int = 0
    likes: int = 0
    comments_count: int = 0
    published_at: datetime | None = None


class VideoDownloaderService:
    """Service for downloading videos from Instagram and YouTube"""
    
    def __init__(self, download_dir: Path, max_videos_per_creator: int = 10):
        """
        Initialize video downloader service
        
        Args:
            download_dir: Directory to store downloaded media
            max_videos_per_creator: Maximum videos to download per creator
        """
        self.download_dir = download_dir
        self.max_videos_per_creator = max_videos_per_creator
        self.download_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize instaloader
        self.insta_loader = instaloader.Instaloader(
            download_videos=True,
            download_video_thumbnails=True,
            download_geotags=False,
            download_comments=False,
            save_metadata=True,
            compress_json=False,
            post_metadata_txt_pattern="",
            dirname_pattern="{profile}",
            filename_pattern="{shortcode}"
        )
        
        logger.info("Video downloader service initialized")
    
    def download_instagram_videos(
        self,
        creator: CreatorProfile,
        content_items: list[ContentRecord],
        max_items: int | None = None
    ) -> list[DownloadedMedia]:
        """
        Download Instagram videos/reels using instaloader
        
        Args:
            creator: Creator profile
            content_items: List of content records with video URLs
            max_items: Maximum items to download (overrides default)
        
        Returns:
            List of downloaded media items
        """
        max_items = max_items or self.max_videos_per_creator
        
        # Filter for video content only
        video_items = [
            item for item in content_items 
            if item.content_type in (ContentType.video, ContentType.short_video)
        ][:max_items]
        
        if not video_items:
            logger.info(f"No video content found for {creator.handle}")
            return []
        
        downloaded = []
        creator_dir = self.download_dir / f"instagram_{creator.creator_id}"
        creator_dir.mkdir(parents=True, exist_ok=True)
        
        for item in video_items:
            try:
                media = self._download_instagram_post(creator, item, creator_dir)
                if media:
                    downloaded.append(media)
            except Exception as e:
                logger.error(f"Failed to download {item.content_id}: {e}")
        
        logger.info(f"Downloaded {len(downloaded)}/{len(video_items)} Instagram videos for {creator.handle}")
        return downloaded
    
    def _download_instagram_post(
        self,
        creator: CreatorProfile,
        content: ContentRecord,
        output_dir: Path
    ) -> DownloadedMedia | None:
        """Download a single Instagram post/reel"""
        
        try:
            # Extract shortcode from URL or content_id
            shortcode = self._extract_instagram_shortcode(content.source_url, content.content_id)
            if not shortcode:
                logger.warning(f"Could not extract shortcode from {content.source_url}")
                return None
            
            # Download using instaloader
            post = instaloader.Post.from_shortcode(self.insta_loader.context, shortcode)
            
            # Download the post
            self.insta_loader.download_post(post, target=str(output_dir))
            
            # Find downloaded files
            video_path = None
            for ext in ['.mp4', '.mov']:
                candidate = output_dir / f"{shortcode}{ext}"
                if candidate.exists():
                    video_path = candidate
                    break
            
            if not video_path:
                logger.warning(f"Video file not found for {shortcode}")
                return None
            
            # Get metadata
            metadata_path = output_dir / f"{shortcode}.json"
            metadata = {}
            if metadata_path.exists():
                metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
            
            # Create DownloadedMedia record
            media = DownloadedMedia(
                content_id=content.content_id,
                creator_id=creator.creator_id,
                platform=SourcePlatform.instagram,
                content_type=content.content_type,
                source_url=content.source_url,
                video_path=video_path,
                metadata_path=metadata_path if metadata_path.exists() else None,
                thumbnail_path=output_dir / f"{shortcode}.jpg" if (output_dir / f"{shortcode}.jpg").exists() else None,
                title=content.title or "",
                description=content.caption or "",
                duration_seconds=post.video_duration if post.is_video else 0.0,
                views=post.video_view_count if post.is_video else 0,
                likes=content.likes,
                comments_count=content.comments_count,
                published_at=content.published_at,
            )
            
            # Save media metadata
            media_json = output_dir / f"{shortcode}_media.json"
            media_json.write_text(json.dumps(asdict(media), indent=2, default=str), encoding='utf-8')
            
            logger.info(f"Downloaded Instagram video: {shortcode}")
            return media
            
        except Exception as e:
            logger.error(f"Error downloading Instagram post {content.content_id}: {e}")
            return None
    
    def download_youtube_videos(
        self,
        creator: CreatorProfile,
        content_items: list[ContentRecord],
        max_items: int | None = None
    ) -> list[DownloadedMedia]:
        """
        Download YouTube videos/shorts using yt-dlp
        
        Args:
            creator: Creator profile
            content_items: List of content records with YouTube URLs
            max_items: Maximum items to download
        
        Returns:
            List of downloaded media items
        """
        max_items = max_items or self.max_videos_per_creator
        
        # Filter for video content
        video_items = [
            item for item in content_items 
            if item.content_type in (ContentType.video, ContentType.short_video)
        ][:max_items]
        
        if not video_items:
            logger.info(f"No video content found for {creator.handle}")
            return []
        
        downloaded = []
        creator_dir = self.download_dir / f"youtube_{creator.creator_id}"
        creator_dir.mkdir(parents=True, exist_ok=True)
        
        for item in video_items:
            try:
                media = self._download_youtube_video(creator, item, creator_dir)
                if media:
                    downloaded.append(media)
            except Exception as e:
                logger.error(f"Failed to download {item.content_id}: {e}")
        
        logger.info(f"Downloaded {len(downloaded)}/{len(video_items)} YouTube videos for {creator.handle}")
        return downloaded
    
    def _download_youtube_video(
        self,
        creator: CreatorProfile,
        content: ContentRecord,
        output_dir: Path
    ) -> DownloadedMedia | None:
        """Download a single YouTube video using yt-dlp"""
        
        try:
            video_id = self._extract_youtube_video_id(content.source_url, content.content_id)
            if not video_id:
                logger.warning(f"Could not extract video ID from {content.source_url}")
                return None
            
            # Output template for yt-dlp
            output_template = str(output_dir / f"{video_id}.%(ext)s")
            
            # yt-dlp command
            # Format: best video + best audio, or best single file
            cmd = [
                "yt-dlp",
                "--format", "bv*+ba/b",  # Best video + audio or best single
                "--output", output_template,
                "--write-info-json",
                "--write-thumbnail",
                "--no-playlist",
                content.source_url
            ]
            
            # Check if yt-dlp is available
            if not shutil.which("yt-dlp"):
                logger.error("yt-dlp not found. Install: pip install yt-dlp")
                return None
            
            # Run download
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode != 0:
                logger.error(f"yt-dlp failed for {video_id}: {result.stderr}")
                return None
            
            # Find downloaded video file
            video_path = None
            for ext in ['.mp4', '.webm', '.mkv']:
                candidate = output_dir / f"{video_id}{ext}"
                if candidate.exists():
                    video_path = candidate
                    break
            
            if not video_path:
                logger.warning(f"Video file not found for {video_id}")
                return None
            
            # Load metadata
            metadata_path = output_dir / f"{video_id}.info.json"
            metadata = {}
            if metadata_path.exists():
                metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
            
            # Create DownloadedMedia record
            media = DownloadedMedia(
                content_id=content.content_id,
                creator_id=creator.creator_id,
                platform=SourcePlatform.youtube,
                content_type=content.content_type,
                source_url=content.source_url,
                video_path=video_path,
                metadata_path=metadata_path if metadata_path.exists() else None,
                thumbnail_path=self._find_thumbnail(output_dir, video_id),
                title=content.title or metadata.get('title', ''),
                description=content.caption or metadata.get('description', ''),
                duration_seconds=metadata.get('duration', 0.0),
                views=content.views or metadata.get('view_count', 0),
                likes=content.likes or metadata.get('like_count', 0),
                comments_count=content.comments_count or metadata.get('comment_count', 0),
                published_at=content.published_at,
            )
            
            # Save media metadata
            media_json = output_dir / f"{video_id}_media.json"
            media_json.write_text(json.dumps(asdict(media), indent=2, default=str), encoding='utf-8')
            
            logger.info(f"Downloaded YouTube video: {video_id}")
            return media
            
        except Exception as e:
            logger.error(f"Error downloading YouTube video {content.content_id}: {e}")
            return None
    
    def _extract_instagram_shortcode(self, url: str, content_id: str) -> str | None:
        """Extract Instagram shortcode from URL or content_id"""
        # Try URL first
        if url:
            match = re.search(r'/p/([A-Za-z0-9_-]+)/', url) or re.search(r'/reel/([A-Za-z0-9_-]+)/', url)
            if match:
                return match.group(1)
        
        # Try content_id (format: ig_12345 or similar)
        if content_id.startswith('ig_'):
            return content_id[3:]
        
        return None
    
    def _extract_youtube_video_id(self, url: str, content_id: str) -> str | None:
        """Extract YouTube video ID from URL or content_id"""
        # Try URL patterns
        if url:
            # youtube.com/watch?v=VIDEO_ID
            match = re.search(r'[?&]v=([A-Za-z0-9_-]{11})', url)
            if match:
                return match.group(1)
            
            # youtu.be/VIDEO_ID or youtube.com/shorts/VIDEO_ID
            match = re.search(r'(?:youtu\.be/|youtube\.com/shorts/)([A-Za-z0-9_-]{11})', url)
            if match:
                return match.group(1)
        
        # Try content_id (format: yt_VIDEO_ID)
        if content_id.startswith('yt_'):
            return content_id[3:]
        
        return None
    
    def _find_thumbnail(self, directory: Path, video_id: str) -> Path | None:
        """Find thumbnail image for a video"""
        for ext in ['.jpg', '.png', '.webp']:
            thumbnail = directory / f"{video_id}{ext}"
            if thumbnail.exists():
                return thumbnail
        return None
    
    def download_all_for_creator(
        self,
        creator: CreatorProfile,
        content_items: list[ContentRecord]
    ) -> list[DownloadedMedia]:
        """
        Download all videos for a creator (both Instagram and YouTube)
        
        Args:
            creator: Creator profile
            content_items: All content records for this creator
        
        Returns:
            List of all downloaded media
        """
        all_media = []
        
        # Download Instagram content
        instagram_content = [
            item for item in content_items 
            if item.platform == SourcePlatform.instagram
        ]
        if instagram_content:
            instagram_media = self.download_instagram_videos(creator, instagram_content)
            all_media.extend(instagram_media)
        
        # Download YouTube content
        youtube_content = [
            item for item in content_items 
            if item.platform == SourcePlatform.youtube
        ]
        if youtube_content:
            youtube_media = self.download_youtube_videos(creator, youtube_content)
            all_media.extend(youtube_media)
        
        return all_media
