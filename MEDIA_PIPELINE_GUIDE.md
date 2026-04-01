# Media Pipeline Integration Guide
## Video Download + Transcription for Instagram & YouTube

## ✅ Integration Complete!

Your system now has a complete media pipeline that:
1. **Downloads** videos, reels, and shorts from Instagram and YouTube
2. **Extracts audio** using FFmpeg
3. **Transcribes** audio using Whisper AI
4. **Stores** transcripts for analysis

---

## 🎯 What Was Implemented

### 1. **VideoDownloaderService** (`services/common/adobe_influencer/transcription/video_downloader.py`)
   - Downloads Instagram videos/reels using `instaloader`
   - Downloads YouTube videos/shorts using `yt-dlp`
   - Saves metadata for each downloaded video
   - Handles both platforms seamlessly

### 2. **Audio Extraction** (`services/common/adobe_influencer/transcription/service.py`)
   - `extract_audio_with_ffmpeg()` - Extracts audio from video files
   - Converts to mono 16kHz MP3 (optimized for speech recognition)
   - Auto-detects FFmpeg installation

### 3. **FasterWhisperAdapter** (`services/common/adobe_influencer/transcription/service.py`)
   - Transcribes audio using Whisper AI models
   - Supports multiple model sizes (tiny, base, small, medium, large)
   - CPU or GPU acceleration
   - Voice activity detection to filter silence

### 4. **MediaPipeline** (`services/common/adobe_influencer/transcription/media_pipeline.py`)
   - Complete end-to-end pipeline
   - Orchestrates download → audio → transcription
   - Batch processing for multiple creators
   - Skips already-processed videos

### 5. **PipelineRunner Integration**
   - Media pipeline automatically runs when `ENABLE_MEDIA_PIPELINE=true`
   - Transcripts integrated into main analysis
   - Configurable via environment variables

---

## 📦 Dependencies

**Already Installed:**
- ✅ `yt-dlp==2025.2.19` - YouTube downloader
- ✅ `instaloader==4.14.1` - Instagram downloader  
- ✅ `faster-whisper==1.1.1` - Whisper transcription

**Required External Tool:**
- **FFmpeg** - Audio/video processing
  - Windows: `winget install Gyan.FFmpeg`
  - Or download: https://ffmpeg.org/download.html

---

## ⚙️ Configuration

### Environment Variables (`.env`)

```env
# Enable/disable media pipeline
ENABLE_MEDIA_PIPELINE=false

# Whisper model size (tiny, base, small, medium, large-v2, large-v3)
# Larger = better quality but slower
# base = good balance for most use cases
WHISPER_MODEL=base

# Maximum videos to download per creator
MAX_VIDEOS_PER_CREATOR=5

# Storage directories
MEDIA_DOWNLOAD_DIR=./data/media/downloads
MEDIA_AUDIO_DIR=./data/media/audio
MEDIA_TRANSCRIPT_DIR=./data/media/transcripts
```

### Whisper Model Sizes

| Model | Parameters | English-only | Multilingual | Speed | Quality |
|-------|-----------|--------------|--------------|-------|---------|
| tiny | 39M | ✓ | ✓ | Fastest | Basic |
| base | 74M | ✓ | ✓ | Fast | Good |
| small | 244M | ✓ | ✓ | Medium | Better |
| medium | 769M | ✓ | ✓ | Slower | Great |
| large-v2 | 1550M | - | ✓ | Slow | Best |
| large-v3 | 1550M | - | ✓ | Slow | Best |

**Recommendation:** Start with `base` model for testing, upgrade to `small` or `medium` for production.

---

## 🚀 Usage

### Option 1: Enable in Main Pipeline

Set in `.env`:
```env
ENABLE_MEDIA_PIPELINE=true
```

Then run normally:
```bash
python run_workflow.py
```

The pipeline will automatically:
1. Ingest creator data
2. Download videos
3. Extract audio
4. Transcribe
5. Include transcripts in analysis

### Option 2: Use Media Pipeline Standalone

