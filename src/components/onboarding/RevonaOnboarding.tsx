import { useState } from "react";
import { provisionWorkforce } from "@/lib/revona-workforce-provision";
import { RevonaDelegationPreview } from "./RevonaDelegationPreview";
import { createWorkforcePlan, type WorkforceInput } from "@/lib/revona-workforce";

type Step = "kind" | "organization" | "goals" | "review";
export function RevonaOnboarding({ onClose }: { onClose: () => void }) {
  const [step, setStep] = useState<Step>("kind");
  const [kind, setKind] = useState<WorkforceInput["kind"]>("business");
  const [organization, setOrganization] = useState("");
  const [goals, setGoals] = useState("");
  const [answer, setAnswer] = useState("");
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);
  const [created, setCreated] = useState<Array<{ id: string; name: string }>>([]);
  const [creationStarted, setCreationStarted] = useState(false);
  const plan = step === "review" ? createWorkforcePlan({ kind, organization, goals }) : null;
  const questions: Record<Exclude<Step, "review">, string> = {
    kind: "Welcome to Revona. Are we building a team for a business or your freelance work?",
    organization: "Great. What should I call your business or freelance practice?",
    goals: "What would you like your AI team to help you accomplish?",
  };
  function next() {
    setError("");
    if (step === "kind") { setStep("organization"); return; }
    if (step === "organization") {
      if (!answer.trim()) { setError("Please enter a name to continue."); return; }
      setOrganization(answer.trim()); setAnswer(""); setStep("goals"); return;
    }
    if (!answer.trim()) { setError("Tell Revona at least one goal."); return; }
    setGoals(answer.trim()); setAnswer(""); setStep("review");
  }
  async function createApprovedTeam() {
    if (!plan || creating || creationStarted) return;
    if (!window.confirm(`Create ${plan.roles.length} inactive-by-default AI agent profiles for ${plan.organization}? This does not connect accounts, grant tool permissions, or execute tasks.`)) return;
    setCreationStarted(true);
    setCreating(true);
    setError("");
    try {
      const result = await provisionWorkforce(plan);
      setCreated(result.created.map(bot => ({ id: bot.id, name: bot.name })));
    } catch (cause) {
      setError(`Team creation failed: ${cause instanceof Error ? cause.message : String(cause)}. Check the agent list before trying again.`);
    } finally {
      setCreating(false);
    }
  }
  function exportPlan() {
    if (!plan) return;
    const blob = new Blob([JSON.stringify(plan, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url; anchor.download = "revona-workforce-plan.json"; anchor.click();
    URL.revokeObjectURL(url);
  }
  return <div role="dialog" aria-modal="true" aria-label="Build your Revona team" className="fixed inset-0 z-[100] flex items-center justify-center bg-black/65 p-4">
    <section className="w-full max-w-xl rounded-2xl border border-hairline bg-card p-6 text-ink shadow-2xl">
      <div className="mb-6 flex items-center justify-between"><h2 className="text-xl font-semibold">Build your AI team</h2><button type="button" onClick={onClose} aria-label="Close onboarding" className="rounded px-3 py-1 hover:bg-raised">✕</button></div>
      {step !== "review" ? <>
        <p className="mb-5 text-base">{questions[step]}</p>
        {step === "kind" ? <div className="mb-5 flex gap-3">
          {(["business", "freelancer"] as const).map((option) => <button type="button" key={option} aria-pressed={kind === option} onClick={() => setKind(option)} className={`rounded-lg border px-4 py-3 capitalize ${kind === option ? "border-current" : "border-hairline"}`}>{option}</button>)}
        </div> : <textarea autoFocus value={answer} onChange={(event) => setAnswer(event.target.value)} maxLength={step === "organization" ? 120 : 2000} rows={step === "goals" ? 4 : 2} className="mb-4 w-full rounded-lg border border-hairline bg-app p-3" placeholder={step === "goals" ? "For example: manage projects, draft client emails and plan social media" : "Your organization name"} />}
        {error && <p role="alert" className="mb-3 text-red-500">{error}</p>}
        <button type="button" onClick={next} className="rounded-lg bg-ink px-5 py-2 text-app">Continue</button>
      </> : <>
        <p className="mb-3">Here is your proposed team for <strong>{plan!.organization}</strong>. Review each role before enabling any integrations.</p>
        <div className="max-h-72 space-y-2 overflow-y-auto">{plan!.roles.map((role) => <div key={role.id} className="rounded-lg border border-hairline p-3"><strong>{role.name}</strong><p className="text-sm text-ink-secondary">{role.purpose}</p></div>)}</div>
        <p className="my-4 text-sm text-ink-secondary">Agent profiles are created only after explicit confirmation. Account connections, permissions and task execution remain separate.</p>
        {created.length > 0 && <p role="status" className="mb-3 text-sm">{created.length} agent profile(s) created. Configure their models and permissions in Revona before use.</p>}
        {error && <p role="alert" className="mb-3 text-sm text-red-500">{error}</p>}
        {created.length === plan!.roles.length && <RevonaDelegationPreview plan={plan!} />}
        <div className="flex flex-wrap gap-3"><button type="button" disabled={creationStarted} onClick={() => { setAnswer(goals); setStep("goals"); }} className="rounded-lg border border-hairline px-4 py-2">Edit goals</button><button type="button" onClick={exportPlan} className="rounded-lg bg-ink px-4 py-2 text-app">Export team plan</button><button type="button" disabled={creating || creationStarted} onClick={createApprovedTeam} className="rounded-lg border border-hairline px-4 py-2 disabled:opacity-50">{creating ? "Creating agents…" : creationStarted ? "Creation attempted" : "Approve and create agents"}</button></div>
      </>}
    </section>
  </div>;
}
