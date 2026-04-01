"""
Test script for YouTube Data API integration

This script tests the YouTube API service and adapter to ensure 
the API key works and data can be fetched correctly.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COMMON = ROOT / "services" / "common"
if str(COMMON) not in sys.path:
    sys.path.insert(0, str(COMMON))

from adobe_influencer.core.config import AppSettings
from adobe_influencer.core.logging import configure_logging, get_logger
from adobe_influencer.core.models import CreatorSeed, SourcePlatform
from adobe_influencer.ingestion.youtube_service import YouTubeAPIService
from adobe_influencer.ingestion.adapters import YouTubeAPIAdapter

logger = get_logger(__name__)


def test_youtube_api_service():
    """Test the YouTube API service with a sample channel"""
    
    settings = AppSettings()
    configure_logging(settings.log_level)
    
    if not settings.youtube_api_key:
        print("❌ YOUTUBE_API_KEY not set in .env file!")
        print("Please add: YOUTUBE_API_KEY=your_api_key_here")
        return False
    
    print(f"✅ YouTube API key found: {settings.youtube_api_key[:20]}...")
    
    # Initialize service
    try:
        youtube_service = YouTubeAPIService(settings.youtube_api_key)
        print("✅ YouTube API service initialized")
    except Exception as e:
        print(f"❌ Failed to initialize YouTube service: {e}")
        return False
    
    # Test with a popular design channel (The Futur)
    test_channel_url = "https://www.youtube.com/@thefutur"
    
    print(f"\n📺 Testing with channel: {test_channel_url}")
    
    # Extract channel ID
    try:
        channel_id = youtube_service.extract_channel_id(test_channel_url)
        print(f"✅ Extracted channel ID: {channel_id}")
    except Exception as e:
        print(f"❌ Failed to extract channel ID: {e}")
        return False
    
    # Get channel info
    try:
        channel_info = youtube_service.get_channel_info(channel_id)
        if channel_info:
            print(f"✅ Channel info retrieved:")
            print(f"   - Title: {channel_info['title']}")
            print(f"   - Subscribers: {channel_info['subscriber_count']:,}")
            print(f"   - Videos: {channel_info['video_count']:,}")
            print(f"   - Views: {channel_info['view_count']:,}")
        else:
            print("❌ No channel info returned")
            return False
    except Exception as e:
        print(f"❌ Failed to get channel info: {e}")
        return False
    
    # Get recent videos
    try:
        videos = youtube_service.get_channel_videos(channel_id, max_results=5)
        if videos:
            print(f"\n✅ Retrieved {len(videos)} videos:")
            for i, video in enumerate(videos[:3], 1):
                print(f"   {i}. {video['title'][:60]}...")
                print(f"      - Views: {video['view_count']:,} | Likes: {video['like_count']:,} | Comments: {video['comment_count']:,}")
        else:
            print("❌ No videos returned")
            return False
    except Exception as e:
        print(f"❌ Failed to get videos: {e}")
        return False
    
    # Get comments from first video
    if videos:
        try:
            first_video = videos[0]
            comments = youtube_service.get_video_comments(first_video['video_id'], max_results=5)
            if comments:
                print(f"\n✅ Retrieved {len(comments)} comments from first video:")
                for i, comment in enumerate(comments[:3], 1):
                    text = comment['text'][:80].replace('\n', ' ')
                    print(f"   {i}. {comment['author']}: {text}...")
            else:
                print("⚠️ No comments (might be disabled)")
        except Exception as e:
            print(f"⚠️ Could not fetch comments: {e}")
    
    print("\n" + "="*60)
    print("✅ ALL TESTS PASSED! YouTube API integration is working!")
    print("="*60)
    return True


def test_youtube_adapter():
    """Test the full YouTube adapter with mock creator seed"""
    
    print("\n\n" + "="*60)
    print("Testing YouTube Adapter Integration")
    print("="*60 + "\n")
    
    settings = AppSettings()
    settings.ensure_paths()
    
    # Create test seed for a design YouTuber
    test_seed = CreatorSeed(
        creator_id="test_youtube_futur",
        handle="thefutur",
        display_name="The Futur",
        profile_url="https://www.youtube.com/@thefutur",
        youtube_channel_url="https://www.youtube.com/@thefutur",
        primary_platform=SourcePlatform.youtube,
        niche="Design education and business",
        bio="Teaching design, branding, and business skills",
        audience_persona=["designers", "entrepreneurs", "creatives"]
    )
    
    # Initialize adapter
    try:
        adapter = YouTubeAPIAdapter(
            api_key=settings.youtube_api_key,
            raw_lake_dir=settings.raw_lake_dir,
            videos_per_channel=5,
            comments_per_video=10
        )
        print("✅ YouTube adapter initialized")
    except Exception as e:
        print(f"❌ Failed to initialize adapter: {e}")
        return False
    
    # Run ingestion
    try:
        creators, content, comments = adapter.ingest([test_seed])
        
        if creators:
            creator = creators[0]
            print(f"\n✅ Creator Profile Created:")
            print(f"   - ID: {creator.creator_id}")
            print(f"   - Name: {creator.display_name}")
            print(f"   - Handle: {creator.handle}")
            print(f"   - Followers: {creator.followers:,}")
            print(f"   - Avg Likes: {creator.avg_likes:,}")
            print(f"   - Avg Comments: {creator.avg_comments:,}")
            print(f"   - Posts (last 30d): {creator.posts_last_30_days}")
        
        print(f"\n✅ Content Records: {len(content)} videos")
        if content:
            print(f"   Sample: {content[0].title[:60]}...")
        
        print(f"\n✅ Comment Records: {len(comments)} comments")
        if comments:
            print(f"   Sample: {comments[0].text[:60]}...")
        
        # Check raw data was saved
        raw_file = settings.raw_lake_dir / f"{test_seed.creator_id}_youtube.json"
        if raw_file.exists():
            data = json.loads(raw_file.read_text(encoding='utf-8'))
            print(f"\n✅ Raw data saved to: {raw_file}")
            print(f"   - Channel data: {len(data['channel'])} fields")
            print(f"   - Videos: {len(data['videos'])}")
            print(f"   - Comments: {len(data['comments'])}")
        
        print("\n" + "="*60)
        print("✅ ADAPTER TEST PASSED!")
        print("="*60)
        return True
        
    except Exception as e:
        print(f"❌ Ingestion failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all YouTube API tests"""
    
    print("\n" + "="*60)
    print("YouTube Data API Integration Test Suite")
    print("="*60 + "\n")
    
    # Test 1: Basic API service
    test1_passed = test_youtube_api_service()
    
    if not test1_passed:
        print("\n❌ Basic API test failed. Please check your API key and quota.")
        return
    
    # Test 2: Full adapter
    test2_passed = test_youtube_adapter()
    
    if test1_passed and test2_passed:
        print("\n\n🎉 ALL TESTS PASSED!")
        print("\nYou can now use YouTube API in your pipeline:")
        print("1. Add youtube_channel_url to creator seeds")
        print("2. Use YouTubeAPIAdapter instead of MockSeedAdapter")
        print("3. Run your pipeline as normal")
    else:
        print("\n\n⚠️ Some tests failed. Check the output above for details.")


if __name__ == "__main__":
    main()
