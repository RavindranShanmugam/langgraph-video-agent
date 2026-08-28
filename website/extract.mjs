#!/usr/bin/env node
/**
 * Renders a site in Chromium and writes a self-contained static frontend package.
 *
 * Unlike `wget --mirror`, this captures the DOM *after* JavaScript has run, so
 * SPA / Wix / Framer / Next.js sites come out as real markup instead of an empty
 * shell. Every asset the browser actually fetched (CSS, fonts, images, media) is
 * saved and all references are rewritten to relative local paths.
 *
 * Usage: node extract.mjs --url https://example.com [options]
 */
import { chromium } from 'playwright';
import { createHash } from 'node:crypto';
import { mkdir, writeFile } from 'node:fs/promises';
import { existsSync, readdirSync } from 'node:fs';
import path from 'node:path';

/**
 * Prefer an already-present Chromium over one Playwright expects to download.
 * Sandboxes often ship a browser whose build number does not match the pinned
 * Playwright release; CHROMIUM_PATH overrides, otherwise we probe the store.
 */
function findChromium() {
  if (process.env.CHROMIUM_PATH && existsSync(process.env.CHROMIUM_PATH)) return process.env.CHROMIUM_PATH;
  const store = process.env.PLAYWRIGHT_BROWSERS_PATH;
  if (!store || !existsSync(store)) return undefined;
  const candidates = readdirSync(store)
    .filter((d) => d.startsWith('chromium-'))
    .map((d) => path.join(store, d, 'chrome-linux', 'chrome'))
    .filter(existsSync);
  return candidates[0];
}

const args = process.argv.slice(2);
const flag = (name, fallback) => {
  const i = args.indexOf(`--${name}`);
  if (i === -1) return fallback;
  const next = args[i + 1];
  return next && !next.startsWith('--') ? next : true;
};
const has = (name) => args.includes(`--${name}`);

const START = flag('url');
if (!START) {
  console.error('Usage: node extract.mjs --url <url> [--out dir] [--max-pages N] [--keep-js] [--wait ms] [--no-screenshots]');
  process.exit(1);
}
const OUT = path.resolve(String(flag('out', 'site')));
const MAX_PAGES = Number(flag('max-pages', 25));
const SETTLE_MS = Number(flag('wait', 2500));
const KEEP_JS = has('keep-js');
const SHOTS = !has('no-screenshots');

const origin = new URL(START).origin;
const saved = new Map();   // absolute asset url -> local path relative to OUT
const pageFor = new Map(); // absolute page url -> local path relative to OUT
const failures = [];

const ASSET_TYPES = new Set(['stylesheet', 'image', 'font', 'media', 'script', 'other']);

/** '/'-> index.html, '/about' -> about/index.html (keeps relative links valid on disk). */
function pagePath(urlStr) {
  const u = new URL(urlStr);
  let p = u.pathname;
  if (p === '' || p === '/') return 'index.html';
  p = p.replace(/^\/+|\/+$/g, '');
  if (/\.html?$/i.test(p)) return p;
  return `${p}/index.html`;
}

function assetPath(urlStr) {
  const u = new URL(urlStr);
  let p = u.pathname.replace(/^\/+/, '') || 'index';
  if (p.endsWith('/')) p += 'index';
  // Query strings are meaningful for CDN assets; fold them into the filename.
  if (u.search) {
    const tag = createHash('sha1').update(u.search).digest('hex').slice(0, 8);
    const ext = path.extname(p);
    p = ext ? `${p.slice(0, -ext.length)}.${tag}${ext}` : `${p}.${tag}`;
  }
  p = p.split('/').map((s) => s.replace(/[^\w.@-]/g, '_')).join('/');
  return `assets/${u.hostname}/${p}`;
}

/** Relative href from one local file to another, POSIX style. */
function relFrom(fromFile, toFile) {
  const r = path.posix.relative(path.posix.dirname(fromFile), toFile);
  return r.startsWith('.') ? r : `./${r}`;
}

async function write(rel, body) {
  const abs = path.join(OUT, rel);
  await mkdir(path.dirname(abs), { recursive: true });
  await writeFile(abs, body);
}

