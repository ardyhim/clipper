---
name: clipper
description: Turn long-form video subtitles or transcripts into ranked short-form clip candidates in the OpenShorts `openshorts.clip-selection.v1` JSON format. For a YouTube URL, download a timestamped transcript (captions, or local audio transcription when captions are unusable), analyze it directly, and emit OpenShorts JSON. Use when the user supplies a YouTube URL, SRT, VTT, TXT, pasted transcript, or OpenShorts transcript export (`openshorts.transcript-export.v1`) and asks for highlights, clip-worthy moments, rankings, or a clip list.
---

# Clipper

Turn a long transcript into a ranked shortlist of moments worth clipping. The only output is the OpenShorts `openshorts.clip-selection.v1` JSON contract.

These are judgments about potential, not predictions of virality.

## Output

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

Read [references/openshorts.md](references/openshorts.md) before writing output. It is the single source of truth for the schema, limits, defaults, and validation checklist. There is no editorial or Markdown output mode.

For a YouTube URL, read [references/youtube.md](references/youtube.md). Pipeline: download one timestamped transcript → analyze that transcript directly → emit OpenShorts JSON. Never return the transcript, build a windowed transcript, or create an OpenShorts export from it.

## Inputs

- `.srt`, `.vtt`, timestamped `.txt`, pasted transcript, or OpenShorts transcript export.
- Read the whole source before choosing clips. Do not ask the user to paste content you can already access.
- For an OpenShorts export, use `transcript.segments[]` and `windows[].text` for content and cut points; `transcript.text` may be a placeholder. Follow the export's `prompt` when it is more specific than this skill, except the non-negotiables.
- For a YouTube URL, follow `references/youtube.md`.
- If timestamps are missing or unreliable, ask for a timestamped transcript. Never fabricate numeric seconds.

## Workflow

### 1. Read the source

- Identify language, speakers, structure, and time coverage.
- Read the whole transcript before choosing clips. Do not write or output a windowed transcript; `windows[]` belongs only to an OpenShorts export you received.
- Check whether timestamps are absolute video time or section-relative.
- Understand references and payoffs before choosing cut points. A line that looks strong alone may be setup for something 90 seconds later.

### 2. Find candidates

Read broadly before narrowing. Look for:

- a hook that creates a question, tension, or "wait, what?"
- a story that pays off: reveal, reversal, confession, punchline, lesson
- real emotion: frustration, joy, embarrassment, relief, pride
- humor, banter, awkwardness, an unexpected reply
- surprise, contradiction, a belief being overturned
- a disagreement worth arguing about
- practical value: a clear explanation, demo, or fix
- relatability: "that's me" or "send this to someone"
- a line that survives outside its context

These are lenses, not categories. A strong moment often fits none cleanly.

**Cold-open rule:** the first two seconds must carry a hook that works on a viewer who has seen nothing else. If the natural start is slow, trim to the hook or move it forward. Do not rely on a title card to do the opening work.

### 3. Shape the segment

Find the smallest segment that delivers the whole experience.

- Start early enough that a cold viewer understands the stakes; cut the throat-clearing before it.
- End after the payoff, reaction, or conclusion — not mid-thought.
- Cut dead air, repetition, and unrelated tangents.
- Never trim a quote into a meaning the speaker did not intend.
- Duration follows the material. 30–90 seconds is common; longer cuts are fine when the story earns them. Do not pad to hit a number, and do not cut a payoff to fit one. Respect an explicit user or export range unless it would misrepresent the source.
- If two edits of the same moment have genuinely different hooks or payoffs, keep both. Otherwise keep one; do not duplicate a moment with cosmetic changes.
- A requested count or range wins, but do not let two clips cover the same moment or share the same payoff.

### 4. Verify timecodes

