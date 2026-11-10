// One controller per mounted directory. History and focus stay with the router.
export function createPageTransition(content: HTMLElement) {
  const doc = content.ownerDocument;
  const reducedMotion = doc.defaultView!.matchMedia("(prefers-reduced-motion: reduce)");
  let active: ViewTransition | undefined;
  let entrance: Animation | undefined;
  let revision = 0;

  function cancel() {
    ++revision;
    active?.skipTransition();
    active = undefined;
    entrance?.cancel();
    entrance = undefined;
  }

  function run(update: () => void) {
    cancel();
    const request = revision;
    if (reducedMotion.matches || doc.hidden) {
      update();
      return;
    }
    if (typeof doc.startViewTransition !== "function") {
      update();
      entrance = content.animate?.([{ opacity: 0.74 }, { opacity: 1 }], {
        duration: 180,
        easing: "ease-out",
      });
      return;
    }

    const transition = doc.startViewTransition(() => {
      // Skipping an old transition still invokes its queued update callback.
      if (request === revision) update();
    });
    active = transition;
    // Skipping before capture rejects ready, but navigation still succeeds.
    void transition.ready.catch(() => {});
    void transition.finished.then(() => {
      if (active === transition) active = undefined;
    });
  }
  return { run, cancel };
}
