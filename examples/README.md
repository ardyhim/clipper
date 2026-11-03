# Clipper example fixture

These files are a fictional test case for the Clipper skill. The transcript is not from a real recording; names, timings, and quotes are invented.

## Files

- `sample.srt` — 2:34 Indonesian two-speaker podcast transcript.
- `example-openshorts-output.json` — the expected output shape, `openshorts.clip-selection.v1`. The sample is short, so it returns three clips even though a typical export asks for 6–12.

The sample uses Indonesian source text and an English-language request. OpenShorts output follows the source language, so the example is fully Indonesian.

## How to run it

1. Attach or reference `sample.srt` and ask for clip candidates. The output is `openshorts.clip-selection.v1` JSON; compare the structure with `example-openshorts-output.json`.
2. Validate it with any JSON parser.
3. Check the structural rules below.

## Structural checks

- JSON parses, uses double quotes, and has no trailing commas.
- `schema` is exactly `openshorts.clip-selection.v1`, with no extra top-level or clip keys.
- `start` and `end` are numbers in absolute seconds, `0 <= start < end <= duration_seconds`.
- Every clip length is inside `clip_duration_seconds`.
- Clips are best first and no pair overlaps.
- `title` is at most 100 characters, `hook` at most 10 words, `reason` one sentence of at most 20 words.
- Each description is 1–2 sentences with 3–5 single-token hashtags.
- Cut points prefer `transcript.segments[]` boundaries; do not invent precision when segments are incomplete.
- No clip claims to know framing or on-screen action that subtitles cannot prove.

## What is intentionally flexible

- The number of clips (three here because the sample is short; the default is 5–8 for a typical long source).
- The scores and ranking.
- The titles, hooks, and descriptions.
- Whether a borderline moment is included.

Treat those as editorial judgment, not golden output.
