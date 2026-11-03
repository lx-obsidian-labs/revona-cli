import { describe, expect, it } from "vitest";
import { chiefOfStaffSystemPrompt } from "./chief-of-staff.ts";

describe("Revona native Chief orchestration contract", () => {
  const bots = [
    { id: "revona-chief", name: "Revona Chief of Staff", section: "Revona", chiefOfStaff: true },
    { id: "revona-research", name: "Revona Intelligence", section: "Revona" },
    { id: "revona-creative", name: "Revona Creative", section: "Revona" },
  ];
  it("exposes specialist IDs to the Chief and native coordination instructions", () => {
    const prompt = chiefOfStaffSystemPrompt("revona-chief", bots, true);
    expect(prompt).toContain("Revona Intelligence");
    expect(prompt).toContain("revona-research");
    expect(prompt).toContain("Revona Creative");
    expect(prompt).toContain("coordinate_bots");
    expect(prompt).toContain("only claim completion after the teammate's result has actually arrived");
  });
  it("does not promise coordination on unsupported engines", () => {
    const prompt = chiefOfStaffSystemPrompt("revona-chief", bots, false);
    expect(prompt).toContain("cannot contact teammates");
    expect(prompt).not.toContain("coordinate_bots");
  });
  it("does not expose hidden specialists", () => {
    const prompt = chiefOfStaffSystemPrompt("revona-chief",
      [...bots, { id: "private", name: "Hidden Revona Agent", section: "Revona", hidden: true }], true);
    expect(prompt).not.toContain("Hidden Revona Agent");
  });
});
