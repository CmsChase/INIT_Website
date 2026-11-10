import { useRef } from "react";
import {
  motion,
  useReducedMotion,
  useScroll,
  useSpring,
  useTransform,
} from "framer-motion";
import { useFitContain } from "./Canvas";
import { editorialAssets as assets } from "./assets";
import { Reveal } from "./Editorial";

export default function HumanStory() {
  const section = useRef<HTMLElement>(null);
  const reduced = useReducedMotion();
  const fit = useFitContain(1512, 850);
  const { scrollYProgress } = useScroll({
    target: section,
    offset: ["start start", "end end"],
  });
  const progress = useSpring(scrollYProgress, {
    stiffness: 150,
    damping: 40,
    mass: 0.5,
  });
  const leftX = useTransform(progress, [0, 0.65, 1], [-60, 0, 0]);
  const rightX = useTransform(progress, [0, 0.65, 1], [60, 0, 0]);
  const statueY = useTransform(progress, [0, 1], [55, -20]);
  const statueScale = useTransform(progress, [0, 1], [0.9, 1]);
  const ruleScale = useTransform(progress, [0, 1], [0.08, 1]);

  return (
    <section
      className="ed-human-story"
      ref={section}
      aria-labelledby="human-story-title"
    >
      <h2 id="human-story-title" className="sr-only">
        Technology opens the door. People build the future.
      </h2>
      <div
        className="ed-human-sticky ed-desktop"
        ref={fit.ref}
        aria-hidden="true"
      >
        <div
          className="ed-human-canvas"
          style={{
            width: 1512,
            height: 850,
            transform: `translate(${fit.x}px, ${fit.y}px) scale(${fit.scale})`,
            transformOrigin: "top left",
          }}
        >
          <div className="ed-human-top">
            <span className="ed-label">01 / OUR SHARED BELIEF</span>
            <span className="ed-kicker">( The human part )</span>
            <span className="ed-label">NOTHING BEGINS WITHOUT US.</span>
          </div>
          <div className="ed-human-cross cross-one">+</div>
          <div className="ed-human-cross cross-two">+</div>
          <motion.img
            className="ed-statue"
            src={assets.statue}
            alt=""
            style={{
              y: reduced ? 0 : statueY,
              scale: reduced ? 1 : statueScale,
            }}
          />
          <motion.div
            className="ed-human-words words-left"
            style={{ x: reduced ? 0 : leftX }}
          >
            TECHNOLOGY
            <br />
            OPENS
            <br />
            <em>the door.</em>
          </motion.div>
          <motion.div
            className="ed-human-words words-right"
            style={{ x: reduced ? 0 : rightX }}
          >
            PEOPLE
            <br />
            BUILD
            <br />
            <em>the future.</em>
          </motion.div>
          <div className="ed-human-bottom">
            <span className="ed-label">
              THE TOOLS ARE NEW.
              <br />
              THE POSSIBILITY IS OURS.
            </span>
            <p>
              Curiosity. Judgment. Care.
              <br />
              The things that make a builder.
            </p>
            <span className="ed-label">KEEP GOING ↓</span>
          </div>
          <motion.div
            className="ed-story-progress"
            style={{ scaleX: reduced ? 1 : ruleScale }}
          />
        </div>
      </div>
      <div className="ed-human-mobile ed-mobile">
        <p className="ed-kicker">( The human part )</p>
        <Reveal>
          <p className="ed-human-mobile-title">
            TECHNOLOGY
            <br />
            OPENS THE DOOR.
          </p>
        </Reveal>
        <img
          src={assets.statue}
          alt=""
          loading="lazy"
          width="350"
          height="450"
        />
        <Reveal>
          <p className="ed-human-mobile-title">
            PEOPLE BUILD
            <br />
            <em>the future.</em>
          </p>
        </Reveal>
        <p className="ed-label">CURIOSITY. JUDGMENT. CARE.</p>
      </div>
    </section>
  );
}
