import test from "node:test";
import assert from "node:assert/strict";
import worker from "./index.ts";

const env = { NVIDIA_NIM_API_KEY: "server-only-key", REVONA_CLIENT_TOKEN: "private-test-token" };
const endpoint = "https://revona.example/v1/chat/completions";
test("health does not expose secrets", async () => {
  const response = await worker.fetch(new Request("https://revona.example/health"), env);
  assert.equal(response.status, 200);
  assert.doesNotMatch(await response.text(), /server-only-key/);
});
test("rejects requests without authentication", async () => {
  const response = await worker.fetch(new Request(endpoint, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ messages: [{ role: "user", content: "hello" }] }) }), env);
  assert.equal(response.status, 401);
});
test("rejects malformed and oversized requests before reaching NVIDIA", async () => {
  const headers = { authorization: "Bearer private-test-token", "content-type": "application/json" };
  const malformed = await worker.fetch(new Request(endpoint, { method: "POST", headers, body: "{}" }), env);
  assert.equal(malformed.status, 400);
  const huge = await worker.fetch(new Request(endpoint, { method: "POST", headers, body: JSON.stringify({ messages: [{ role: "user", content: "a".repeat(100001) }] }) }), env);
  assert.equal(huge.status, 413);
});
test("refuses streaming until a safe streaming contract is implemented", async () => {
  const response = await worker.fetch(new Request(endpoint, { method: "POST", headers: { authorization: "Bearer private-test-token" }, body: JSON.stringify({ stream: true, messages: [{ role: "user", content: "hi" }] }) }), env);
  assert.equal(response.status, 400);
});
