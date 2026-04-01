from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

import instaloader
from faster_whisper import WhisperModel


INSTAGRAM_PROFILES = [
    "anikjaindesign",
    "saptarshiux",
    "wanderwithsky",
]


@dataclass
class VideoItem:
    platform: str
    source_profile: str
    source_url: str
    video_id: str
    title: str
    description: str
    video_url: str | None
    local_video_path: str | None = None
    local_audio_path: str | None = None
    transcript_txt_path: str | None = None
    transcript_json_path: str | None = None
    metadata_path: str | None = None
    published_at: str | None = None
    likes: int | None = None
    comments: int | None = None


def slugify(value: str, max_length: int = 80) -> str:
    value = re.sub(r"[^\w\s-]", "", value, flags=re.ASCII).strip().lower()
    value = re.sub(r"[-\s]+", "_", value)
    return (value[:max_length] or "item").strip("_")


def run_command(command: list[str], cwd: Path | None = None) -> None:
    print(f"$ {' '.join(command)}", flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def find_ffmpeg_binary() -> str:
    env_binary = os.getenv("FFMPEG_BINARY")
    if env_binary and Path(env_binary).exists():
        return env_binary

    from_path = shutil.which("ffmpeg")
    if from_path:
        return from_path

    local_appdata = Path(os.getenv("LOCALAPPDATA", ""))
    if local_appdata:
        winget_packages = local_appdata / "Microsoft" / "WinGet" / "Packages"
        for candidate in winget_packages.glob("Gyan.FFmpeg*/*/bin/ffmpeg.exe"):
            if candidate.exists():
                return str(candidate)

    raise FileNotFoundError(
        "ffmpeg binary not found. Set FFMPEG_BINARY or install ffmpeg."
    )


def profile_urls_from_text(text: str) -> list[str]:
    return re.findall(r"https?://[^\s]+", text or "")


def youtube_urls_from_profile(profile: instaloader.Profile) -> list[str]:
    candidates = []
    if profile.external_url:
        candidates.append(profile.external_url)
    candidates.extend(profile_urls_from_text(profile.biography))
    seen = set()
    youtube_links = []
    for url in candidates:
        host = urlparse(url).netloc.lower()
        if "youtube.com" in host or "youtu.be" in host:
            if url not in seen:
                youtube_links.append(url)
                seen.add(url)
    return youtube_links


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def load_manifest(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_manifest(path: Path, manifest: dict[str, dict]) -> None:
    write_json(path, manifest)


def enumerate_instagram_videos(
    loader: instaloader.Instaloader, username: str, max_items: int | None = None
) -> tuple[list[VideoItem], list[str], dict]:
    profile = instaloader.Profile.from_username(loader.context, username)
    profile_metadata = {
        "username": profile.username,
        "full_name": profile.full_name,
        "biography": profile.biography,
        "external_url": profile.external_url,
        "followers": profile.followers,
        "followees": profile.followees,
        "mediacount": profile.mediacount,
        "userid": profile.userid,
    }

    items: list[VideoItem] = []
    for post in profile.get_posts():
        caption = post.caption or ""
        if post.is_video:
            items.append(
                VideoItem(
                    platform="instagram",
                    source_profile=username,
                    source_url=f"https://www.instagram.com/p/{post.shortcode}/",
                    video_id=post.shortcode,
                    title=(caption.splitlines()[0] if caption else post.shortcode)[:200],
                    description=caption,
                    video_url=post.video_url,
                    published_at=post.date_utc.isoformat() if post.date_utc else None,
                    likes=post.likes,
                    comments=post.comments,
                )
            )
            if max_items is not None and len(items) >= max_items:
                break
            continue

        try:
            sidecar_nodes = list(post.get_sidecar_nodes())
        except Exception:
            sidecar_nodes = []

        for index, node in enumerate(sidecar_nodes, start=1):
            if not getattr(node, "is_video", False):
                continue
            items.append(
                VideoItem(
                    platform="instagram",
                    source_profile=username,
                    source_url=f"https://www.instagram.com/p/{post.shortcode}/",
                    video_id=f"{post.shortcode}_{index}",
                    title=(caption.splitlines()[0] if caption else post.shortcode)[:200],
                    description=caption,
                    video_url=node.video_url,
                    published_at=post.date_utc.isoformat() if post.date_utc else None,
                    likes=post.likes,
                    comments=post.comments,
                )
            )
            if max_items is not None and len(items) >= max_items:
                break

        if max_items is not None and len(items) >= max_items:
            break

    return items, youtube_urls_from_profile(profile), profile_metadata


def download_with_ytdlp(item: VideoItem, destination_dir: Path) -> Path:
    destination_dir.mkdir(parents=True, exist_ok=True)
    output_template = str(destination_dir / f"{item.video_id}.%(ext)s")
    run_command(
        [
            "yt-dlp",
            "--no-progress",
            "--no-warnings",
            "-o",
            output_template,
            item.video_url or item.source_url,
        ]
    )
    matches = sorted(destination_dir.glob(f"{item.video_id}.*"))
    media_matches = [
        path
        for path in matches
        if path.suffix.lower() in {".mp4", ".mkv", ".webm", ".mov", ".m4v", ".mp3", ".m4a"}
    ]
    if not media_matches:
        raise FileNotFoundError(f"yt-dlp did not produce a media file for {item.video_id}")
    return media_matches[0]


def download_youtube_source(
    url: str, destination_dir: Path, max_items: int | None = None
) -> list[Path]:
    destination_dir.mkdir(parents=True, exist_ok=True)
    output_template = str(destination_dir / "%(channel_id)s__%(id)s__%(title).80B.%(ext)s")
    before = {path.resolve() for path in destination_dir.glob("*")}
    command = [
        "yt-dlp",
        "--ignore-errors",
        "--yes-playlist",
        "--no-progress",
        "--no-warnings",
        "-o",
        output_template,
    ]
    if max_items is not None:
        command.extend(["--playlist-end", str(max_items)])
    command.append(url)
    run_command(command)
    after = {path.resolve() for path in destination_dir.glob("*")}
    new_files = sorted(
        path
        for path in after - before
        if path.suffix.lower() in {".mp4", ".mkv", ".webm", ".mov", ".m4v", ".mp3", ".m4a"}
    )
    return new_files


def extract_audio(ffmpeg_binary: str, input_path: Path, audio_path: Path) -> None:
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    run_command(
        [
            ffmpeg_binary,
            "-y",
            "-i",
            str(input_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(audio_path),
        ]
    )


def transcribe_audio(
    model: WhisperModel,
    audio_path: Path,
    transcript_txt_path: Path,
    transcript_json_path: Path,
) -> None:
    segments, info = model.transcribe(str(audio_path), vad_filter=True)
    collected_segments = []
    lines = []
    for segment in segments:
        line = segment.text.strip()
        if not line:
            continue
        lines.append(line)
        collected_segments.append(
            {
                "start": segment.start,
                "end": segment.end,
                "text": line,
            }
        )

    transcript_txt_path.parent.mkdir(parents=True, exist_ok=True)
    transcript_txt_path.write_text("\n".join(lines), encoding="utf-8")
    write_json(
        transcript_json_path,
        {
            "language": info.language,
            "language_probability": info.language_probability,
            "duration": info.duration,
            "segments": collected_segments,
        },
    )


def process_video_item(
    item: VideoItem,
    output_root: Path,
    ffmpeg_binary: str,
    model: WhisperModel,
) -> VideoItem:
    item_dir = output_root / item.platform / item.source_profile / slugify(item.video_id)
    raw_dir = item_dir / "raw"
    audio_dir = item_dir / "audio"
    transcript_dir = item_dir / "transcript"

    if item.video_url:
        existing_media = next(iter(raw_dir.glob("*")), None) if raw_dir.exists() else None
        video_path = existing_media or download_with_ytdlp(item, raw_dir)
        item.local_video_path = str(video_path)

    metadata_path = item_dir / "metadata.json"
    item.metadata_path = str(metadata_path)
    write_json(metadata_path, asdict(item))

    if item.local_video_path:
        audio_path = audio_dir / f"{Path(item.local_video_path).stem}.wav"
        if not audio_path.exists():
            extract_audio(ffmpeg_binary, Path(item.local_video_path), audio_path)
        item.local_audio_path = str(audio_path)

        transcript_txt_path = transcript_dir / f"{audio_path.stem}.txt"
        transcript_json_path = transcript_dir / f"{audio_path.stem}.json"
        if not transcript_txt_path.exists() or not transcript_json_path.exists():
            transcribe_audio(model, audio_path, transcript_txt_path, transcript_json_path)
        item.transcript_txt_path = str(transcript_txt_path)
        item.transcript_json_path = str(transcript_json_path)
        write_json(metadata_path, asdict(item))

    return item


def discover_youtube_items(downloaded_files: Iterable[Path], source_profile: str) -> list[VideoItem]:
    items = []
    for media_file in downloaded_files:
        items.append(
            VideoItem(
                platform="youtube",
                source_profile=source_profile,
                source_url=str(media_file),
                video_id=media_file.stem,
                title=media_file.stem,
                description="",
                video_url=None,
                local_video_path=str(media_file),
            )
        )
    return items


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download Instagram and YouTube videos, extract audio, and transcribe them."
    )
    parser.add_argument(
        "--output-root",
        default="yt_insta_videos",
        help="Folder where downloads, metadata, and transcripts will be stored.",
    )
    parser.add_argument(
        "--whisper-model",
        default="small",
        help="faster-whisper model name. Example: tiny, base, small, medium, large-v3.",
    )
    parser.add_argument(
        "--instagram-profile",
        action="append",
        dest="instagram_profiles",
        default=[],
        help="Instagram profile username. Can be passed multiple times.",
    )
    parser.add_argument(
        "--skip-youtube",
        action="store_true",
        help="Do not attempt YouTube discovery via profile bio/external links.",
    )
    parser.add_argument(
        "--skip-instagram",
        action="store_true",
        help="Do not process Instagram profiles.",
    )
    parser.add_argument(
        "--youtube-url",
        action="append",
        dest="youtube_urls",
        default=[],
        help="Explicit YouTube channel or playlist URL. Can be passed multiple times.",
    )
    parser.add_argument(
        "--max-items-per-source",
        type=int,
        default=None,
        help="Limit how many videos to process from each Instagram or YouTube source.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_root = Path(args.output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    manifest_path = output_root / "manifest.json"
    manifest = load_manifest(manifest_path)

    ffmpeg_binary = find_ffmpeg_binary()
    print(f"Using ffmpeg: {ffmpeg_binary}", flush=True)
    model = WhisperModel(args.whisper_model, device="cpu", compute_type="int8")
    loader = instaloader.Instaloader(
        download_comments=False,
        save_metadata=False,
        compress_json=False,
        download_video_thumbnails=False,
        download_geotags=False,
    )

    instagram_profiles = [] if args.skip_instagram else (args.instagram_profiles or INSTAGRAM_PROFILES)
    explicit_youtube_urls = args.youtube_urls or []
    all_items: list[VideoItem] = []

    for username in instagram_profiles:
        print(f"Enumerating Instagram profile: {username}", flush=True)
        items, youtube_urls, profile_metadata = enumerate_instagram_videos(
            loader, username, max_items=args.max_items_per_source
        )
        write_json(output_root / "instagram" / username / "profile_metadata.json", profile_metadata)
        for item in items:
            if item.video_id in manifest:
                restored = VideoItem(**manifest[item.video_id])
                all_items.append(restored)
                continue
            processed = process_video_item(item, output_root, ffmpeg_binary, model)
            manifest[processed.video_id] = asdict(processed)
            save_manifest(manifest_path, manifest)
            all_items.append(processed)

        if args.skip_youtube:
            continue

        for youtube_url in youtube_urls:
            print(f"Discovered YouTube source for {username}: {youtube_url}", flush=True)
            youtube_download_dir = output_root / "youtube" / username / "raw"
            downloaded_files = download_youtube_source(
                youtube_url,
                youtube_download_dir,
                max_items=args.max_items_per_source,
            )
            for item in discover_youtube_items(downloaded_files, username):
                if item.video_id in manifest:
                    restored = VideoItem(**manifest[item.video_id])
                    all_items.append(restored)
                    continue
                processed = process_video_item(item, output_root, ffmpeg_binary, model)
                manifest[processed.video_id] = asdict(processed)
                save_manifest(manifest_path, manifest)
                all_items.append(processed)

    for youtube_url in explicit_youtube_urls:
        source_profile = slugify(Path(urlparse(youtube_url).path).name or "youtube")
        print(f"Downloading explicit YouTube source: {youtube_url}", flush=True)
        youtube_download_dir = output_root / "youtube" / source_profile / "raw"
        downloaded_files = download_youtube_source(
            youtube_url,
            youtube_download_dir,
            max_items=args.max_items_per_source,
        )
        for item in discover_youtube_items(downloaded_files, source_profile):
            if item.video_id in manifest:
                restored = VideoItem(**manifest[item.video_id])
                all_items.append(restored)
                continue
            processed = process_video_item(item, output_root, ffmpeg_binary, model)
            manifest[processed.video_id] = asdict(processed)
            save_manifest(manifest_path, manifest)
            all_items.append(processed)

    summary = {
        "output_root": str(output_root),
        "item_count": len(all_items),
        "items": [asdict(item) for item in all_items],
    }
    write_json(output_root / "summary.json", summary)
    print(f"Completed. Results written to {output_root}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
