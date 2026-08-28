# ravs-site

Ravindran Shanmugam / Ravs LLC — static site. Plain HTML, CSS and a little JS.
No build step: open `index.html`, or serve the folder.

```
index.html     home — hero, projects, business OS, process, reels, contact
about.html     about — dark variant
styles.css     everything, one file
assets/        portrait, resume, reels
```

## Layout

Structure follows the reference site (floating pill nav, oversized wordmark over
a faded portrait, meta strip, horizontally scrolling card rows, one full-bleed
accent panel, large closing contact block). The CSS is written from scratch — the
reference is Wix output, whose absolutely-positioned generated styles are both
unmaintainable and visibly broken at some widths on the live site.

## Still to add

- **`assets/resume.pdf`** — the Resume button in the nav points here and 404s
  until the file exists.
- **Project links** — only the LangGraph card links out. Add a `<a class="more">`
  to the other two once those repos are public.

## Reels

`assets/reels/` is generated. Instagram export clips are 10-50MB each; they get
re-encoded to capped-height H.264 (yuv420p, audio stripped, faststart) with a
poster frame, so nothing downloads until a card is hovered.

```bash
npm install                                   # once, brings its own ffmpeg
npm run reels -- "C:\path\to\media\reels"     # newest 6 clips
npm run reels -- clip.mp4 --max 3 --crf 32    # specific files, smaller
npm run reels -- --list                       # what is wired up
npm run reels -- --clear                      # remove all
```

Then add a caption and Instagram permalink per clip in
`assets/reels/reels.json`. The row renders from that manifest — with no
manifest the section falls back to just the follow button.
