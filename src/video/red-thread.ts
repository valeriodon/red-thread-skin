/**
 * <red-thread>: the drawn half of the Red Thread skin.
 *
 * One canvas over the picture draws everything the viewer sees: the thread that is the timeline,
 * the play triangle it folds into on pause, the preview hanging from it, the volume pull cord and
 * the captions and fullscreen icons. It reads the Video.js player store every frame and calls the
 * store's actions; the real Video.js controls stay in the DOM for keyboard and assistive technology.
 */

// The skin does not know which features the host player was built with, so the store is read loosely.
// biome-ignore lint/suspicious/noExplicitAny: feature state is optional per player
type Store = any;
// biome-ignore lint/suspicious/noExplicitAny: media components share the HTMLMediaElement shape
type Media = any;
type Point = [number, number];

const N = 140;
const clamp = (v: number, a: number, b: number) => Math.min(b, Math.max(a, v));
const spring = (x: number, v: number, target: number, k: number, c: number, dt: number): [number, number] => {
  const nv = v + ((target - x) * k - v * c) * dt;
  return [x + nv * dt, nv];
};
const two = (n: number) => String(n).padStart(2, '0');
const formatTime = (seconds: number) => {
  const s = Math.max(0, Math.floor(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return h ? `${h}:${two(m)}:${two(s % 60)}` : `${two(m)}:${two(s % 60)}`;
};

function mount(host: HTMLElement, signal: AbortSignal) {
  const container = (host.closest('media-container') ?? host.parentElement) as HTMLElement;
  const canvas = document.createElement('canvas');
  canvas.setAttribute('aria-hidden', 'true');
  host.replaceChildren(canvas);
  const sx = canvas.getContext('2d') as CanvasRenderingContext2D;
  const motionQuery = matchMedia('(prefers-reduced-motion: reduce)');
  let RM = motionQuery.matches;
  const find =<T extends HTMLElement>(selector: string) => container.querySelector<T>(selector);
  const ccBtn = find('.rt-captions-button');
  const fsBtn = find('.rt-fullscreen-button');
  const chapterEl = find('.rt-chapter');
  const captionsEl = find('.rt-captions');
  const captionsText = captionsEl?.querySelector('span') ?? null;
  const topBar = find('.rt-top');
  const muteBtn = find('.rt-mute-button');
  const playBtn = find('.rt-play-button');
  const sliderEl = find('.rt-time-slider');
  const focused = (el: HTMLElement | null) => !!el && el.matches(':focus-visible, :has(:focus-visible)');
  let RED = '#ff4530';

  const getStore = (): Store | null => {
    // biome-ignore lint/suspicious/noExplicitAny: walking up to whichever player element provides the store
    let el: any = host;
    while (el) {
      if (el.store) return el.store;
      el = el.parentElement;
    }
    return null;
  };

  let mediaEl: Media = null;
  const getMedia = (): Media => {
    if (mediaEl?.isConnected) return mediaEl;
    mediaEl = null;
    for (const el of Array.from(container.children) as Media[]) {
      if ('currentTime' in el && 'textTracks' in el) {
        mediaEl = el;
        hideNativeCues(el);
        break;
      }
    }
    return mediaEl;
  };

  /** The skin writes captions itself; media components with a shadow root need the rule inside it. */
  function hideNativeCues(el: Media) {
    try {
      if (!el.shadowRoot) return;
      const sheet = new CSSStyleSheet();
      sheet.replaceSync('video::-webkit-media-text-track-container{opacity:0}');
      el.shadowRoot.adoptedStyleSheets = [...el.shadowRoot.adoptedStyleSheets, sheet];
    } catch {
      // Native captions stay visible, which is still correct.
    }
  }

  // ── state ──────────────────────────────────────────────────────────────────────────────────
  let W = 0;
  let H = 0;
  let dpr = 1;
  let fNow = 0;
  let ready = false;
  // thread
  let sag = 1;
  let sagV = 0;
  let morph = 1;
  let morphV = 0;
  let yb = 0;
  let ybV = 0;
  let intro = RM ? 1 : 0;
  let hov = 0;
  const harm = [0, 0, 0, 0, 0, 0];
  let pluckAt = -9;
  // pointer
  let drag = false;
  let volDrag = false;
  let volHover = false;
  let tap: { x: number; y: number } | null = null;
  let pend: { x: number; y: number } | null = null;
  // How far the pointer may wander and still count as a tap; a finger wobbles more than a mouse.
  let slop = 5;
  let inZone = false;
  let pu = 0.5;
  let px = 0;
  let py = 0;
  let lastSeekAt = 0;
  // time
  let dur = 0;
  let disp = 0;
  let lastMedia = -1;
  let pendingTo = -1;
  let pendingUntil = 0;
  let glide: { from: number; to: number; t0: number; bead: boolean } | null = null;
  // hanging preview
  let su = 0.5;
  let lastSu = 0.5;
  let signHold = 0;
  let swing = 0;
  let swingV = 0;
  let pop = 0;
  let popV = 0;
  const sprites = new Map<string, HTMLImageElement>();
  // pull cord
  let cordLen = 0;
  let cordAng = 0;
  let cordV = 0;
  // Where the browser leaves loudness to the hardware buttons (iPhone), the cord is the mute switch.
  let volumeFixed = false;
  // icons
  const ico = {
    cc: { h: 0, c: 0, v: 0, at: -9, a: 0, on: false },
    fs: { h: 0, c: 0, v: 0, at: -9, a: 0 },
  };
  let topA = 1;
  let lastCue = '';

  const PAD = () => clamp(W * 0.04, 18, 40);
  const ZONE = () => H * 0.58;
  const CORDX = () => W - PAD();
  const CORD = (level: number) => 26 + level * H * 0.28;
  const CORD_MUTED = 16;
  const nowS = () => performance.now() / 1000;

  motionQuery.addEventListener(
    'change',
    () => {
      RM = motionQuery.matches;
      if (RM) intro = 1;
    },
    { signal }
  );

  function size() {
    const r = canvas.getBoundingClientRect();
    dpr = Math.min(2, window.devicePixelRatio || 1);
    W = r.width;
    H = r.height;
    RED = getComputedStyle(container).getPropertyValue('--rt-thread').trim() || RED;
    const cw = Math.round(W * dpr);
    const ch = Math.round(H * dpr);
    if (canvas.width !== cw || canvas.height !== ch) {
      canvas.width = cw;
      canvas.height = ch;
      // Resizing clears the canvas after this frame's draw, so paint again before the browser does.
      if (ready) render(fNow, 0);
    }
    if (!yb) yb = H * 0.6;
  }
  const resizeObserver = new ResizeObserver(size);
  resizeObserver.observe(canvas);
  signal.addEventListener('abort', () => resizeObserver.disconnect());
  size();

  function pluck(u0: number, a: number) {
    if (RM) return;
    const u = clamp(u0, 0.04, 0.96);
    for (let k = 1; k <= 6; k++) {
      harm[k - 1] = ((2 * a) / (k * k * Math.PI * Math.PI * u * (1 - u))) * Math.sin(k * Math.PI * u);
    }
    pluckAt = nowS();
  }
  function kick(icon: { a: number; at: number }, a: number) {
    if (RM) return;
    icon.a = a;
    icon.at = nowS();
  }

  // ── actions ────────────────────────────────────────────────────────────────────────────────
  function togglePaused() {
    const s = getStore();
    if (!s) return;
    if (s.paused) Promise.resolve(s.play?.()).catch(() => {});
    else s.pause?.();
  }
  function seekTo(u: number) {
    const s = getStore();
    if (!s || !dur) return;
    pendingTo = clamp(u, 0, 0.999) * dur;
    pendingUntil = nowS() + 2;
    Promise.resolve(s.seek?.(pendingTo)).catch(() => {});
  }

  // ── pointer ────────────────────────────────────────────────────────────────────────────────
  function point(e: PointerEvent) {
    const r = canvas.getBoundingClientRect();
    px = e.clientX - r.left;
    py = e.clientY - r.top;
    pu = clamp((px - PAD()) / (W - 2 * PAD()), 0, 1);
  }
  const onCord = () => Math.abs(px - CORDX()) < 24 && py < cordLen + 28;

  canvas.addEventListener(
    'pointerdown',
    (e) => {
      if (e.button) return;
      point(e);
      slop = e.pointerType === 'mouse' ? 5 : 10;
      try {
        canvas.setPointerCapture(e.pointerId);
      } catch {
        // Capture is a nicety; the gesture still works without it.
      }
      container.setAttribute('data-rt-pointer', '');
      container.focus({ preventScroll: true });
      if (onCord()) {
        volDrag = true;
        tap = { x: px, y: py };
      } else if (py > ZONE() && dur) {
        pend = { x: px, y: py };
        inZone = true;
      } else tap = { x: px, y: py };
    },
    { signal }
  );

  canvas.addEventListener(
    'pointermove',
    (e) => {
      point(e);
      const s = getStore();
      if (e.pointerType === 'mouse' && !drag && !volDrag) {
        inZone = py > ZONE();
        volHover = onCord();
      }
      if (pend && Math.hypot(px - pend.x, py - pend.y) > slop) {
        pend = null;
        drag = true;
        glide = null;
      }
      if (drag && nowS() - lastSeekAt > 0.15) {
        lastSeekAt = nowS();
        seekTo(pu);
      }
      if (tap && Math.hypot(px - tap.x, py - tap.y) > slop) tap = null;
      if (volDrag && !tap && s) {
        if (volumeFixed) {
          // Pull down for sound, push up for silence.
          const mute = py < (CORD_MUTED + CORD(0.6)) / 2;
          if (mute !== !!s.muted) s.setMuted?.(mute);
        } else {
          if (s.muted) s.setMuted?.(false);
          s.setVolume?.(clamp((py - 26) / (H * 0.28), 0, 1));
        }
        if (!RM) cordV += (e.movementX || 0) * 0.03;
      }
    },
    { signal }
  );

  function release(e: PointerEvent) {
    const s = getStore();
    if (pend) {
      // A plain click: the preview stays where you clicked, the thread goes tight, the red runs up to it.
      pend = null;
      if (e.type === 'pointerup' && dur) {
        const to = clamp(pu, 0, 0.999);
        const from = disp / dur;
        seekTo(to);
        if (!RM) {
          glide = { from, to, t0: nowS(), bead: true };
          pluck(to, 3);
          swingV += (to > from ? -1 : 1) * 2.2;
          popV = 5;
        }
        su = to;
        lastSu = to;
        signHold = nowS() + 1.1;
      }
      if (e.pointerType !== 'mouse') inZone = false;
    } else if (drag) {
      drag = false;
      seekTo(pu);
      pluck(pu, clamp(py - yb, -46, 46));
      if (e.pointerType !== 'mouse') inZone = false;
    } else if (volDrag) {
      volDrag = false;
      if (tap && s) {
        s.setMuted?.(!s.muted);
        if (!RM) cordV += 3;
      }
    } else if (tap && e.type === 'pointerup') {
      togglePaused();
    }
    tap = null;
  }
  canvas.addEventListener('pointerup', release, { signal });
  canvas.addEventListener('pointercancel', release, { signal });
  canvas.addEventListener(
    'pointerleave',
    () => {
      if (!drag) inZone = false;
      volHover = false;
    },
    { signal }
  );
  // A finger scrolls the page, unless it starts on the thread, on the cord, or the player fills the screen.
  canvas.addEventListener(
    'touchstart',
    (e) => {
      const t = e.touches[0];
      if (!t) return;
      const r = canvas.getBoundingClientRect();
      const x = t.clientX - r.left;
      const y = t.clientY - r.top;
      const s = getStore();
      const filling = fsm.phase !== 'idle' || s?.isFullscreen;
      if (filling || y > ZONE() || (Math.abs(x - CORDX()) < 24 && y < cordLen + 28)) e.preventDefault();
    },
    { passive: false, signal }
  );
  // The pointer handlers above already acted on the touch. Without this the browser's follow-up click
  // could land on a button that the same tap has just made visible.
  canvas.addEventListener(
    'touchend',
    (e) => {
      if (e.cancelable) e.preventDefault();
    },
    { passive: false, signal }
  );

  for (const [btn, icon] of [
    [ccBtn, ico.cc],
    [fsBtn, ico.fs],
  ] as const) {
    btn?.addEventListener(
      'pointerenter',
      () => {
        icon.h = 1;
        kick(icon, 2.2);
      },
      { signal }
    );
    btn?.addEventListener(
      'pointerleave',
      () => {
        icon.h = 0;
      },
      { signal }
    );
  }

  // ── fullscreen: four threads reach the corners of the screen, go tight and pull the player open ──
  const fsm = { phase: 'idle' as 'idle' | 'shoot' | 'pull' | 'full' | 'release', t0: 0, g: 0, gv: 0, a: 0 };
  let placeholder: HTMLElement | null = null;
  let backdrop: HTMLElement | null = null;
  let ropes: HTMLCanvasElement | null = null;
  let savedStyle = '';
  let wasFullscreen = false;

  function stretchStart() {
    if (fsm.phase !== 'idle') return;
    const r = container.getBoundingClientRect();
    placeholder = document.createElement('div');
    placeholder.style.cssText = `width:100%;aspect-ratio:${r.width}/${r.height};`;
    // Lift the player out of the page at the exact spot it occupies, then leave a stand-in behind it,
    // so nothing moves on the first frame.
    savedStyle = container.style.cssText;
    const st = container.style;
    st.position = 'fixed';
    st.inset = 'auto';
    st.left = `${r.left}px`;
    st.top = `${r.top}px`;
    st.width = `${r.width}px`;
    st.height = `${r.height}px`;
    st.maxWidth = 'none';
    st.aspectRatio = 'auto';
    st.zIndex = '2147483001';
    container.after(placeholder);
    backdrop = document.createElement('div');
    backdrop.style.cssText = 'position:fixed;inset:0;background:#000;opacity:0;pointer-events:none;z-index:2147483000';
    ropes = document.createElement('canvas');
    ropes.style.cssText = 'position:fixed;inset:0;width:100%;height:100%;pointer-events:none;z-index:2147483002';
    document.body.append(backdrop, ropes);

    document.documentElement.style.overflow = 'hidden';
    fsm.phase = 'shoot';
    fsm.t0 = nowS();
    fsm.a = 0;
    fsm.g = 0;
    fsm.gv = 0;
    wasFullscreen = false;
    kick(ico.fs, 4);
  }
  function stretchRelease() {
    if (fsm.phase === 'full' || fsm.phase === 'pull') fsm.phase = 'release';
    kick(ico.fs, 4);
  }
  function stretchEnd() {
    container.style.cssText = savedStyle;
    placeholder?.remove();
    backdrop?.remove();
    ropes?.remove();
    placeholder = backdrop = ropes = null;
    document.documentElement.style.overflow = '';
    fsm.phase = 'idle';
    fsm.g = 0;
    fsm.gv = 0;
  }
  signal.addEventListener('abort', () => {
    if (fsm.phase !== 'idle') stretchEnd();
  });

  function toggleFullscreen(): boolean {
    const s = getStore();
    if (!s || RM) return false;
    if (s.isFullscreen) return false; // leaving real fullscreen is the player's job; the release follows it
    if (fsm.phase === 'idle') stretchStart();
    else stretchRelease();
    return true;
  }
  // Runs before the button's own handler, so the stretch can play before the browser takes over.
  fsBtn?.addEventListener(
    'click',
    (e) => {
      if (toggleFullscreen()) {
        e.stopImmediatePropagation();
        e.preventDefault();
      }
    },
    { capture: true, signal }
  );
  container.addEventListener(
    'keydown',
    (e) => {
      container.removeAttribute('data-rt-pointer');
      if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.altKey) return;
      const s = getStore();
      if (e.key.toLowerCase() === 'f' && s) {
        if (!toggleFullscreen()) {
          if (s.isFullscreen) Promise.resolve(s.exitFullscreen?.()).catch(() => {});
          else Promise.resolve(s.requestFullscreen?.()).catch(() => {});
        }
        e.preventDefault();
      } else if (e.key === 'Escape' && fsm.phase === 'full' && !s?.isFullscreen) {
        stretchRelease();
      }
    },
    { signal }
  );

  function stretchStep(now: number, dt: number, s: Store) {
    if (fsm.phase === 'idle' || !placeholder || !backdrop || !ropes) return;
    if (fsm.phase === 'shoot') {
      const k = Math.min(1, (now - fsm.t0) / 0.24);
      fsm.a = 1 - (1 - k) ** 3;
      if (k >= 1) fsm.phase = 'pull';
    } else if (fsm.phase === 'pull') {
      [fsm.g, fsm.gv] = spring(fsm.g, fsm.gv, 1, 95, 12, dt);
      if (Math.abs(fsm.g - 1) < 0.012 && Math.abs(fsm.gv) < 0.12) {
        fsm.g = 1;
        fsm.gv = 0;
        fsm.phase = 'full';
        Promise.resolve(s.requestFullscreen?.()).catch(() => {});
      }
    } else if (fsm.phase === 'full') {
      if (s.isFullscreen) wasFullscreen = true;
      else if (wasFullscreen) {
        wasFullscreen = false;
        fsm.phase = 'release';
      }
    } else if (fsm.phase === 'release') {
      fsm.a = 1;
      [fsm.g, fsm.gv] = spring(fsm.g, fsm.gv, 0, 130, 16, dt);
      if (Math.abs(fsm.g) < 0.012 && Math.abs(fsm.gv) < 0.12) {
        stretchEnd();
        return;
      }
    }
    const r = placeholder.getBoundingClientRect();
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const g = fsm.g;
    const gc = clamp(g, 0, 1);
    const x0 = r.left * (1 - g);
    const y0 = r.top * (1 - g);
    const w = r.width + (vw - r.width) * g;
    const h = r.height + (vh - r.height) * g;
    const st = container.style;
    st.position = 'fixed';
    st.inset = 'auto';
    st.left = `${x0}px`;
    st.top = `${y0}px`;
    st.width = `${w}px`;
    st.height = `${h}px`;
    st.maxWidth = 'none';
    st.aspectRatio = 'auto';
    st.zIndex = '2147483001';
    st.borderRadius = gc >= 1 ? '0' : `calc(var(--rt-radius) * ${1 - gc})`;
    backdrop.style.opacity = String(
      Math.max(fsm.phase === 'shoot' ? fsm.a * 0.35 : 0.35 * (fsm.phase === 'pull' ? 1 : gc), gc * 0.94)
    );
    const d = Math.min(2, window.devicePixelRatio || 1);
    if (ropes.width !== Math.round(vw * d) || ropes.height !== Math.round(vh * d)) {
      ropes.width = Math.round(vw * d);
      ropes.height = Math.round(vh * d);
    }
    const tx = ropes.getContext('2d') as CanvasRenderingContext2D;
    tx.setTransform(d, 0, 0, d, 0, 0);
    tx.clearRect(0, 0, vw, vh);
    if (fsm.phase === 'full') return;
    tx.lineCap = 'round';
    tx.lineWidth = 2.5;
    tx.strokeStyle = RED;
    tx.globalAlpha =
      fsm.phase === 'release' ? clamp((g - 0.25) * 2.2, 0, 1) : fsm.phase === 'pull' ? clamp((1 - g) * 4, 0, 1) : 1;
    const slack = fsm.phase === 'release' ? (1 - gc) * 26 : 0;
    const m = 6;
    const corners: [number, number, number, number][] = [
      [x0, y0, m, m],
      [x0 + w, y0, vw - m, m],
      [x0 + w, y0 + h, vw - m, vh - m],
      [x0, y0 + h, m, vh - m],
    ];
    for (const c of corners) {
      const ex = c[0] + (c[2] - c[0]) * fsm.a;
      const ey = c[1] + (c[3] - c[1]) * fsm.a;
      tx.beginPath();
      tx.moveTo(c[0], c[1]);
      tx.quadraticCurveTo((c[0] + ex) / 2, (c[1] + ey) / 2 + slack, ex, ey);
      tx.stroke();
      tx.beginPath();
      tx.arc(ex, ey, 3.2, 0, 7);
      tx.fillStyle = '#fff';
      tx.fill();
    }
    tx.globalAlpha = 1;
  }

  // ── drawing ────────────────────────────────────────────────────────────────────────────────
  let playing = false;
  let muted = false;
  let volume = 1;
  let waiting = false;

  function linePoint(u: number, now: number): Point {
    const env = 4 * u * (1 - u);
    let y = sag * Math.min(40, H * 0.11) * env;
    const tau = now - pluckAt;
    if (tau < 3) {
      const d = Math.exp(-3.2 * tau);
      for (let k = 1; k <= 6; k++) y += harm[k - 1] * Math.sin(k * Math.PI * u) * Math.cos(k * 24 * tau) * d;
    }
    // While it plays the thread trembles with the volume.
    if (playing && !muted && !RM) {
      y += volume * 2.4 * env * Math.sin(u * 46 + now * 9) * (0.55 + 0.45 * Math.sin(now * 2.3 + u * 5));
    }
    // While it buffers a bump runs along the thread.
    if (waiting && !RM) {
      const c = ((now * 0.9) % 1.4) - 0.2;
      y -= 7 * Math.exp(-((u - c) * (u - c)) / 0.004);
    }
    const pmax = Math.min(46, H * 0.1);
    const pull = drag ? clamp(py - yb, -pmax, pmax) : clamp((py - yb) * 0.22, -7, 7) * hov;
    if (pull) {
      const a = clamp(pu, 0.03, 0.97);
      y += u < a ? (pull * u) / a : (pull * (1 - u)) / (1 - a);
    }
    return [PAD() + u * (W - 2 * PAD()), yb + y];
  }

  function resample(Q: Point[], n: number): Point[] {
    const d = [0];
    for (let i = 1; i < Q.length; i++) d.push(d[i - 1] + Math.hypot(Q[i][0] - Q[i - 1][0], Q[i][1] - Q[i - 1][1]));
    const total = d[d.length - 1];
    const out: Point[] = [];
    let j = 1;
    for (let i = 0; i <= n; i++) {
      const t = (total * i) / n;
      while (j < Q.length - 1 && d[j] < t) j++;
      const a = Q[j - 1];
      const b = Q[j];
      const k = (t - d[j - 1]) / (d[j] - d[j - 1] || 1);
      out.push([a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k]);
    }
    return out;
  }

  function box(el: HTMLElement | null): Point | null {
    if (!el) return null;
    const r = el.getBoundingClientRect();
    if (!r.width) return null;
    const c = canvas.getBoundingClientRect();
    return [r.left - c.left + r.width / 2, r.top - c.top + r.height / 2];
  }
  function curve(x0: number, y0: number, x1: number, y1: number, ox: number, oy: number) {
    sx.beginPath();
    sx.moveTo(x0, y0);
    sx.quadraticCurveTo((x0 + x1) / 2 + ox * 2, (y0 + y1) / 2 + oy * 2, x1, y1);
    sx.stroke();
  }
  function pin(x: number, y: number) {
    sx.beginPath();
    sx.arc(x, y, 1.7, 0, 7);
    sx.fillStyle = '#fff';
    sx.fill();
  }

  function drawIcons(now: number, dt: number, s: Store) {
    const vibOf = (icon: { a: number; at: number }) => {
      const t = now - icon.at;
      return t < 1.5 ? icon.a * Math.exp(-5 * t) * Math.cos(40 * t) : 0;
    };
    sx.lineCap = 'round';
    sx.globalAlpha = topA;
    // Captions: two strands on pins. Loose and white when off, tight and red when on.
    const ccAt = box(ccBtn);
    if (ccAt) {
      const icon = ico.cc;
      const on = !!s.subtitlesShowing;
      if (on !== icon.on) {
        icon.on = on;
        kick(icon, 5);
      }
      if (RM) icon.c = on ? 1 : 0;
      else [icon.c, icon.v] = spring(icon.c, icon.v, on ? 1 : 0, 170, 11, dt);
      const [x, y] = ccAt;
      const vib = vibOf(icon);
      const k = 1 - icon.c;
      sx.strokeStyle = on ? RED : 'rgba(255,255,255,.85)';
      sx.lineWidth = 2.2;
      curve(x - 10, y - 4.5, x + 10, y - 4.5, 0, k * 6.5 + vib);
      curve(x - 10, y + 4.5, x + 3 + 7 * k, y + 4.5, 0, k * 5 - vib * 0.8);
      pin(x - 10, y - 4.5);
      pin(x + 10, y - 4.5);
      pin(x - 10, y + 4.5);
      pin(x + 3 + 7 * k, y + 4.5);
    }
    // Fullscreen: a thread on four pins. It sags at rest and goes tight on hover.
    const fsAt = box(fsBtn);
    if (fsAt) {
      const icon = ico.fs;
      const on = fsm.phase !== 'idle' || !!s.isFullscreen;
      if (RM) icon.c = icon.h;
      else [icon.c, icon.v] = spring(icon.c, icon.v, icon.h, 170, 10, dt);
      const [x, y] = fsAt;
      const e = (on ? 5.5 : 7) + 2.5 * icon.c;
      const b = (1 - icon.c) * 2.8 + vibOf(icon);
      sx.strokeStyle = on ? RED : 'rgba(255,255,255,.9)';
      sx.lineWidth = 2;
      curve(x - e, y - e, x + e, y - e, 0, b);
      curve(x + e, y - e, x + e, y + e, -b, 0);
      curve(x + e, y + e, x - e, y + e, 0, -b);
      curve(x - e, y + e, x - e, y - e, b, 0);
      pin(x - e, y - e);
      pin(x + e, y - e);
      pin(x + e, y + e);
      pin(x - e, y + e);
    }
    sx.globalAlpha = 1;
  }

  /** The storyboard frame for a time, when the media provides a thumbnails track. */
  function spriteAt(s: Store, time: number): { img: HTMLImageElement; x: number; y: number; w: number; h: number } | null {
    const track = s.thumbnailsTrack;
    const cues = track?.cues;
    if (!cues?.length) return null;
    let cue = null;
    for (const c of cues) {
      if (time >= c.startTime && time < c.endTime) {
        cue = c;
        break;
      }
    }
    cue ??= cues[cues.length - 1];
    const text: string = cue.text ?? cue.url ?? '';
    const [file, hash = ''] = text.split('#');
    let url = file;
    try {
      url = new URL(file, track.src || getMedia()?.currentSrc || location.href).href;
    } catch {
      // Keep the cue's own text as the address.
    }
    let img = sprites.get(url);
    if (!img) {
      img = new Image();
      img.crossOrigin = 'anonymous';
      img.src = url;
      sprites.set(url, img);
    }
    if (!img.complete || !img.naturalWidth) return null;
    const m = /xywh=(\d+),(\d+),(\d+),(\d+)/.exec(hash);
    if (m) return { img, x: +m[1], y: +m[2], w: +m[3], h: +m[4] };
    return { img, x: 0, y: 0, w: img.naturalWidth, h: img.naturalHeight };
  }

  function activeCueText(s: Store): string {
    if (!s.subtitlesShowing) return '';
    const tracks = getMedia()?.textTracks;
    if (!tracks) return '';
    for (let i = 0; i < tracks.length; i++) {
      const t = tracks[i];
      if (t.mode !== 'showing' || (t.kind !== 'subtitles' && t.kind !== 'captions')) continue;
      const cues = t.activeCues;
      if (!cues?.length) return '';
      const lines: string[] = [];
      for (let j = 0; j < cues.length; j++) lines.push(String(cues[j].text ?? '').replace(/<[^>]+>/g, ''));
      return lines.join('\n').trim();
    }
    return '';
  }

  function render(now: number, dt: number) {
    const s = getStore();
    if (!s || !W || !H) return;
    fNow = now;
    ready = true;
    if (dt > 0) stretchStep(now, dt, s);

    // ── read the player ──
    const media = getMedia();
    dur = s.duration > 0 && Number.isFinite(s.duration) ? s.duration : 0;
    playing = !s.paused;
    muted = !!s.muted;
    volume = typeof s.volume === 'number' ? s.volume : 1;
    waiting = !!s.waiting && playing;
    const tMedia: number = media ? media.currentTime || 0 : s.currentTime || 0;
    if (lastMedia < 0) {
      lastMedia = tMedia;
      disp = tMedia;
    }
    // A jump that did not come from the pointer (arrow keys, number keys, another control):
    // the preview slides along the thread to the new spot.
    if (dur && dt > 0 && !drag && pendingTo < 0) {
      const target = glide && !glide.bead ? glide.to * dur : lastMedia;
      if (!(glide?.bead) && Math.abs(tMedia - target) > 1.2) {
        if (RM) disp = tMedia;
        else {
          glide = { from: disp / dur, to: tMedia / dur, t0: now, bead: false };
          su = glide.from;
          lastSu = su;
        }
        signHold = now + 1.1;
      }
    }
    lastMedia = tMedia;
    if (pendingTo >= 0 && (Math.abs(tMedia - pendingTo) < 1 || now > pendingUntil)) pendingTo = -1;

    const sliderFocus = focused(sliderEl);
    const active = inZone || drag || !!glide || now < signHold || sliderFocus;
    // Start loading the storyboard early, so the first preview already has a picture.
    if (!sprites.size && s.thumbnailsTrack?.cues?.length) spriteAt(s, 0);
    const TR = Math.min(W, H) * 0.15;
    const morphT = !playing && !active ? 1 : 0;
    const signW = clamp(W * 0.13, 56, 120);
    const ybT = active ? Math.min(H * 0.68, H - ((signW * 9) / 16 + 58)) : playing ? H * 0.9 : H * 0.46 + TR;
    if (RM) {
      sag = playing ? 0 : 1;
      morph = morphT;
      yb = ybT;
    } else {
      [sag, sagV] = spring(sag, sagV, playing ? 0 : 1, 90, 9, dt);
      [morph, morphV] = spring(morph, morphV, morphT, 130, 13, dt);
      [yb, ybV] = spring(yb, ybV, ybT, 150, 19, dt);
      intro = Math.min(1, intro + dt / 1.1);
    }
    hov += ((inZone && !drag && !pend && !glide ? 1 : 0) - hov) * Math.min(1, dt * 12);
    const topT = !topBar || topBar.hasAttribute('data-visible') ? 1 : 0;
    topA = RM ? topT : topA + (topT - topA) * Math.min(1, dt * 10);

    volumeFixed = s.volumeAvailability === 'unsupported';
    const cordT = muted ? CORD_MUTED : CORD(volumeFixed ? 0.6 : volume);
    if (RM) {
      // The cord takes its length at once and hangs still.
      cordLen = cordT;
      cordAng = 0;
      cordV = 0;
    } else {
      cordLen = cordLen ? cordLen + (cordT - cordLen) * Math.min(1, dt * 10) : cordT;
      [cordAng, cordV] = spring(cordAng, cordV, 0, 60, 4, dt);
      cordAng = clamp(cordAng, -0.7, 0.7);
    }

    if (glide) {
      const k = clamp((now - glide.t0) / 0.32, 0, 1);
      const gu = glide.from + (glide.to - glide.from) * (1 - (1 - k) ** 3);
      disp = gu * dur;
      if (!glide.bead) su = gu;
      if (k >= 1) glide = null;
    } else if (drag) {
      disp = pu * dur;
      su = pu;
    } else {
      disp = pendingTo >= 0 ? pendingTo : tMedia;
      const p0 = dur ? clamp(disp / dur, 0, 1) : 0;
      if (sliderFocus && !inZone) su = p0;
      else if (!active) su = pu;
      else if (now >= signHold || inZone) su += (pu - su) * Math.min(1, dt * 22);
    }
    [pop, popV] = spring(pop, popV, 0, 260, 14, dt);
    const vel = dt > 0 ? (su - lastSu) / dt : 0;
    lastSu = su;
    if (RM) {
      swing = 0;
      swingV = 0;
    } else {
      swingV += (-70 * swing - 7 * swingV - (active ? clamp(vel, -3, 3) * 16 : 0)) * dt;
      swing = clamp(swing + swingV * dt, -0.45, 0.45);
    }

    const p = dur ? clamp(disp / dur, 0, 1) : 0;
    const chapters: [number, string][] = dur
      ? Array.from((s.chaptersCues ?? []) as { startTime: number; text: string }[], (c) => [c.startTime / dur, c.text])
      : [];
    const chapterAt = (u: number) => {
      let name = '';
      for (const c of chapters) if (u >= c[0] - 1e-6) name = c[1];
      return name;
    };
    let bufU = p;
    for (const range of (s.buffered ?? []) as [number, number][]) {
      if (dur && disp >= range[0] - 0.5 && disp <= range[1] + 0.5) bufU = Math.max(bufU, range[1] / dur);
    }

    // ── the thread, and the triangle it folds into on pause ──
    const pad = PAD();
    const L = W - 2 * pad;
    let P: Point[] = [];
    let tri: Point[] | null = null;
    for (let i = 0; i <= N; i++) P.push(linePoint(i / N, now));
    if (morph > 0.002) {
      const uc = (W / 2 - TR * 0.6 - pad) / L;
      const Q: Point[] = [];
      for (let i = 0; i <= 40; i++) Q.push(linePoint((uc * i) / 40, now));
      const b0 = Q[Q.length - 1];
      tri = [
        [b0[0], b0[1] - 2 * TR],
        [b0[0] + TR * 1.6, b0[1] - TR],
        [b0[0], b0[1]],
      ];
      Q.push(tri[0], tri[1], tri[2]);
      for (let i = 1; i <= 40; i++) Q.push(linePoint(uc + ((1 - uc) * i) / 40, now));
      const R = resample(Q, N);
      P = P.map((a, i) => [a[0] + (R[i][0] - a[0]) * morph, a[1] + (R[i][1] - a[1]) * morph]);
    }
    const at = (f: number): Point => {
      const x = clamp(f, 0, 1) * N;
      const i = Math.min(N - 1, Math.floor(x));
      const k = x - i;
      return [P[i][0] + (P[i + 1][0] - P[i][0]) * k, P[i][1] + (P[i + 1][1] - P[i][1]) * k];
    };
    const end = intro;
    const mc = clamp(morph, 0, 1);
    const bold = clamp(Math.max(hov, morph, drag ? 1 : 0, playing ? 0 : 1), 0, 1);
    const stroke = (f0: number, f1: number, style: string, w: number, oy: number) => {
      if (f1 <= f0) return;
      sx.beginPath();
      let pt = at(f0);
      sx.moveTo(pt[0], pt[1] + oy);
      for (let i = Math.ceil(f0 * N); i < f1 * N; i++) sx.lineTo(P[i][0], P[i][1] + oy);
      pt = at(f1);
      sx.lineTo(pt[0], pt[1] + oy);
      sx.strokeStyle = style;
      sx.lineWidth = w;
      sx.stroke();
    };

    sx.setTransform(dpr, 0, 0, dpr, 0, 0);
    sx.clearRect(0, 0, W, H);
    sx.lineCap = 'round';
    sx.lineJoin = 'round';
    if (morph > 0.01) {
      sx.fillStyle = `rgba(8,10,16,${(0.3 * mc).toFixed(3)})`;
      sx.fillRect(0, 0, W, H);
    }
    if (tri && morph > 0.6 && end >= 1) {
      sx.beginPath();
      sx.moveTo(tri[0][0], tri[0][1]);
      sx.lineTo(tri[1][0], tri[1][1]);
      sx.lineTo(tri[2][0], tri[2][1]);
      sx.closePath();
      sx.fillStyle = `rgba(255,255,255,${(0.16 * clamp((morph - 0.6) / 0.4, 0, 1)).toFixed(3)})`;
      sx.fill();
    }
    stroke(0, end, 'rgba(0,0,0,.28)', 2.5 + bold * 1.5, 3);
    stroke(0, end, 'rgba(8,10,16,.38)', 4.5 + bold * 2, 0);
    // Not yet buffered is fainter than buffered; played is red.
    stroke(Math.min(bufU, end), end, `rgba(255,255,255,${(0.3 + 0.65 * mc).toFixed(2)})`, 1.5 + bold * 1.2, 0);
    stroke(Math.min(p, end), Math.min(bufU, end), `rgba(255,255,255,${(0.62 + 0.33 * mc).toFixed(2)})`, 1.5 + bold * 1.2, 0);
    stroke(0, Math.min(p, end), RED, 2 + bold * 1.5, 0);
    if (end >= 1) {
      sx.fillStyle = '#fff';
      for (const u of [0, 1]) {
        const pt = at(u);
        sx.beginPath();
        sx.arc(pt[0], pt[1], 2.5, 0, 7);
        sx.fill();
      }
      // Chapters are knots.
      for (const c of chapters) {
        if (c[0] <= 0.001) continue;
        const pt = at(c[0]);
        sx.beginPath();
        sx.arc(pt[0], pt[1], 3 + bold, 0, 7);
        sx.fillStyle = c[0] <= p ? RED : '#fff';
        sx.fill();
      }
      const b = at(p);
      sx.beginPath();
      sx.arc(b[0], b[1], drag ? 9 : 4.5 + bold * 2 + hov * 1.5, 0, 7);
      sx.fillStyle = RED;
      sx.fill();
      sx.beginPath();
      sx.arc(b[0], b[1], 1.6 + bold * 0.6, 0, 7);
      sx.fillStyle = '#fff';
      sx.fill();
      // With reduced motion no bump runs along the thread, so a still ring around the bead says it is buffering.
      if (waiting && RM) {
        sx.beginPath();
        sx.arc(b[0], b[1], 10, 0, 7);
        sx.strokeStyle = '#fff';
        sx.lineWidth = 1.5;
        sx.stroke();
      }
    }

    // ── the preview, hanging from the thread like a photo on a clothesline ──
    if (active && end >= 1 && dur) {
      const sprite = spriteAt(s, su * dur);
      const h = at(su);
      const tw = signW;
      const th = sprite ? (tw * sprite.h) / sprite.w : 0;
      const dx = clamp(h[0], tw / 2 + 6, W - tw / 2 - 6) - h[0];
      const name = chapterAt(su);
      const label = name ? `${formatTime(su * dur)}  ${name}` : formatTime(su * dur);
      sx.save();
      sx.translate(h[0], h[1]);
      sx.rotate(swing);
      sx.scale(1 + pop * 0.5, 1 + pop * 0.5);
      sx.strokeStyle = 'rgba(255,255,255,.85)';
      sx.lineWidth = 1;
      sx.beginPath();
      sx.moveTo(-3, 0);
      sx.lineTo(dx - tw * 0.32, 9);
      sx.moveTo(3, 0);
      sx.lineTo(dx + tw * 0.32, 9);
      sx.stroke();
      if (sprite) {
        sx.fillStyle = 'rgba(0,0,0,.3)';
        sx.fillRect(dx - tw / 2 + 2, 12, tw, th);
        sx.fillStyle = '#fff';
        sx.fillRect(dx - tw / 2 - 2, 7, tw + 4, th + 4);
        sx.drawImage(sprite.img, sprite.x, sprite.y, sprite.w, sprite.h, dx - tw / 2, 9, tw, th);
      }
      sx.font = '500 11px ui-monospace, "SF Mono", Menlo, Consolas, monospace';
      sx.textAlign = 'center';
      sx.textBaseline = 'top';
      const maxW = W * 0.6;
      let text = label;
      while (text.length > 6 && sx.measureText(text).width > maxW) text = `${text.slice(0, -2).trimEnd()}…`;
      const lw = sx.measureText(text).width;
      const ly = sprite ? th + 15 : 9;
      const lx = clamp(h[0] + dx, lw / 2 + 8, W - lw / 2 - 8) - h[0];
      sx.fillStyle = 'rgba(8,10,16,.78)';
      sx.fillRect(lx - lw / 2 - 5, ly, lw + 10, 17);
      sx.fillStyle = '#fff';
      sx.fillText(text, lx, ly + 3);
      sx.restore();
    }

    // ── the volume pull cord ──
    const cx0 = CORDX();
    const ex = cx0 + Math.sin(cordAng) * cordLen;
    const ey = Math.cos(cordAng) * cordLen;
    sx.globalAlpha = 0.35 + 0.65 * topA;
    sx.beginPath();
    sx.moveTo(cx0 + 2, 0);
    sx.lineTo(ex + 2, ey + 3);
    sx.strokeStyle = 'rgba(0,0,0,.28)';
    sx.lineWidth = 3;
    sx.stroke();
    sx.beginPath();
    sx.moveTo(cx0, 0);
    sx.lineTo(ex, ey);
    sx.strokeStyle = muted ? 'rgba(255,255,255,.7)' : RED;
    sx.lineWidth = 2.5;
    sx.stroke();
    sx.beginPath();
    sx.arc(ex, ey, volDrag ? 8 : 6, 0, 7);
    sx.fillStyle = muted ? '#fff' : RED;
    sx.fill();
    sx.beginPath();
    sx.arc(ex, ey, 1.8, 0, 7);
    sx.fillStyle = muted ? '#11151b' : '#fff';
    sx.fill();
    sx.globalAlpha = 1;

    drawIcons(now, dt, s);

    // The cord's label goes over the icons: with the cord short, on a small player, it reaches them.
    if (volHover || volDrag) {
      const text = muted ? 'MUTE' : volumeFixed ? 'SOUND' : `VOL ${Math.round(volume * 100)}`;
      sx.font = '500 11px ui-monospace, "SF Mono", Menlo, Consolas, monospace';
      sx.textAlign = 'right';
      sx.textBaseline = 'middle';
      const lw = sx.measureText(text).width;
      sx.fillStyle = 'rgba(8,10,16,.92)';
      sx.fillRect(ex - 16 - lw - 5, ey - 9, lw + 10, 18);
      sx.fillStyle = '#fff';
      sx.fillText(text, ex - 16, ey);
    }
    sx.textAlign = 'left';

    // The real mute button rides on the cord's knob, and the real slider lies along the thread,
    // so their focus rings frame what the canvas draws.
    if (muteBtn) {
      muteBtn.style.top = `${Math.round(ey)}px`;
      muteBtn.style.left = `${Math.round(ex)}px`;
    }
    if (sliderEl) {
      sliderEl.style.top = `${Math.round(yb - 24)}px`;
      sliderEl.style.bottom = 'auto';
      sliderEl.style.height = '48px';
    }
    // Focused while playing, the play button shows a pause sign made of two strands.
    if (playing && focused(playBtn)) {
      const c = box(playBtn);
      if (c) {
        const r = Math.min(W, H) * 0.07;
        sx.strokeStyle = RED;
        sx.lineWidth = 3;
        sx.lineCap = 'round';
        for (const dx of [-r * 0.45, r * 0.45]) {
          sx.beginPath();
          sx.moveTo(c[0] + dx, c[1] - r);
          sx.lineTo(c[0] + dx, c[1] + r);
          sx.stroke();
          pin(c[0] + dx, c[1] - r);
          pin(c[0] + dx, c[1] + r);
        }
      }
    }

    // ── text the DOM owns ──
    if (chapterEl) {
      const name = chapterAt(p);
      if (chapterEl.textContent !== name) chapterEl.textContent = name;
    }
    if (captionsEl && captionsText) {
      const cue = activeCueText(s);
      if (cue !== lastCue) {
        lastCue = cue;
        captionsEl.hidden = !cue;
        if (cue) {
          captionsText.textContent = cue;
          captionsEl.removeAttribute('data-in');
          void captionsEl.offsetWidth;
          captionsEl.setAttribute('data-in', '');
        }
      }
    }
  }

  let last = performance.now();
  function frame(n: number) {
    if (signal.aborted) return;
    const dt = Math.min(0.05, (n - last) / 1000);
    last = n;
    render(n / 1000, dt);
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
}

class RedThreadElement extends HTMLElement {
  #stop: AbortController | null = null;

  connectedCallback() {
    this.#stop?.abort();
    this.#stop = new AbortController();
    mount(this, this.#stop.signal);
  }

  disconnectedCallback() {
    this.#stop?.abort();
    this.#stop = null;
  }
}

if (!customElements.get('red-thread')) customElements.define('red-thread', RedThreadElement);

export { RedThreadElement };
