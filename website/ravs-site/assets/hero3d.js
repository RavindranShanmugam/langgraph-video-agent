/* Hero graph — the LangGraph video agent's own pipeline, in 3D.
 *
 * Nodes and edges mirror agent/nodes/ in the repo the Featured Projects card
 * links to: ingest → transcribe → plan → select → assemble → render, with
 * fallback hanging off select and rejoining at render. That branch is the
 * point the copy makes ("a failure is contained to the node that caused it"),
 * so it is drawn differently from the happy path.
 *
 * Loaded only after index.html decides the device should have it — see the
 * guards there. This module assumes it was called deliberately.
 */
import * as THREE from './vendor/three.module.min.js';

const INK    = 0x14161A;
const ACCENT = 0xE6FF4A;
const EDGE   = 0xB0B0AC;
const FAINT  = 0xD4D4D0;

/* x, y, z laid out so the graph reads left-to-right flat-on, but gains real
   depth as it turns. Hand-placed rather than generated — a force layout put
   the branch behind the main chain at every useful camera angle. */
const NODES = [
  { id: 'ingest',     pos: [-2.6,  0.70, -0.40] },
  { id: 'transcribe', pos: [-1.6, -0.20,  0.60] },
  { id: 'plan',       pos: [-0.5,  0.80,  0.10] },
  { id: 'select',     pos: [ 0.6, -0.10, -0.60] },
  { id: 'assemble',   pos: [ 1.7,  0.70,  0.50] },
  { id: 'render',     pos: [ 2.6, -0.30, -0.10] },
  { id: 'fallback',   pos: [ 0.9, -1.55,  0.40] },
];

/* [from, to, isFallbackPath] */
const EDGES = [
  ['ingest',     'transcribe', false],
  ['transcribe', 'plan',       false],
  ['plan',       'select',     false],
  ['select',     'assemble',   false],
  ['assemble',   'render',     false],
  ['select',     'fallback',   true ],
  ['fallback',   'render',     true ],
];

/* The pulse walks the happy path only. Watching it skip the fallback branch is
   the whole idea: the recovery route exists but is not the normal one. */
const PULSE_PATH = [0, 1, 2, 3, 4];

/* Reused so the loop never allocates a Color per node per frame. */
const FLASH_ON  = new THREE.Color(ACCENT);
const FLASH_OFF = new THREE.Color(0x000000);

