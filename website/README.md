# Site extractor

Renders a website in a real browser and writes a **self-contained static frontend
package** — plain HTML, CSS, JS and assets, no build step, openable from disk.

## Why not `wget --mirror`

`wget` fetches the HTML the server sends. Most modern portfolio sites (Wix,
Squarespace, Framer, Webflow, Next.js, any React SPA) send an effectively empty
shell and build the page with JavaScript, so a `wget` mirror captures no content.

This tool loads the page in Chromium, waits for the network to settle, scrolls the
full height to trigger lazy-loaded images, and only then serialises the DOM. What
you get is the page as a visitor actually sees it.

## Setup

Needs Node 18+ (`node --version`). From a checkout of this repo:

```bash
git fetch origin
git checkout claude/website-frontend-extraction-ukb9qt
cd website
npm install
npx playwright install chromium
```

Run each line separately on **Windows PowerShell 5.1** — it rejects `&&` as a
separator (use `;` instead, or just press Enter between commands).

Order matters: run `npx playwright install chromium` **from inside `website/`,
after `npm install`**. Elsewhere, `npx` fetches whatever Playwright is newest and
installs a browser build that the pinned 1.56.1 will not look for, producing
`Executable doesn't exist`. If npx offers to install a version other than
1.56.1, answer `n` — you are in the wrong directory.

Chromium is discovered from `PLAYWRIGHT_BROWSERS_PATH` or the default per-user
cache on Windows, macOS and Linux. To use a Chrome you already have, set
`CHROMIUM_PATH` to its executable.

## Usage

```bash
npm run extract -- --url https://www.sriramvenkatassamy.com/
npm run serve            # browse the result at http://localhost:8080
```

Output lands in `site/`:

```
site/
  index.html                    # '/'          -> index.html
  about/index.html              # '/about'     -> about/index.html
  assets/<host>/...             # css, images, fonts, media
  screenshots/*.png             # full-page render of each page
  extraction-manifest.json      # every page + asset captured, and any failures
```

The screenshots are the fastest way to check the capture is faithful — compare one
against the live site — and they double as a design reference when rebuilding.

### Options

| Flag | Default | Meaning |
| --- | --- | --- |
| `--url <url>` | *required* | Page to start from. |
| `--out <dir>` | `site` | Output directory. |
| `--max-pages <n>` | `25` | Cap on same-origin pages crawled. |
| `--wait <ms>` | `2500` | Settle time after scrolling, for animations and late loads. |
| `--keep-js` | off | Keep the original `<script>` tags (see below). |
| `--no-screenshots` | off | Skip full-page screenshot capture. |

`CHROMIUM_PATH=/path/to/chrome` overrides browser discovery.

## About `--keep-js`

By default scripts are **stripped**. The captured DOM is already the rendered
result; if the original framework JS were left in, it would boot on load and
re-render — typically wiping the very markup that was captured. Stripping yields a
page that looks right and is genuinely static. `<noscript>` blocks and `ld+json`
metadata are always preserved.

Use `--keep-js` if you need interactive behaviour and are prepared to debug
hydration. Purely decorative scripts usually survive; app frameworks usually don't.

## Known limits

- **Same-origin only.** Third-party embeds (fonts, analytics, YouTube, maps) are
  saved when the browser fetches them, but embedded iframes still point outward.
- **Anything requiring a server** — forms, search, auth — is inert in a static copy.
- **Unreachable assets** are listed under `failures` in the manifest. References
  that could not be localised are rewritten to their absolute origin URL, so they
  still load online rather than 404-ing silently.
- Assets are captured at a 1440x900 viewport; art-directed sources that only apply
  at other breakpoints may not be requested by the browser. Those referenced from
  CSS are recovered by the sweep pass; those referenced only from `srcset` may not be.

## Verification

The extractor was validated against a fixture reproducing the hard cases:
JS-rendered DOM, cross-directory `url()` references, query-string asset URLs, and
nested page links. The extracted package re-loads offline with all references
resolving and no failed requests.

## Note on reuse

This copies a site's markup, styling and media. Those are the author's work and are
typically protected by copyright regardless of being publicly served. Fine for
archiving, migrating a site you control, or local reference — get permission before
republishing someone else's site.
