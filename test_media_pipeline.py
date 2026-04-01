"""
Test script for complete media pipeline:
- Download videos/reels/shorts from Instagram or YouTube
- Extract audio using FFmpeg
- Transcribe using Whisper
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COMMON = ROOT / "services" / "common"
if str(COMMON) not in sys.path:
    sys.path.insert(0, str(COMMON))

from adobe_influencer.core.config import AppSettings
from adobe_influencer.core.logging import configure_logging, get_logger
from adobe_influencer.core.models import CreatorProfile, ContentRecord, ContentType, SourcePlatform
from adobe_influencer.transcription.media_pipeline import MediaPipeline
from datetime import datetime, UTC

logger = get_logger(__name__)


def test_instagram_reels():
    """Test downloading and transcribing Instagram reels"""
    
    print("\n" + "="*60)
    print("Testing Instagram Reels Pipeline")
    print("="*60 + "\n")
    
    settings = AppSettings()
    settings.ensure_paths()
    configure_logging(settings.log_level)
    
    # Create test creator (Anik Jain - design creator)
    creator = CreatorProfile(
        creator_id="test_anikjain",
        handle="anikjaindesign",
        display_name="Anik Jain",
        primary_platform=SourcePlatform.instagram,
        profile_url="https://www.instagram.com/anikjaindesign/",
        niche="Brand design and creative education",
        bio="Design creator",
        followers=463212,
        avg_likes=4694,
        avg_comments=133,
        posts_last_30_days=8,
        audience_persona=["designers", "creatives"]
    )
    
    # Create test content (a recent reel)
    content_items = [
        ContentRecord(
            content_id="ig_test_reel_1",
            creator_id="test_anikjain",
            platform=SourcePlatform.instagram,
            content_type=ContentType.short_video,
            source_url="https://www.instagram.com/reel/DWT3VjziLkV/",  # Real reel URL
            title="Design Tutorial",
            caption="Design tips and tricks",
            published_at=datetime.now(UTC),
            likes=5000,
            comments_count=100,
            views=50000,
            raw_payload_path="test"
        )
    ]
    
    # Initialize pipeline
    pipeline = MediaPipeline(
        download_dir=settings.media_download_dir,
        audio_dir=settings.media_audio_dir,
        transcript_dir=settings.media_transcript_dir,
        whisper_model="base",
        max_videos_per_creator=2,
        skip_existing=True
    )
    
    print("✅ Media pipeline initialized")
    print(f"   - Download dir: {settings.media_download_dir}")
    print(f"   - Audio dir: {settings.media_audio_dir}")
    print(f"   - Transcript dir: {settings.media_transcript_dir}")
    
    # Process creator
    print(f"\n📺 Processing {creator.display_name}...")
    transcripts = pipeline.process_creator(creator, content_items)
    
    if transcripts:
        print(f"\n✅ SUCCESS! Generated {len(transcripts)} transcript segments")
        print("\nSample transcripts:")
        for i, seg in enumerate(transcripts[:3], 1):
            print(f"  {i}. [{seg.start_seconds:.1f}s - {seg.end_seconds:.1f}s] {seg.text[:80]}...")
    else:
        print("\n⚠️ No transcripts generated (video might not have audio or download failed)")
    
    # Show statistics
    stats = pipeline.get_statistics()
    print(f"\n📊 Pipeline Statistics:")
    print(f"   - Videos downloaded: {stats['videos_downloaded']}")
    print(f"   - Audio files: {stats['audio_extracted']}")
    print(f"   - Transcripts: {stats['transcripts_created']}")
    
    return len(transcripts) > 0


def test_youtube_shorts():
    """Test downloading and transcribing YouTube shorts"""
    
    print("\n" + "="*60)
    print("Testing YouTube Shorts Pipeline")
    print("="*60 + "\n")
    
    settings = AppSettings()
    settings.ensure_paths()
    
    # Create test creator
    creator = CreatorProfile(
        creator_id="test_youtube_design",
        handle="designcourse",
        display_name="DesignCourse",
        primary_platform=SourcePlatform.youtube,
        profile_url="https://www.youtube.com/@DesignCourse",
        youtube_channel_url="https://www.youtube.com/@DesignCourse",
        niche="UI/UX design education",
        bio="Design tutorials",
        followers=1000000,
        avg_likes=10000,
        avg_comments=500,
        posts_last_30_days=10,
        audience_persona=["designers", "students"]
    )
    
    # Create test content (a YouTube short)
    content_items = [
        ContentRecord(
            content_id="yt_test_short_1",
            creator_id="test_youtube_design",
            platform=SourcePlatform.youtube,
            content_type=ContentType.short_video,
            source_url="https://www.youtube.com/shorts/dQw4w9WgXcQ",  # Example Short URL
            title="Design Tips",
            caption="Quick design tutorial",
            published_at=datetime.now(UTC),
            likes=5000,
            comments_count=100,
            views=100000,
            raw_payload_path="test"
        )
    ]
    
    # Initialize pipeline
    pipeline = MediaPipeline(
        download_dir=settings.media_download_dir,
        audio_dir=settings.media_audio_dir,
        transcript_dir=settings.media_transcript_dir,
        whisper_model="base",
        max_videos_per_creator=2
    )
    
    print("✅ Media pipeline initialized")
    
    # Process creator
    print(f"\n📺 Processing {creator.display_name}...")
    transcripts = pipeline.process_creator(creator, content_items)
    
    if transcripts:
        print(f"\n✅ SUCCESS! Generated {len(transcripts)} transcript segments")
        print("\nSample transcripts:")
        for i, seg in enumerate(transcripts[:3], 1):
            print(f"  {i}. [{seg.start_seconds:.1f}s - {seg.end_seconds:.1f}s] {seg.text[:80]}...")
    else:
        print("\n⚠️ No transcripts generated")
    
    return len(transcripts) > 0


def test_requirements():
    """Check if all required tools are installed"""
    
    print("\n" + "="*60)
    print("Checking Requirements")
    print("="*60 + "\n")
    
    requirements_met = True
    
    # Check FFmpeg
    try:
        from adobe_influencer.transcription.service import find_ffmpeg_binary
        ffmpeg_path = find_ffmpeg_binary()
        print(f"✅ FFmpeg found: {ffmpeg_path}")
    except FileNotFoundError as e:
        print(f"❌ FFmpeg not found: {e}")
        requirements_met = False
    
    # Check yt-dlp
    import shutil
    if shutil.which("yt-dlp"):
        print("✅ yt-dlp found")
    else:
        print("❌ yt-dlp not found. Install: pip install yt-dlp")
        requirements_met = False
    
    # Check instaloader
    try:
        import instaloader
        print("✅ instaloader installed")
    except ImportError:
        print("❌ instaloader not found. Install: pip install instaloader")
        requirements_met = False
    
    # Check faster-whisper
    try:
        import faster_whisper
        print("✅ faster-whisper installed")
    except ImportError:
        print("❌ faster-whisper not found. Install: pip install faster-whisper")
        requirements_met = False
    
    print()
    return requirements_met


def main():
    """Run all media pipeline tests"""
    
    print("\n" + "="*60)
    print("Media Pipeline Test Suite")
    print("Video Download + Audio Extraction + Transcription")
    print("="*60)
    
    # Check requirements first
    if not test_requirements():
        print("\n❌ Some requirements are missing. Please install them first.")
        print("\nInstallation commands:")
        print("  pip install yt-dlp")
        print("  pip install instaloader")
        print("  pip install faster-whisper")
        print("  winget install Gyan.FFmpeg  (Windows)")
        return
    
    print("\n✅ All requirements met!\n")
    
    # Test Instagram
    print("="*60)
    print("NOTE: Instagram downloading requires authentication.")
    print("You may need to login to instaloader first:")
    print("  instaloader --login YOUR_USERNAME")
    print("="*60 + "\n")
    
    choice = input("Test Instagram reels? (y/n): ").lower()
    if choice == 'y':
        try:
            test_instagram_reels()
        except Exception as e:
            print(f"\n❌ Instagram test failed: {e}")
            import traceback
            traceback.print_exc()
    
    # Test YouTube
    print("\n")
    choice = input("Test YouTube shorts? (y/n): ").lower()
    if choice == 'y':
        try:
            test_youtube_shorts()
        except Exception as e:
            print(f"\n❌ YouTube test failed: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "="*60)
    print("Tests Complete!")
    print("="*60)
    print("\nTo enable in your main pipeline:")
    print("1. Set ENABLE_MEDIA_PIPELINE=true in .env")
    print("2. Run your normal pipeline")
    print("3. Videos will be downloaded and transcribed automatically")


if __name__ == "__main__":
    main()
