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
- Enable GitHub secret scanning, push protection, and Dependabot alerts when the
  repository is public.

## Deployment Boundary

The supplied Compose configuration binds application ports to `127.0.0.1` and is
intended for a trusted local machine. The shared API token does not provide user
identity, authorization scopes, revocation, or durable rate limiting. Internet or
multi-user deployment requires additional controls described in the README.

The model provider receives request text, selected schema information, generated
SQL, and query results. Do not connect confidential data until this processing is
approved for the intended environment.
