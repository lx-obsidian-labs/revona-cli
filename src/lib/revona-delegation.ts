import type { createWorkforcePlan } from "./revona-workforce";

export type RevonaPlan = ReturnType<typeof createWorkforcePlan>;
export type DelegationProposal = {
  task: string;
  chiefRoleId: "chief_of_staff";
  assigneeRoleId: string;
  assigneeName: string;
  reason: string;
  status: "awaiting_approval";
  executionEnabled: false;
};

const ROUTING: ReadonlyArray<{ keywords: RegExp; roleId: string; reason: string }> = [
  { keywords: /email|inbox|correspondence|reply|letter|client message/i, roleId: "email", reason: "Communications specializes in correspondence." },
  { keywords: /social|tiktok|instagram|facebook|content|campaign|post|marketing/i, roleId: "social", reason: "Creative specializes in content and campaigns." },
  { keywords: /invoice|expense|budget|account|financial|reconcil|payroll/i, roleId: "finance", reason: "Finance specializes in financial reporting." },
  { keywords: /research|competitor|investigat|industry|market analys/i, roleId: "research", reason: "Intelligence specializes in research and analysis." },
  { keywords: /project|milestone|deadline|delivery|schedule|task|operation/i, roleId: "projects", reason: "Operations specializes in project delivery." },
];

/**
 * Produce a human-reviewable assignment, never execute it. Only agents in the
 * approved workforce proposal are eligible; the Chief remains the coordinator.
 */
export function proposeRevonaDelegation(plan: RevonaPlan, rawTask: string): DelegationProposal {
  const task = String(rawTask ?? "").trim().slice(0, 2000);
  if (!task) throw new TypeError("A task description is required");
  if (!plan.roles.some(role => role.id === "chief_of_staff")) throw new Error("Chief of Staff is missing");
  const candidates = plan.roles.filter(role => role.id !== "chief_of_staff");
  if (!candidates.length) throw new Error("No specialist agents are available");
  const match = ROUTING.find(route => route.keywords.test(task) && candidates.some(role => role.id === route.roleId));
  const chosen = match ? candidates.find(role => role.id === match.roleId)! :
    candidates.find(role => role.id === "projects") ?? candidates[0];
  return {
    task,
    chiefRoleId: "chief_of_staff",
    assigneeRoleId: chosen.id,
    assigneeName: chosen.name,
    reason: match?.reason ?? "This specialist is available to review and plan the assignment.",
    status: "awaiting_approval",
    executionEnabled: false,
  };
}
