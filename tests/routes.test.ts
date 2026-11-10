import test from "node:test";
import assert from "node:assert/strict";
import { parseRoute, routes } from "../src/lib/routes.ts";

test("opens root for a bare GitHub Pages URL", () => {
  for (const hash of ["", "#", "#/", "#/root"])
    assert.equal(parseRoute(hash), "root");
});

test("all published hash routes survive direct linking and trailing slashes", () => {
  for (const route of routes) {
    assert.equal(parseRoute(`#/${route}`), route);
    assert.equal(parseRoute(`#/${route}/`), route);
    const repositoryUrl = new URL(`https://example.github.io/INIT_/#/${route}`);
    assert.equal(repositoryUrl.pathname, "/INIT_/");
    assert.equal(parseRoute(repositoryUrl.hash), route);
  }
});

test("unknown and malformed routes have an intentional recovery page", () => {
  for (const hash of [
    "#/missing",
    "#/about/missing",
    "#/%E0%A4%A",
    "#/constructor",
  ]) {
    assert.equal(parseRoute(hash), "not-found");
  }
});
