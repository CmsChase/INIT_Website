import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useInView } from "framer-motion";

// Inlines an exported SVG (fetched as text from its URL) so its shapes can animate: stroked lines draw
// themselves in, filled shapes (waveform bars) grow from their centre. The styles live in
// `src/editorial.css` under `.fx-svg`. Like the text effects, it plays once in view unless `play`
// is given.

const SHAPES = "path, line, rect, circle, ellipse, polyline, polygon";

// one request per SVG file, shared by every copy on the page (desktop + mobile canvas)
const sources = new Map<string, Promise<string>>();

function loadSvg(url: string) {
  let source = sources.get(url);
  if (!source) {
    source = fetch(url)
      .then((res) => (res.ok ? res.text() : ""))
      .catch(() => "");
    sources.set(url, source);
  }
  return source;
}
const SVG_NS = "http://www.w3.org/2000/svg";

type Options = {
  /** Seconds over which the starts of all shapes are spread. */
  spread: number;
  /** Indices of stroked shapes that also get a pulse running along them, in a loop. */
  pulse: number[];
  /** Filled bars keep moving once grown in, like a live audio level. */
  bounce: boolean;
};

function firstX(el: Element) {
  const match = /M\s*(-?[\d.]+)/.exec(el.getAttribute("d") ?? "");
  return match ? Number(match[1]) : 0;
}

// A Figma export often packs a whole grid (or a whole waveform) into one <path>. Split it into
// one path per subpath so the pieces can be staggered. The original opacity moves to a group,
// otherwise pieces that touch would darken each other.
function splitSubpaths(doc: Document, path: Element) {
  const parts = (path.getAttribute("d") ?? "").match(/M[^M]+/g);
  if (!parts || parts.length < 2) return;
  const group = doc.createElementNS(SVG_NS, "g");
  const opacity = path.getAttribute("opacity");
  if (opacity) group.setAttribute("opacity", opacity);
  for (const d of parts) {
    const piece = path.cloneNode(false) as Element;
    piece.removeAttribute("opacity");
    piece.setAttribute("d", d.trim());
    group.appendChild(piece);
  }
  path.replaceWith(group);
}

function seeded(a: number, b: number) {
  const s = Math.sin(a * 127.1 + b * 311.7) * 43758.5453;
  return s - Math.floor(s);
}

