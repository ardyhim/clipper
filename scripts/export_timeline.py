#!/usr/bin/env python3
"""Export an OpenShorts clip-selection JSON as an editable timeline.

Reads an ``openshorts.clip-selection.v1`` file and writes either:

* FCPXML 1.9 (``.fcpxml``) - DaVinci Resolve, Final Cut Pro.
* CMX3600 EDL (``.edl``)   - Resolve, Premiere Pro, and most NLEs.

Every clip is laid end to end on a single "selects" timeline, or exported as
its own timeline with ``--layout split``. Clip names and markers carry the
OpenShorts title, so the edit stays navigable after import.

Examples:
    python export_timeline.py clips.json --media podcast.mp4
    python export_timeline.py clips.json --media podcast.mp4 --format both
    python export_timeline.py clips.json --media podcast.mp4 --layout split --handles 1.5
    python export_timeline.py clips.json --url https://youtu.be/VIDEO_ID --fps 29.97
"""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
import sys
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import NoReturn

SCHEMA = "openshorts.clip-selection.v1"

# Exact fractions for the rates NLEs actually use.
STANDARD_RATES = [
    Fraction(24000, 1001),
    Fraction(24, 1),
    Fraction(25, 1),
    Fraction(30000, 1001),
    Fraction(30, 1),
    Fraction(50, 1),
    Fraction(60000, 1001),
    Fraction(60, 1),
]


def fail(message: str) -> NoReturn:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(2)


def warn(message: str) -> None:
    print(f"warning: {message}", file=sys.stderr)


def parse_rate(text: str) -> Fraction:
    """Turn ``29.97`` or ``30000/1001`` into an exact frame rate."""
    text = text.strip()
    if "/" in text:
        try:
            rate = Fraction(text)
        except (ValueError, ZeroDivisionError):
            fail(f"invalid frame rate: {text}")
        return rate
    try:
        rate = Fraction(text)
    except ValueError:
        fail(f"invalid frame rate: {text}")
    best = min(STANDARD_RATES, key=lambda candidate: abs(float(candidate) - float(rate)))
    if abs(float(best) - float(rate)) < 0.02:
        return best
    return rate


def parse_seconds(value: object, label: str) -> Fraction:
    if isinstance(value, bool) or value is None:
        fail(f"{label} must be a number")
    try:
        seconds = Fraction(str(value))
    except (ValueError, ZeroDivisionError):
        fail(f"{label} must be a number, got {value!r}")
    if seconds < 0:
        fail(f"{label} must be zero or greater, got {value!r}")
    return seconds


def to_frames(seconds: Fraction, fps: Fraction) -> int:
    return int(round(seconds * fps))


def time_value(frames: int, fps: Fraction) -> str:
    """FCPXML time string using exact frame arithmetic."""
    value = Fraction(frames) / fps if frames else Fraction(0)
    if value == 0:
        return "0s"
    if value.denominator == 1:
        return f"{value.numerator}s"
    return f"{value.numerator}/{value.denominator}s"


