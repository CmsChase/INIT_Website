import { useEffect, useState } from "react";

const STORAGE_KEY = "init-intro-seen";
const HOLD_MS = 2000;
const FADE_MS = 400;
function shouldShowIntro() {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches)
    return false;
  // A shared direct link should open its destination immediately.
  if (window.location.hash && !["#/", "#/root"].includes(window.location.hash))
    return false;
  try {
    return sessionStorage.getItem(STORAGE_KEY) !== "1";
  } catch {
    return true;
  }
}

export default function Intro() {
  const [visible, setVisible] = useState(shouldShowIntro);
  const [leaving, setLeaving] = useState(false);

  useEffect(() => {
    if (!visible) return;
    try {
      sessionStorage.setItem(STORAGE_KEY, "1");
    } catch {
      /* Storage can be disabled. */
    }
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const start = window.setTimeout(() => setLeaving(true), HOLD_MS);
    const end = window.setTimeout(() => setVisible(false), HOLD_MS + FADE_MS);
    // Keyboard users never have to wait for an introduction or find a skip control.
    const skip = () => setVisible(false);
    window.addEventListener("keydown", skip, { once: true });
    return () => {
      clearTimeout(start);
      clearTimeout(end);
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", skip);
    };
  }, [visible]);

  if (!visible) return null;
  return (
    <div
      className={`intro ${leaving ? "intro-leaving" : ""}`}
      aria-hidden="true"
      onPointerDown={() => setVisible(false)}
    >
      <div className="intro-wordmark">
        INIT<span className="intro-syntax">://<span className="intro-cursor">_</span></span>
      </div>
    </div>
  );
}