const CSS_REF = /url\(\s*(['"]?)([^'")]+)\1\s*\)|@import\s+(['"])([^'"]+)\3/g;

/** Every absolute URL a stylesheet references. */
function cssRefs(css, cssUrl) {
  const out = new Set();
  for (const m of css.matchAll(CSS_REF)) {
    const ref = m[2] ?? m[4];
    if (!ref || /^(data:|blob:|#)/i.test(ref)) continue;
    try { out.add(new URL(ref, cssUrl).toString().split('#')[0]); } catch {}
  }
  return out;
}

/** Rewrite url(...) and @import inside a stylesheet to local relative paths. */
function rewriteCss(css, cssUrl, cssLocal) {
  return css.replace(CSS_REF, (m, q, ref, iq, iref) => {
    const target = ref ?? iref;
    if (!target || /^(data:|blob:|#)/i.test(target)) return m;
    let abs;
    try { abs = new URL(target, cssUrl).toString().split('#')[0]; } catch { return m; }
    const local = saved.get(abs);
    const replacement = local ? relFrom(cssLocal, local) : abs;
    return ref !== undefined ? `url(${q}${replacement}${q})` : `@import ${iq}${replacement}${iq}`;
  });
}

const executablePath = findChromium();
if (executablePath) console.log(`Using Chromium at ${executablePath}`);
const browser = await chromium.launch({ executablePath });
const ctx = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  userAgent: 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36',
});

const cssBodies = new Map(); // asset url -> raw css text, rewritten after the crawl

ctx.on('response', async (res) => {
  const url = res.url().split('#')[0];
  if (!/^https?:/.test(url) || saved.has(url) || !res.ok()) return;
  const type = res.request().resourceType();
  if (!ASSET_TYPES.has(type)) return;
  if (type === 'script' && !KEEP_JS) return;
  try {
    const buf = await res.body();
    const rel = assetPath(url);
    saved.set(url, rel);
    if (type === 'stylesheet') cssBodies.set(url, buf.toString('utf8'));
    else await write(rel, buf);
  } catch (e) {
    failures.push({ url, reason: e.message });
  }
});

const queue = [new URL(START).toString()];
const seen = new Set(queue);
const pages = [];

while (queue.length && pages.length < MAX_PAGES) {
  const url = queue.shift();
  const page = await ctx.newPage();
  try {
    await page.goto(url, { waitUntil: 'networkidle', timeout: 60000 });
    // Scroll the full height so lazy-loaded images and reveal animations fire.
    await page.evaluate(async () => {
      await new Promise((done) => {
        let y = 0;
        const step = () => {
          window.scrollBy(0, window.innerHeight);
          y += window.innerHeight;
          if (y < document.body.scrollHeight + window.innerHeight) setTimeout(step, 120);
          else { window.scrollTo(0, 0); done(); }
        };
        step();
      });
    });
    await page.waitForTimeout(SETTLE_MS);

    if (SHOTS) {
      // A full-page render is the reference for rebuilding the design later,
      // and the quickest way to eyeball whether the capture is faithful.
      const shot = `screenshots/${pagePath(url).replace(/\/?index\.html$/, '') || 'index'}.png`;
      await mkdir(path.dirname(path.join(OUT, shot)), { recursive: true });
      await page.screenshot({ path: path.join(OUT, shot), fullPage: true });
    }

    const local = pagePath(url);
    pageFor.set(url, local);
    const html = await page.content();
    const title = await page.title();
    const links = await page.$$eval('a[href]', (as) => as.map((a) => a.href));
    pages.push({ url, local, title, html });

    for (const l of links) {
      const clean = l.split('#')[0];
      if (!clean.startsWith(origin) || seen.has(clean)) continue;
      if (/\.(pdf|zip|jpg|jpeg|png|gif|svg|webp|mp4|webm|docx?)$/i.test(clean)) continue;
      seen.add(clean);
      queue.push(clean);
    }
    console.log(`  captured ${local.padEnd(32)} ${title}`);
  } catch (e) {
    failures.push({ url, reason: e.message });
    console.error(`  FAILED ${url}: ${e.message}`);
  } finally {
    await page.close();
  }
}

// A browser only downloads a background-image when some element matches the
// rule, so assets behind unused rules (alternate themes, hover states,
// breakpoints not hit at this viewport) are missing at this point. Sweep the
// stylesheets and fetch anything that was referenced but never requested.
let sweepQueue = [...cssBodies.keys()];
let fetched = 0;
while (sweepQueue.length) {
  const next = [];
  for (const cssUrl of sweepQueue) {
    for (const ref of cssRefs(cssBodies.get(cssUrl), cssUrl)) {
      if (saved.has(ref)) continue;
      try {
        const r = await ctx.request.get(ref, { timeout: 20000 });
        if (!r.ok()) { failures.push({ url: ref, reason: `HTTP ${r.status()}` }); continue; }
        const buf = await r.body();
        const rel = assetPath(ref);
        saved.set(ref, rel);
        fetched++;
        if (/\.css($|\?)/i.test(ref) || (r.headers()['content-type'] || '').includes('text/css')) {
          cssBodies.set(ref, buf.toString('utf8'));
          next.push(ref);          // an @import can pull in further stylesheets
        } else {
          await write(rel, buf);
        }
      } catch (e) {
        failures.push({ url: ref, reason: e.message });
      }
    }
  }
  sweepQueue = next;
}
if (fetched) console.log(`  swept ${fetched} asset(s) referenced only by unused CSS rules`);

// Stylesheets are written last so that url() targets are all known by then.
for (const [url, css] of cssBodies) {
  const rel = saved.get(url);
  await write(rel, rewriteCss(css, url, rel));
}

// Rewrite each captured page's references to local relative paths.
for (const p of pages) {
  let html = p.html;
  const swap = (ref) => {
    if (!ref || /^(data:|blob:|mailto:|tel:|javascript:|#)/i.test(ref)) return null;
    let abs;
    try { abs = new URL(ref, p.url).toString().split('#')[0]; } catch { return null; }
    const target = saved.get(abs) || pageFor.get(abs);
    return target ? relFrom(p.local, target) : null;
  };

  // src / href / poster attributes
  html = html.replace(/\b(src|href|poster)=("|')(.*?)\2/gi, (m, attr, q, ref) => {
    const r = swap(ref);
    return r ? `${attr}=${q}${r}${q}` : m;
  });
  // srcset candidate lists
  html = html.replace(/\bsrcset=("|')(.*?)\1/gi, (m, q, list) => {
    const out = list.split(',').map((c) => {
      const [ref, ...rest] = c.trim().split(/\s+/);
      const r = swap(ref);
      return [r || ref, ...rest].join(' ');
    }).join(', ');
    return `srcset=${q}${out}${q}`;
  });
  // <style> blocks and inline style="" url()s
  html = html.replace(/<style[^>]*>([\s\S]*?)<\/style>/gi, (m, css) =>
    m.replace(css, rewriteCss(css, p.url, p.local)));

  if (!KEEP_JS) {
    // The DOM is already rendered; leaving framework JS in would re-hydrate and
    // wipe it. Strip scripts but keep <noscript> content and JSON-LD metadata.
    html = html.replace(/<script(?![^>]*application\/ld\+json)[^>]*>[\s\S]*?<\/script>/gi, '');
  }
  await write(p.local, html);
}

const manifest = {
  source: START,
  extractedAt: new Date().toISOString(),
  jsStripped: !KEEP_JS,
  pages: pages.map(({ url, local, title }) => ({ url, local, title })),
  assets: [...saved.entries()].map(([url, local]) => ({ url, local })),
  sweptAssets: fetched,
  failures,
};
await write('extraction-manifest.json', JSON.stringify(manifest, null, 2));

await browser.close();
console.log(`\nDone. ${pages.length} page(s), ${saved.size} asset(s), ${failures.length} failure(s) -> ${OUT}`);
if (failures.length) console.log('See extraction-manifest.json for the failure list.');
