# Clipper

An Agent Skill that turns long-form video subtitles or transcripts into ranked short-form clip candidates in the OpenShorts `openshorts.clip-selection.v1` JSON format. For a YouTube URL, it downloads a timestamped transcript, analyzes it, and returns the clips.

## What it does

- Reads `.srt`, `.vtt`, timestamped `.txt`, pasted transcripts, or OpenShorts transcript exports (`openshorts.transcript-export.v1`).
- Generates a timestamped transcript from a YouTube URL: captions first, local audio transcription as a fallback.
- Finds hooks, stories, emotion, humor, surprises, useful insights, and discussion-worthy moments.
- Ranks candidates on a weighted 0–100 score with calibration anchors.
- Emits only the `openshorts.clip-selection.v1` JSON contract.

The skill is deliberately editorial about which moments to pick. The rubric is a calibration tool, not a formula; the model is allowed to break it when the material gives a better reason.

## Output

Return only valid JSON — no fences, no commentary, no extra keys:

- `schema`: exactly `openshorts.clip-selection.v1`
- `clips[]`: best first, each with `start`, `end`, `score`, `title`, `hook`, `reason`, `description_tiktok`, and `description_instagram`

Starts and ends are absolute seconds as numbers. Clips do not overlap and stay inside the requested duration range. The full contract, defaults, and validation checklist live in [`references/openshorts.md`](references/openshorts.md).

## Timeline export (optional)

The JSON contract stays the only analysis output. When you want to start editing, [`scripts/export_timeline.py`](scripts/export_timeline.py) turns that JSON into a timeline you can import:

- **FCPXML 1.9** (`.fcpxml`) — DaVinci Resolve and Final Cut Pro.
- **CMX3600 EDL** (`.edl`) — Resolve, Premiere Pro, and most other NLEs.

Every clip is placed end to end on one "selects" timeline. The OpenShorts title becomes the clip name and a timeline marker. Clips reference the original media; nothing is transcoded or copied.

```bash
# Resolve/FCP
python .agents/skills/clipper/scripts/export_timeline.py \
  transcripts/i_WVOVSweEg.clips.json --media podcast.mp4

# Both formats, vertical 1080x1920, 29.97 fps
python .agents/skills/clipper/scripts/export_timeline.py \
  transcripts/i_WVOVSweEg.clips.json --media podcast.mp4 \
  --format both --width 1080 --height 1920 --fps 29.97

# No local file yet: download the source first with yt-dlp
python .agents/skills/clipper/scripts/export_timeline.py \
  transcripts/i_WVOVSweEg.clips.json --url https://youtu.be/i_WVOVSweEg
```

Requirements: Python 3.9+, `ffmpeg`/`ffprobe` on `PATH`, and `yt-dlp` only when using `--url`. Frame rate, size, duration, and audio presence are read from the media; override them with `--fps`, `--width`, `--height`, `--duration`. Other useful flags: `--gap` (black between clips), `--sort start|score`, `--no-audio`, `--name`, `--out-dir`.

### Subtitles

Subtitles are retimed **by default**. The exporter looks next to the clips file and the media for a matching `.srt`, `.vtt`, or OpenShorts transcript export `.json` (`<name>.srt`, `<name>.vtt`, `<name>.json`) and writes an SRT for every timeline:

- combined: `<name>.timeline.srt`
- split: `<name>.timelines/01-<slug>.srt`

Cue times are clipped to each cut, shifted to their new timeline position, and follow `--gap` and `--handles`. Pick a file explicitly with `--subtitles captions.srt`, or skip auto-detection with `--no-subtitles`.

In Resolve: import the `.srt` into the Media Pool (right-click → **Import Subtitle**), then drag it onto the timeline's subtitle track. Subtitles stay editable. Overlapping cues from the source keep their timing; Resolve may trim them to fit one subtitle track. Nothing is burned into the picture.

### One timeline vs. separate timelines

By default all clips go on one **selects** timeline. For production work where each clip needs its own trim, reframe, subtitles, and export, use `--layout split` or `--layout both`:

```bash
# One timeline per clip, with 1.5s of extra footage on each side
python .agents/skills/clipper/scripts/export_timeline.py \
  transcripts/i_WVOVSweEg.clips.json --media podcast.mp4 \
  --layout split --handles 1.5 --format both

# Keep the selects overview and also emit the per-clip timelines
python .agents/skills/clipper/scripts/export_timeline.py \
  transcripts/i_WVOVSweEg.clips.json --media podcast.mp4 --layout both
```

Split output goes to a `<clips-name>.timelines/` folder, one file per clip:

```text
transcripts/i_WVOVSweEg.timelines/
├── 01-sampo-dulu-atau-sabun-dulu.fcpxml
├── 02-pengin-jackson-menang.fcpxml
└── ...
```

Why separate files instead of one FCPXML with several projects? Resolve does not reliably import every project from one FCPXML — in practice it exposes only one sequence at import time. One file per timeline is predictable: import each file, and each becomes its own timeline.

`--handles` adds footage before and after the selected cut (clamped to the media) so the editor can adjust the in/out without going back to the source. It only applies to split timelines; `--gap` only applies to the combined timeline.

