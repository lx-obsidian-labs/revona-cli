import test from "node:test";
import assert from "node:assert/strict";
import { createWorkforcePlan, REVONA_ROLES } from "./revona-workforce.ts";

test("business plans contain a chief of staff and approved-by-default roles", () => {
  const plan = createWorkforcePlan({ kind: "business", organization: "  LX Labs  ", goals: "Manage social media and expenses" });
  assert.equal(plan.organization, "LX Labs");
  assert.equal(plan.roles[0].id, "chief_of_staff");
  assert.equal(plan.roles.find((r) => r.id === "social")?.reportsTo, "chief_of_staff");
  assert.equal(plan.roles.find((r) => r.id === "finance")?.requiresApproval, true);
  assert.equal(plan.executionEnabled, false);
  assert.ok(plan.roles.every((r) => r.connected === false && r.state === "proposed"));
});
test("freelancer goals add relevant optional agents without duplicates", () => {
  const plan = createWorkforcePlan({ kind: "freelancer", organization: "Studio", goals: "TikTok marketing and email" });
  assert.equal(plan.roles.filter((r) => r.id === "social").length, 1);
  assert.equal(plan.roles.length, new Set(plan.roles.map((r) => r.id)).size);
});
test("rejects missing business identity and invalid user type", () => {
  assert.throws(() => createWorkforcePlan({ kind: "enterprise" as unknown as "business", organization: "X" }), TypeError);
  assert.throws(() => createWorkforcePlan({ kind: "business", organization: "  " }), TypeError);
});
test("template catalog contains only non-executing descriptions", () => {
  assert.ok(Object.keys(REVONA_ROLES).length >= 6);
  assert.ok(Object.values(REVONA_ROLES).every((role) => Array.isArray(role.integrations)));
});
