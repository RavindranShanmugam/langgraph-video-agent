# Repo notes

Two unrelated things share this repo.

- **`agent/`, `app.py`, `run.py`** — the LangGraph video agent (Python). See `README.md`.
- **`website/`** — Ravs LLC site work (Node). Everything below is about that.

## website/

```
ravs-site/      THE SITE. Static HTML/CSS/JS, no build step.
portfolio/      earlier single-page version, superseded by ravs-site/
site/           extracted copy of sriramvenkatassamy.com — reference only
extract.mjs     the extractor that produced site/
add-reels.mjs   turns Instagram export clips into web-ready video
```

`ravs-site/` is the deliverable. Its layout follows the structure of
`site/` (floating pill nav, oversized wordmark hero over a faded portrait,
meta strip, horizontally scrolling card rows, one full-bleed accent panel,
large closing contact block), with Ravi's own content, across a light home
page and a dark about page.

The CSS is written from scratch. `site/` is Wix output — generated font
stacks like `wfont_800732_...`, two dozen leftover `Add a Title` placeholder
headings, and absolutely-positioned blocks that visibly overlap on its own
about page at 1440px. It is a design reference, not a code source.

`portfolio/` and `site/` can both be deleted once you are happy with
`ravs-site/`. Keeping them costs nothing but they are not built on.

## Running it

```bash
cd website
npm install                    # brings its own ffmpeg and chromium
npx http-server ravs-site -p 8080 -c-1
```

Or just open `ravs-site/index.html` — there is no build step.

## Open items

- **`ravs-site/assets/resume.pdf` does not exist.** The Resume button in the
  nav of both pages points at it and 404s until the file is added.
- **Two of three project cards have no link.** Only the LangGraph card has a
  "View the code" link; add one to the other two when those repos are public.
- **The Instagram row is empty.** See below.

## Instagram reels

`ravs-site/assets/reels/` is generated, not hand-written.

```bash
cd website
npm run reels -- "C:\path\to\instagram-export\media\reels"   # newest 6
npm run reels -- --list
npm run reels -- --clear
```

Export clips are 10-50MB each. Each is re-encoded to capped-height H.264
with the audio stripped and a poster frame pulled, and the page renders the
row lazily from `reels.json`. Add a caption and Instagram permalink per clip
by editing that file. With no manifest the section falls back to just the
follow button.

`-pix_fmt yuv420p` in `add-reels.mjs` is load-bearing: without it libx264
rejects the high profile on 4:4:4 sources, and Safari and iOS refuse to
decode the output at all.

## Things that bit us

- **Viewport meta.** Its absence makes every `max-width` media query inert on
  a phone; the page renders at desktop width. Both pages have it.
- **Playwright version pinning.** `extract.mjs` needs the browser build that
  matches the pinned Playwright. Run `npm run browser` from inside `website/`
  — running `npx playwright install` elsewhere pulls a newer Playwright and
  installs a build the pinned version never looks for.
- **Windows PowerShell 5.1** rejects `&&` as a command separator. Use `;` or
  separate lines.
- **`git fetch` before `git checkout`** on a clone that predates a branch,
  or the checkout fails with *pathspec did not match*.

## Verifying changes

Both pages were checked in Chromium at 1440x900 and 390x844 for failed
requests, JS errors, and horizontal overflow. Worth repeating after layout
changes — horizontal overflow in particular is invisible until someone opens
it on a phone.
