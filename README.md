# Revona CLI

**Developer automation project | LX Obsidian Labs**

**Development stage:** Active Development (not a production-readiness claim)  
**Verification:** Automated tests and CI are configured; the security-hardening PR passed Python 3.11 and 3.12 package CI on commit `1a2c5dfe`; the change remains unmerged.  
**Implemented scope under review:** CLI packaging, agent configuration, session storage, file tools and opt-in command execution.  
**Next milestone:** Review and merge the workspace-hardening PR after checking regression-test coverage, then verify tool authorization and filesystem security end to end.

Development stage and engineering quality are separate assessments. Unimplemented roadmap features are not defects; weaknesses in implemented security boundaries remain relevant. [Evaluation standard](https://github.com/lx-obsidian-labs/lx-obsidian-labs/blob/main/PORTFOLIO_EVALUATION.md).

Revona CLI is part of LX Obsidian Labs' exploration of AI-assisted development workflows and agent tooling.

> **Verification status:** This introduction does not certify the current CLI commands, supported providers, installation procedure or release readiness. Review the source and release artifacts before using this software.

## Engineering areas to explore

- Command-line interface design and developer experience
- Agent orchestration and automation workflows
- Integration boundaries, configuration and error handling
- Testing and operational reliability

These are areas for technical review, **not a verified list of completed features**.

## Getting started

1. Clone the repository.
2. Inspect the root project manifest and documentation to identify the actual runtime and supported commands.
3. Review configuration examples before entering credentials.
4. Do not commit API keys or other secrets.
5. Run only the installation and test commands confirmed by the source.

## Documentation roadmap

- [ ] Verify source structure, original authorship and upstream dependencies
- [ ] Document supported operating systems and runtime requirements
- [ ] Provide verified installation and first-run examples
- [ ] Explain CLI commands with actual terminal output
- [ ] Describe agent architecture and provider integrations
- [ ] Add automated tests and CI evidence
- [ ] Publish versioned releases and a changelog
- [ ] Add license and third-party attribution after review

## Evidence and security

- [Python test workflow](.github/workflows/python-package.yml)
- [Workspace boundary regression tests](tests/test_workspace_boundary.py)
- [Shell execution boundary tests](tests/test_shell_boundary.py)
- [Security model and limitations](docs/SECURITY_MODEL.md)
- [Engineering case study](docs/ENGINEERING_CASE_STUDY.md)

These links identify inspectable implementation and test assets; they are not a substitute for a passing CI run.

## Engineering portfolio

Maintained by **LX Obsidian Labs**, founded by Nathan Vilane.

[Portfolio](https://github.com/lx-obsidian-labs) · [Contact](mailto:vilanenathan@gmail.com)
