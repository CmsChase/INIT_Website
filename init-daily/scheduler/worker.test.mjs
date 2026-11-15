import assert from "node:assert/strict";
import { test } from "node:test";
import worker from "./worker.mjs";

test("dispatch targets INIT Daily on main and previews unless live is explicitly enabled", async (t) => {
  const dispatch = t.mock.method(globalThis, "fetch", async () => Response.json({ workflow_run_id: 123 }));
  const log = t.mock.method(console, "log", () => {});

  for (const live of [undefined, "false", "true"]) {
    await worker.scheduled({}, { GITHUB_DISPATCH_TOKEN: "mock-token", LIVE_PUBLISH: live });
  }

  assert.equal(dispatch.mock.callCount(), 3);
  for (const { arguments: [url, request] } of dispatch.mock.calls) {
    assert.equal(url, "https://api.github.com/repos/CmsChase/INIT_Website/actions/workflows/init-daily.yml/dispatches");
    assert.equal(request.method, "POST");
    assert.equal(request.redirect, "error");
    assert.equal(request.headers.Authorization, "Bearer mock-token");
    const body = JSON.parse(request.body);
    assert.equal(body.ref, "main");
    assert.equal(body.inputs.scheduled_delivery, true);
    assert.equal(body.inputs.no_ai, false);
    assert.equal(body.return_run_details, true);
  }
  const inputs = dispatch.mock.calls.map(({ arguments: [, request] }) => JSON.parse(request.body).inputs);
  assert.deepEqual(inputs.map(({ dry_run }) => dry_run), [true, true, false]);
  assert.match(log.mock.calls[0].arguments[0], /preview · run 123$/);
  assert.match(log.mock.calls[2].arguments[0], /scheduled delivery · run 123$/);
});

test("missing credentials fail before any HTTP request", async (t) => {
  const dispatch = t.mock.method(globalThis, "fetch", () => assert.fail("Unexpected dispatch"));
  await assert.rejects(worker.scheduled({}, {}), /^Error: Configure the GITHUB_DISPATCH_TOKEN Worker secret$/);
  assert.equal(dispatch.mock.callCount(), 0);
});

test("API and transport errors omit credential and response details", async (t) => {
  const dispatch = t.mock.method(globalThis, "fetch", async () => new Response("provider detail", { status: 403 }));
  const env = { GITHUB_DISPATCH_TOKEN: "mock-token" };
  await assert.rejects(worker.scheduled({}, env), /^Error: GitHub dispatch failed \(HTTP 403\)$/);
  dispatch.mock.mockImplementation(async () => { throw new Error(env.GITHUB_DISPATCH_TOKEN); });
  await assert.rejects(worker.scheduled({}, env), /^Error: Could not confirm GitHub dispatch\./);
});
