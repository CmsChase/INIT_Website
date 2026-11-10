import { useLayoutEffect, useRef, useState, useSyncExternalStore, type ReactNode } from "react";

// Scale transforms stay on plain elements, separate from Motion transforms.
export function useFitContain(designWidth: number, designHeight: number) {
  const ref = useRef<HTMLDivElement>(null);
  const [fit, setFit] = useState({ scale: 1, x: 0, y: 0 });
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const fitTo = (width: number, height: number) => {
      if (!width || !height) return;
      const scale = Math.min(width / designWidth, height / designHeight);
      setFit({
        scale,
        x: (width - designWidth * scale) / 2,
        y: (height - designHeight * scale) / 2,
      });
    };
    const first = el.getBoundingClientRect();
    fitTo(first.width, first.height);
    const observer = new ResizeObserver(([entry]) =>
      fitTo(entry.contentRect.width, entry.contentRect.height),
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [designWidth, designHeight]);
  return { ref, ...fit, edge: fit.y / fit.scale };
}

function useFitScale(designWidth: number) {
  const ref = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const first = el.getBoundingClientRect().width;
    if (first) setScale(first / designWidth);
    const observer = new ResizeObserver(([entry]) => {
      if (entry.contentRect.width)
        setScale(entry.contentRect.width / designWidth);
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, [designWidth]);
  return { ref, scale };
}

function useFitScaleAuto(designWidth: number) {
  const outerRef = useRef<HTMLDivElement>(null);
  const innerRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  const [naturalHeight, setNaturalHeight] = useState(0);
  useLayoutEffect(() => {
    const el = outerRef.current;
    if (!el) return;
    const first = el.getBoundingClientRect().width;
    if (first) setScale(first / designWidth);
    const observer = new ResizeObserver(([entry]) => {
      if (entry.contentRect.width)
        setScale(entry.contentRect.width / designWidth);
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, [designWidth]);
  useLayoutEffect(() => {
    const el = innerRef.current;
    if (!el) return;
    // Include padding and follow font loading and freely wrapping content.
    const measure = () => setNaturalHeight(el.offsetHeight);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  return { outerRef, innerRef, scale, naturalHeight };
}

type CanvasProps = {
  children: ReactNode;
  className?: string;
  height?: number;
};

const mobileQuery = "(max-width: 1023px)";
function subscribeToBreakpoint(update: () => void) {
  const query = window.matchMedia(mobileQuery);
  query.addEventListener("change", update);
  return () => query.removeEventListener("change", update);
}

export function DesignCanvas(props: CanvasProps) {
  const mobile = useSyncExternalStore(
    subscribeToBreakpoint,
    () => window.matchMedia(mobileQuery).matches,
    () => false,
  );
  // Only mount the visible artwork so navigation samples one halftone canvas.
  return mobile ? <MobileCanvas {...props} /> : <DesktopCanvas {...props} />;
}

function DesktopCanvas({ children, className = "", height = 760 }: CanvasProps) {
  const desktop = useFitScale(1512);
  return (
      <div
        ref={desktop.ref}
        className={`ed-desktop ed-canvas-wrap ${className}`}
        style={{ aspectRatio: `1512 / ${height}` }}
      >
        <div
          className="ed-canvas"
          style={{
            width: 1512,
            height,
            transform: `scale(${desktop.scale})`,
            transformOrigin: "top left",
          }}
        >
          {children}
        </div>
      </div>
  );
}

function MobileCanvas({ children, className = "" }: CanvasProps) {
  const mobile = useFitScaleAuto(440);
  return (
      <div
        ref={mobile.outerRef}
        className={`ed-mobile ed-canvas-wrap ${className}`}
        style={{ height: mobile.naturalHeight * mobile.scale }}
      >
        <div
          ref={mobile.innerRef}
          className="ed-canvas ed-mobile-canvas"
          style={{
            width: 440,
            transform: `scale(${mobile.scale})`,
            transformOrigin: "top left",
          }}
        >
          {children}
        </div>
      </div>
  );
}