```python
from adobe_influencer.core.config import AppSettings
from adobe_influencer.transcription.media_pipeline import MediaPipeline

settings = AppSettings()
settings.ensure_paths()

# Initialize pipeline
pipeline = MediaPipeline(
    download_dir=settings.media_download_dir,
    audio_dir=settings.media_audio_dir,
    transcript_dir=settings.media_transcript_dir,
    whisper_model="base",
    max_videos_per_creator=10
)

# Process creators
transcripts = pipeline.process_creator(creator, content_items)

# Get statistics
stats = pipeline.get_statistics()
print(f"Processed {stats['videos_downloaded']} videos")
```

### Option 3: Download Videos Only

```python
from adobe_influencer.transcription.video_downloader import VideoDownloaderService

downloader = VideoDownloaderService(
    download_dir=Path("./downloads"),
    max_videos_per_creator=5
)

# Download Instagram content
instagram_media = downloader.download_instagram_videos(creator, content_items)

# Download YouTube content
youtube_media = downloader.download_youtube_videos(creator, content_items)
```

---

## 🧪 Testing

Run the test suite:

```bash
python test_media_pipeline.py
```

This will:
1. Check all requirements (FFmpeg, yt-dlp, etc.)
2. Test Instagram reel downloading
3. Test YouTube short downloading  
4. Test audio extraction
5. Test transcription
6. Show sample outputs

---

## 📁 Output Structure

```
data/media/
├── downloads/
│   ├── instagram_creator_id/
│   │   ├── shortcode.mp4
│   │   ├── shortcode.jpg
│   │   ├── shortcode.json
│   │   └── shortcode_media.json
│   └── youtube_creator_id/
│       ├── video_id.mp4
│       ├── video_id.jpg
│       ├── video_id.info.json
│       └── video_id_media.json
├── audio/
│   ├── ig_shortcode.mp3
│   └── yt_video_id.mp3
└── transcripts/
    ├── ig_shortcode_transcript.json
    └── yt_video_id_transcript.json
```

### Transcript JSON Format

```json
{
  "content_id": "ig_ABC123",
  "creator_id": "creator_001",
  "platform": "instagram",
  "source_url": "https://instagram.com/reel/ABC123/",
  "video_path": "path/to/video.mp4",
  "audio_path": "path/to/audio.mp3",
  "duration_seconds": 45.2,
  "segment_count": 12,
  "segments": [
    {
      "transcript_id": "ig_ABC123_seg_0",
      "start_seconds": 0.0,
      "end_seconds": 3.5,
      "text": "Hey everyone, in this video I'll show you...",
      "confidence": -0.23
    }
  ]
}
```

---

## 🎓 Supported Platforms & Content

### Instagram
- ✅ Regular videos
- ✅ Reels
- ✅ IGTV
- ⚠️ Requires Instagram login for private profiles

### YouTube
- ✅ Regular videos
- ✅ Shorts
- ✅ Public videos
- ❌ Private/unlisted videos

---

## 🔧 Advanced Configuration

### Instagram Authentication

For downloading from private Instagram accounts:

```bash
# Login once
instaloader --login YOUR_INSTAGRAM_USERNAME

# Credentials saved in ~/.config/instaloader/
```

### Custom FFmpeg Path

If FFmpeg not auto-detected, set environment variable:

```env
FFMPEG_BINARY=C:/path/to/ffmpeg.exe
```

### GPU Acceleration

For faster transcription with NVIDIA GPU:

```python
pipeline = MediaPipeline(
    whisper_model="base",
    # This will auto-detect GPU if available
)
```

Whisper will automatically use CUDA if available.

---

## 📊 Performance Guidelines

### Transcription Speed (base model)

| Content | Duration | Transcription Time | 
|---------|----------|-------------------|
| Instagram Reel | 15-30 sec | ~5-10 sec |
| YouTube Short | 60 sec | ~15-20 sec |
| Full Video | 5 min | ~1-2 min |

**Note:** First run downloads Whisper model (~150MB), subsequent runs are faster.

### Resource Usage

