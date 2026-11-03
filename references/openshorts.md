# OpenShorts contract

The only output of this skill. Read this before writing.

## Output: `openshorts.clip-selection.v1`

Return only valid JSON — no fences, no commentary, no extra keys.

```json
{
  "schema": "openshorts.clip-selection.v1",
  "clips": [
    {
      "start": 12.5,
      "end": 42.0,
      "score": 85,
      "title": "A specific title, max 100 characters",
      "hook": "The strongest hook, max 10 words",
      "reason": "One sentence, max 20 words, naming what makes the moment work.",
      "description_tiktok": "1-2 sentences that tease the payoff. #hashtag #hashtag #hashtag",
      "description_instagram": "1-2 sentences that tease the payoff. #hashtag #hashtag #hashtag"
    }
  ]
}
```

## Rules

- `schema` exactly `openshorts.clip-selection.v1`.
- `start` and `end` are absolute seconds as JSON numbers, not strings. `0 <= start < end <= duration_seconds`.
- Best first. `score` is an integer 0–100; always include it. Use the six-criterion rubric internally; do not add `score_breakdown`.
- Respect `clip_duration_seconds` and `recommended_clip_count`. If the user overrides them, follow the user.
- `title` is at most 100 characters; `hook` at most 10 words; `reason` one sentence of at most 20 words. Count characters and words, not tokens.
- `description_tiktok` and `description_instagram` are each 1–2 sentences that tease the payoff plus 3–5 relevant hashtags. Hashtags must be single tokens with no spaces. Do not use unrelated trending tags.
- Write `title`, `hook`, `reason`, and descriptions in the source language unless the user explicitly asks for another language.
- Open on the hook: the first two seconds must stop a cold viewer. Context can follow; do not cut the payoff to fit.
- Prefer `transcript.segments[]` boundaries. Never cut in the middle of a word. If the segment timings are incomplete, use the nearest reliable boundary; do not invent precision.
- No two clips may cover the same moment or share the same payoff.
- Include every field above for every clip. Do not add fields the contract does not list. If you cannot fill a field honestly, choose a different moment rather than inventing content or emitting an empty value.
- If the source has no reliable timestamps, do not fabricate numeric seconds. Say what is missing and ask for a timestamped transcript instead of emitting invalid OpenShorts JSON.

## Input: `openshorts.transcript-export.v1`

An OpenShorts export is JSON with `schema: "openshorts.transcript-export.v1"` (or a compatible version). Read the whole file before choosing clips.

- `language` — write `title`, `hook`, `reason`, and descriptions in this language unless the user explicitly asks for another.
- `duration_seconds` — absolute upper bound for every `end`.
- `clip_duration_seconds` — allowed clip length range; respect it.
- `recommended_clip_count` — requested number of clips; respect it.
- `prompt` and `output_contract` — task specification and exact output schema. Follow them when more specific than this file; the non-negotiables still win.
- `transcript.segments[]` — timed segments; use them for cut points.
- `windows[]` — grouped consecutive segments with `id`, `start`, `end`, and `text`; use them for navigation and context. A clip may start and end anywhere, not only on a window boundary.
- `transcript.text` — may be a short summary or placeholder; do not assume it is the full transcript. Use `windows[].text` and `segments[].text` for content.

This section applies only when the user supplied such an export. A transcript downloaded from YouTube is not converted into this format: analyze the SRT/VTT directly and emit only the clip-selection JSON.

Exports sometimes contain trailing commas and are not strict JSON. Repair a temporary copy (remove trailing commas only), never edit the user's file, and never change transcript text. If the file still cannot be parsed, report the concrete parse error and ask for a valid export.

## Defaults for plain transcripts and YouTube sources

When the input is not an OpenShorts export, apply these silently — they are not output fields:

- `duration_seconds`: last verified end timestamp.
- `clip_duration_seconds`: 30–90 seconds.
- `recommended_clip_count`: 5–8 distinct clips.
- `language`: the transcript's spoken language.

For YouTube, follow `references/youtube.md`: download a timestamped transcript, analyze it directly, and emit the clip-selection JSON. Do not create a windowed transcript or an intermediate OpenShorts export.

## Validate before responding

- JSON parses; no trailing commas.
- `schema` is exactly `openshorts.clip-selection.v1`, with no extra top-level or clip keys.
- `0 <= start < end <= duration_seconds`.
- Every clip length is inside `clip_duration_seconds`.
- Clip count matches `recommended_clip_count` when present, otherwise the strongest 5–8 clips (or the user's override).
- Clips are best first; no pair overlaps.
- `title` ≤ 100 characters, `hook` ≤ 10 words, `reason` ≤ 20 words and one sentence.
- Each description is 1–2 sentences with 3–5 single-token hashtags.
- Language matches the source language.
- No fabricated quotes, timecodes, or visual claims.
