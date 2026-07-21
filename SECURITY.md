# Security Policy

## Supported Version

Security fixes are applied to the latest release on `main`.

## Reporting a Vulnerability

Do not disclose suspected vulnerabilities in a public issue. Use GitHub private
vulnerability reporting from the repository's **Security** tab and include:

- The affected component and version
- Reproduction steps or a minimal proof of concept
- Expected and observed behavior
- Potential impact

Avoid including real API keys, database credentials, personal data, or production
records in the report.

## Secret Handling

- Keep `.env` local. It is ignored by Git and excluded from Docker build contexts.
- Use unique values for every password and token in `.env`.
- Rotate a secret immediately if it appears in a commit, log, screenshot, issue, or
  message.
- Never place real credentials in `.env.example`, tests, documentation, or GitHub
  Actions configuration.
- Evaluation reports contain case IDs, pass/fail status, and timing by default;
  questions, answers, rows, and SQL require explicit inclusion or are omitted.
- Prometheus labels and structured events must never include prompts, SQL,
  credentials, tool arguments, or returned rows. Keep `AGENT_VERBOSE=false`.
- Query feedback is an explicit persistence action. Protect the local feedback
  volume and exported JSONL because they contain reviewed questions and SQL.
- Enable GitHub secret scanning, push protection, and Dependabot alerts when the
  repository is public.

## Deployment Boundary

The supplied Compose configuration binds application ports to `127.0.0.1` and is
intended for a trusted local machine. The shared API token does not provide user
identity, authorization scopes, revocation, or durable rate limiting. Internet or
multi-user deployment requires additional controls described in the README.

The model provider receives request text, selected schema information, generated
SQL, and policy-filtered query results. Direct sensitive values are masked, but
questions and aggregate values may still be confidential. Do not connect such
data until this processing is approved for the intended environment.

Query-plan rejections and database errors returned by the API are intentionally
generic. Detailed database exceptions must remain in restricted local logs and
must not be copied into public reports or issues.

Privacy controls are defined in `privacy_policy.json`. Keep denylists and masks in
source control, keep secrets out of the policy, and test policy changes before
connecting a different schema. Database permissions remain the final enforcement
boundary and must not be replaced by model instructions.
