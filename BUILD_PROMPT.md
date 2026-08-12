# The build prompt

Paste everything in the block below into Claude Code (or any coding agent) and it
builds the tool. It is not a summary — it's the full spec, written out of the
working version, including the parts that cost me hours to find.

Goes in the video description and the repo README.

---

```
Build me a command-line + Streamlit tool that turns a long video into vertical
short-form clips. Python 3.10+, Windows-friendly. Use LangGraph.

## Stack (don't substitute these)

- LangGraph for the graph, `anthropic` SDK for the model call.
- Model: `claude-sonnet-5` (override with a MODEL env var).
- Transcription: `openai-whisper` specifically, NOT faster-whisper — the
  word-timestamp crash and its workaround below are openai-whisper behaviour.
  Default size `small`; expose base/small/medium.
- Read the API key from ANTHROPIC_API_KEY, and **load a .env file at startup**
  (the project folder AND the user's home folder). Shipping a .env.example
  without reading it is the single easiest way to get a tool that looks like it
  works but silently falls back to evenly-spaced clips on every run.
- Default to 3 clips.

## The shape (this is the important part)

Build it as a StateGraph, NOT a linear script. Every stage is its own node with
its own retry count and its own answer to "what happens if I fail?".

  START -> ingest -> transcribe --(has speech)--> select --(got clips)--> plan
                          |                          |
                          +--(no speech)--> fallback <+ (no clips)
                                               |
                                               v
                                    plan -> render -> assemble -> END

Two real conditional edges:
  - after transcribe: no usable transcript -> fallback (don't even call the model)
  - after select:     model returned nothing usable -> fallback

Per-node policy:
  ingest      fatal      no readable video means there is nothing to do
  transcribe  non-fatal  route to fallback, keep going
  select      non-fatal  route to fallback, keep going
  fallback    -          evenly spaced clips so a run ALWAYS produces something
  plan        fatal      fails only if zero clips survive validation
  render      per-clip   one bad clip is recorded and skipped; the others render
  assemble    -          writes manifest.json + report.md

Wrap each node in a decorator that does retry -> status -> error capture, and
have it append failures to state["errors"] (use an operator.add reducer so
nodes never clobber each other). Do not rely on LangGraph's RetryPolicy — its
keyword name has moved between releases.

## Nodes

ingest      ffprobe the duration, extract 16kHz mono wav via ffmpeg.
            ALSO measure mean volume (ffmpeg volumedetect). If it's <= -60 dB
            the audio is silent: skip transcription entirely and mark the state.
            Otherwise a silent track produces hallucinated filler and the failure
            surfaces later as a confusing "model returned no clips".

transcribe  Whisper with word_timestamps=True.
            WRAP IT: word-timestamp alignment intermittently raises
            "cannot reshape tensor of 0 elements". It's nondeterministic because
            temperature fallback makes decoding nondeterministic - the same file
            can succeed one run and crash the next. On exception, retry with
            word_timestamps=False and carry on with line-level timings.

select      One model call. Give it the transcript segments (start, end, text)
            and ask for the best N moments. Use structured outputs so the JSON is
            schema-valid; fall back to regex-extracting the JSON object if the
            model/SDK rejects that. Raise if it returns zero clips - the graph
            routes to fallback.

            Schema: {"clips": [{"start": number, "end": number,
            "title": string, "reason": string}]} — all required,
            additionalProperties false. On the anthropic SDK that's
            output_config={"format": {"type": "json_schema", "schema": ...}}.

fallback    N clips, the whole duration split evenly. plan clamps them after.

plan        Clamp every clip into the source duration and the length rules
            (15-60s), drop overlaps, sort, number them. Raise if nothing survives.

render      One ffmpeg pass per clip. Isolate failures per clip.

assemble    manifest.json (what was cut, from where, why, plus non-fatal errors)
            and a human-readable report.md.

## The selection prompt

system:
  You are an expert short-form video editor (YouTube Shorts, Reels, TikTok).
  You find the moments in a long video that would perform best as standalone
  shorts. A great short is self-contained, has a strong hook in the first 2
  seconds, and delivers one clear payoff. Titles are punchy and honest - never
  clickbait, never invented claims.

user:
  Pick the N best moments from this video for short-form clips (each 15-60
  seconds). For each: exact start/end times in seconds aligned to the transcript
  segments, a punchy title (max 6 words), and a one-line reason it works as a
  hook. Rules: clips must not overlap; each must stand on its own; prefer moments
  with a clear hook, a surprising point, or an actionable tip.
  <transcript segments as json>

"self-contained" and "one clear payoff" are load-bearing. Remove them and you get
moments that only make sense if you watched the whole video.

## The render (cut + vertical + captions in ONE pass)

filter_complex:
  [0:v]split=2[bg][fg];
  [bg]scale=1080:1920:force_original_aspect_ratio=increase,
      crop=1080:1920,boxblur=40:1,eq=brightness=-0.18[bgb];
  [fg]scale=1080:1920:force_original_aspect_ratio=decrease[fgs];
  [bgb][fgs]overlay=(W-w)/2:(H-h)/2[base];
  [base]subtitles=clip_N.ass[v]

Put -ss before -i for fast seeking, -t after. Encode libx264 crf 20 veryfast,
aac 160k, 30fps.

Run ffmpeg with cwd set to the working directory and reference the .ass file by
BARE FILENAME - a Windows absolute path inside the subtitles filter needs
drive-letter escaping and will bite you.

## Captions

Build an ASS file per clip from the word timestamps, offset to the clip start
(that's why they never drift). Whole phrase on screen, active word highlighted
via karaoke \k timing. Group ~4 words, break on gaps > 0.6s.

Style: Arial Black, size ~92 at 1080x1920, active word yellow (&H0000FFFF),
upcoming white (&H00FFFFFF), black outline, MarginV ~520.

The ASS file needs its full scaffolding or libass ignores it: a [Script Info]
block with ScriptType v4.00+ and PlayResX/PlayResY set to 1080/1920 (get those
wrong and every caption lands in the wrong place), then [V4+ Styles] with the
Format: line, then [Events] with its own Format: line before the Dialogue rows.

Name each clip's file clip_<n>.ass and the output short_<n>_<slugged title>.mp4.

If a segment has no word timings (see the transcribe fallback above), synthesise
them by spreading the words evenly across the segment - approximate captions beat
no captions.

## UI

Streamlit. Two source modes: a path on disk (default - long videos are gigabytes
and uploading them through a browser is pointless) and an upload. Raise
server.maxUploadSize in .streamlit/config.toml; the 200MB default rejects real
footage.

Run the graph on a worker thread and poll a thread-safe status bus from the main
thread, so the node states can animate live as the run progresses. Cache the
Whisper model in a plain module-level dict - st.cache_resource doesn't work from
the worker thread.

## Windows details that will waste your afternoon

- sys.stdout.reconfigure(encoding="utf-8", errors="replace") or printing a report
  containing an arrow crashes with UnicodeEncodeError on cp1252.
- truststore.inject_into_ssl() so the Anthropic SDK trusts the OS cert store.
- ffmpeg auto-applies rotation metadata on decode; don't flip footage yourself.

## Deliver

Folder structure, requirements.txt, .env.example, README, logging to console +
file, and a headless CLI runner alongside the Streamlit app.
```

---

## Tested — 2026-08-11

I built this from the spec alone in a clean folder and ran it on a real video.
It works: the graph ran, Claude picked two genuine moments with titles and
reasons, and it rendered 1080x1920 verticals with captions burned in.

Four gaps the test exposed, all now patched into the spec above:

1. **The .env was never loaded.** The spec asked for a `.env.example` but never
   said to *read* one — so the first run authenticated with nothing, `select`
   failed non-fatally, and the graph quietly produced evenly-spaced clips. It
   looked like a successful run. This was the important find: a silent
   degradation, not a crash.
2. No model was named anywhere — a builder could reasonably have reached for a
   different provider entirely.
3. "Whisper" didn't say which package; the documented crash workaround only
   applies to openai-whisper.
4. No output schema for the structured call, and no ASS scaffolding — both
   guessable, both able to fail quietly.

## Honest framing for the video

What this gets someone: a working equivalent of the tool. Not a byte-identical
copy of mine — different agents make different choices, and they'll still need
ffmpeg installed and an API key.

What it does NOT need: my repo. That's the point. The spec is the giveaway; the
repo is just the reference implementation.

The line already in the recorded VO — *"the tool's in the description if you want
it, but you can do all three of those without it"* — supports this exactly. No
reshoot needed.
