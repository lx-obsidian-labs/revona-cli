# Revona CLI — Verification Runbook

**Reviewed:** 2026-11-07 · **Stage:** Alpha per package metadata; release readiness not certified.

## Installation and packaging

The `pyproject.toml` manifest declares Python >=3.11, a setuptools build backend, and the `revona` entry point at `agent.cli:main`. The listed dependencies include OpenAI SDK, Click, Rich, Requests and HTTPX.

Use a fresh virtual environment and a supported Python version:

```bash
python -m venv .venv
# Activate the environment using your platform's standard command
python -m pip install --upgrade pip
python -m pip install -e .
python -m pytest
```

**Caution:** The test command requires pytest to be installed and test discovery to be configured. Verify actual test requirements before using it as a release gate. A clean installation, CLI invocation and passing tests have not been confirmed by this document.

## Threat model and acceptance criteria

Read [SECURITY_MODEL.md](SECURITY_MODEL.md). Verify at least:

| Boundary | Acceptance test |
| --- | --- |
| Workspace containment | Reject path traversal and symlink escapes |
| Shell execution | Require explicit authorization for dangerous commands; prevent implicit execution |
| Tool invocation | Deny unauthorized tools and malformed arguments |
| Configuration | Fail safely when provider credentials are missing |
| Sensitive output | Avoid logging tokens, private keys and personal data |
| Network/provider access | Handle timeouts, rate limits and provider errors without unsafe retries |
| Session persistence | Validate file permissions and prevent unintended cross-workspace access |

## Release evidence

- Record the exact default-branch SHA and merged workspace-hardening PR provenance.
- Run tests on supported Python versions and retain CI URLs and outcomes.
- Perform safe end-to-end command tests in an isolated disposable workspace.
- Check package metadata, license and original/upstream code attribution.
- Publish versioned release notes and supported-platform constraints.

## Known verification gap

The workspace-hardening pull request was merged on 2026-11-06, but this document does not establish that the default branch's tests passed or that all command-execution boundaries are secure.

[README](../README.md) · [Security model](SECURITY_MODEL.md)
