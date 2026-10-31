import { describe, expect, it } from "vitest";
import { revonaToolEnvironment } from "./credential-boundary.ts";

describe("Revona untrusted tool environment", () => {
  it("removes workspace, control plane, provider and generic credentials", () => {
    const source = {
      PATH: "/usr/bin", OMB_LICENSE_KEY: "license", OMB_CLOUD_AI_TOKEN: "cloud",
      OPENAI_API_KEY: "provider", GITHUB_TOKEN: "github", AWS_SECRET_ACCESS_KEY: "aws",
      CUSTOM_API_KEY: "custom", SERVICE_AUTH_TOKEN: "token",
    };
    const cleaned = revonaToolEnvironment(source);
    expect(cleaned).toEqual({ PATH: "/usr/bin" });
    expect(source.OPENAI_API_KEY).toBe("provider");
  });
  it("rejects sensitive overrides", () => {
    expect(() => revonaToolEnvironment({}, { OPENAI_API_KEY: "leak" })).toThrow();
  });
  it("allows ordinary nonsecret settings", () => {
    expect(revonaToolEnvironment({ PATH: "/bin" }, { LANG: "en_US.UTF-8" })).toEqual({
      PATH: "/bin", LANG: "en_US.UTF-8",
    });
  });
});
