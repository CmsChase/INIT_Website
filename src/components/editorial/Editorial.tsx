import { motion, useReducedMotion } from "framer-motion";
import type { ReactNode } from "react";
import { DesignCanvas } from "./Canvas";
import DotMatrix from "./DotMatrix";
import InlineSvg from "./InlineSvg";
import { editorialAssets as assets } from "./assets";
import { PathLink } from "../Shared";
import "../../editorial.css";

const INK = [45, 45, 45] as const;
const SOFT_INK = [138, 138, 138] as const;
const BUILDER_GLYPHS = [" ", ".", ":", "/", "+", "<", ">", "{", "}", "_"];
const EASE = [0.23, 1, 0.32, 1] as const;

export function Reveal({
  children,
  className = "",
  delay = 0,
}: {
  children: ReactNode;
  className?: string;
  delay?: number;
}) {
  const reduced = useReducedMotion();
  return (
    <motion.div
      className={className}
      initial={reduced ? false : { opacity: 0, y: 22 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.12 }}
      transition={{ duration: 0.7, delay, ease: EASE }}
    >
      {children}
    </motion.div>
  );
}

export function RevealLines({ lines, immediate = false }: { lines: string[]; immediate?: boolean }) {
  return (
    <>
      <span className="sr-only">{lines.join(" ")}</span>
      <span
        aria-hidden="true"
        className={immediate ? "ed-title-lines" : "ed-title-lines ed-title-entrance"}
      >
        {lines.map((line, index) => (
          <span className="ed-line-mask" key={line}>
            <span style={{ animationDelay: `${index * 80}ms` }}>
              {line}
            </span>
          </span>
        ))}
      </span>
    </>
  );
}

export function ReferenceArrow() {
  return (
    <img
      className="ed-arrow"
      src={assets.arrow}
      alt=""
      width="19"
      height="19"
    />
  );
}

export function Halftone({
  src,
  width = 240,
  height = 240,
  soft = false,
  className = "",
}: {
  src: string;
  width?: number;
  height?: number;
  soft?: boolean;
  className?: string;
}) {
  return (
    <div className={`ed-halftone ${className}`} aria-hidden="true">
      <DotMatrix
        src={src}
        width={width}
        height={height}
        pitch={soft ? 6 : 3}
        gain={soft ? 20 : 1.3}
        threshold={0.09}
        dotScale={0.95}
        radius={65}
        ink={soft ? SOFT_INK : INK}
        inkOpacity={soft ? 0.42 : 0.9}
        glyphs={BUILDER_GLYPHS}
        glyphScale={1.8}
      />
    </div>
  );
}

export function GridArtwork() {
  return (
    <div className="ed-grid-art" aria-hidden="true">
      <InlineSvg svg={assets.gridA} fit spread={0.8} />
      <InlineSvg svg={assets.gridB} fit spread={1} delay={0.2} />
    </div>
  );
}

export function EditorialHero({
  number,
  label,
  lines,
  description,
  variant,
}: {
  number: string;
  label: string;
  lines: string[];
  description: string;
  variant: "about" | "builds" | "community";
}) {
  return (
    <header className={`ed-hero ed-hero-${variant}`}>
      <DesignCanvas height={760}>
        <div className="ed-hero-background">
          <Halftone src={assets.backdrop} width={1512} height={760} soft />
        </div>
        <div className="ed-hero-topline">
          <span className="ed-label">
            [ {number} — {label} ]
          </span>
          <span className="ed-label">THE AI-NATIVE GENERATION</span>
        </div>
        <div className="ed-hero-title">
          <p className="ed-kicker">
            {variant === "about"
              ? "( A beginning, together )"
              : variant === "builds"
                ? "( From thought to thing )"
                : "( The art of building together )"}
          </p>
          <h1>
            <RevealLines lines={lines} immediate={variant === "about"} />
          </h1>
        </div>
        <div className="ed-hero-description">
          <span className="ed-small-square" />
          <p>{description}</p>
        </div>
        <div className="ed-hero-annotation">
          <span>INIT://</span>
          <span>
            {variant === "about"
              ? "CURIOSITY IS A STARTING POINT."
              : variant === "builds"
                ? "EXPERIMENTS. NOT JUST IDEAS."
                : "ACROSS DISCIPLINES. ACROSS BORDERS."}
          </span>
        </div>
        <div className="ed-hero-bottomline">
          <span className="ed-label">INITIALIZE SOMETHING NEW.</span>
          <span className="ed-label">SCROLL TO EXPLORE ↓</span>
        </div>
      </DesignCanvas>
    </header>
  );
}

export function EditorialJoinStrip() {
  return (
    <section className="ed-join-strip">
      <span className="ed-label">AN OPEN INVITATION</span>
      <Reveal>
        <h2>
          Something starts
          <br />
          <em>with you.</em>
        </h2>
      </Reveal>
      <PathLink to="join" className="ed-button">
        <span>FIND YOUR STARTING POINT</span>
        <ReferenceArrow />
      </PathLink>
    </section>
  );
}
