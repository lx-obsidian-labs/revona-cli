# Agent execution security and verification

Revona is an experimental developer agent, **not a sandbox**. Its tools can read and write files, and optional shell commands can run with the privileges of the current OS user. Do not use it on untrusted repositories or with production credentials.

## Shell execution

Shell execution is disabled by default. To opt in for a trusted local session, set `REVONA_ALLOW_SHELL=1` in the environment before launching Revona. Commands are passed as argument arrays with `shell=False`, avoiding shell expansion and pipelines. The executable allowlist is **not** a sandbox: permitted programs such as Python, Node, and package managers can still execute arbitrary code. Use an isolated container or VM, a restricted OS user, and no sensitive credentials when enabling this feature.

## Local verification

Run from the repository root:

```sh
python -m pip install .
python -m unittest discover -s tests -p 'test_*.py' -v
revona --help
```

The CI workflow covers Python 3.11 and 3.12. A committed workflow is not proof of a passing run; inspect GitHub Actions for results before claiming the checks are green.

## Known limitations

- File read/write/edit tools do not yet enforce a workspace boundary or per-action approvals.
- Web fetching does not yet enforce an outbound host policy.
- Existing session files may contain prompts or tool results and should be treated as sensitive.
- Shell opt-in is an execution switch, not a capability restriction.
- Dependency and code-provenance audits are ongoing.

These limitations must be addressed before describing Revona as secure for autonomous use in sensitive environments.
