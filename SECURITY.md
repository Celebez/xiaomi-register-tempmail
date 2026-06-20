# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| 1.0.x   | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security issue, please **DO NOT** open a public issue. Instead:

1. Email the maintainer (see GitHub profile)
2. Include steps to reproduce
3. Allow up to 72 hours for a response

## Security Considerations

This tool handles:

- **2Captcha API keys** — keep them out of git. Use `.env` (already in `.gitignore`).
- **Xiaomi account credentials** — `accounts.jsonl` is gitignored. Don't share this file.
- **mail.tm passwords** — generated locally, only used to retrieve verification codes.
- **HTTP proxy** — optional, configured via `HTTP_PROXY` env var.

## Best Practices

1. **Never commit `.env`** — already excluded by `.gitignore`
2. **Use a dedicated 2Captcha account** — top up with small amounts only
3. **Rotate mail.tm passwords** — though they're disposable, defense in depth
4. **Review `accounts.jsonl` output** — contains plaintext passwords by design (since you need to log into the created accounts later)
5. **Don't share your `accounts.jsonl`** — treat it like a password vault

## Known Limitations

- `payload_template.json` may become stale as Xiaomi updates their frontend. The repo contains a template from when the reverse-engineering was done; if registration starts failing with 400 errors, the template needs to be recaptured via Playwright (see `docs/FLOW.md`).
- 2Captcha solve quality varies; expect 30-50% of solves to require retry.