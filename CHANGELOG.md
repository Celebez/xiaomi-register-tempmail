# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] - 2026-06-20

### Added
- Batch registration script (`batch_tempmail.py`) with full 8-step Xiaomi API flow
- mail.tm integration as disposable email provider (no Gmail/IMAP setup needed)
- `--count N` flag for batch size
- `--resume` flag to skip already-registered emails
- `--start-from N` flag to resume from a specific index
- `--sleep N` flag for delay between accounts
- `--dry-run` flag for simulating the flow without 2Captcha charges
- 429 rate-limit handling with exponential backoff for mail.tm API
- Auto-retry for captcha solve (up to 4 attempts per account)
- Per-account JSONL output (`accounts.jsonl` for success, `failed.jsonl` for failure)
- Detailed Indonesian-language README with step-by-step install instructions for Ubuntu, Fedora, and Arch
- Demo GIF (110×35, Tokyo Night theme) showing `--dry-run` mode
- EUI encryption helper (`scripts/encrypt.cjs`) using crypto-js
- Browser fingerprint template (`docs/payload_template.json`)
- Reverse-engineering notes (`docs/FLOW.md`)

### Security
- `.gitignore` excludes `accounts.jsonl`, `failed.jsonl`, `.env` (so credentials never leak)
- API keys read only from environment variables

[Unreleased]: https://github.com/Celebez/xiaomi-register-tempmail/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/Celebez/xiaomi-register-tempmail/releases/tag/v1.0.0