export function mountHeroGraph(canvas) {
  const byId = new Map(NODES.map(n => [n.id, new THREE.Vector3(...n.pos)]));

  const renderer = new THREE.WebGLRenderer({
    canvas, alpha: true, antialias: true, powerPreference: 'low-power',
  });
  renderer.setClearAlpha(0);

  const scene  = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(40, 1, 0.1, 100);
  camera.position.set(0, 0, 6.0);

  scene.add(new THREE.AmbientLight(0xffffff, 2.1));
  const key = new THREE.DirectionalLight(0xffffff, 2.4);
  key.position.set(3, 5, 6);
  scene.add(key);
  const rim = new THREE.DirectionalLight(0xffffff, 0.9);
  rim.position.set(-5, -2, -4);
  scene.add(rim);

  /* One group so the whole graph turns as a unit and the parallax stays
     independent of the spin. */
  const graph = new THREE.Group();
  /* The node cloud's centroid sits below y=0; lift it so it reads centred. */
  graph.position.y = 0.36;
  scene.add(graph);

  /* ---- nodes ---------------------------------------------------------- */
  const nodeGeo  = new THREE.SphereGeometry(0.26, 32, 24);
  const nodeMats = new Map();
  const meshes   = new Map();

  for (const n of NODES) {
    const isFallback = n.id === 'fallback';
    const mat = new THREE.MeshStandardMaterial({
      color: isFallback ? 0xFFFFFF : INK,
      roughness: isFallback ? 0.9 : 0.66,
      metalness: 0.0,
      emissive: 0x000000,
    });
    /* The fallback node is drawn hollow — outlined, not filled — so it reads as
       a path that exists but is not normally taken. */
    const mesh = new THREE.Mesh(nodeGeo, mat);
    mesh.position.copy(byId.get(n.id));
    mesh.scale.setScalar(isFallback ? 0.74 : 1);
    graph.add(mesh);

    if (isFallback) {
      const ring = new THREE.Mesh(
        new THREE.SphereGeometry(0.265, 32, 24),
        new THREE.MeshBasicMaterial({ color: EDGE, side: THREE.BackSide }),
      );
      ring.scale.setScalar(0.74);
      ring.position.copy(mesh.position);
      graph.add(ring);
    }

    nodeMats.set(n.id, mat);
    meshes.set(n.id, mesh);
  }

  /* ---- edges ----------------------------------------------------------- */
  /* A cylinder oriented between two points. Cheaper and thicker-looking than
     LineSegments, which render hairline-thin and wash out on white. */
  const edgeGeo = new THREE.CylinderGeometry(1, 1, 1, 10, 1, true);
  const UP = new THREE.Vector3(0, 1, 0);

  for (const [from, to, isFallback] of EDGES) {
    const a = byId.get(from), b = byId.get(to);
    const mid = a.clone().add(b).multiplyScalar(0.5);
    const dir = b.clone().sub(a);
    const len = dir.length();

    const tube = new THREE.Mesh(edgeGeo, new THREE.MeshBasicMaterial({
      color: isFallback ? FAINT : EDGE,
      transparent: isFallback,
      opacity: isFallback ? 0.85 : 1,
    }));
    tube.position.copy(mid);
    tube.quaternion.setFromUnitVectors(UP, dir.clone().normalize());
    tube.scale.set(isFallback ? 0.026 : 0.038, len, isFallback ? 0.026 : 0.038);
    graph.add(tube);
  }

  /* ---- travelling pulse ------------------------------------------------ */
  const pulse = new THREE.Mesh(
    new THREE.SphereGeometry(0.115, 20, 16),
    new THREE.MeshBasicMaterial({ color: ACCENT }),
  );
  graph.add(pulse);

  const SEG_MS = 900;   /* time to cross one edge */
  const HOLD_MS = 260;  /* pause on arrival, while the node flashes */
  const CYCLE = PULSE_PATH.length * (SEG_MS + HOLD_MS);

  /* ---- interaction ----------------------------------------------------- */
  let targetX = 0, targetY = 0, curX = 0, curY = 0;
  const fine = matchMedia('(pointer: fine)').matches;

  function onMove(e) {
    const r = canvas.getBoundingClientRect();
    targetY = ((e.clientX - (r.left + r.width  / 2)) / r.width)  * 0.42;
    targetX = ((e.clientY - (r.top  + r.height / 2)) / r.height) * 0.28;
  }
  if (fine) window.addEventListener('mousemove', onMove, { passive: true });

  /* ---- sizing ---------------------------------------------------------- */
  function resize() {
    const r = canvas.getBoundingClientRect();
    if (!r.width || !r.height) return;
    renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
    renderer.setSize(r.width, r.height, false);
    camera.aspect = r.width / r.height;
    /* Pull the camera back on narrow boxes so the graph never crops. */
    camera.position.z = 6.0 * Math.max(1, 1.45 / camera.aspect);
    camera.updateProjectionMatrix();
  }
  const ro = new ResizeObserver(resize);
  ro.observe(canvas);
  resize();

  /* ---- loop ------------------------------------------------------------ */
  let raf = 0, running = false, t0 = 0;

  function frame(now) {
    if (!running) return;
    raf = requestAnimationFrame(frame);
    if (!t0) t0 = now;
    const t = now - t0;

    graph.rotation.y = 0.28 + t * 0.000085;

    /* Ease the parallax rather than tracking the cursor exactly. */
    curX += (targetX - curX) * 0.045;
    curY += (targetY - curY) * 0.045;
    graph.rotation.x = curX;
    graph.position.x = curY * 0.5;

    /* Advance the pulse and flash whichever node it just reached. */
    const p = t % CYCLE;
    const idx = Math.floor(p / (SEG_MS + HOLD_MS));
    const local = p - idx * (SEG_MS + HOLD_MS);
    const a = byId.get(NODES[PULSE_PATH[idx]].id);
    const b = byId.get(NODES[PULSE_PATH[idx] + 1].id);
    const k = Math.min(1, local / SEG_MS);
    /* smoothstep — the pulse eases out of a node and into the next */
    const e = k * k * (3 - 2 * k);
    pulse.position.lerpVectors(a, b, e);
    pulse.visible = k < 1;   /* absorbed by the node it reaches */

    for (const n of NODES) {
      const mat = nodeMats.get(n.id);
      if (n.id === 'fallback') continue;
      const arrived = k >= 1 && NODES[PULSE_PATH[idx] + 1].id === n.id;
      mat.emissive.lerp(arrived ? FLASH_ON : FLASH_OFF, arrived ? 0.42 : 0.12);
    }

    renderer.render(scene, camera);
  }

  function start() { if (!running) { running = true; raf = requestAnimationFrame(frame); } }
  function stop()  { running = false; cancelAnimationFrame(raf); }

  /* Only burn frames while the hero is on screen and the tab is focused. */
  const io = new IntersectionObserver(
    ([entry]) => (entry.isIntersecting && !document.hidden ? start() : stop()),
    { threshold: 0.01 },
  );
  io.observe(canvas);
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) stop(); else start();
  });

  /* Losing the GL context on a laptop lid-close should not leave a dead canvas. */
  canvas.addEventListener('webglcontextlost', e => { e.preventDefault(); stop(); });
  canvas.addEventListener('webglcontextrestored', () => { resize(); start(); });

  start();
  canvas.classList.add('is-live');
}
