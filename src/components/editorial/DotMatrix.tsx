import { useEffect, useRef, type CSSProperties } from "react";

/**
 * Interactive halftone renderer: resamples an image or a looping video into a
 * grid of dots (dot size = brightness, color = source color) and draws it to a
 * canvas. Near the cursor the dots bulge outward and turn into flickering ASCII
 * glyphs; entering the block sends a "re-assembly" wave with glitchy row shifts
 * across it. Coordinates are in design px - the canvas is sized to
 * `width`/`height` and follows whatever transform:scale() its parent applies.
 */

export type DotMatrixCrop = { x: number; y: number; w: number; h: number };
type Box = { x0: number; y0: number; x1: number; y1: number };

// lightest to heaviest; an array, not a string, so glyphs outside the BMP (𝄞) stay whole
const GLYPHS = Array.from(" .,:;_<>/*+=O#SF");
const GLYPH_FONT = "'Fragment Mono', ui-monospace, monospace";

// Music notation instead of ASCII, lightest to heaviest (index 0 is never drawn). System symbol
// fonts carry these, Fragment Mono does not.
export const MUSIC_GLYPHS = [" ", "·", "♭", "♮", "♯", "♩", "♪", "♫", "♬", "𝄞"];
export const MUSIC_GLYPH_FONT =
  "'Apple Symbols', 'Segoe UI Symbol', 'Noto Music', 'Noto Sans Symbols 2', serif";
const SUPERSAMPLE = 3;

function hash(a: number, b: number) {
  const s = Math.sin(a * 127.1 + b * 311.7) * 43758.5453;
  return s - Math.floor(s);
}

function smoothstep(e0: number, e1: number, x: number) {
  const t = Math.min(1, Math.max(0, (x - e0) / (e1 - e0)));
  return t * t * (3 - 2 * t);
}

