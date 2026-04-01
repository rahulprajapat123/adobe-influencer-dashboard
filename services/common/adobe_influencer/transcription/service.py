from __future__ import annotations

import json
import os
import shutil
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from adobe_influencer.core.logging import get_logger
from adobe_influencer.core.models import ContentRecord, TranscriptSegment

logger = get_logger(__name__)


class TranscriptionAdapter(ABC):
    @abstractmethod
    def transcribe(self, content_items: list[ContentRecord]) -> list[TranscriptSegment]:
        raise NotImplementedError


class MockTranscriptAdapter(TranscriptionAdapter):
    def __init__(self, sample_dir: Path) -> None:
        self.sample_dir = sample_dir

    def transcribe(self, content_items: list[ContentRecord]) -> list[TranscriptSegment]:
        payload = json.loads((self.sample_dir / "transcripts.json").read_text(encoding="utf-8"))
        content_ids = {item.content_id for item in content_items}
        transcripts = [TranscriptSegment(**row) for row in payload if row["content_id"] in content_ids]
        logger.info("Loaded %s mock transcript segments", len(transcripts))
        return transcripts


class FasterWhisperAdapter(TranscriptionAdapter):
    """Transcription adapter using faster-whisper for local inference"""
    
    def __init__(
        self,
        model_name: str = "base",
        device: str = "auto",
        compute_type: str = "int8",
        download_root: Path | None = None
    ):
        """
        Initialize faster-whisper transcription adapter
        
        Args:
            model_name: Whisper model size (tiny, base, small, medium, large-v2, large-v3)
            device: Device to run on ("cpu", "cuda", or "auto")
            compute_type: Computation precision ("int8", "float16", "float32")
            download_root: Directory to store model files
        """
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        
        try:
            from faster_whisper import WhisperModel
            
            # Auto-detect device if needed
            if self.device == "auto":
                try:
                    import torch
                    self.device = "cuda" if torch.cuda.is_available() else "cpu"
                except ImportError:
                    self.device = "cpu"
            
            # Adjust compute type based on device
            if self.device == "cpu" and self.compute_type == "float16":
                logger.warning("float16 not efficient on CPU, switching to int8")
                self.compute_type = "int8"
            
            logger.info(f"Initializing Whisper model '{model_name}' on {self.device} with {self.compute_type}")
            
            # Initialize model
            self.model = WhisperModel(
                model_name,
                device=self.device,
                compute_type=self.compute_type,
                download_root=str(download_root) if download_root else None
            )
            
            logger.info("Whisper model loaded successfully")
            
        except ImportError as e:
            logger.error("faster-whisper not installed. Install: pip install faster-whisper")
            raise ImportError("faster-whisper package required") from e
    
    def transcribe(self, content_items: list[ContentRecord]) -> list[TranscriptSegment]:
        """
        Transcribe audio/video files using faster-whisper
        
        Note: This expects audio files to already be extracted.
        Use extract_audio_with_ffmpeg() first if you have video files.
        
        Args:
            content_items: List of content records (should have audio_path metadata)
        
        Returns:
            List of transcript segments
        """
        raise NotImplementedError(
            "FasterWhisperAdapter requires audio extraction first. "
            "Use MediaPipeline for complete video->audio->transcript flow."
        )
    
    def transcribe_audio_file(
        self,
        audio_path: Path,
        content_id: str,
        creator_id: str
    ) -> list[TranscriptSegment]:
        """
        Transcribe a single audio file
        
        Args:
            audio_path: Path to audio file (mp3, wav, m4a, etc.)
            content_id: Content ID to associate with segments
            creator_id: Creator ID
        
        Returns:
            List of transcript segments with timestamps
        """
        if not audio_path.exists():
            logger.error(f"Audio file not found: {audio_path}")
            return []
        
        try:
            logger.info(f"Transcribing {audio_path.name}...")
            
            # Run transcription
            segments, info = self.model.transcribe(
                str(audio_path),
                beam_size=5,
                vad_filter=True,  # Voice activity detection
                vad_parameters=dict(min_silence_duration_ms=500)
            )
            
            # Convert to TranscriptSegment models
            transcript_segments = []
            for i, segment in enumerate(segments):
                transcript_segments.append(
                    TranscriptSegment(
                        transcript_id=f"{content_id}_seg_{i}",
                        content_id=content_id,
                        creator_id=creator_id,
                        start_seconds=segment.start,
                        end_seconds=segment.end,
                        text=segment.text.strip(),
                        confidence=segment.avg_logprob  # Log probability as confidence proxy
                    )
                )
            
            logger.info(
                f"Transcribed {audio_path.name}: "
                f"{len(transcript_segments)} segments, "
                f"language: {info.language} "
                f"(probability: {info.language_probability:.2f})"
            )
            
            return transcript_segments
            
        except Exception as e:
            logger.error(f"Transcription failed for {audio_path}: {e}")
            return []


def extract_audio_with_ffmpeg(video_path: Path, audio_path: Path) -> Path:
    """
    Extract audio from video file using FFmpeg
    
    Args:
        video_path: Path to input video file
        audio_path: Path for output audio file (will be created)
    
    Returns:
        Path to extracted audio file
    
    Raises:
        FileNotFoundError: If FFmpeg not found or video doesn't exist
        RuntimeError: If extraction fails
    """
    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")
    
    # Find FFmpeg binary
    ffmpeg_bin = find_ffmpeg_binary()
    
    # Ensure output directory exists
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    
    # FFmpeg command to extract audio
    # -vn: no video
    # -acodec: audio codec 
    # -ar: audio sample rate
    # -ac: audio channels
    cmd = [
        ffmpeg_bin,
        "-i", str(video_path),
        "-vn",  # No video
        "-acodec", "libmp3lame",  # MP3 codec
        "-ar", "16000",  # 16kHz sample rate (good for speech)
        "-ac", "1",  # Mono
        "-b:a", "64k",  # 64kbps bitrate
        "-y",  # Overwrite output file
        str(audio_path)
    ]
    
    try:
        logger.info(f"Extracting audio from {video_path.name}...")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg failed: {result.stderr}")
        
        if not audio_path.exists():
            raise RuntimeError(f"Audio file was not created: {audio_path}")
        
        logger.info(f"Audio extracted to {audio_path.name}")
        return audio_path
        
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Audio extraction timed out for {video_path}")
    except Exception as e:
        raise RuntimeError(f"Audio extraction failed: {e}")


def find_ffmpeg_binary() -> str:
    """
    Find FFmpeg binary on the system
    
    Returns:
        Path to FFmpeg executable
    
    Raises:
        FileNotFoundError: If FFmpeg not found
    """
    # Check environment variable
    env_binary = os.getenv("FFMPEG_BINARY")
    if env_binary and Path(env_binary).exists():
        return env_binary
    
    # Check PATH
    from_path = shutil.which("ffmpeg")
    if from_path:
        return from_path
    
    # Check Windows WinGet packages (common installation location)
    local_appdata = Path(os.getenv("LOCALAPPDATA", ""))
    if local_appdata:
        winget_packages = local_appdata / "Microsoft" / "WinGet" / "Packages"
        for candidate in winget_packages.glob("Gyan.FFmpeg*/*/bin/ffmpeg.exe"):
            if candidate.exists():
                return str(candidate)
    
    raise FileNotFoundError(
        "FFmpeg binary not found. Please install FFmpeg:\n"
        "  - Windows: winget install Gyan.FFmpeg\n"
        "  - Or download from: https://ffmpeg.org/download.html\n"
        "  - Or set FFMPEG_BINARY environment variable"
    )
