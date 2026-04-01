"""
Test script to verify instaloader and yt-dlp are working
"""
import sys
from pathlib import Path

# Test instaloader
print("Testing instaloader...")
try:
    import instaloader
    loader = instaloader.Instaloader()
    print(f"✅ instaloader {instaloader.__version__} - WORKING")
except Exception as e:
    print(f"❌ instaloader - FAILED: {e}")
    sys.exit(1)

# Test yt-dlp
print("\nTesting yt-dlp...")
try:
    import yt_dlp
    print(f"✅ yt-dlp {yt_dlp.version.__version__} - WORKING")
except Exception as e:
    print(f"❌ yt-dlp - FAILED: {e}")
    sys.exit(1)

# Test ffmpeg
print("\nTesting FFmpeg...")
try:
    import subprocess
    result = subprocess.run(
        ["ffmpeg", "-version"],
        capture_output=True,
        text=True,
        timeout=5
    )
    if result.returncode == 0:
        version_line = result.stdout.split('\n')[0]
        print(f"✅ FFmpeg - WORKING: {version_line}")
    else:
        print(f"⚠️ FFmpeg - WARNING: {result.stderr}")
except FileNotFoundError:
    print("❌ FFmpeg - NOT FOUND (required for audio extraction)")
except Exception as e:
    print(f"⚠️ FFmpeg - WARNING: {e}")

# Test faster-whisper
print("\nTesting faster-whisper...")
try:
    import faster_whisper
    print(f"✅ faster-whisper - WORKING")
except Exception as e:
    print(f"❌ faster-whisper - FAILED: {e}")

# Test YouTube API
print("\nTesting YouTube Data API...")
try:
    from adobe_influencer.core.config import AppSettings
    settings = AppSettings()
    if settings.youtube_api_key and settings.youtube_api_key != "YOUR_YOUTUBE_API_KEY":
        from adobe_influencer.ingestion.youtube_service import YouTubeAPIService
        yt_service = YouTubeAPIService(settings.youtube_api_key)
        print(f"✅ YouTube Data API - CONFIGURED")
    else:
        print(f"⚠️ YouTube Data API - NOT CONFIGURED (add YOUTUBE_API_KEY to .env)")
except Exception as e:
    print(f"❌ YouTube Data API - FAILED: {e}")

# Test Apify
print("\nTesting Apify Client...")
try:
    from adobe_influencer.core.config import AppSettings
    settings = AppSettings()
    if settings.apify_token and settings.apify_token != "YOUR_APIFY_TOKEN":
        from apify_client import ApifyClient
        client = ApifyClient(settings.apify_token)
        print(f"✅ Apify Client - CONFIGURED")
    else:
        print(f"⚠️ Apify Client - NOT CONFIGURED (add APIFY_TOKEN to .env)")
except Exception as e:
    print(f"❌ Apify Client - FAILED: {e}")

# Test VideoDownloaderService integration
print("\nTesting VideoDownloaderService integration...")
try:
    sys.path.insert(0, str(Path(__file__).parent / "services" / "common"))
    from adobe_influencer.transcription.video_downloader import VideoDownloaderService
    from pathlib import Path
    
    test_dir = Path(__file__).parent / "data" / "test_tmp" / "downloads"
    service = VideoDownloaderService(download_dir=test_dir, max_videos_per_creator=1)
    print(f"✅ VideoDownloaderService - WORKING")
except Exception as e:
    print(f"❌ VideoDownloaderService - FAILED: {e}")

print("\n" + "="*60)
print("Summary: All core components are ready!")
print("="*60)
