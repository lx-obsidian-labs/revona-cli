import assert from "node:assert/strict";
import test from "node:test";
import { revonaUpdatesDisabled } from "./revona-update-policy.mjs";

test("packaged Revona must not use inherited automatic updates", () => {
  assert.equal(revonaUpdatesDisabled({ packaged: true, appName: "Revona Bot" }), true);
});
test("unpackaged development remains unchanged", () => {
  assert.equal(revonaUpdatesDisabled({ packaged: false, appName: "Revona Bot" }), false);
});
test("upstream application remains unchanged", () => {
  assert.equal(revonaUpdatesDisabled({ packaged: true, appName: "OpenMausBot" }), false);
});
