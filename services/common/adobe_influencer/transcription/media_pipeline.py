"""
Media Pipeline

Complete pipeline for downloading, extracting audio, and transcribing
creator videos from Instagram and YouTube.
"""

from __future__ import annotations

import json
from pathlib import Path

from adobe_influencer.core.logging import get_logger
from adobe_influencer.core.models import ContentRecord, CreatorProfile, TranscriptSegment
from adobe_influencer.transcription.video_downloader import VideoDownloaderService, DownloadedMedia
from adobe_influencer.transcription.service import (
    FasterWhisperAdapter,
    extract_audio_with_ffmpeg
)

logger = get_logger(__name__)


class MediaPipeline:
    """
    Complete pipeline for processing creator media:
    1. Download videos/reels/shorts
    2. Extract audio using FFmpeg
    3. Transcribe audio using Whisper
    4. Store transcripts
    """
    
    def __init__(
        self,
        download_dir: Path,
        audio_dir: Path,
        transcript_dir: Path,
        whisper_model: str = "base",
        max_videos_per_creator: int = 10,
        skip_existing: bool = True
    ):
        """
        Initialize media pipeline
        
        Args:
            download_dir: Directory for downloaded videos
            audio_dir: Directory for extracted audio files
            transcript_dir: Directory for transcript JSON files
            whisper_model: Whisper model size (tiny, base, small, medium, large)
            max_videos_per_creator: Maximum videos to process per creator
            skip_existing: Skip already processed videos
        """
        self.download_dir = download_dir
        self.audio_dir = audio_dir
        self.transcript_dir = transcript_dir
        self.max_videos_per_creator = max_videos_per_creator
        self.skip_existing = skip_existing
        
        # Create directories
        for directory in [download_dir, audio_dir, transcript_dir]:
            directory.mkdir(parents=True, exist_ok=True)
        
        # Initialize services
        self.downloader = VideoDownloaderService(
            download_dir=download_dir,
            max_videos_per_creator=max_videos_per_creator
        )
        
        self.transcriber = FasterWhisperAdapter(
            model_name=whisper_model,
            device="auto",
            compute_type="int8"
        )
        
        logger.info(
            f"Media pipeline initialized: "
            f"model={whisper_model}, max_videos={max_videos_per_creator}"
        )
    
    def process_creator(
        self,
        creator: CreatorProfile,
        content_items: list[ContentRecord]
    ) -> list[TranscriptSegment]:
        """
        Process all media for a creator
        
        Args:
            creator: Creator profile
            content_items: Content records for this creator
        
        Returns:
            List of transcript segments for all videos
        """
        logger.info(f"Processing media for {creator.display_name} (@{creator.handle})")
        
        all_transcripts = []
        
        # Step 1: Download videos
        downloaded_media = self.downloader.download_all_for_creator(creator, content_items)
        
        if not downloaded_media:
            logger.info(f"No videos downloaded for {creator.handle}")
            return []
        
        # Step 2 & 3: Extract audio and transcribe each video
        for media in downloaded_media:
            try:
                transcripts = self._process_single_media(media)
                all_transcripts.extend(transcripts)
            except Exception as e:
                logger.error(f"Failed to process {media.content_id}: {e}")
        
        logger.info(
            f"Completed processing for {creator.handle}: "
            f"{len(downloaded_media)} videos, {len(all_transcripts)} transcript segments"
        )
        
        return all_transcripts
    
    def _process_single_media(self, media: DownloadedMedia) -> list[TranscriptSegment]:
        """
        Process a single downloaded media item
        
        Args:
            media: Downloaded media item
        
        Returns:
            List of transcript segments
        """
        if not media.video_path or not media.video_path.exists():
            logger.warning(f"Video file missing for {media.content_id}")
            return []
        
        # Define output paths
        audio_filename = f"{media.content_id}.mp3"
        audio_path = self.audio_dir / audio_filename
        
        transcript_filename = f"{media.content_id}_transcript.json"
        transcript_path = self.transcript_dir / transcript_filename
        
        # Check if already processed
        if self.skip_existing and transcript_path.exists():
            logger.info(f"Skipping {media.content_id} (already transcribed)")
            # Load existing transcripts
            try:
                existing_data = json.loads(transcript_path.read_text(encoding='utf-8'))
                return [TranscriptSegment(**seg) for seg in existing_data.get('segments', [])]
            except Exception as e:
                logger.warning(f"Could not load existing transcript: {e}")
        
        # Step 1: Extract audio
        try:
            if not audio_path.exists():
                extract_audio_with_ffmpeg(media.video_path, audio_path)
            else:
                logger.info(f"Audio already extracted: {audio_filename}")
            
            media.audio_path = audio_path
            
        except Exception as e:
            logger.error(f"Audio extraction failed for {media.content_id}: {e}")
            return []
        
        # Step 2: Transcribe audio
        try:
            transcripts = self.transcriber.transcribe_audio_file(
                audio_path=audio_path,
                content_id=media.content_id,
                creator_id=media.creator_id
            )
            
            if not transcripts:
                logger.warning(f"No transcription generated for {media.content_id}")
                return []
            
            # Save transcripts
            transcript_data = {
                "content_id": media.content_id,
                "creator_id": media.creator_id,
                "platform": media.platform.value,
                "source_url": media.source_url,
                "video_path": str(media.video_path),
                "audio_path": str(audio_path),
                "duration_seconds": media.duration_seconds,
                "segment_count": len(transcripts),
                "segments": [
                    {
                        "transcript_id": seg.transcript_id,
                        "start_seconds": seg.start_seconds,
                        "end_seconds": seg.end_seconds,
                        "text": seg.text,
                        "confidence": seg.confidence,
                    }
                    for seg in transcripts
                ]
            }
            
            transcript_path.write_text(
                json.dumps(transcript_data, indent=2, ensure_ascii=False),
                encoding='utf-8'
            )
            
            logger.info(f"Saved transcript: {transcript_filename}")
            return transcripts
            
        except Exception as e:
            logger.error(f"Transcription failed for {media.content_id}: {e}")
            return []
    
    def process_batch(
        self,
        creators: list[CreatorProfile],
        content_by_creator: dict[str, list[ContentRecord]]
    ) -> dict[str, list[TranscriptSegment]]:
        """
        Process media for multiple creators
        
        Args:
            creators: List of creator profiles
            content_by_creator: Dict mapping creator_id to content records
        
        Returns:
            Dict mapping creator_id to transcript segments
        """
        all_transcripts = {}
        
        for creator in creators:
            content_items = content_by_creator.get(creator.creator_id, [])
            if content_items:
                transcripts = self.process_creator(creator, content_items)
                all_transcripts[creator.creator_id] = transcripts
        
        total_segments = sum(len(segs) for segs in all_transcripts.values())
        logger.info(
            f"Batch processing complete: "
            f"{len(creators)} creators, {total_segments} total transcript segments"
        )
        
        return all_transcripts
    
    def get_statistics(self) -> dict:
        """Get pipeline statistics"""
        
        # Count downloaded videos
        video_count = sum(1 for _ in self.download_dir.rglob("*.mp4"))
        video_count += sum(1 for _ in self.download_dir.rglob("*.webm"))
        
        # Count extracted audio files
        audio_count = sum(1 for _ in self.audio_dir.rglob("*.mp3"))
        
        # Count transcripts
        transcript_count = sum(1 for _ in self.transcript_dir.rglob("*_transcript.json"))
        
        return {
            "videos_downloaded": video_count,
            "audio_extracted": audio_count,
            "transcripts_created": transcript_count,
            "download_dir": str(self.download_dir),
            "audio_dir": str(self.audio_dir),
            "transcript_dir": str(self.transcript_dir),
        }
