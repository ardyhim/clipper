# YouTube → transcript → OpenShorts

Use this when the user supplies a YouTube URL. The deliverable is the OpenShorts clip-selection JSON. The transcript is the intermediate artifact that makes it possible.

Pipeline: download or generate one timestamped transcript → analyze it with `SKILL.md` → emit `openshorts.clip-selection.v1`.

Do not build an intermediate transcript export or `windows[]` structure. The downloaded SRT/VTT is enough; analyze it directly. `windows[]` is only an input field of an OpenShorts export the user supplied.

Always pass `--no-playlist`. Treat the URL as one video. If it is clearly a channel or playlist, ask for or choose a single video.

## 1. Check tools

- `yt-dlp` — required to list and fetch captions.
- `ffmpeg` — required only for the audio-transcription fallback.
- A local speech-to-text CLI — optional, needed only when no usable captions exist. Check `whisper --help` or `whisper-ctranslate2 --help`.

If `yt-dlp` is missing, explain the dependency and ask for an SRT/VTT. Do not claim a download that did not happen.

## 2. List caption tracks

```bash
yt-dlp --list-subs --no-warnings --no-playlist "URL"
```

- Prefer the user's requested language.
- Otherwise prefer the video's original or spoken language when it can be identified. Do not assume English or Indonesian.
- Prefer uploader-provided captions over automatic ones.

Optional metadata without media:

```bash
yt-dlp --skip-download --dump-single-json --no-playlist --no-warnings "URL"
```

Read only what you need: title, id, duration, language.

## 3. Fetch captions

Use the exact language code reported by `--list-subs`:

```bash
yt-dlp --skip-download --no-playlist --no-warnings \
  --write-subs --sub-langs "LANG" \
  --sub-format "srt/vtt/best" --convert-subs srt \
  -o "%(title).200B [%(id)s].%(ext)s" \
  "URL"
```

- Pass the URL as one quoted argument. Do not concatenate it into an unescaped shell string.
- `--skip-download` is intentional here. Do not fetch video or thumbnails.
- On Windows, add `--windows-filenames` if the title contains characters that break paths.

## 4. Validate the transcript

1. Confirm the file exists, is non-empty, and has usable text and timestamps. Prefer the converted `.srt`; `.vtt` is acceptable.
2. If no manual track was produced, retry with automatic captions. Replace `--write-subs` with `--write-auto-subs`.
3. Note the source internally (`manual`, `auto_generated`, `auto_translated`, or `unknown`) so you can state limitations. It is not an output field.
4. If the desired language is missing, consider another spoken-language track. Do not silently substitute a translation; state it.
5. If a track is machine-translated and identifiable, say so.
6. Check that timestamps are absolute video time and cover the source.
7. Automatic captions are often rolling: consecutive cues overlap and repeat text. Deduplicate repeated lines before reading, and do not treat an overlap as two separate utterances.
8. If cue boundaries are too coarse or heavily overlapping, fetch the `json3` format and use its word-level timings to refine cut points.
9. Keep the raw cue text. Do not paraphrase or punctuation-clean it into a different meaning.

If captions are absent, unusable, or clearly incomplete, go to step 5. Do not conclude "no subtitles" from a single failed command. Retry only with a sensible fix, such as updating `yt-dlp`.

## 5. Fallback: transcribe the audio

Use this only when no usable caption track exists and a local transcriber is installed. This is the only path where downloading media is allowed, and it is audio only.

```bash
yt-dlp --no-playlist --no-warnings -x --audio-format mp3 \
  -o "%(id)s.%(ext)s" "URL"
```

```bash
whisper "VIDEO_ID.mp3" --output_format srt --output_dir .
```

- Keep the smallest audio that still transcribes reliably.
- Preserve word or segment timestamps. If the tool emits VTT or TXT, keep the timestamped variant; do not reduce the transcript to plain text.
- Pass `--language` when the spoken language is known; let the tool detect it otherwise.
- Label the result as local ASR, not as an official caption track.
- If no transcriber is installed, say which dependency is missing and ask for an SRT/VTT. Do not pretend a transcript was generated.

## 6. Save the transcript

Default path: `transcripts/<video_id>.srt` in the session working directory. If the user names a directory, use it. Rename or copy the fetched file to that canonical name so the path is predictable. Keep the source provenance alongside it:

- original URL;
- video id and title;
- chosen language;
- caption source, or `local ASR`;
- any translation or conversion limitation.

Do not overwrite an existing transcript silently. Add a suffix or ask.

If the filesystem is read-only, keep the transcript in context, say it was not saved, and continue with the analysis.

## 7. Analyze and emit OpenShorts

Read the saved transcript with the workflow in `SKILL.md`, then follow `references/openshorts.md`.

- Analyze the saved SRT/VTT directly. Do not convert it into `openshorts.transcript-export.v1`, do not create a `windows[]` or other windowed transcript, and do not return the transcript as the deliverable.
- Return only the OpenShorts JSON. Never return the transcript instead of the clips.
- Use the transcript's timestamps for `start` and `end`; never rescale or invent them.
- If the transcript has no reliable timestamps, do not fabricate numeric seconds. Say what is missing and ask for a timestamped file.

## Errors and safety

- Report the concrete error: no caption track, private or unavailable video, authentication required, rate limit, or outdated `yt-dlp`.
- Never bypass access controls.
- Use only content the user is authorized to retrieve. Respect platform terms, copyright, and applicable law.
- If tools or network are unavailable, say so and ask for the subtitle file.
