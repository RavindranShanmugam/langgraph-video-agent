# Simulation report — ravs-site

Run against `http://127.0.0.1:8081/` (index.html + about.html) in headless
Chromium, 2026-08-28. Five personas driven through real sessions, plus the
edge-case battery. Every finding below was reproduced in the browser.

Cast: **Rusher**, **Skeptic**, **Phone user**, **Keyboard-only**, plus a
**Slow-connection** persona swapped in for Returning visitor — the site is two
pages with no state to return to, but it *is* aimed at small-business owners in
the Triangle who will open it on mobile data, so that risk was the realer one.

Evidence screenshots: `scratchpad/sim/`.

---

### [RESOLVED — was BLOCKER] The Resume button in the nav 404s on both pages

> **Fixed 2026-08-28.** The nav on both pages now points at `resume.html`, a
> full résumé page, instead of the missing `assets/resume.pdf`. Re-verified:
> all three internal links return 200.

- **Persona:** Skeptic (also any recruiter)
- **Steps:** Load `/index.html` → click **Resume** in the top-right nav.
- **Expected:** A CV, since the nav offers it as a primary destination.
- **Actual:** `GET /assets/resume.pdf` → **404**. The file does not exist.
- **Evidence:** `Resume link status: 404`; link audit row `404 http://127.0.0.1:8081/assets/resume.pdf`
- **Fix:** Add `assets/resume.pdf`, or remove the button until the file exists.

This is the worst thing on the site. The Skeptic's whole job is verifying you're
real, and the nav hands them a broken page. A missing button costs nothing; a
broken one costs trust.

---

### [MAJOR] "Every system here is real" — but two of three cards can't be checked

- **Persona:** Skeptic
- **Steps:** Read the Featured Projects subhead → try to verify each card.
- **Expected:** Three verifiable projects, per the subhead: *"Every system here
  is real, running, and published openly on GitHub."*
- **Actual:** Only **LangGraph Video Agent** has a "View the code" link.
  **Speed-to-Lead** and **Finance Spreadsheet Agent** have none.
- **Evidence:**
  ```
  NO LINK   Speed-to-Lead             -> null
  NO LINK   Finance Spreadsheet Agent -> null
  HAS LINK  LangGraph Video Agent     -> github.com/.../langgraph-video-agent
  ```
- **Fix:** Link the other two repos, or soften the subhead so the claim matches
  what's actually linkable.

The copy makes a falsifiable promise and two thirds of the evidence is absent.
A skeptic who notices reads it as padding.

---

### [MINOR] Every page load logs a 404 for `reels.json`, and the section renders empty

- **Persona:** all
- **Steps:** Load any page with devtools open.
- **Expected:** No console errors.
- **Actual:** `net::ERR_ABORTED http://127.0.0.1:8081/assets/reels/reels.json`
  on every load. The "On Instagram" section shows a heading and a follow button
  with no content between them.
- **Fix:** Ship a `reels.json` (even `[]`), or `HEAD`-check before fetching.

Degrades gracefully — the section doesn't break — but it's a permanent red error
in the console of a site whose selling point is that you build reliable systems.

---

### [MINOR] 26 pieces of text are under 12px on a phone, some at 10px

- **Persona:** Phone user
- **Steps:** 390x844, read the page without zooming.
- **Expected:** Body and label text legible at arm's length.
- **Actual:** 26 elements compute under 12px; the meta strip is 11px and card
  tags ("LIVE", "VOICE AI") are 10px.
- **Evidence:** `text < 12px : 26` — matches Impeccable's 24 `undersized-ui-text`
  hits independently.
- **Fix:** Raise the floor to 12px on mobile; the ramp can stay as-is on desktop.

---

### [MINOR] Ten tap targets are under 44px on mobile

- **Persona:** Phone user
- **Steps:** 390x844, touch emulation on; measure every anchor.
- **Actual:** Nav pills are 36px tall; the three footer social icons are 34x34.
- **Evidence:** `tap targets < 44px : 10` (smallest 34x34 — Instagram, LinkedIn,
  GitHub).