Notes:

- Cut points are snapped to the nearest frame of the chosen rate, so a millisecond of transcript timing can move.
- In Resolve: `File > Import > Timeline` and choose the `.fcpxml`. The media is linked by absolute path; use the Media Pool's "Relink" if you move it.
- For 9:16 output, pass `--width 1080 --height 1920`. The source is not auto-cropped — framing remains an editorial decision.
- An EDL carries cuts and clip names but not transforms, effects, or marker text. FCPXML is the richer format.

## Duration and count

For a plain transcript, the defaults are 30–90 seconds and 5–8 distinct clips. An OpenShorts export's `clip_duration_seconds` and `recommended_clip_count` override both. There is no padding to hit a count, and no payoff is cut to fit a duration.

## YouTube

For a YouTube URL the skill runs the full pipeline in one go:

1. Generate a timestamped transcript. Prefer manual captions, then automatic captions, then local audio transcription only if captions are absent or unusable.
2. Save it to `transcripts/<video_id>.srt` in the session working directory unless the user names another directory.
3. Analyze the saved transcript directly. Do not build a windowed transcript or convert it into an `openshorts.transcript-export.v1`.
4. Return only the OpenShorts JSON.

The transcript is an intermediate file, not a deliverable. See [`references/youtube.md`](references/youtube.md).

## Files

```text
clipper/
├── SKILL.md                  # entry point: stance, workflow, routing, non-negotiables
├── scripts/
│   └── export_timeline.py    # optional: clip-selection JSON → FCPXML/EDL
├── references/
│   ├── openshorts.md         # contract: output schema, limits, defaults, validation
│   └── youtube.md            # YouTube → transcript workflow
└── examples/
    ├── sample.srt            # fictional 2:34 transcript
    ├── example-openshorts-output.json  # default output mode
    └── README.md             # how to use the fixture
```

`SKILL.md` is loaded into context when the skill runs. `references/` and `examples/` are read only when needed. `references/openshorts.md` is the single source of truth for the schema and its limits.

## Dependencies for YouTube links

Command execution, network access, and [`yt-dlp`](https://github.com/yt-dlp/yt-dlp). Caption fetching uses `--skip-download` and `--no-playlist`, so it retrieves captions for one video, not media or an entire playlist.

The audio-transcription fallback additionally needs `ffmpeg` and a local Whisper-compatible CLI (`whisper` or `whisper-ctranslate2`). It downloads audio only, never video.

If the agent cannot execute commands, reach the network, or find a transcriber when one is needed, it should say why and ask for an SRT/VTT instead. A failed attempt does not prove captions do not exist. See `references/youtube.md` for the full workflow and error handling.

## Install / use

Copy the `clipper` folder into the skills directory supported by your agent. The entry point is `SKILL.md`.

For OpenCode, the project-level locations are `.opencode/skills/`, `.claude/skills/`, or `.agents/skills/`. The global location is `~/.config/opencode/skills/` (Windows: `%USERPROFILE%\.config\opencode\skills\`). In this project the skill lives in `.agents/skills/clipper` and is also installed globally.

## Example instructions

**From a YouTube link:**

> Generate a timestamped transcript for `https://www.youtube.com/watch?v=VIDEO_ID`, save it, analyze it for short-form clip candidates, and return only the OpenShorts JSON. Prefer original-language manual captions; use auto captions or local transcription only if needed.

**From a subtitle file:**

> Analyze the attached SRT with the Clipper skill. Find the strongest clip candidates and return the OpenShorts JSON. Flag visual details that cannot be confirmed from subtitles alone.

**From an OpenShorts export:**

> Analyze this OpenShorts transcript export and return only the `openshorts.clip-selection.v1` JSON. Follow the export's prompt, language, clip duration range, and recommended clip count.

## Testing the skill

The files in `examples/` are a structural fixture. Scores and rankings are editorial, so treat differences as judgment calls, not failures. Check that:

- JSON parses, uses double quotes, and has no trailing commas;
- every timecode falls on a cue boundary in `sample.srt`;
- `schema` is exactly `openshorts.clip-selection.v1`, with no extra keys;
- `start` and `end` are numbers in absolute seconds, in range, with no overlaps;
- every clip length is inside the default or export duration range;
- `title` ≤ 100 characters, `hook` ≤ 10 words, `reason` ≤ 20 words and one sentence;
- each description is 1–2 sentences with 3–5 single-token hashtags.

See `examples/README.md` for the full checklist.

## Limitations

The skill selects and ranks editorial moments; it does not cut video or guarantee virality. Subtitle-only analysis cannot verify framing, on-screen action, or visual reactions. YouTube captions may be absent, inaccurate, translated, or inaccessible, and local transcription accuracy varies. Only retrieve content you are authorized to access and respect applicable terms and law.

The timeline exporter builds an edit from existing timecodes; it does not transcode, crop, reframe, or burn captions. It also cannot repair unreliable timestamps. Importing a timeline into an NLE does not replace the media, so keep the source file at its original path or relink it after import.
