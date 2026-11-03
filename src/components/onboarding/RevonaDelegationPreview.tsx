import { useState } from "react";
import { proposeRevonaDelegation, type DelegationProposal, type RevonaPlan } from "@/lib/revona-delegation";

/** Preview only: never invokes agent execution, external services or privileged APIs. */
export function RevonaDelegationPreview({ plan }: { plan: RevonaPlan }) {
  const [task, setTask] = useState("");
  const [proposal, setProposal] = useState<DelegationProposal | null>(null);
  const [error, setError] = useState("");
  function preview() {
    try {
      setProposal(proposeRevonaDelegation(plan, task));
      setError("");
    } catch (cause) {
      setProposal(null);
      setError(cause instanceof Error ? cause.message : String(cause));
    }
  }
  return <section className="mt-4 rounded-xl border border-hairline p-4" aria-label="Chief of Staff task preview">
    <h3 className="font-semibold">Chief of Staff · Task delegation</h3>
    <p className="mt-1 text-sm text-ink-secondary">Suggest an assignment for one of your specialists. This preview does not execute tasks.</p>
    <textarea aria-label="Describe a task" rows={3} maxLength={2000} value={task}
      onChange={event => { setTask(event.target.value); setProposal(null); }}
      placeholder="e.g. Prepare a social media campaign"
      className="my-3 w-full rounded-lg border border-hairline bg-app p-3" />
    <button type="button" onClick={preview} className="rounded-lg border border-hairline px-4 py-2">Preview assignment</button>
    {error && <p role="alert" className="mt-3 text-sm text-red-500">{error}</p>}
    {proposal && <div role="status" className="mt-3 rounded-lg border border-hairline p-3">
      <strong>{proposal.assigneeName}</strong>
      <p className="text-sm text-ink-secondary">{proposal.reason}</p>
      <p className="text-sm">Awaiting approval · No execution</p>
    </div>}
  </section>;
}
