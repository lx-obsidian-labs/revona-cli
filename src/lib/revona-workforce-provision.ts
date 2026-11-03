import { api, type Bot } from "@/state/store";
import type { createWorkforcePlan } from "./revona-workforce";

export type WorkforcePlan = ReturnType<typeof createWorkforcePlan>;
export type WorkforceProvisionResult = { created: Bot[]; warnings: string[] };

/**
 * Provision explicitly approved, safe-by-default agents through the existing
 * bot API. No account connections, automatic execution or privileged approvals.
 * The caller must obtain confirmation before invoking this function.
 */
export async function provisionWorkforce(
  plan: WorkforcePlan,
  request: typeof api = api,
): Promise<WorkforceProvisionResult> {
  if (!plan || plan.executionEnabled !== false || !plan.roles.length) throw new Error("Invalid workforce proposal");
  if (plan.roles.some(role => role.requiresApproval !== true || role.state !== "proposed")) {
    throw new Error("Only unactivated proposals can be provisioned");
  }
  const created: Bot[] = [];
  const warnings: string[] = [];
  try {
    for (const role of plan.roles) {
      const response = await request<{ bot: Bot }>("/api/bots", {
        method: "POST",
        body: JSON.stringify({
          name: role.name,
          title: role.name,
          description: role.purpose,
          useDefaults: false,
          settings: { approvalMode: "ask" },
        }),
      });
      if (!response.bot?.id) throw new Error(`No agent ID returned for ${role.name}`);
      created.push(response.bot);
    }
  } catch (error) {
    const leftovers: string[] = [];
    for (const bot of [...created].reverse()) {
      try { await request(`/api/bots/${encodeURIComponent(bot.id)}`, { method: "DELETE" }); }
      catch { leftovers.push(bot.name); }
    }
    const message = error instanceof Error ? error.message : String(error);
    throw new Error(leftovers.length ? `${message}. Manual cleanup needed: ${leftovers.join(", ")}` : message);
  }
  // Chief designation uses the original engine's privileged profile endpoint.
  // A failure must not undo an already-created workforce; surface it for review.
  const chief = created[plan.roles.findIndex(role => role.id === "chief_of_staff")];
  if (chief) {
    try {
      await request(`/api/bots/${encodeURIComponent(chief.id)}`, {
        method: "PATCH",
        body: JSON.stringify({ chiefOfStaff: true }),
      });
    } catch (error) {
      warnings.push(`Chief of Staff designation needs review: ${error instanceof Error ? error.message : String(error)}`);
    }
  }
  warnings.push("Agents were created without external account connections or automatic execution. Configure models and permissions before use.");
  return { created, warnings };
}
