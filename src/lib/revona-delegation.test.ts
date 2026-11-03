import test from "node:test";
import assert from "node:assert/strict";
import { createWorkforcePlan } from "./revona-workforce.ts";
import { proposeRevonaDelegation } from "./revona-delegation.ts";

const business = createWorkforcePlan({ kind: "business", organization: "LX Labs", goals: "Marketing and projects" });

test("routes communication requests to Revona Communications", () => {
  const proposal = proposeRevonaDelegation(business, "Reply to a client email");
  assert.equal(proposal.assigneeRoleId, "email");
  assert.equal(proposal.status, "awaiting_approval");
  assert.equal(proposal.executionEnabled, false);
});
test("routes marketing to Revona Creative and finance to Revona Finance", () => {
  assert.equal(proposeRevonaDelegation(business, "Prepare TikTok content").assigneeRoleId, "social");
  assert.equal(proposeRevonaDelegation(business, "Summarize expenses").assigneeRoleId, "finance");
});
test("does not delegate to unavailable roles", () => {
  const freelancer = createWorkforcePlan({ kind: "freelancer", organization: "Studio" });
  const proposal = proposeRevonaDelegation(freelancer, "Analyze payroll expenses");
  assert.ok(freelancer.roles.some(role => role.id === proposal.assigneeRoleId));
  assert.notEqual(proposal.assigneeRoleId, "finance");
});
test("requires a task and Chief of Staff", () => {
  assert.throws(() => proposeRevonaDelegation(business, " "), TypeError);
  assert.throws(() => proposeRevonaDelegation({ ...business, roles: business.roles.filter(role => role.id !== "chief_of_staff") }, "Research"), /Chief of Staff/);
});
