import { useState } from "react";
import { Mic, Plus, Users } from "lucide-react";
import { t } from "@/lib/i18n";
import { RevonaOnboarding } from "./RevonaOnboarding";
import { useStore } from "@/state/store";

/** First-run Chief step: offer a Revona workforce preview without provisioning agents. */
export function EmptyChatShell() {
  const [open, setOpen] = useState(false);
  const { dispatch } = useStore();
  return (
    <main className="relative flex h-full min-w-0 flex-1 flex-col bg-app">
      <div className="mx-auto flex max-w-lg flex-1 flex-col items-center justify-center gap-4 p-6 text-center">
        <Users size={36} aria-hidden="true" className="text-ink-secondary" />
        <h2 className="text-xl font-semibold text-ink">Build your AI team with Revona</h2>
        <p className="text-sm text-ink-secondary">Tell us about your work and review a team tailored to your goals. No agents or integrations are activated without your approval.</p>
        <button type="button" onClick={() => setOpen(true)} className="rounded-lg border border-hairline bg-card px-5 py-3 font-medium text-ink hover:bg-raised">Plan my AI team</button>
      </div>
      <div aria-hidden="true" className="pointer-events-none absolute inset-x-[50px] bottom-[17px] flex h-11 items-center gap-2 rounded-[22px] border-[0.5px] border-ink/10 bg-composer px-2">
        <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-ink/[0.04] text-ink-secondary"><Plus size={16} /></span>
        <span className="min-w-0 flex-1 truncate text-[14px] text-ink-tertiary">{t("onboarding.shell.placeholder")}</span>
        <span className="flex size-7 shrink-0 items-center justify-center text-ink-secondary"><Mic size={16} /></span>
      </div>
      {open && <RevonaOnboarding onClose={() => setOpen(false)} onOpenChief={(chiefId) => { setOpen(false); dispatch({ type: "select", id: chiefId }); }} />}
    </main>
  );
}
