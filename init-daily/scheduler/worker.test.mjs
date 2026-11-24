import assert from "node:assert/strict";
import { test } from "node:test";
import worker from "./worker.mjs";

const daily = { cron: "5 1 * * *" };

test("dispatch targets INIT Daily on main and previews unless live is explicitly enabled", async (t) => {
  const dispatch = t.mock.method(globalThis, "fetch", async () => Response.json({ workflow_run_id: 123 }));
  const log = t.mock.method(console, "log", () => {});

  for (const live of [undefined, "false", "true"]) {
    await worker.scheduled(daily, { GITHUB_DISPATCH_TOKEN: "mock-token", LIVE_PUBLISH: live });
  }

  assert.equal(dispatch.mock.callCount(), 3);
  for (const { arguments: [url, request] } of dispatch.mock.calls) {
    assert.equal(url, "https://api.github.com/repos/CmsChase/INIT_Website/actions/workflows/init-daily.yml/dispatches");
    assert.equal(request.method, "POST");
    assert.equal(request.redirect, "manual");
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

test("one-time trigger dispatches on the configured UTC instant only", async (t) => {
  const dispatch = t.mock.method(globalThis, "fetch", async () => Response.json({ workflow_run_id: 123 }));
  const log = t.mock.method(console, "log", () => {});
  const env = { GITHUB_DISPATCH_TOKEN: "mock-token", ONE_TIME_TRIGGER_AT: "2026-11-15T05:50:00Z" };
  const cron = "50 5 15 11 *";
  const scheduledTime = Date.parse(env.ONE_TIME_TRIGGER_AT);

  await worker.scheduled({ cron, scheduledTime: Date.parse("2027-11-15T05:50:00Z") }, env);
  await worker.scheduled({ cron, scheduledTime }, { GITHUB_DISPATCH_TOKEN: "mock-token" });
  assert.equal(dispatch.mock.callCount(), 0);

  await worker.scheduled({ cron, scheduledTime }, env);
  assert.equal(dispatch.mock.callCount(), 1);
  assert.match(log.mock.calls[0].arguments[0], /preview · run 123$/);
});

test("missing credentials fail before any HTTP request", async (t) => {
  const dispatch = t.mock.method(globalThis, "fetch", () => assert.fail("Unexpected dispatch"));
  await assert.rejects(worker.scheduled(daily, {}), /^Error: Configure the GITHUB_DISPATCH_TOKEN Worker secret$/);
  assert.equal(dispatch.mock.callCount(), 0);
});

test("diagnostic cron is one-time and always previews even with live publishing", async (t) => {
  const dispatch = t.mock.method(globalThis, "fetch", async () => Response.json({ workflow_run_id: 123 }));
  t.mock.method(console, "log", () => {});
  const env = { GITHUB_DISPATCH_TOKEN: "mock-token", LIVE_PUBLISH: "true", PROBE_TRIGGER_AT: "2026-11-24T09:40:00Z" };
  const event = { cron: "40 9 24 11 *", scheduledTime: Date.parse(env.PROBE_TRIGGER_AT) };
  await worker.scheduled(event, env);
  assert.equal(dispatch.mock.callCount(), 1);
  assert.equal(JSON.parse(dispatch.mock.calls[0].arguments[1].body).inputs.dry_run, true);
  await worker.scheduled({ ...event, scheduledTime: Date.parse("2027-11-24T09:40:00Z") }, env);
  assert.equal(dispatch.mock.callCount(), 1);
});

test("API and transport errors omit credential and response details", async (t) => {
  const dispatch = t.mock.method(globalThis, "fetch", async () => new Response("provider detail", { status: 403 }));
  const env = { GITHUB_DISPATCH_TOKEN: "mock-token" };
  await assert.rejects(worker.scheduled(daily, env), /^Error: GitHub dispatch failed \(HTTP 403\)$/);
  dispatch.mock.mockImplementation(async () => { throw new Error(env.GITHUB_DISPATCH_TOKEN); });
  await assert.rejects(worker.scheduled(daily, env), /^Error: Could not confirm GitHub dispatch \(network_error\)\./);
  dispatch.mock.mockImplementation(async () => { throw new TypeError(env.GITHUB_DISPATCH_TOKEN); });
  await assert.rejects(worker.scheduled(daily, env), /^Error: Could not confirm GitHub dispatch \(runtime_request_error\)\./);
});

test("redirect response is rejected without forwarding the GitHub credential", async (t) => {
  const dispatch = t.mock.method(globalThis, "fetch", async (_url, request) => {
    assert.equal(request.redirect, "manual");
    return new Response(null, {status:302,headers:{Location:"https://untrusted.example/collect"}});
  });
  await assert.rejects(worker.scheduled(daily, {GITHUB_DISPATCH_TOKEN:"mock-token"}), /^Error: GitHub dispatch failed \(HTTP 302\)$/);
  assert.equal(dispatch.mock.callCount(), 1);
});
