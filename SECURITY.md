# Security Policy

## Supported versions

Security fixes are provided for the latest release on the `main` branch.
Older versions may be asked to upgrade before a fix is issued.

| Version | Supported |
| --- | --- |
| Latest release | Yes |
| Older releases | No |

## Reporting a vulnerability

Please do not disclose vulnerabilities in public GitHub issues, discussions,
pull requests, or Telegram chats.

Use GitHub's private vulnerability reporting feature:

1. Open the repository's **Security** tab.
2. Select **Advisories**.
3. Select **Report a vulnerability**.

Include:

- The affected version or commit.
- Reproduction steps or a minimal proof of concept.
- Expected impact.
- Any suggested mitigation.

If private vulnerability reporting is unavailable, contact the repository
owner privately through the contact method listed on their GitHub profile.
Please allow a reasonable response window before any public disclosure.

## Secrets and credentials

Never commit or include these values in bug reports, screenshots, logs, or
container images:

- `BOT_TOKEN`
- `DATABASE_URL`
- `PANEL_PASSWORD`
- `PANEL_SECRET_KEY`
- Session cookies or CSRF tokens

If a credential is exposed, rotate it immediately. Deleting it from the latest
commit is not sufficient because it may remain in Git history.

## Deployment guidance

- Set a strong, unique `PANEL_PASSWORD`.
- Set a random `PANEL_SECRET_KEY`.
- Keep `PANEL_SECURE_COOKIE=true` in HTTPS deployments.
- Restrict PostgreSQL to private networking when possible.
- Keep dependencies and container base images updated.
- Back up PostgreSQL before applying migrations in production.
- Do not expose the PostgreSQL port publicly unless required.

The included Docker Compose configuration binds PostgreSQL only to the internal
Compose network by default.

