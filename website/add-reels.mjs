#!/usr/bin/env node
/**
 * Turns Instagram-export reels into web-ready clips for the site.
 *
 * An export .mp4 is typically 10-50MB, shot vertical, with audio — far too
 * heavy to serve directly. Each clip is re-encoded to a capped-height H.264
 * file with audio stripped (the row plays muted anyway) and a poster frame
 * pulled so nothing downloads until the viewer actually hovers a card.
 *
 * Usage:
 *   node add-reels.mjs <file-or-folder> [...]        # add clips
 *   node add-reels.mjs --list                        # show what is wired up
 *   node add-reels.mjs --clear                       # remove all clips
 *
 * Options:
 *   --max <n>        most clips to take from a folder (default 6)
 *   --height <px>    output height, width follows aspect (default 1280)
 *   --crf <n>        quality, lower is better/bigger (default 30)
 *   --out <dir>      output dir (default ravs-site/assets/reels)
 */
import { execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const argv = process.argv.slice(2);
const opt = (name, fb) => { const i = argv.indexOf(`--${name}`); return i === -1 ? fb : argv[i + 1]; };
const has = (name) => argv.includes(`--${name}`);

/* fileURLToPath, not URL.pathname: on Windows the latter yields "/C:/..." and
   path.resolve then prepends the drive again, giving "C:\C:\...". */
const HERE    = path.dirname(fileURLToPath(import.meta.url));
const OUT     = path.resolve(opt('out', path.join(HERE, 'ravs-site/assets/reels')));
const MANIFEST= path.join(OUT, 'reels.json');
const MAX     = Number(opt('max', 6));
const HEIGHT  = Number(opt('height', 1280));
const CRF     = Number(opt('crf', 30));

let ffmpeg;
try {
  ffmpeg = (await import('ffmpeg-static')).default;
} catch {
  console.error('ffmpeg-static is missing. Run `npm install` in website/ first.');
  process.exit(1);
}
if (!ffmpeg || !existsSync(ffmpeg)) {
  console.error('ffmpeg binary not found. Run `npm install` in website/ first.');
  process.exit(1);
}

const read = () => (existsSync(MANIFEST) ? JSON.parse(readFileSync(MANIFEST, 'utf8')) : []);
const mb = (p) => (statSync(p).size / 1048576).toFixed(1);

if (has('list')) {
  const reels = read();
  if (!reels.length) console.log('No reels wired up yet.');
  else for (const r of reels) console.log(`  ${r.file.padEnd(16)} ${mb(path.join(OUT, r.file)).padStart(6)} MB  ${r.caption || ''}`);
  process.exit(0);
}

if (has('clear')) {
  if (existsSync(OUT)) rmSync(OUT, { recursive: true, force: true });
  console.log('Cleared', OUT);
  process.exit(0);
}

// Expand folders into their .mp4 files, newest first — an export folder holds
// far more clips than belong on a landing page.
const inputs = [];
for (const arg of argv.filter((a) => !a.startsWith('--') && !/^\d+$/.test(a))) {
  const p = path.resolve(arg);
  if (!existsSync(p)) { console.error(`skip (not found): ${arg}`); continue; }
  if (statSync(p).isDirectory()) {
    const vids = readdirSync(p)
      .filter((f) => /\.(mp4|mov|m4v)$/i.test(f))
      .map((f) => path.join(p, f))
      .sort((a, b) => statSync(b).mtimeMs - statSync(a).mtimeMs);
    inputs.push(...vids);
  } else inputs.push(p);
}

if (!inputs.length) {
  console.error('Nothing to do. Pass one or more .mp4 files, or a folder of them.');
  process.exit(1);
}

const take = inputs.slice(0, MAX);
if (inputs.length > take.length) console.log(`Found ${inputs.length} clips, taking the ${take.length} newest (raise with --max).`);

mkdirSync(OUT, { recursive: true });
const reels = read();
let n = reels.length;

for (const src of take) {
  n += 1;
  const base   = `reel-${String(n).padStart(2, '0')}`;
  const file   = `${base}.mp4`;
  const poster = `${base}.jpg`;
  process.stdout.write(`  ${path.basename(src)} (${mb(src)} MB) -> ${file} `);
  try {
    execFileSync(ffmpeg, [
      '-y', '-loglevel', 'error', '-i', src,
      // Cap the height, keep the aspect, force even dimensions for H.264.
      '-vf', `scale=-2:'min(${HEIGHT},ih)'`,
      '-c:v', 'libx264', '-profile:v', 'high', '-crf', String(CRF), '-preset', 'slow',
      // 4:2:0 is mandatory for Safari/iOS — without it they refuse to decode,
      // and libx264 rejects the high profile for 4:4:4 sources outright.
      '-pix_fmt', 'yuv420p',
      '-movflags', '+faststart',   // metadata first so playback starts early
      '-an',                       // the row plays muted; audio is dead weight
      path.join(OUT, file),
    ]);
    execFileSync(ffmpeg, [
      '-y', '-loglevel', 'error', '-i', path.join(OUT, file),
      '-vf', 'thumbnail', '-frames:v', '1', '-q:v', '4',
      path.join(OUT, poster),
    ]);
    console.log(`${mb(path.join(OUT, file))} MB`);
    reels.push({ file, poster, caption: '', link: '' });
  } catch (e) {
    n -= 1;
    console.log('FAILED');
    console.error(`    ${e.message.split('\n')[0]}`);
    // Do not leave a truncated clip behind for the page to try to play.
    for (const f of [file, poster]) {
      const p = path.join(OUT, f);
      if (existsSync(p)) rmSync(p, { force: true });
    }
  }
}

writeFileSync(MANIFEST, JSON.stringify(reels, null, 2) + '\n');
const total = reels.reduce((s, r) => s + statSync(path.join(OUT, r.file)).size, 0) / 1048576;
console.log(`\n${reels.length} reel(s), ${total.toFixed(1)} MB total -> ${OUT}`);
console.log(`Add a caption or an Instagram permalink per clip by editing ${path.relative(process.cwd(), MANIFEST)}.`);
