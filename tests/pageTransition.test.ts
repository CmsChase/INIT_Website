import assert from "node:assert/strict";
import test from "node:test";
import { createPageTransition } from "../src/lib/pageTransition.ts";

function surface(reduced: boolean, capture?: (update: () => void) => unknown) {
  const events: string[] = [];
  const content = {
    ownerDocument: {
      defaultView: { matchMedia: () => ({ matches: reduced }) },
      hidden: false,
      startViewTransition: capture,
    },
    animate() {
      events.push("fade");
      return { cancel: () => events.push("cancel") };
    },
  };
  return { transition: createPageTransition(content as unknown as HTMLElement), events };
}

test("an interrupted snapshot cannot commit an earlier destination after the latest one", () => {
  const updates: (() => void)[] = [];
  let skips = 0;
  const { transition, events } = surface(false, update => {
    updates.push(update);
    return { ready: Promise.resolve(), finished: Promise.resolve(), skipTransition: () => ++skips };
  });
  transition.run(() => events.push("about"));
  transition.run(() => events.push("join"));
  updates[1]();
  updates[0]();
  assert.equal(skips, 1);
  assert.deepEqual(events, ["join"]);
});

test("reduced motion navigates immediately without capturing or animating", () => {
  const { transition, events } = surface(true, () => assert.fail("unexpected snapshot"));
  transition.run(() => events.push("about"));
  assert.deepEqual(events, ["about"]);
});

test("the fallback paints content before fading and cancels an interrupted fade", () => {
  const { transition, events } = surface(false);
  transition.run(() => events.push("about"));
  transition.run(() => events.push("join"));
  assert.deepEqual(events, ["about", "fade", "cancel", "join", "fade"]);
});