export default function DotMatrix({
  src,
  video = false,
  width,
  height,
  crop,
  flipX = false,
  pitch = 10,
  gain = 1.8,
  threshold = 0.08,
  dotScale = 0.9,
  radius = 110,
  sweepOnEnter = true,
  ink,
  inkOpacity = 0.4,
  glyphs = GLYPHS,
  glyphFont = GLYPH_FONT,
  glyphScale = 1,
  className,
  style,
}: {
  src: string;
  video?: boolean;
  width: number;
  height: number;
  /** region of the source (in source px) to show; default = object-cover */
  crop?: DotMatrixCrop;
  flipX?: boolean;
  /** distance between dot centers, design px */
  pitch?: number;
  /** brightness boost - averaging a source that is itself dotted loses ~half the light */
  gain?: number;
  /** cells darker than this stay empty */
  threshold?: number;
  /** max dot diameter as a fraction of pitch */
  dotScale?: number;
  /** cursor influence radius, design px */
  radius?: number;
  sweepOnEnter?: boolean;
  /** dark-on-light mode: a cell's value is how much darker than white it is, and every dot is
   *  drawn in this one rgb color (a constant outside the component) instead of the source color */
  ink?: readonly [number, number, number];
  /** ink mode: opacity of a fully lit dot; glyphs under the cursor go darker than this */
  inkOpacity?: number;
  /** glyphs a cell turns into near the cursor, lightest to heaviest; index 0 is never drawn.
   *  A constant outside the component, like `crop` */
  glyphs?: readonly string[];
  /** CSS font-family list for the glyphs */
  glyphFont?: string;
  /** glyph size relative to the default (1.25 cells) */
  glyphScale?: number;
  className?: string;
  style?: CSSProperties;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const precisePointer = window.matchMedia(
      "(hover: hover) and (pointer: fine)",
    );

    const cols = Math.max(1, Math.round(width / pitch));
    const rows = Math.max(1, Math.round(height / pitch));
    const cellW = width / cols;
    const cellH = height / rows;
    const count = cols * rows;

    // per-cell sampled source: brightness 0..1 and a normalized color
    const lum = new Float32Array(count);
    const colR = new Uint8ClampedArray(count);
    const colG = new Uint8ClampedArray(count);
    const colB = new Uint8ClampedArray(count);

    const sampler = document.createElement("canvas");
    sampler.width = cols * SUPERSAMPLE;
    sampler.height = rows * SUPERSAMPLE;
    const sctx = sampler.getContext("2d", { willReadFrequently: true });
    if (!sctx) return;

    let source: HTMLImageElement | HTMLVideoElement | null = null;
    let sourceReady = false;
    let disposed = false;

    function sourceSize() {
      if (!source) return { w: 0, h: 0 };
      if (source instanceof HTMLVideoElement)
        return { w: source.videoWidth, h: source.videoHeight };
      return { w: source.naturalWidth, h: source.naturalHeight };
    }

    function resolveCrop(): DotMatrixCrop {
      if (crop) return crop;
      const { w, h } = sourceSize();
      // object-cover
      const s = Math.max(width / w, height / h);
      const cw = width / s;
      const ch = height / s;
      return { x: (w - cw) / 2, y: (h - ch) / 2, w: cw, h: ch };
    }

    function sample() {
      if (!source || !sctx) return;
      const c = resolveCrop();
      sctx.clearRect(0, 0, sampler.width, sampler.height);
      sctx.save();
      if (flipX) {
        sctx.translate(sampler.width, 0);
        sctx.scale(-1, 1);
      }
      sctx.imageSmoothingEnabled = true;
      sctx.imageSmoothingQuality = "high";
      sctx.drawImage(
        source,
        c.x,
        c.y,
        c.w,
        c.h,
        0,
        0,
        sampler.width,
        sampler.height,
      );
      sctx.restore();
      const data = sctx.getImageData(0, 0, sampler.width, sampler.height).data;
      const rowStride = sampler.width * 4;
      const n = SUPERSAMPLE * SUPERSAMPLE;
      for (let cy = 0; cy < rows; cy++) {
        for (let cx = 0; cx < cols; cx++) {
          let r = 0;
          let g = 0;
          let b = 0;
          let dark = 0;
          for (let sy = 0; sy < SUPERSAMPLE; sy++) {
            let o = (cy * SUPERSAMPLE + sy) * rowStride + cx * SUPERSAMPLE * 4;
            for (let sx = 0; sx < SUPERSAMPLE; sx++) {
              const a = data[o + 3] / 255;
              r += data[o] * a;
              g += data[o + 1] * a;
              b += data[o + 2] * a;
              dark +=
                (1 - Math.max(data[o], data[o + 1], data[o + 2]) / 255) * a;
              o += 4;
            }
          }
          r /= n;
          g /= n;
          b /= n;
          const max = Math.max(r, g, b);
          const i = cy * cols + cx;
          if (ink) {
            lum[i] = Math.min(1, (dark / n) * gain);
            continue;
          }
          lum[i] = Math.min(1, (max / 255) * gain);
          if (max > 0) {
            // keep the hue, push it toward full saturation/brightness so dots read vivid
            const k = 255 / max;
            colR[i] = r * k;
            colG[i] = g * k;
            colB[i] = b * k;
          }
        }
      }
    }

    if (video) {
      const v = document.createElement("video");
      v.src = src;
      v.muted = true;
      v.loop = true;
      v.playsInline = true;
      v.autoplay = true;
      v.crossOrigin = "anonymous";
      v.addEventListener("loadeddata", () => {
        sourceReady = true;
      });
      source = v;
    } else {
      const img = new Image();
      img.decoding = "async";
      // the pixels are read back with getImageData: a cloud image must load in CORS mode or the
      // canvas is tainted and the read throws
      img.crossOrigin = "anonymous";
      img.onload = () => {
        if (disposed) return;
        try {
          sample();
          sourceReady = true;
          canvas.dataset.loaded = "true";
        } catch {
          // Artwork is decorative: a failed CORS read must not break the page.
          sourceReady = false;
          return;
        }
        fullNext = true;
        dirty = true;
        kick();
      };
      img.onerror = () => {
        sourceReady = false;
      };
      img.src = src;
      source = img;
    }

    // pointer state, in design px relative to the canvas
    const pointer = { x: -9999, y: -9999, sx: -9999, sy: -9999, inside: false };
    let hover = 0;
    let sweepStart = -1;
    let dirty = true;
    let visible = false;
    let raf = 0;
    let lastBucket = -1;
    let lastVideoTime = -1;
    // The canvas size is read on demand, not every frame: for a few frames after a window resize
    // (the parent's scale lands a React render later) and when the canvas comes into view.
    let measureFrames = 30;
    let lastDpr = window.devicePixelRatio;
    // Outside the cursor's reach every dot sits still, so while only the cursor plays only the
    // box around it is redrawn. `lastBox` is that box in the previous frame (to put it back),
    // `fullNext` asks for a whole-canvas redraw (first frame, new size, new source, after a sweep).
    let lastBox: Box | null = null;
    let fullNext = true;

    function kick() {
      if (visible && !raf && !disposed) raf = requestAnimationFrame(frame);
    }

    function onPointerMove(e: PointerEvent) {
      if (
        reducedMotion.matches ||
        !precisePointer.matches ||
        e.pointerType !== "mouse"
      )
        return;
      // A hidden copy (the other breakpoint's canvas, a scrolled-away section) skips the rect
      // read. The pointer is outside it all the same, so coming back is a fresh enter (sweep).
      if (!visible) {
        pointer.inside = false;
        return;
      }
      // dragged to a screen with another pixel ratio, maybe without a resize event
      if (window.devicePixelRatio !== lastDpr) onResize();
      kick();
      const rect = canvas!.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      const x = ((e.clientX - rect.left) / rect.width) * width;
      const y = ((e.clientY - rect.top) / rect.height) * height;
      const inside = x >= 0 && y >= 0 && x <= width && y <= height;
      if (inside && !pointer.inside) {
        if (sweepOnEnter) sweepStart = performance.now();
        if (pointer.sx < -1000) {
          pointer.sx = x;
          pointer.sy = y;
        }
      }
      pointer.inside = inside;
      pointer.x = x;
      pointer.y = y;
    }
    // The pointer left the window (mouseout with nowhere to go), or a finger lifted: a touch never
    // gets the move that would take it outside, so without this the effect stays stuck on.
    function onPointerGone() {
      pointer.inside = false;
      kick();
    }
    function onMotionPreferenceChange() {
      if (reducedMotion.matches) {
        pointer.inside = false;
        hover = 0;
        sweepStart = -1;
        fullNext = true;
        dirty = true;
        kick();
      }
    }
    function onMouseOut(e: MouseEvent) {
      if (!e.relatedTarget) onPointerGone();
    }
    function onPointerEnd(e: PointerEvent) {
      if (e.pointerType !== "mouse") onPointerGone();
    }
    function onResize() {
      lastDpr = window.devicePixelRatio;
      measureFrames = 30;
      kick();
    }

    function ensureBackingSize() {
      const rect = canvas!.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const bw = Math.max(1, Math.round(rect.width * dpr));
      const bh = Math.max(1, Math.round(rect.height * dpr));
      if (canvas!.width !== bw || canvas!.height !== bh) {
        canvas!.width = bw;
        canvas!.height = bh;
        fullNext = true;
        dirty = true;
      }
    }

    const baseR = Math.min(cellW, cellH) * 0.5 * dotScale;
    const glyphSize = Math.min(cellW, cellH) * 1.25 * glyphScale;
    // how far a cell's dot or glyph can reach from its centre, and how far the cursor's push and
    // its glyphs can reach from the cursor
    const cellReach =
      Math.max(baseR * 1.5, glyphSize * 1.5) + Math.max(cellW, cellH);
    const cursorReach = radius + cellW * 1.4 + cellReach;

    function sweepTime(now: number) {
      return sweepStart < 0 ? -1 : (now - sweepStart) / 700;
    }

    // The box around the cursor, snapped outward to whole backing pixels so that clearing and
    // clipping it leaves no half-covered seam at its edges.
    function cursorBox(): Box {
      const kx = canvas!.width / width;
      const ky = canvas!.height / height;
      const x0 = Math.floor(Math.max(0, pointer.sx - cursorReach) * kx) / kx;
      const y0 = Math.floor(Math.max(0, pointer.sy - cursorReach) * ky) / ky;
      const x1 = Math.ceil(Math.min(width, pointer.sx + cursorReach) * kx) / kx;
      const y1 =
        Math.ceil(Math.min(height, pointer.sy + cursorReach) * ky) / ky;
      return { x0, y0, x1, y1 };
    }

    // `region` (design px) limits the redraw to that box: it is cleared and only the cells that
    // can reach into it are drawn, clipped to it. Without it the whole canvas is redrawn.
    function draw(now: number, region: Box | null) {
      if (!ctx) return;
      ctx.setTransform(
        canvas!.width / width,
        0,
        0,
        canvas!.height / height,
        0,
        0,
      );
      let cx0 = 0;
      let cx1 = cols - 1;
      let cy0 = 0;
      let cy1 = rows - 1;
      if (region) {
        ctx.save();
        ctx.beginPath();
        ctx.rect(
          region.x0,
          region.y0,
          region.x1 - region.x0,
          region.y1 - region.y0,
        );
        ctx.clip();
        ctx.clearRect(
          region.x0,
          region.y0,
          region.x1 - region.x0,
          region.y1 - region.y0,
        );
        cx0 = Math.max(0, Math.floor((region.x0 - cellReach) / cellW));
        cx1 = Math.min(cols - 1, Math.ceil((region.x1 + cellReach) / cellW));
        cy0 = Math.max(0, Math.floor((region.y0 - cellReach) / cellH));
        cy1 = Math.min(rows - 1, Math.ceil((region.y1 + cellReach) / cellH));
      } else {
        ctx.clearRect(0, 0, width, height);
      }

      const sweepT = sweepTime(now);
      const sweeping = sweepT >= 0 && sweepT < 1.4;
      const bucket = Math.floor(now / 70);
      const px = pointer.sx;
      const py = pointer.sy;
      const r2 = radius * radius;
      ctx.font = `${glyphSize}px ${glyphFont}`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";

      for (let cy = cy0; cy <= cy1; cy++) {
        // glitch: during the sweep some rows slide sideways for a moment
        let rowShift = 0;
        if (sweeping) {
          const h = hash(cy, bucket);
          if (h < 0.08) rowShift = (hash(cy + 7, bucket) - 0.5) * cellW * 6;
        }
        for (let cx = cx0; cx <= cx1; cx++) {
          const i = cy * cols + cx;
          const l = lum[i];
          let x = (cx + 0.5) * cellW + rowShift;
          let y = (cy + 0.5) * cellH;

          // cursor influence
          let f = 0;
          if (hover > 0.001) {
            const dx = x - px;
            const dy = y - py;
            const d2 = dx * dx + dy * dy;
            if (d2 < r2) {
              const d = Math.sqrt(d2);
              f = hover * (1 - smoothstep(0, radius, d));
              if (d > 0.001) {
                const push = f * cellW * 1.4;
                x += (dx / d) * push;
                y += (dy / d) * push;
              }
            }
          }

          // re-assembly wave, travelling along the diagonal
          let wave = 0;
          if (sweeping) {
            const p = (cx / cols + cy / rows) * 0.5;
            const front = sweepT - 0.2;
            wave = 1 - Math.min(1, Math.abs(p - front) / 0.18);
          }

          const lit = Math.min(1, l + f * 0.35 + wave * 0.25);
          if (lit < threshold && f < 0.2 && wave < 0.2) continue;

          const shade = 0.45 + 0.55 * lit;
          if (ink) {
            const alpha = Math.min(
              1,
              inkOpacity * shade * (1 + f * 1.2 + wave * 0.6),
            );
            ctx.fillStyle = `rgba(${ink[0]},${ink[1]},${ink[2]},${alpha.toFixed(3)})`;
          } else {
            ctx.fillStyle = `rgb(${(colR[i] * shade) | 0},${(colG[i] * shade) | 0},${(colB[i] * shade) | 0})`;
          }

          const glyphMode = f > 0.3 || (wave > 0.35 && hash(i, bucket) < wave);
          if (glyphMode && lit >= threshold * 0.5) {
            const flicker = hash(i, bucket) * 0.35;
            const gi = Math.min(
              glyphs.length - 1,
              Math.max(1, Math.floor((lit + flicker) * (glyphs.length - 1))),
            );
            ctx.fillText(glyphs[gi], x, y);
            continue;
          }
          if (lit < threshold) continue;
          const rad = baseR * Math.sqrt(lit) * (1 + f * 0.5);
          ctx.beginPath();
          ctx.arc(x, y, rad, 0, Math.PI * 2);
          ctx.fill();
        }
      }
      if (region) ctx.restore();
      lastBucket = bucket;
    }

    function render(now: number) {
      const sweepT = sweepTime(now);
      const sweeping = sweepT >= 0 && sweepT < 1.4;
      if (fullNext || sweeping || source instanceof HTMLVideoElement) {
        draw(now, null);
        lastBox = null;
        // the last sweep frame can leave rows shifted, so the frame after it is whole again
        fullNext = sweeping;
        return;
      }
      const box = hover > 0.001 ? cursorBox() : null;
      const region =
        box && lastBox
          ? {
              x0: Math.min(box.x0, lastBox.x0),
              y0: Math.min(box.y0, lastBox.y0),
              x1: Math.max(box.x1, lastBox.x1),
              y1: Math.max(box.y1, lastBox.y1),
            }
          : (box ?? lastBox);
      if (region) draw(now, region);
      lastBox = box;
    }

    function frame(now: number) {
      raf = 0;
      if (disposed || !visible) return;
      if (measureFrames > 0) {
        measureFrames--;
        ensureBackingSize();
      }

      const targetHover = pointer.inside ? 1 : 0;
      hover += (targetHover - hover) * 0.12;
      if (Math.abs(targetHover - hover) < 0.002) hover = targetHover;
      let moving = false;
      if (pointer.inside) {
        pointer.sx += (pointer.x - pointer.sx) * 0.25;
        pointer.sy += (pointer.y - pointer.sy) * 0.25;
        // snap once the lag is far below a pixel, so a resting cursor stops costing redraws
        if (
          Math.abs(pointer.x - pointer.sx) < 0.01 &&
          Math.abs(pointer.y - pointer.sy) < 0.01
        ) {
          pointer.sx = pointer.x;
          pointer.sy = pointer.y;
        } else {
          moving = true;
        }
      }

      const sweeping = sweepStart >= 0 && now - sweepStart < 1000;
      const animating = hover > 0.001 || sweeping;
      if (
        source instanceof HTMLVideoElement &&
        sourceReady &&
        source.currentTime !== lastVideoTime
      ) {
        lastVideoTime = source.currentTime;
        sample();
        dirty = true;
      }
      // Glyphs flicker on a 70ms clock. Between its ticks a frame only differs from the last one
      // if the cursor, the hover fade or the sweep moved.
      const settling = moving || hover !== targetHover || sweeping;
      if (
        animating &&
        (Math.floor(now / 70) !== lastBucket || (pointer.inside && settling))
      )
        dirty = true;
      // the cursor's box is still drawn but the effect has faded out: put it back once
      if (!animating && lastBox) dirty = true;
      if (fullNext && sourceReady) dirty = true;
      if (sourceReady && dirty) {
        render(now);
        dirty = false;
      }
      // Idle (nothing under the cursor, no sweep, nothing pending): stop. A pointer move, a
      // resize, the source loading or the canvas coming back into view starts the loop again.
      const busy =
        animating ||
        pointer.inside ||
        lastBox !== null ||
        (fullNext && sourceReady) ||
        measureFrames > 0 ||
        source instanceof HTMLVideoElement;
      if (busy) raf = requestAnimationFrame(frame);
    }

    const io = new IntersectionObserver(
      ([entry]) => {
        visible = entry.isIntersecting;
        if (source instanceof HTMLVideoElement) {
          if (visible) source.play().catch(() => {});
          else source.pause();
        }
        if (visible) {
          measureFrames = Math.max(measureFrames, 30);
          dirty = true;
          kick();
        }
      },
      { rootMargin: "100px" },
    );
    io.observe(canvas);
    window.addEventListener("pointermove", onPointerMove, { passive: true });
    window.addEventListener("pointerup", onPointerEnd, { passive: true });
    window.addEventListener("pointercancel", onPointerEnd, { passive: true });
    window.addEventListener("resize", onResize);
    document.addEventListener("mouseout", onMouseOut);
    reducedMotion.addEventListener("change", onMotionPreferenceChange);

    return () => {
      disposed = true;
      io.disconnect();
      cancelAnimationFrame(raf);
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerEnd);
      window.removeEventListener("pointercancel", onPointerEnd);
      window.removeEventListener("resize", onResize);
      document.removeEventListener("mouseout", onMouseOut);
      reducedMotion.removeEventListener("change", onMotionPreferenceChange);
      if (source instanceof HTMLImageElement) {
        source.onload = null;
        source.onerror = null;
      }
      if (source instanceof HTMLVideoElement) {
        source.pause();
        source.removeAttribute("src");
        source.load();
      }
    };
  }, [
    src,
    video,
    width,
    height,
    crop,
    flipX,
    pitch,
    gain,
    threshold,
    dotScale,
    radius,
    sweepOnEnter,
    ink,
    inkOpacity,
    glyphs,
    glyphFont,
    glyphScale,
  ]);

  return (
    <canvas
      ref={canvasRef}
      className={className}
      style={{ width, height, display: "block", ...style }}
    />
  );
}
