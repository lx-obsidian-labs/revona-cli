/**
 * Revona workforce templates. Pure data/planning layer: no credentials, tool
 * permissions or external side effects are granted by choosing a template.
 */
export const REVONA_ROLES = Object.freeze({
  chief_of_staff: { name: "Revona Chief of Staff", purpose: "Coordinate work, propose assignments and report progress.", capabilities: ["planning", "delegation"], integrations: [] },
  email: { name: "Revona Communications", purpose: "Draft and organize correspondence for approval.", capabilities: ["drafting", "inbox_triage"], integrations: ["email"] },
  social: { name: "Revona Creative", purpose: "Plan content and prepare posts for review.", capabilities: ["content_planning", "drafting"], integrations: ["social"] },
  finance: { name: "Revona Finance", purpose: "Categorize records and prepare financial summaries; no payments.", capabilities: ["reporting", "reconciliation"], integrations: ["accounting"] },
  projects: { name: "Revona Operations", purpose: "Organize tasks, milestones and status updates.", capabilities: ["planning", "tracking"], integrations: ["project_management"] },
  research: { name: "Revona Intelligence", purpose: "Research topics and summarize sources.", capabilities: ["research", "summarization"], integrations: ["web"] },
} as const);
type RoleId = keyof typeof REVONA_ROLES;
export type WorkforceInput = { kind: "business" | "freelancer"; organization: string; goals?: string };
const BUSINESS_ROLES: RoleId[] = ["chief_of_staff", "email", "social", "finance", "projects"];
const FREELANCER_ROLES: RoleId[] = ["chief_of_staff", "email", "projects", "research"];
const TASK_KEYWORDS: Array<[RegExp, RoleId]> = [
  [/email|inbox|mail|client message/i, "email"],
  [/social|marketing|post|content|tiktok|instagram/i, "social"],
  [/invoice|finance|expense|bookkeep|budget/i, "finance"],
  [/project|deadline|milestone|task|delivery/i, "projects"],
  [/research|competitor|market|investigat/i, "research"],
];
export function createWorkforcePlan(input: WorkforceInput) {
  if (!input || !["business", "freelancer"].includes(input.kind)) throw new TypeError("kind must be business or freelancer");
  const organization = String(input.organization ?? "").trim().slice(0, 120);
  if (!organization) throw new TypeError("organization is required");
  const goals = String(input.goals ?? "").trim().slice(0, 2000);
  const requested = new Set(input.kind === "business" ? BUSINESS_ROLES : FREELANCER_ROLES);
  for (const [pattern, role] of TASK_KEYWORDS) if (pattern.test(goals)) requested.add(role);
  const roles = [...requested].map((id) => ({
    id,
    ...REVONA_ROLES[id],
    reportsTo: id === "chief_of_staff" ? null : "chief_of_staff",
    state: "proposed",
    requiresApproval: true,
    connected: false,
  }));
  return {
    schemaVersion: 1,
    organization,
    kind: input.kind,
    goals,
    roles,
    executionEnabled: false,
    approvalRequiredFor: ["external_messages", "publishing", "financial_transactions", "credential_access", "delegation"],
  };
}