function prepare(
  source: string,
  uid: string,
  { spread, pulse, bounce }: Options,
) {
  // Two copies of one SVG on the page (desktop + mobile canvas) would share gradient and
  // clip-path ids, and a reference that resolves into the hidden copy renders nothing.
  const unique = source
    .replace(/id="([^"]+)"/g, `id="$1-${uid}"`)
    .replace(/url\(#([^)]+)\)/g, `url(#$1-${uid})`);
  const doc = new DOMParser().parseFromString(unique, "image/svg+xml");
  const svg = doc.documentElement;
  if (svg.localName !== "svg" || doc.querySelector("parsererror"))
    return { html: "", width: 0, height: 0 };
  // Remote artwork is data, not executable markup. Keep the drawing vocabulary
  // used by these grids and reject scripts, event handlers and external URLs.
  const tags = new Set([
    "svg",
    "g",
    "path",
    "line",
    "rect",
    "circle",
    "ellipse",
    "polyline",
    "polygon",
    "defs",
    "linearGradient",
    "radialGradient",
    "stop",
    "clipPath",
    "mask",
    "title",
    "desc",
  ]);
  for (const element of Array.from(svg.querySelectorAll("*"))) {
    if (!tags.has(element.localName)) {
      element.remove();
      continue;
    }
  }
  for (const element of [svg, ...Array.from(svg.querySelectorAll("*"))]) {
    for (const attribute of Array.from(element.attributes)) {
      if (
        /^on/i.test(attribute.name) ||
        /href/i.test(attribute.name) ||
        attribute.name === "style" ||
        (/url\(/i.test(attribute.value) &&
          !/^url\(#[a-zA-Z0-9_-]+\)$/.test(attribute.value))
      ) {
        element.removeAttribute(attribute.name);
      }
    }
  }
  const width = Number(svg.getAttribute("width"));
  const height = Number(svg.getAttribute("height"));
  svg.setAttribute("width", "100%");
  svg.setAttribute("height", "100%");

  const live = (el: Element) => !el.closest("defs, clipPath, mask");
  const stroked = (el: Element) =>
    (el.getAttribute("stroke") ?? "none") !== "none";

  // `pathLength`, which the draw-in relies on, is only dependable on <path>.
  for (const line of Array.from(svg.querySelectorAll("line")).filter(live)) {
    const path = doc.createElementNS(SVG_NS, "path");
    for (const { name, value } of Array.from(line.attributes)) {
      if (!["x1", "y1", "x2", "y2"].includes(name))
        path.setAttribute(name, value);
    }
    const at = (name: string) => line.getAttribute(name) ?? "0";
    path.setAttribute("d", `M${at("x1")} ${at("y1")}L${at("x2")} ${at("y2")}`);
    line.replaceWith(path);
  }
  for (const path of Array.from(svg.querySelectorAll("path")).filter(live))
    splitSubpaths(doc, path);

  const shapes = Array.from(svg.querySelectorAll(SHAPES)).filter(live);
  const lines = shapes.filter(stroked);
  const bars = shapes
    .filter((el) => !stroked(el))
    .sort((a, b) => firstX(a) - firstX(b));

  lines.forEach((el, i) => {
    el.setAttribute("pathLength", "1");
    el.setAttribute("class", "fx-draw");
    el.setAttribute(
      "style",
      `--fx-at:${((i / Math.max(lines.length - 1, 1)) * spread).toFixed(3)}s`,
    );
  });
  bars.forEach((el, i) => {
    el.setAttribute("class", "fx-bar");
    let style = `--fx-at:${((i / Math.max(bars.length - 1, 1)) * spread).toFixed(3)}s`;
    // live bars keep bouncing like a level meter; each gets its own depth and pace (seeded by
    // index, so two copies of the same SVG move alike)
    if (bounce) {
      const low = 0.25 + seeded(i, 1) * 0.45;
      const pace = 0.45 + seeded(i, 2) * 0.6;
      style += `;--fx-low:${low.toFixed(3)};--fx-pace:${pace.toFixed(3)}s`;
    }
    el.setAttribute("style", style);
  });
  pulse.forEach((index, order) => {
    const line = lines[index];
    if (!line) return;
    const comet = line.cloneNode(false) as Element;
    comet.setAttribute("class", "fx-comet");
    comet.setAttribute("style", `--fx-at:${(order * 1.7).toFixed(1)}s`);
    comet.removeAttribute("stroke-opacity");
    line.after(comet);
  });

  return { html: new XMLSerializer().serializeToString(svg), width, height };
}

export default function InlineSvg({
  svg,
  className = "",
  play,
  delay = 0,
  spread = 0.9,
  pulse,
  fit = false,
  live = false,
  paused = false,
}: {
  /** URL of the SVG file; its markup is fetched and inlined. */
  svg: string;
  className?: string;
  play?: boolean;
  /** Seconds before the first shape starts. */
  delay?: number;
  spread?: number;
  pulse?: number[];
  /** Take the size from `className` instead of the SVG's own width/height. */
  fit?: boolean;
  /** Waveform bars keep bouncing after they grow in. `'bottom'` for bars standing on a common
   *  baseline (an equalizer): they grow and bounce from their foot instead of their centre. */
  live?: boolean | "bottom";
  /** Freeze the looping animations (the parent has faded this out). Off screen they freeze anyway. */
  paused?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [source, setSource] = useState("");
  useEffect(() => {
    let live = true;
    loadSvg(svg).then((text) => {
      if (live) setSource(text);
    });
    return () => {
      live = false;
    };
  }, [svg]);
  const uid = useId().replace(/[^a-zA-Z0-9]/g, "");
  const inView = useInView(ref, { once: true, amount: 0.15 });
  // the bounce and the pulses loop forever; nobody sees them off screen
  const onScreen = useInView(ref);
  const looping = !!live || !!pulse?.length;
  const pulseKey = pulse?.join(",") ?? "";
  const prepared = useMemo(
    () =>
      source
        ? prepare(source, uid, {
            spread,
            pulse: pulseKey ? pulseKey.split(",").map(Number) : [],
            bounce: !!live,
          })
        : null,
    [source, uid, spread, pulseKey, live],
  );

  return (
    <div
      ref={ref}
      aria-hidden="true"
      className={`fx-svg ${(play ?? inView) ? "is-drawn" : ""} ${live ? "is-live" : ""} ${live === "bottom" ? "is-grounded" : ""} ${looping && (paused || !onScreen) ? "is-paused" : ""} ${className}`}
      style={{
        ...(fit || !prepared
          ? null
          : { width: prepared.width, height: prepared.height }),
        ["--fx-delay" as string]: `${delay}s`,
      }}
      dangerouslySetInnerHTML={{ __html: prepared?.html ?? "" }}
    />
  );
}
