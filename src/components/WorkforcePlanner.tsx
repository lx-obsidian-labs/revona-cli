import { useState } from "react";
import { createWorkforcePlan, type WorkforceInput } from "@/lib/revona-workforce";
import { provisionWorkforce } from "@/lib/revona-workforce-provision";

/** Advisory-only workforce preview. Agent creation remains an explicit separate action. */
export function WorkforcePlanner() {
  const [kind, setKind] = useState<WorkforceInput["kind"]>("business");
  const [organization, setOrganization] = useState("");
  const [goals, setGoals] = useState("");
  const [showPlan, setShowPlan] = useState(false);
  const [creating, setCreating] = useState(false);
  const [result, setResult] = useState("");
  const [error, setError] = useState("");
  const plan = showPlan && organization.trim()
    ? createWorkforcePlan({ kind, organization, goals })
    : null;
  return (
    <section aria-label="Revona workforce planner" className="border-b border-hairline/40 px-5 py-3 text-[13px]">
      <details>
        <summary className="cursor-pointer font-semibold text-ink">Plan an AI workforce for your business</summary>
        <p className="my-2 text-ink-secondary">Describe what you do. Revona will recommend a team for your review. This preview does not create agents or connect accounts.</p>
        <div className="grid gap-2 sm:grid-cols-2">
          <label className="flex flex-col gap-1">I work as
            <select value={kind} onChange={event => { setKind(event.target.value as WorkforceInput["kind"]); setShowPlan(false); }} className="rounded-lg border border-hairline/40 bg-inset p-2">
              <option value="business">A business</option><option value="freelancer">A freelancer</option>
            </select>
          </label>
          <label className="flex flex-col gap-1">Business or professional name
            <input value={organization} onChange={event => { setOrganization(event.target.value); setShowPlan(false); }} maxLength={120} className="rounded-lg border border-hairline/40 bg-inset p-2" placeholder="e.g. LX Obsidian Labs" />
          </label>
        </div>
        <label className="mt-2 flex flex-col gap-1">What should your team help with?
          <textarea value={goals} onChange={event => { setGoals(event.target.value); setShowPlan(false); }} maxLength={2000} rows={2} className="rounded-lg border border-hairline/40 bg-inset p-2" placeholder="Client emails, projects, social media, finance…" />
        </label>
        <button type="button" disabled={!organization.trim()} onClick={() => setShowPlan(true)} className="mt-2 rounded-lg bg-accent px-3 py-2 font-medium text-white disabled:opacity-40">Recommend my team</button>
        {plan && <div className="mt-3" aria-live="polite">
          <p className="font-semibold">{plan.roles.length} proposed agents — approval required before activation</p>
          <ul className="mt-2 grid gap-2 sm:grid-cols-2">
            {plan.roles.map(role => <li key={role.id} className="rounded-lg border border-hairline/40 p-2">
              <strong>{role.name}</strong><p className="text-ink-secondary">{role.purpose}</p>
              {role.reportsTo && <span className="text-ink-secondary">Reports to Chief of Staff</span>}
            </li>)}
          </ul>
          <button type="button" disabled={creating || !!result} className="mt-3 rounded-lg bg-accent px-3 py-2 font-medium text-white disabled:opacity-40" onClick={() => {
            if (!window.confirm(`Create ${plan.roles.length} agents? They will not have connected accounts or automatic execution permissions.`)) return;
            setCreating(true); setError("");
            void provisionWorkforce(plan).then(({ created }) => setResult(`${created.length} agents created. Close this dialog and refresh your agent list to see them.`)).catch(cause => setError(cause instanceof Error ? cause.message : String(cause))).finally(() => setCreating(false));
          }}>{creating ? "Creating agents…" : "Approve and create these agents"}</button>
          {result && <p role="status" className="mt-2 text-ink">{result}</p>}
          {error && <p role="alert" className="mt-2 text-danger">{error}</p>}
        </div>}
      </details>
    </section>
  );
}
