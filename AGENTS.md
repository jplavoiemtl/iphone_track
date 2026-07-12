# Repository Instructions

## Planning

- Use `doc/PROJECT_PLAN.md` as the only canonical feature-planning document.
- Update its **Active Work**, **Prioritized Backlog**, and **Completed Milestones** sections instead of creating new phase-plan files.
- Keep planning content suitable for a public Git repository.

## Secrets and Sensitive Information

- Never put credentials or secrets in `doc/PROJECT_PLAN.md` or any tracked file.
- Do not include API keys, access tokens, passwords, webhook URLs, session keys, private certificates, or environment-variable values.
- Do not include private IP addresses, internal hostnames, device identifiers, usernames, precise home locations, or raw GPS coordinates. Use placeholders such as `<OWNTRACKS_HOST>` or descriptive text instead.
- Before committing planning changes, review the diff for sensitive values. If a feature depends on a secret, document only the environment-variable name and where it is configured.
- Keep actual secrets in environment variables or ignored local/deployment configuration, never in Git.

## Commit Messages

- Use a concise, outcome-focused subject line.
- Include a body that summarizes the important behavior, UI, documentation, and
  testing changes in enough detail to understand the commit without opening the diff.
- State any relevant tests that could not be run.
- End every commit created by Codex with an `Implemented-by` trailer containing
  `Codex` and the model identity available in the current session. Never guess or
  invent a model version.
- Trailer format: `Implemented-by: Codex (<model-name>)`
