# LangGraph Video Agent

An open-source agent pipeline that turns long-form video into edited short-form cuts.

It's built on LangGraph as a directed graph rather than a script. Transcription, segment
selection, reasoning over transcript content, tool calls, and output assembly each run as
discrete nodes with their own retry and error handling.

That structure is the point. In a linear pipeline, one bad Whisper pass or one malformed
model response takes down the entire run and you start over from the top. As a graph, a
failure is contained to the node that caused it — the rest of the state survives, the failed
node retries on its own terms, and any single node can be swapped or re-run in isolation.

Output is 1080×1920 vertical with a blur-fill background and word-by-word animated captions.

---

## The graph

```
START → ingest → transcribe ─┬─(has speech)──→ select ─┬─(clips)──→ plan → render → assemble → END
                             │                          │
                             └─(no speech)───→ fallback ←┘ (no clips)
```

| Node | Does | On failure |
|---|---|---|
| `ingest` | Checks ffmpeg, probes duration, extracts 16 kHz mono audio | **Fatal** — no readable video, nothing to do |
| `transcribe` | Whisper with word-level timestamps | Non-fatal → routes to `fallback` |
| `select` | Claude reasons over the transcript and picks the moments | Non-fatal → routes to `fallback` |
| `fallback` | Even-split selection so a run always produces cuts | Fatal (arithmetic only) |
| `plan` | Clamps to the length rules, drops overlaps, numbers the clips | Fatal if nothing survives |
| `render` | One ffmpeg pass per clip: cut + blur-fill + burn captions | **Per-clip isolation** — a bad cut is recorded, the rest still render |
| `assemble` | Writes `manifest.json` + `report.md` | Fatal |

The two conditional edges carry the real decisions. Everything else is a straight line —
which is the point: the branching lives in the graph instead of inside a 400-line script.

---

## Install

Needs **ffmpeg on PATH** and Python 3.10+.

```bash
pip install -r requirements.txt
cp .env.example .env          # then add your key
```

`.env` (this folder, or your home folder):

```
ANTHROPIC_API_KEY=sk-ant-...
```

No key? The graph still runs — `select` fails non-fatally and the run routes to the
even-split fallback.

---

## Run

**UI** (watch the graph light up node by node):

```bash
streamlit run app.py
```

**Headless:**

```bash
python run.py path/to/video.mp4 --clips 3 --whisper small --out ./shorts
```

```
--clips N          how many shorts (default 3)
--whisper MODEL    base | small | medium (default small)
--out DIR          output folder (default ./shorts)
--no-captions      skip caption burn-in
--uppercase        UPPERCASE captions
```

**LangGraph Studio:**

```bash
langgraph dev        # graph is exposed as `video_agent` in langgraph.json
```

---

## Output

Everything lands in the output folder:

- `short_1_<title>.mp4` … — the cuts
- `manifest.json` — machine-readable: what got cut, from where, why, plus any non-fatal errors
- `report.md` — the same thing for humans

`agent.log` in the project root has the full node-by-node trace.

---

## Configuration

All via environment variables or `.env`:

| Variable | Default | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Without it, selection falls back to even-split |
| `MODEL` | `claude-sonnet-5` | `claude-opus-5` gives noticeably better picks on long or rambling footage |
| `EFFORT` | `medium` | `low` · `medium` · `high` · `xhigh` · `max` |
| `WHISPER_MODEL` | `small` | `medium` is the most accurate (best captions) and the slowest |
| `NUM_CLIPS` | `3` | |
| `SHORT_MIN_SECS` / `SHORT_MAX_SECS` | `15` / `60` | Clip length rules enforced in `plan` |
| `NODE_RETRIES` | `2` | Retries per node before it gives up |
| `OUTPUT_DIR` | `./shorts` | |

Caption styling (font, size, colours, position, words-per-line) lives at the top of
[`agent/config.py`](agent/config.py).

---

## Layout

```
agent/
  config.py        settings + .env loading + logging
  state.py         the typed graph state (errors use an append reducer)
  bus.py           thread-safe status bus — drives the live UI
  runtime.py       the @node decorator: retry, error capture, status
  graph.py         StateGraph wiring + the two routers
  ffmpeg_tools.py  the tool layer — the only place that shells out
  captions.py      word-level ASS caption builder
  nodes/           one file per node
app.py             Streamlit UI with the live graph view
run.py             headless CLI
```

## Extending it

Each node is a plain function taking the state dict and returning a partial update, wrapped
in `@node(name, retries=…, fatal=…)`. To swap the selection logic — a different model, an
energy-based heuristic, a human-in-the-loop picker — replace `agent/nodes/select.py` and
leave everything else alone. That's the property the graph structure buys you.

To add a stage (an uploader, a thumbnail generator), add the node and one edge in
`agent/graph.py`.
