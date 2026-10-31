import {
  CONTROL_PLANE_ENV,
  CONTROL_PLANE_ENV_PREFIX,
  PROVIDER_CREDENTIAL_ENV,
  WORKSPACE_CREDENTIAL_ENV,
} from "../credential-env.ts";

/**
 * A conservative environment for untrusted tool execution.
 * Integration into real subprocess launchers remains a separate task.
 */
const sensitiveNames = new Set([
  ...CONTROL_PLANE_ENV,
  ...PROVIDER_CREDENTIAL_ENV,
  ...WORKSPACE_CREDENTIAL_ENV,
  "GITHUB_TOKEN",
  "GH_TOKEN",
  "AWS_SECRET_ACCESS_KEY",
  "AWS_SESSION_TOKEN",
  "NPM_TOKEN",
].map((name) => name.toUpperCase()));

function isSensitiveName(key: string): boolean {
  const upper = key.toUpperCase();
  return sensitiveNames.has(upper) ||
    upper.startsWith(CONTROL_PLANE_ENV_PREFIX) ||
    /(?:_API_KEY|_AUTH_TOKEN|_ACCESS_TOKEN|_SECRET|_TOKEN|_PASSWORD|_PRIVATE_KEY)$/.test(upper);
}

export function revonaToolEnvironment(
  source: Readonly<Record<string, string | undefined>>,
  allowed: Readonly<Record<string, string>> = {},
): Record<string, string | undefined> {
  const env: Record<string, string | undefined> = {};
  for (const [key, value] of Object.entries(source)) {
    if (!isSensitiveName(key)) env[key] = value;
  }
  for (const [key, value] of Object.entries(allowed)) {
    if (isSensitiveName(key)) {
      throw new Error("Revona: sensitive environment overrides are not allowed");
    }
    env[key] = value;
  }
  return env;
}