- **Fix:** Pad the social icons to 44x44 and the nav pills to 44px tall.

Worth calibrating: 34x34 clears the WCAG 2.5.8 AA floor of 24x24, so this is not
a conformance failure. It's below the 44px comfort standard, and the three
smallest sit in a row in the footer where mis-taps are likeliest.

---

### [MINOR] Horizontal overflow appears below ~300px of viewport width

- **Persona:** Phone user zooming in
- **Steps:** Load at progressively narrower widths.
- **Actual:**
  ```
  195px: overflow 84px      320px: overflow 0px
  260px: overflow 19px      390px: overflow 0px
  ```
- **Fix:** Find the fixed-width element that stops shrinking under 300px.

Real 200% browser zoom on a 390px phone lands near a 195px CSS viewport, which
is how a low-vision user reaches this. At every normal width the page is clean.

---

### [POLISH] `ravi.jpg` has no width/height, so the nav can reflow as it loads

- **Persona:** Slow connection
- **Steps:** Throttle to ~400kbps, reload, watch the header.
- **Actual:** The only `<img>` on the page carries neither attribute nor a CSS
  aspect-ratio.
- **Fix:** Add `width="40" height="40"` to the brand image.

---

### [POLISH] The primary CTA is roughly four screens down

- **Persona:** Rusher
- **Steps:** Land cold, look for how to contact.
- **Actual:** "Book a 20-minute call" sits at y=3321 on desktop, y=3676 on
  mobile.
- **Fix:** Optional — the sticky nav already carries "Let's Talk".

Filed as polish, not major, precisely because the nav is `position: sticky` and
"Let's Talk" never leaves the screen. The conversion path is genuinely always
one click away; this is about the *scroll* CTA, not about reachability.

---

## Checked and cleared — these are NOT defects

Worth recording, because three of them looked like bugs until the browser said
otherwise:

- **`Let'sDiscuss`** — the DOM is `Let's<br>Discuss`, an intentional two-line
  heading. A text dump makes it look like a missing space. It renders correctly.
- **LinkedIn returning `999`** — that is LinkedIn refusing an automated request,
  not a broken link. The URL is correct.
- **Focus indicators** — a computed-style probe reported `outline-width: 0px` on
  four links, which looked like a serious keyboard-accessibility defect.
  Screenshotting each one focused *and* unfocused disproved it: the border
  darkens and thickens visibly on every stop. All 14 focus stops are visible and
  in correct document order.
- **Horizontal overflow** at 390 / 768 / 1440 / 2560 — zero at all four.
- **`about.html`** deep-linked cold — zero console errors, zero failed requests,
  no overflow at 1440 or 390. It stands alone correctly.
- **Back button** after navigating to About returns to the homepage correctly.
- **Forms** — the form-abuse battery (empty submit, 5,000-char paste, unicode,
  double-fire) did not run: the site has **0 forms, 0 inputs, 0 buttons**. All
  conversion is outbound links. Nothing to abuse.

## What worked

- **The sticky nav.** It is the single reason the buried CTA is not a real
  problem. "Let's Talk" is reachable from every scroll position on every
  viewport.
- **The mobile layout.** Zero horizontal overflow at every real device width,
  and the hero degrades to the original centred version cleanly.
- **The new 3D hero's guards.** On a throttled ~400kbps link the H1 "RAVI" was
  painted at 1816ms and the WebGL hero correctly never loaded at all. It also
  stays out of the document entirely below 1000px and under reduced-motion.
  That is the behaviour you want and it holds under pressure.
- **`about.html` is clean.** Not one error, failed request, or overflow.
- **Tab order** follows visual order exactly, with no keyboard traps.

## The one change  — done

**Ship `assets/resume.pdf` or delete the Resume button.**

Everything else on this list is a refinement. This one was a promise the site
made in its top-right corner, on both pages, to exactly the person you most
need to convince — and it resolved to a 404.

**Closed 2026-08-28** by adding `resume.html` and repointing the nav on both
pages. The next-highest item is now the MAJOR above: two of three project cards
still can't be verified, against a subhead that promises all three can.
