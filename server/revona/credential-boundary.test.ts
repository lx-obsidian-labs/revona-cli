import { describe, expect, it } from "vitest";
import { revonaToolEnvironment } from "./credential-boundary.ts";

describe("Revona untrusted tool environment", () => {
  it("removes workspace, control plane, provider and generic credentials", () => {
    const source = {
      PATH: "/usr/bin", OMB_LICENSE_KEY: "license", OMB_CLOUD_AI_TOKEN: "cloud",
      OPENAI_API_KEY: "provider", GITHUB_TOKEN: "github", AWS_SECRET_ACCESS_KEY: "aws",
      CUSTOM_API_KEY: "custom", SERVICE_AUTH_TOKEN: "token",
    };
    expect(revonaToolEnvironment(source)).toEqual({ PATH: "/usr/bin" });
    expect(source.OPENAI_API_KEY).toBe("provider");
  });
  it("rejects sensitive overrides including control-plane names", () => {
    for (const key of ["OPENAI_API_KEY", "GITHUB_TOKEN", "GH_TOKEN", "OMB_CLOUD_AI_TOKEN", "OMB_LICENSE_KEY", "NPM_TOKEN"]) {
      expect(() => revonaToolEnvironment({}, { [key]: "leak" })).toThrow();
    }
  });
  it("strips lowercase and mixed-case secret names", () => {
    expect(revonaToolEnvironment({
      Path: "/bin", github_token: "secret", openai_api_key: "secret",
      Omb_Cloud_Ai_Token: "secret", service_password: "secret",
      cloud_private_key: "secret",
    })).toEqual({ Path: "/bin" });
  });
  it("allows ordinary nonsecret settings", () => {
    expect(revonaToolEnvironment({ PATH: "/bin" }, { LANG: "en_US.UTF-8" })).toEqual({
      PATH: "/bin", LANG: "en_US.UTF-8",
    });
  });
});
