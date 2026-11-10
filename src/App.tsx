import { lazy, Suspense, useEffect, useLayoutEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { parseRoute, routes, routeTitles } from "./lib/routes";
import { createPageTransition } from "./lib/pageTransition";
import { Arrow } from "./components/Icons";
import { PathLink } from "./components/Shared";
import Intro from "./components/Intro";
const DirectoryPage = lazy(() => import("./pages/DirectoryPage"));

export default function App() {
  const [page, setPage] = useState(() => parseRoute(window.location.hash));
  const [navigationCount, setNavigationCount] = useState(0);
  const main = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!main.current) return;
    const transition = createPageTransition(main.current);
    const onHashChange = () => {
      const destination = parseRoute(window.location.hash);
      transition.run(() => {
        flushSync(() => {
          setPage(destination);
          setNavigationCount((count) => count + 1);
        });
      });
    };
    window.addEventListener("hashchange", onHashChange);
    return () => {
      window.removeEventListener("hashchange", onHashChange);
      transition.cancel();
    };
  }, []);

  useLayoutEffect(() => {
    document.title = `INIT:// — ${routeTitles[page]}`;
    if (navigationCount > 0) {
      window.scrollTo({ top: 0, behavior: "instant" });
      main.current?.focus({ preventScroll: true });
    }
  }, [page, navigationCount]);

  return (
    <>
      <Intro />
      <a
        className="skip-link"
        href="#main"
        onClick={(event) => {
          event.preventDefault();
          main.current?.focus();
        }}
      >
        Skip to content
      </a>
      <div
        className={`site-shell${page !== "not-found" ? " editorial-site" : ""}`}
      >
        <header className="site-header">
          <PathLink to="root" className="wordmark">
            <span aria-label="INIT home">
              INIT://<span className="wordmark-cursor">_</span>
            </span>
          </PathLink>
          <nav aria-label="Main navigation">
            {routes.map((route) => (
              <PathLink
                to={route}
                key={route}
                current={page === route}
                className={`nav-link ${page === route ? "is-active" : ""}`}
              >
                <span>/{route}</span>
                {route === "join" && <Arrow diagonal />}
              </PathLink>
            ))}
          </nav>
          <span className="header-note">
            <span className="status-dot" />A PLACE TO BEGIN
          </span>
        </header>
        <div className="path-bar">
          <span>
            <span className="path-prefix">INIT:</span>/
            {page === "not-found" ? "404" : page}
            <span className="path-cursor">_</span>
          </span>
          <span>IDEAS BECOME REAL HERE.</span>
        </div>
        <main id="main" tabIndex={-1} ref={main} data-navigated={navigationCount > 0 || undefined}>
          <Suspense
            fallback={
              <p role="status" style={{ padding: "60px 24px" }}>
                Opening directory…
              </p>
            }
          >
            {page !== "not-found" ? (
              <DirectoryPage route={page} />
            ) : (
              <section className="not-found">
                <p className="eyebrow">404 / DIRECTORY NOT FOUND</p>
                <h1>
                  A different
                  <br />
                  <span className="serif">starting point.</span>
                </h1>
                <p>
                  This directory doesn’t exist. Let’s get you back to the
                  beginning.
                </p>
                <PathLink to="root" className="button button-dark">
                  Back to root <Arrow />
                </PathLink>
              </section>
            )}
          </Suspense>
        </main>
        <footer className="site-footer">
          <div className="footer-top">
            <PathLink to="root" className="wordmark">
              INIT://<span className="wordmark-cursor">_</span>
            </PathLink>
            <p>Initialize something new.</p>
            <PathLink to="join" className="text-link">
              The beginning is open <Arrow diagonal />
            </PathLink>
          </div>
          <div className="footer-bottom">
            <span>© {new Date().getFullYear()} INIT://</span>
            <span>BUILT ON CURIOSITY. OPEN TO POSSIBILITY.</span>
            <a
              href="#top"
              onClick={(event) => {
                event.preventDefault();
                window.scrollTo({
                  top: 0,
                  behavior: window.matchMedia(
                    "(prefers-reduced-motion: reduce)",
                  ).matches
                    ? "instant"
                    : "smooth",
                });
                document
                  .querySelector<HTMLAnchorElement>(".site-header .wordmark")
                  ?.focus({ preventScroll: true });
              }}
            >
              BACK TO TOP ↑
            </a>
          </div>
        </footer>
      </div>
    </>
  );
}