- OpenShorts output uses absolute seconds as JSON numbers.
- Use source timestamps exactly. Prefer `transcript.segments[]` boundaries; never cut in the middle of a word.
- Compute duration from start/end. Never invent precision or treat line numbers as timecodes.
- If timestamps are missing or unreliable, say so plainly and ask for a timestamped transcript. Do not emit a made-up number.
- Note section-relative timestamps explicitly.

### 5. Score and rank

Score 0–100 on six criteria. The weights are a starting point; adjust them to the content (a tutorial may weight practical value over humor) without adding fields to the output.

| Criterion | Weight | Question |
|---|---:|---|
| Hook | 25% | How fast does this earn attention? |
| Emotion, humor, surprise | 20% | Is there a real feeling or jolt? |
| Retention, progression | 20% | Does it keep developing toward something? |
| Standalone clarity | 15% | Can a newcomer follow it? |
| Shareability, discussion | 10% | Would someone send it or argue with it? |
| Concision, editability | 10% | Can it be cut cleanly, without dead zones? |

Weighted average, rounded to a whole number.

- **90–100 Exceptional** — distinctive, self-contained, strong on several axes.
- **80–89 Strong** — clear hook and payoff; minor fixes.
- **70–79 Good** — works, but needs a tighter open, trim, or context.
- **60–69 Moderate** — a useful moment with a real weakness.
- **Below 60 Weak** — usually omit unless the user wants exhaustive coverage.

Calibrate: 85 = you would send it to a friend; 75 = you would finish it but not share it; 65 = mainly fans of the source care. A 95 should be rare. Do not inflate. Ties go to the clip that is clearer and needs fewer assumptions.

The score must be explainable from the notes. Keep the six-criterion breakdown internal and emit only the integer `score`.

### 6. Check visual dependence

Subtitles prove words, not pictures. Flag:

- speaker changes that may require reframing
- jokes or reactions that depend on a face, gesture, prop, or on-screen text
- gameplay, demos, or action away from the speaker
- long monologues that may suit a single framing

Treat these as unverified. Do not declare that a crop will work; the skill chooses the moment, the editor handles framing.

There is no visual-review field in the OpenShorts contract: prefer moments that work on audio, and never assert a reaction or prop the transcript does not prove. If a moment depends on an unverified visual, choose a safer moment rather than inventing metadata.

### 7. Final pass

- Remove duplicates and clips that add nothing distinct.
- Re-check every start/end and duration.
- Titles must be honest and specific.
- No fabricated quotes, out-of-context distortion, or invented visual detail.
- Flag claims that may need fact-checking.
- Do not predict views, retention, or virality.
- Validate the output against `references/openshorts.md` before responding.

## Interaction

- If the input and task are clear, analyze directly. Do not ask for confirmation.
- Attempt the YouTube workflow when a URL is supplied and tools and network are available.
- For a YouTube URL, do not stop after downloading the transcript; continue through analysis to OpenShorts output.
- Ask only when an essential input is missing.
- Respect a requested count, duration, platform, or language; if it conflicts with honesty, explain the trade-off briefly.
- Default to the strongest 5–8 distinct clips; fewer when the source is short or thin. An OpenShorts export's `recommended_clip_count` overrides this. Never pad to a count.
- If there are no strong moments, say so and give the best available with modest scores.
- Be concise and specific; return only the JSON, with no commentary outside it.

## Non-negotiables

1. Never fabricate words, visuals, or timecodes.
2. Judge clips, not sentences.
3. Keep enough context for a cold viewer.
4. Scores must discriminate and be explainable.
5. Subtitle analysis cannot confirm framing or on-screen action.
6. No virality guarantees.
7. Output only the OpenShorts contract.

## Optional post-processing

Timeline export is a separate step, not part of the analysis response. If the user explicitly asks to open the clips in an NLE, run [`scripts/export_timeline.py`](scripts/export_timeline.py) on the JSON you produced. It writes FCPXML/EDL selects timelines and needs the source video; see [README.md](README.md#timeline-export-optional). Never add export keys or commentary to the OpenShorts JSON.