def timecode(frames: int, nominal_fps: int) -> str:
    frames = int(frames)
    ff = frames % nominal_fps
    total_seconds = frames // nominal_fps
    ss = total_seconds % 60
    mm = (total_seconds // 60) % 60
    hh = total_seconds // 3600
    return f"{hh:02d}:{mm:02d}:{ss:02d}:{ff:02d}"


def probe_media(path: Path) -> dict:
    """Read width, height, duration, frame rate, and audio presence."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        fail("ffprobe not found; install ffmpeg or pass --fps/--width/--height/--duration")

    result = subprocess.run(
        [ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        fail(f"ffprobe could not read {path}: {result.stderr.strip()}")

    data = json.loads(result.stdout or "{}")
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if not video:
        fail(f"{path} has no video stream")

    rate = video.get("avg_frame_rate") or video.get("r_frame_rate") or "30/1"
    if rate in {"0/0", "0"}:
        rate = video.get("r_frame_rate") or "30/1"

    return {
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "duration": float(data.get("format", {}).get("duration") or 0.0),
        "rate": parse_rate(rate),
        "has_audio": any(s.get("codec_type") == "audio" for s in streams),
    }


def download_media(url: str, out_dir: Path) -> Path:
    yt_dlp = shutil.which("yt-dlp")
    if not yt_dlp:
        fail("yt-dlp not found; install it or download the video yourself and pass --media")
    out_dir.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            yt_dlp,
            "--no-playlist",
            "-f",
            "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b",
            "--merge-output-format",
            "mp4",
            "--print",
            "after_move:filepath",
            "-o",
            str(out_dir / "%(id)s.%(ext)s"),
            url,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        fail(f"yt-dlp failed: {result.stderr.strip()}")

    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if lines:
        path = Path(lines[-1])
        if path.is_file():
            return path

    candidates = sorted(out_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    if candidates:
        return candidates[0]
    fail("yt-dlp finished but no media file was found")


@dataclass
class Clip:
    title: str
    source_in: int
    duration: int
    timeline_offset: int = 0


def load_clips(path: Path, fps: Fraction, sort_mode: str) -> list[Clip]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        fail(f"{path} is not valid JSON: {exc}")

    if isinstance(data, list):
        raw_clips = data
    elif isinstance(data, dict):
        schema = data.get("schema")
        if schema and schema != SCHEMA:
            fail(f"unexpected schema {schema!r}; expected {SCHEMA!r}")
        raw_clips = data.get("clips")
        if not isinstance(raw_clips, list):
            fail(f"{path} has no clips array")
    else:
        fail(f"{path} must contain a JSON object")

    if not raw_clips:
        fail(f"{path} contains no clips")

    parsed: list[tuple[float, Clip]] = []
    for index, item in enumerate(raw_clips, start=1):
        if not isinstance(item, dict):
            fail(f"clip {index} is not an object")
        start = parse_seconds(item.get("start"), f"clip {index} start")
        end = parse_seconds(item.get("end"), f"clip {index} end")
        if end <= start:
            fail(f"clip {index} end ({end}) must be greater than start ({start})")

        start_frame = to_frames(start, fps)
        end_frame = to_frames(end, fps)
        if end_frame - start_frame < 1:
            end_frame = start_frame + 1

        title = str(item.get("title") or f"Clip {index}").replace("\n", " ").strip()
        score = item.get("score")
        sort_key = float(score) if isinstance(score, (int, float)) else 0.0
        parsed.append((sort_key, Clip(title=title, source_in=start_frame, duration=end_frame - start_frame)))

    if sort_mode == "start":
        parsed.sort(key=lambda pair: pair[1].source_in)
    elif sort_mode == "score":
        parsed.sort(key=lambda pair: pair[0], reverse=True)
    elif sort_mode != "input":
        fail(f"unknown sort mode: {sort_mode}")

    clips = [clip for _, clip in parsed]

    by_source = sorted(clips, key=lambda clip: clip.source_in)
    for previous, current in zip(by_source, by_source[1:]):
        if current.source_in < previous.source_in + previous.duration:
            warn(
                f"clips overlap in the source: {previous.title!r} and {current.title!r}; "
                "the selects timeline repeats that footage"
            )
    return clips


def rate_label(fps: Fraction) -> str:
    return str(int(round(float(fps))))


def format_name(width: int, height: int, fps: Fraction) -> str:
    label = rate_label(fps)
    if (width, height) == (1280, 720):
        return f"FFVideoFormat720p{label}"
    if (width, height) == (1920, 1080):
        return f"FFVideoFormat1080p{label}"
    if (width, height) == (3840, 2160):
        return f"FFVideoFormat2160p{label}"
    if (width, height) == (1080, 1920):
        return f"FFVideoFormatVertical1080p{label}"
    return f"FFVideoFormat{width}x{height}p{label}"


def build_fcpxml(
    clips: list[Clip],
    media: Path,
    fps: Fraction,
    width: int,
    height: int,
    media_width: int,
    media_height: int,
    has_audio: bool,
    asset_frames: int,
    project_name: str,
    timeline_duration: int,
) -> ET.ElementTree:
    root = ET.Element("fcpxml", {"version": "1.9"})
    resources = ET.SubElement(root, "resources")

    unit = Fraction(1, 1) / fps
    frame_duration = f"{unit.numerator}/{unit.denominator}s"

    sequence_format_id = "r1"
    ET.SubElement(
        resources,
        "format",
        {
            "id": sequence_format_id,
            "name": format_name(width, height, fps),
            "frameDuration": frame_duration,
            "width": str(width),
            "height": str(height),
        },
    )

    asset_format_id = sequence_format_id
    if (media_width, media_height) != (width, height):
        asset_format_id = "r2"
        ET.SubElement(
            resources,
            "format",
            {
                "id": asset_format_id,
                "name": format_name(media_width, media_height, fps),
                "frameDuration": frame_duration,
                "width": str(media_width),
                "height": str(media_height),
            },
        )

    asset_id = "r3"
    asset_attrs = {
        "id": asset_id,
        "name": media.name,
        "start": "0s",
        "duration": time_value(asset_frames, fps),
        "hasVideo": "1",
        "format": asset_format_id,
    }
    if has_audio:
        asset_attrs.update(
            {
                "hasAudio": "1",
                "audioSources": "1",
                "audioChannels": "2",
                "audioRate": "48000",
            }
        )
    asset = ET.SubElement(resources, "asset", asset_attrs)
    ET.SubElement(
        asset,
        "media-rep",
        {
            "kind": "original-media",
            "src": media.resolve().as_uri(),
        },
    )

    library = ET.SubElement(root, "library")
    event = ET.SubElement(library, "event", {"name": project_name})
    project = ET.SubElement(event, "project", {"name": project_name})
    sequence = ET.SubElement(
        project,
        "sequence",
        {
            "format": sequence_format_id,
            "duration": time_value(timeline_duration, fps),
            "tcStart": "0s",
            "tcFormat": "NDF",
            "audioLayout": "stereo",
            "audioRate": "48k",
        },
    )
    spine = ET.SubElement(sequence, "spine")

    for clip in clips:
        clip_element = ET.SubElement(
            spine,
            "clip",
            {
                "name": clip.title,
                "offset": time_value(clip.timeline_offset, fps),
                "duration": time_value(clip.duration, fps),
                "start": time_value(clip.source_in, fps),
            },
        )
        ET.SubElement(
            clip_element,
            "video",
            {
                "ref": asset_id,
                "offset": "0s",
                "duration": time_value(clip.duration, fps),
                "start": time_value(clip.source_in, fps),
            },
        )
        if has_audio:
            ET.SubElement(
                clip_element,
                "audio",
                {
                    "ref": asset_id,
                    "offset": "0s",
                    "duration": time_value(clip.duration, fps),
                    "start": time_value(clip.source_in, fps),
                    "role": "dialogue",
                },
            )
        ET.SubElement(
            clip_element,
            "marker",
            {
                "start": "0s",
                "duration": time_value(1, fps),
                "value": clip.title,
                "completed": "0",
            },
        )

    ET.indent(root, space="  ")
    return ET.ElementTree(root)


def write_fcpxml(tree: ET.ElementTree, destination: Path) -> None:
    xml_body = ET.tostring(tree.getroot(), encoding="unicode")
    content = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE fcpxml>\n' + xml_body + "\n"
    destination.write_text(content, encoding="utf-8")


def write_edl(
    clips: list[Clip],
    media: Path,
    fps: Fraction,
    destination: Path,
    project_name: str,
) -> None:
    nominal = int(round(float(fps)))
    reel_source = re.sub(r"[^A-Z0-9]", "", media.stem.upper())[:8] or "AX"
    record_start = 3600 * nominal

    lines = [
        f"TITLE:   {project_name}",
        "FCM: NON-DROP FRAME",
        "",
    ]
    for index, clip in enumerate(clips, start=1):
        source_in = clip.source_in
        source_out = clip.source_in + clip.duration
        record_in = record_start + clip.timeline_offset
        record_out = record_in + clip.duration
        lines.append(
            f"{index:03d}  {reel_source:<8} V     C        "
            f"{timecode(source_in, nominal)} {timecode(source_out, nominal)} "
            f"{timecode(record_in, nominal)} {timecode(record_out, nominal)}"
        )
        lines.append(f"* FROM CLIP NAME: {clip.title}")
        lines.append(f"* SOURCE FILE: {media.name}")
        lines.append("")

    destination.write_text("\n".join(lines), encoding="utf-8")


def default_base_name(clips_path: Path) -> str:
    name = clips_path.name
    for suffix in (".clips.json", ".json"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return clips_path.stem


def slugify(text: str, max_length: int = 60) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_text).strip("-").lower()
    return slug[:max_length].rstrip("-") or "clip"


def add_handles(clip: Clip, handles: int, media_frames: int) -> Clip:
    """Extend a clip on both sides, clamped to the media."""
    start = max(0, clip.source_in - handles)
    end = clip.source_in + clip.duration + handles
    if media_frames:
        end = min(end, media_frames)
    if end <= start:
        end = start + clip.duration
    return Clip(title=clip.title, source_in=start, duration=end - start, timeline_offset=0)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export an OpenShorts clip selection as an FCPXML/EDL timeline.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("clips", type=Path, help="openshorts.clip-selection.v1 JSON file")
    parser.add_argument("--media", type=Path, help="source video (required unless --url is used)")
    parser.add_argument("--url", help="YouTube/video URL to download with yt-dlp when --media is absent")
    parser.add_argument("--download-dir", type=Path, default=Path("downloads"))
    parser.add_argument("--out-dir", type=Path, help="output directory (default: next to the clips file)")
    parser.add_argument("--format", choices=["fcpxml", "edl", "both"], default="fcpxml")
    parser.add_argument("--name", help="project/timeline name")
    parser.add_argument("--fps", help="override frame rate, e.g. 23.976, 25, 29.97, 30000/1001")
    parser.add_argument("--width", type=int, help="sequence width (default: source width)")
    parser.add_argument("--height", type=int, help="sequence height (default: source height)")
    parser.add_argument("--duration", type=float, help="source duration in seconds when ffprobe is unavailable")
    parser.add_argument("--sort", choices=["input", "start", "score"], default="input")
    parser.add_argument("--gap", type=float, default=0.0, help="seconds of black between clips (default: 0)")
    parser.add_argument(
        "--layout",
        choices=["combined", "split", "both"],
        default="combined",
        help="one selects timeline (default), one timeline per clip, or both",
    )
    parser.add_argument(
        "--handles",
        type=float,
        default=0.0,
        help="seconds of extra footage on each side of a split clip (default: 0)",
    )
    parser.add_argument("--no-audio", action="store_true", help="omit audio from the timeline")
    args = parser.parse_args()

    clips_path: Path = args.clips
    if not clips_path.is_file():
        fail(f"clips file not found: {clips_path}")

    if args.media:
        media = args.media
        if not media.is_file():
            fail(f"media file not found: {media}")
    elif args.url:
        media = download_media(args.url, args.download_dir)
        print(f"downloaded: {media}")
    else:
        fail("pass --media /path/to/video.mp4 (or --url to download it)")

    probe = probe_media(media)
    fps = parse_rate(args.fps) if args.fps else probe["rate"]
    if (args.width is None) != (args.height is None):
        fail("pass both --width and --height, or neither")
    width = args.width or probe["width"] or 1920
    height = args.height or probe["height"] or 1080
    has_audio = probe["has_audio"] and not args.no_audio
    media_duration = args.duration if args.duration is not None else probe["duration"]

    clips = load_clips(clips_path, fps, args.sort)

    gap_frames = to_frames(parse_seconds(args.gap, "gap"), fps)
    offset = 0
    for clip in clips:
        clip.timeline_offset = offset
        offset += clip.duration + gap_frames
    timeline_duration = offset - gap_frames if clips else 0

    max_source_end = max(clip.source_in + clip.duration for clip in clips)
    media_frames = int(math.ceil(media_duration * fps)) if media_duration else 0
    if media_frames and max_source_end > media_frames:
        warn(
            f"a clip ends at {max_source_end / float(fps):.2f}s but the media is only "
            f"{media_frames / float(fps):.2f}s long; the tail will be black/offline"
        )
    asset_frames = max(media_frames, max_source_end + 1)

    base = default_base_name(clips_path)
    project_name = args.name or f"{base} selects"
    out_dir = args.out_dir or clips_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.layout == "combined" and args.handles:
        warn("--handles only applies to split timelines; ignoring it")
    if args.layout in {"split", "both"} and args.gap:
        warn("--gap only applies to the combined timeline; ignoring it for split timelines")

    def emit_fcpxml(seq_clips: list[Clip], duration: int, name: str, destination: Path) -> Path:
        tree = build_fcpxml(
            clips=seq_clips,
            media=media,
            fps=fps,
            width=width,
            height=height,
            media_width=probe["width"] or width,
            media_height=probe["height"] or height,
            has_audio=has_audio,
            asset_frames=asset_frames,
            project_name=name,
            timeline_duration=duration,
        )
        write_fcpxml(tree, destination)
        ET.parse(destination)  # fail early if the document is malformed
        return destination

    def emit_edl(seq_clips: list[Clip], name: str, destination: Path) -> Path:
        write_edl(seq_clips, media, fps, destination, name)
        return destination

    combined_written: list[Path] = []
    split_written: list[Path] = []

    if args.layout in {"combined", "both"}:
        if args.format in {"fcpxml", "both"}:
            combined_written.append(
                emit_fcpxml(clips, timeline_duration, project_name, out_dir / f"{base}.timeline.fcpxml")
            )
        if args.format in {"edl", "both"}:
            combined_written.append(
                emit_edl(clips, project_name, out_dir / f"{base}.timeline.edl")
            )

    split_dir = None
    if args.layout in {"split", "both"}:
        split_dir = out_dir / f"{base}.timelines"
        split_dir.mkdir(parents=True, exist_ok=True)
        handles = to_frames(parse_seconds(args.handles, "handles"), fps)
        for index, clip in enumerate(clips, start=1):
            held = add_handles(clip, handles, media_frames)
            file_stem = f"{index:02d}-{slugify(clip.title)}"
            timeline_name = f"{index:02d} {clip.title}"
            if args.format in {"fcpxml", "both"}:
                split_written.append(
                    emit_fcpxml([held], held.duration, timeline_name, split_dir / f"{file_stem}.fcpxml")
                )
            if args.format in {"edl", "both"}:
                split_written.append(
                    emit_edl([held], timeline_name, split_dir / f"{file_stem}.edl")
                )

    total_seconds = timeline_duration / float(fps)
    print(f"{len(clips)} clips -> {total_seconds:.2f}s at {float(fps):.3f} fps")
    for path in combined_written:
        print(f"wrote: {path}")
    if split_dir is not None:
        print(f"wrote {len(split_written)} files ({len(clips)} timelines) in: {split_dir}")


if __name__ == "__main__":
    main()