- **CPU:** base model works well on modern CPUs
- **RAM:** ~2GB for base model
- **GPU:** Optional, speeds up by 2-5x
- **Disk:** ~500MB per hour of video

---

## 🐛 Troubleshooting

### "FFmpeg not found"

Install FFmpeg:
```bash
# Windows
winget install Gyan.FFmpeg

# Or download from: https://ffmpeg.org/download.html
```

### "yt-dlp failed"

Update yt-dlp:
```bash
pip install --upgrade yt-dlp
```

### "Instagram download failed"

Login to Instagram:
```bash
instaloader --login YOUR_USERNAME
```

### "Transcription is very slow"

Use a smaller model:
```env
WHISPER_MODEL=tiny  # Fastest
WHISPER_MODEL=base  # Good balance
```

Or enable GPU if available.

### "Out of memory"

Reduce batch size:
```env
MAX_VIDEOS_PER_CREATOR=2
```

Or use tiny/base model instead of large.

---

## 💡 Best Practices

### 1. **Start Small**
- Test with 1-2 creators first
- Use `base` model initially
- Set `MAX_VIDEOS_PER_CREATOR=3`

### 2. **Optimize Settings**
```env
# For quick testing
WHISPER_MODEL=tiny
MAX_VIDEOS_PER_CREATOR=2

# For production quality
WHISPER_MODEL=small
MAX_VIDEOS_PER_CREATOR=10
```

### 3. **Monitor Storage**
- Videos: ~50-200MB each
- Audio: ~1-5MB each
- Transcripts: ~10-50KB each

Clear old downloads periodically.

### 4. **Respect Rate Limits**
- Instagram: Don't download too many at once
- YouTube: yt-dlp handles rate limits automatically

---

## 📈 Integration with Analysis Pipeline

Transcripts are automatically used for:

1. **Theme Detection** - Identify topics discussed in videos
2. **Adobe Product Signals** - Find mentions of Adobe tools
3. **Content Quality** - Analyze communication style
4. **Audience Intent** - Understand what viewers are learning
5. **Evidence Snippets** - Extract quotes for reports

The transcripts become part of the `TranscriptSegment` model and flow through the entire analysis pipeline.

---

## 🎯 Example Workflow

```python
from adobe_influencer.core.config import AppSettings
from adobe_influencer.pipelines.runner import PipelineRunner

# Enable media pipeline
settings = AppSettings()
settings.enable_media_pipeline = True
settings.whisper_model = "base"
settings.max_videos_per_creator = 5

# Run complete pipeline (ingestion + media + analysis)
runner = PipelineRunner(settings)
recommendations = runner.run()

# Results include video transcripts in analysis
for rec in recommendations:
    print(f"{rec.creator_name}: {rec.overall_brand_fit}")
    # Scores now include video content analysis!
```

---

## 📝 Files Created/Modified

**Created:**
- ✅ `services/common/adobe_influencer/transcription/video_downloader.py`
- ✅ `services/common/adobe_influencer/transcription/media_pipeline.py`
- ✅ `test_media_pipeline.py`
- ✅ `MEDIA_PIPELINE_GUIDE.md` (this file)

**Modified:**
- ✅ `services/common/adobe_influencer/transcription/service.py` - Complete implementation
- ✅ `services/common/adobe_influencer/core/config.py` - Added media settings
- ✅ `services/common/adobe_influencer/pipelines/runner.py` - Integrated media pipeline
- ✅ `.env` - Added media configuration

---

## 🎉 Success!

Your media pipeline is fully integrated! You can now:

- ✅ Download Instagram reels and videos
- ✅ Download YouTube videos and shorts
- ✅ Extract audio from all videos
- ✅ Transcribe using Whisper AI
- ✅ Integrate transcripts into your analysis
- ✅ Run everything automatically in your pipeline

**Next Steps:**
1. Install FFmpeg if not already installed
2. Set `ENABLE_MEDIA_PIPELINE=true` in `.env`
3. Run `python test_media_pipeline.py` to verify
4. Run `python run_workflow.py` for full analysis

Enjoy your enhanced creator intelligence system! 🚀
