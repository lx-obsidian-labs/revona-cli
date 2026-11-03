import test from "node:test";
import assert from "node:assert/strict";
import { createWorkforcePlan } from "./revona-workforce.ts";
import { provisionWorkforce } from "./revona-workforce-provision.ts";
import type { api } from "@/state/store";

type Request = typeof api;
const fakeBot = (id: string, name: string) => ({ id, name });

test("approved workforce provisions named Revona agents without credentials or auto execution", async () => {
  const plan = createWorkforcePlan({ kind: "freelancer", organization: "Example", goals: "Research clients" });
  const calls: Array<{ path: string; method: string; body?: Record<string, unknown> }> = [];
  const request = (async (path: string, options?: RequestInit) => {
    const body = options?.body ? JSON.parse(String(options.body)) as Record<string, unknown> : undefined;
    calls.push({ path, method: options?.method ?? "GET", body });
    return { bot: fakeBot(String(calls.length), String(body?.name)) };
  }) as Request;
  const result = await provisionWorkforce(plan, request);
  assert.equal(result.created.length, plan.roles.length);
  assert.equal(calls.filter(call => call.method === "POST").length, plan.roles.length);
  assert.ok(calls.some(call => call.method === "PATCH" && call.path === "/api/bots/1"));
  assert.ok(calls.filter(call => call.method === "POST").every(call => call.body?.useDefaults === false));
  assert.ok(calls.filter(call => call.method === "POST").every(call => (call.body?.settings as { approvalMode: string }).approvalMode === "ask"));
  assert.ok(calls.every(call => !("reportsTo" in (call.body ?? {}))));
  assert.ok(result.created.every(bot => bot.name.startsWith("Revona")));
});

test("failed creation rolls back previously created agents in reverse order", async () => {
  const plan = createWorkforcePlan({ kind: "freelancer", organization: "Example", goals: "Project work" });
  const deleted: string[] = [];
  let created = 0;
  const request = (async (path: string, options?: RequestInit) => {
    if (options?.method === "DELETE") { deleted.push(path); return {}; }
    created++;
    if (created === 3) throw new Error("simulated backend failure");
    return { bot: fakeBot(String(created), "Revona test") };
  }) as Request;
  await assert.rejects(provisionWorkforce(plan, request), /simulated backend failure/);
  assert.deepEqual(deleted, ["/api/bots/2", "/api/bots/1"]);
});

test("rejects an execution-enabled or unapproved workforce proposal", async () => {
  const plan = createWorkforcePlan({ kind: "business", organization: "Example" });
  const request = (async () => { throw new Error("must not call backend"); }) as Request;
  await assert.rejects(provisionWorkforce({ ...plan, executionEnabled: true }, request), /Invalid workforce proposal/);
  await assert.rejects(provisionWorkforce({ ...plan, roles: plan.roles.map((role, index) => index ? role : { ...role, requiresApproval: false }) }, request), /Only unactivated proposals/);
});

test("Chief configuration failure is surfaced without deleting created agents", async () => {
  const plan = createWorkforcePlan({ kind: "business", organization: "Example", goals: "Marketing" });
  const calls: Array<{ path: string; method: string }> = [];
  let count = 0;
  const request = (async (path: string, options?: RequestInit) => {
    const method = options?.method ?? "GET";
    calls.push({ path, method });
    if (method === "PATCH") throw new Error("permission denied");
    if (method === "POST") {
      count++;
      return { bot: fakeBot(String(count), "Revona agent") };
    }
    throw new Error("unexpected request");
  }) as Request;
  const result = await provisionWorkforce(plan, request);
  assert.equal(result.created.length, plan.roles.length);
  assert.ok(result.warnings.some(warning => /Chief of Staff designation needs review: permission denied/.test(warning)));
  assert.equal(calls.filter(call => call.method === "DELETE").length, 0);
});

test("Chief configuration uses the created Chief ID, not an assumed fixed ID", async () => {
  const plan = createWorkforcePlan({ kind: "freelancer", organization: "Example", goals: "Research" });
  const calls: Array<{ path: string; method: string; body?: Record<string, unknown> }> = [];
  const request = (async (path: string, options?: RequestInit) => {
    const method = options?.method ?? "GET";
    const body = options?.body ? JSON.parse(String(options.body)) as Record<string, unknown> : undefined;
    calls.push({ path, method, body });
    if (method === "POST") return { bot: fakeBot(`agent-${calls.length}`, String(body?.name)) };
    return {};
  }) as Request;
  await provisionWorkforce(plan, request);
  const patch = calls.find(call => call.method === "PATCH");
  assert.equal(patch?.path, "/api/bots/agent-1");
  assert.deepEqual(patch?.body, { chiefOfStaff: true });
});
