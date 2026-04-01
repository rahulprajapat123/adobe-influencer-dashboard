"""
Direct test of media pipeline with real videos
"""
import os
import sys
sys.path.insert(0, 'services/common')

from adobe_influencer.transcription.media_pipeline import MediaPipeline
from adobe_influencer.core.config import AppSettings
from adobe_influencer.core.models import CreatorProfile, ContentRecord, SourcePlatform, ContentType
from datetime import datetime

def main():
    print("=" * 60)
    print("Direct Media Pipeline Test")
    print("=" * 60)
    
    # Initialize settings
    settings = AppSettings()
    
    # Initialize pipeline with directories
    pipeline = MediaPipeline(
        download_dir=settings.media_download_dir,
        audio_dir=settings.media_audio_dir,
        transcript_dir=settings.media_transcript_dir,
        whisper_model="base",
        max_videos_per_creator=1  # Just test 1 video
    )
    print(f"\n✅ Pipeline initialized")
    print(f"   - Whisper model: base")
    print(f"   - Max videos: 1")
    
    # Test with YouTube (easier than Instagram)
    print("\n" + "=" * 60)
    print("Testing YouTube Short")
    print("=" * 60)
    
    # Create test creator profile
    test_creator = CreatorProfile(
        creator_id="test_creator_1",
        display_name="The Futur",
        handle="@thefutur",
        primary_platform=SourcePlatform.youtube,
        profile_url="https://www.youtube.com/@thefutur",
        niche="Design & Business",
        bio="Design education",
        followers=2800000
    )
    
    # Create test content record
    test_content = ContentRecord(
        content_id="test_short_1",
        creator_id="test_creator_1",
        platform=SourcePlatform.youtube,
        content_type=ContentType.short_video,
        source_url="https://www.youtube.com/shorts/dQw4w9WgXcQ",
        published_at=datetime.now(),
        likes=500,
        comments_count=50,
        views=10000,
        raw_payload_path="data/raw_lake/test_short_1.json"
    )
    
    print(f"\n📺 Processing: {test_creator.display_name}")
    print(f"   Video URL: {test_content.source_url}")
    
    try:
        results = pipeline.process_creator(test_creator, [test_content])
        
        print(f"\n✅ Processing complete!")
        print(f"   - Transcripts created: {len(results)}")
        
        for result in results:
            print(f"\n📄 Transcript segment:")
            print(f"   - Content ID: {result.content_id}")
            print(f"   - Text preview: {result.text[:200] if result.text else 'No text'}...")
            
    except Exception as e:
        print(f"\n❌ Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
    
    # Print statistics
    stats = pipeline.get_statistics()
    print(f"\n📊 Pipeline Statistics:")
    print(f"   - Videos downloaded: {stats['videos_downloaded']}")
    print(f"   - Audio extracted: {stats['audio_extracted']}")
    print(f"   - Transcripts created: {stats['transcripts_created']}")
    
    print("\n" + "=" * 60)
    print("Test Complete!")
    print("=" * 60)
    
    print("\n" + "=" * 60)
    print("Test Complete!")
    print("=" * 60)

if __name__ == "__main__":
    main()
