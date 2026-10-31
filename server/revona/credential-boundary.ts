import { stripWorkspaceCredentialEnv, PROVIDER_CREDENTIAL_ENV } from "../credential-env.ts";

/**
 * Revona's fail-closed environment boundary for untrusted tools.
 * Never pass the parent's environment object directly to an agent process.
 */
export function revonaToolEnvironment(
  source: Readonly<Record<string, string | undefined>>,
  allowed: Readonly<Record<string, string>> = {},
): Record<string, string | undefined> {
  const env = { ...source };
  stripWorkspaceCredentialEnv(env);
  const blocked = new Set(PROVIDER_CREDENTIAL_ENV.map((key) => key.toUpperCase()));
  for (const key of Object.keys(env)) {
    const upper = key.toUpperCase();
    if (blocked.has(upper) || upper.endsWith("_API_KEY") || upper.endsWith("_AUTH_TOKEN") ||
        upper.endsWith("_ACCESS_TOKEN") || upper.endsWith("_SECRET") ||
        upper === "AWS_SECRET_ACCESS_KEY" || upper === "GITHUB_TOKEN" || upper === "GH_TOKEN") {
      delete env[key];
    }
  }
  for (const [key, value] of Object.entries(allowed)) {
    const upper = key.toUpperCase();
    if (blocked.has(upper) || /(?:_API_KEY|_AUTH_TOKEN|_ACCESS_TOKEN|_SECRET)$/.test(upper)) {
      throw new Error("Revona: sensitive environment overrides are not allowed");
    }
    env[key] = value;
  }
  return env;
}
